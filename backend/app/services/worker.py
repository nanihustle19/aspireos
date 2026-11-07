"""Background worker for async jobs: document scanning, exports, imports, outbox processing.

Ported from MongoDB to PostgreSQL/SQLAlchemy. Run as a separate process:
    python -m app.services.worker
"""
import asyncio
import csv
import io
import logging
import smtplib
import ssl
from email.message import EmailMessage
from datetime import datetime, timezone

from sqlalchemy import select, update, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import async_session
from app.models.base import new_uuid
from app.models.audit import (
    BackgroundJob, Document, TimelineEvent, Notification, EmailOutbox,
)
from app.models.candidate import Candidate
from app.models.user import User
from app.models.group import Group, Membership
from app.services.storage import get_object, check_eicar, check_extension

logger = logging.getLogger("benchos.worker")


# ── Constants ────────────────────────────────────────────────────

EXPORT_COLS = [
    "id", "first_name", "last_name", "email", "phone", "status",
    "primary_skill", "skills", "experience_years", "location",
    "visa_status", "group_name", "pay_rate", "bill_rate", "target_rate", "created_at",
]

ADMIN = "ADMIN"
OPERATIONS = "OPERATIONS"
EMPLOYEE = "EMPLOYEE"


# ── Helpers ──────────────────────────────────────────────────────

def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _notify(
    session: AsyncSession, org_id: str, user_ids: list[str],
    title: str, body: str, link: str | None = None,
):
    """Create notifications + email outbox entries."""
    result = await session.execute(
        select(User.id, User.email).where(
            User.id.in_(list(set(user_ids))), User.status == "ACTIVE"
        )
    )
    for row in result.all():
        session.add(Notification(
            id=new_uuid(), organization_id=org_id, user_id=row.id,
            title=title, body=body, link=link, read=False,
        ))
        session.add(EmailOutbox(
            id=new_uuid(), organization_id=org_id, to=row.email,
            subject=title, body=body, status="PENDING", attempts=0,
        ))


def _norm_email(e: str | None) -> str | None:
    if not e:
        return None
    return e.strip().lower()


def _norm_phone(p: str | None) -> str | None:
    if not p:
        return None
    import re
    return re.sub(r"\D", "", p)[-10:] or None


def _can_see_pay(user_row) -> bool:
    return user_row.role in (ADMIN, OPERATIONS)


def _can_see_bill(user_row, groups: dict, group_id: str | None) -> bool:
    if user_row.role in (ADMIN, OPERATIONS):
        return True
    return groups.get(group_id) in ("LEAD", "MARKETING")


async def _load_groups(session: AsyncSession, user_id: str) -> dict[str, str]:
    result = await session.execute(
        select(Membership.group_id, Membership.role).where(
            Membership.user_id == user_id, Membership.active == True
        )
    )
    return {row.group_id: row.role for row in result.all()}


# ── Job Handlers ─────────────────────────────────────────────────

async def run_scan(session: AsyncSession, job: BackgroundJob):
    """SIMULATED malware scan: extension allowlist, size and EICAR signature check."""
    doc_id = (job.payload or {}).get("document_id")
    result = await session.execute(
        select(Document).where(Document.id == doc_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        return {"error": "document missing"}

    # Simulate scan latency
    await asyncio.sleep(2)

    reason = None
    try:
        data, _ = await get_object(doc.storage_path)
        reason = check_eicar(data)
    except Exception as e:
        reason = f"Unable to read object: {e}"

    if not reason:
        reason = check_extension(doc.original_filename)

    status = "FAILED" if reason else "PASSED"
    doc.scan_status = status
    doc.scan_reason = reason
    doc.scanned_at = utcnow()

    # Timeline entry
    session.add(TimelineEvent(
        id=new_uuid(),
        organization_id=doc.organization_id,
        candidate_id=doc.candidate_id,
        event=f"DOCUMENT_SCAN_{status}",
        detail=f"{doc.original_filename}: {reason or 'clean'} (simulated scanner)",
        actor_name="System",
        meta={},
    ))

    await _notify(
        session, doc.organization_id, [doc.uploaded_by],
        f"Document scan {status.lower()}",
        f"{doc.original_filename}: {reason or 'clean'}",
        f"/candidates/{doc.candidate_id}",
    )

    return {"scan_status": status, "reason": reason}


async def run_export(session: AsyncSession, job: BackgroundJob):
    """Export candidates to CSV with rate redaction based on user role."""
    # Load the requesting user
    result = await session.execute(
        select(User).where(User.id == job.created_by)
    )
    user = result.scalar_one_or_none()
    if not user:
        return {"error": "user not found"}

    groups = await _load_groups(session, user.id) if user.role == EMPLOYEE else {}

    # Build group name lookup
    grp_result = await session.execute(
        select(Group.id, Group.name).where(
            Group.organization_id == user.organization_id
        )
    )
    group_names = {row.id: row.name for row in grp_result.all()}

    # Build candidate query with scope
    query = select(Candidate).where(
        Candidate.organization_id == user.organization_id
    )
    if user.role == EMPLOYEE:
        group_ids = list(groups.keys())
        if group_ids:
            query = query.where(Candidate.current_group_id.in_(group_ids))
        else:
            query = query.where(Candidate.id == None)  # no access

    # Apply filters
    flt = (job.payload or {}).get("filters") or {}
    if flt.get("status"):
        query = query.where(Candidate.status.in_(flt["status"].split(",")))

    result = await session.execute(query)
    candidates = result.scalars().all()

    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=EXPORT_COLS, extrasaction="ignore")
    w.writeheader()
    n = 0
    for c in candidates:
        row_dict = {
            "id": c.id,
            "first_name": c.first_name,
            "last_name": c.last_name,
            "email": c.email,
            "phone": c.phone,
            "status": c.status,
            "primary_skill": c.primary_skill,
            "skills": "; ".join(c.skills or []),
            "experience_years": c.experience_years,
            "location": c.location,
            "visa_status": c.visa_status,
            "group_name": group_names.get(c.current_group_id),
            "created_at": str(c.created_at) if c.created_at else None,
        }
        # Rate redaction
        if _can_see_pay(user):
            row_dict["pay_rate"] = c.pay_rate
        else:
            row_dict["pay_rate"] = "REDACTED"

        if _can_see_bill(user, groups, c.current_group_id):
            row_dict["bill_rate"] = c.bill_rate
            row_dict["target_rate"] = c.target_rate
        else:
            row_dict["bill_rate"] = "REDACTED"
            row_dict["target_rate"] = "REDACTED"

        w.writerow(row_dict)
        n += 1

    job.result_csv = out.getvalue()
    await _notify(
        session, user.organization_id, [user.id],
        "Export ready", f"{n} candidates exported",
    )
    return {"rows": n}


async def run_import(session: AsyncSession, job: BackgroundJob):
    """Import candidates from parsed CSV rows."""
    created, skipped, errors = 0, 0, []
    rows = (job.payload or {}).get("rows", [])
    org_id = job.organization_id

    for i, row in enumerate(rows, start=2):
        fn = (row.get("first_name") or "").strip()
        ln = (row.get("last_name") or "").strip()
        if not fn or not ln:
            errors.append(f"Row {i}: missing name")
            skipped += 1
            continue

        # Duplicate check by email/phone
        email_n = _norm_email(row.get("email"))
        phone_n = _norm_phone(row.get("phone"))
        if email_n:
            dup = await session.execute(
                select(Candidate.id).where(
                    Candidate.organization_id == org_id,
                    Candidate.email_norm == email_n,
                ).limit(1)
            )
            if dup.scalar_one_or_none():
                errors.append(f"Row {i}: duplicate email {row.get('email')}")
                skipped += 1
                continue
        if phone_n:
            dup = await session.execute(
                select(Candidate.id).where(
                    Candidate.organization_id == org_id,
                    Candidate.phone_norm == phone_n,
                ).limit(1)
            )
            if dup.scalar_one_or_none():
                errors.append(f"Row {i}: duplicate phone {row.get('phone')}")
                skipped += 1
                continue

        cid = new_uuid()
        try:
            exp = float(row.get("experience_years") or 0) or None
        except ValueError:
            exp = None

        session.add(Candidate(
            id=cid,
            organization_id=org_id,
            first_name=fn,
            last_name=ln,
            email=row.get("email") or None,
            phone=row.get("phone") or None,
            email_norm=email_n,
            phone_norm=phone_n,
            primary_skill=row.get("primary_skill") or None,
            skills=[s.strip() for s in (row.get("skills") or "").split(";") if s.strip()],
            experience_years=exp,
            location=row.get("location") or None,
            visa_status=row.get("visa_status") or None,
            status="NEW",
            current_group_id=None,
            owner_id=None,
            version=1,
            source="CSV Import",
            created_by=job.created_by,
            bench_since=None,
        ))
        session.add(TimelineEvent(
            id=new_uuid(),
            organization_id=org_id,
            candidate_id=cid,
            event="CREATED",
            detail=f"Imported from {(job.payload or {}).get('filename', 'CSV')}",
            actor_name=job.created_by_name,
            meta={},
        ))
        created += 1

    await _notify(
        session, org_id, [job.created_by],
        "Import finished", f"{created} created, {skipped} skipped",
    )
    return {"created": created, "skipped": skipped, "errors": errors[:200]}


# ── Handler Registry ─────────────────────────────────────────────

HANDLERS = {
    "SCAN": run_scan,
    "EXPORT_CANDIDATES": run_export,
    "IMPORT_CANDIDATES": run_import,
}


# ── Outbox Processing ───────────────────────────────────────────

def send_email(msg: EmailOutbox):
    settings = get_settings()
    email = EmailMessage()
    email["From"] = settings.SMTP_FROM
    email["To"] = msg.to
    email["Subject"] = msg.subject
    email.set_content(msg.body)
    tls = ssl.create_default_context()
    if settings.SMTP_PORT == 465:
        connection = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15, context=tls)
    else:
        connection = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15)
    with connection as smtp:
        if settings.SMTP_PORT != 465:
            smtp.starttls(context=tls)
        if settings.SMTP_USER:
            smtp.login(settings.SMTP_USER, settings.SMTP_PASS)
        smtp.send_message(email)


async def process_outbox(session: AsyncSession):
    if not get_settings().SMTP_HOST:
        return
    result = await session.execute(
        select(EmailOutbox).where(EmailOutbox.status == "PENDING")
        .order_by(EmailOutbox.attempts, EmailOutbox.created_at)
        .limit(1).with_for_update(skip_locked=True)
    )
    msg = result.scalar_one_or_none()
    if msg is None:
        return
    msg.attempts += 1
    try:
        await asyncio.to_thread(send_email, msg)
    except (OSError, smtplib.SMTPException, ValueError) as exc:
        logger.warning("Email delivery failed for outbox entry %s (%s)", msg.id, type(exc).__name__)
        if msg.attempts >= 5:
            msg.status = "FAILED"
    else:
        msg.status = "SENT"
        msg.sent_at = utcnow()
        msg.body = ""


# ── Main Worker Loop ────────────────────────────────────────────

async def worker_loop(types: list[str] | None = None, outbox: bool = True):
    """Main worker loop. Polls for pending jobs and processes them.

    Args:
        types: List of job types to handle. Defaults to all.
        outbox: Whether to also process email outbox.
    """
    if types is None:
        types = list(HANDLERS.keys())

    logger.info(f"Worker started. Handling: {types}, outbox={outbox}")

    while True:
        try:
            async with async_session() as session:
                # Find and claim next pending job
                result = await session.execute(
                    select(BackgroundJob)
                    .where(
                        BackgroundJob.status == "PENDING",
                        BackgroundJob.type.in_(types),
                    )
                    .order_by(BackgroundJob.created_at)
                    .limit(1)
                    .with_for_update(skip_locked=True)
                )
                job = result.scalar_one_or_none()

                if job:
                    job.status = "RUNNING"
                    job.started_at = utcnow()
                    await session.commit()

                    try:
                        handler = HANDLERS[job.type]
                        job_result = await handler(session, job)
                        job.status = "COMPLETED"
                        job.result = job_result
                        job.finished_at = utcnow()
                    except Exception as e:
                        logger.exception(f"Job {job.id} ({job.type}) failed")
                        job.status = "FAILED"
                        job.error = str(e)
                        job.finished_at = utcnow()

                    await session.commit()
                    continue

                # No pending jobs — process outbox if enabled
                if outbox:
                    await process_outbox(session)
                    await session.commit()

        except Exception:
            logger.exception("Worker loop error")

        await asyncio.sleep(1.5)


# ── Entrypoint ───────────────────────────────────────────────────

async def main():
    """Run the background worker as a standalone process."""
    await worker_loop()


if __name__ == "__main__":
    asyncio.run(main())


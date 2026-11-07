"""Candidate CRUD, lifecycle, group assignment, notes, tasks, documents — /api"""
import re
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, UploadFile, File, Form, Query
from fastapi.responses import Response as FileResponse
from pydantic import BaseModel
from sqlalchemy import select, update, and_, or_, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.constants import (
    ADMIN, OPERATIONS, EMPLOYEE, AUDITOR, STATUSES, MARKETING_STATES,
    TRANSITIONS, FULL_FIELDS, MARKETING_FIELDS, MAX_UPLOAD_SIZE,
)
from app.exceptions import NotFoundError, ForbiddenError, ConflictError, LockedError, ValidationError
from app.models.candidate import Candidate, CandidateGroupAssignment
from app.models.group import Group, Membership
from app.models.user import User
from app.models.pipeline import Submission, Interview as InterviewModel, Offer
from app.models.audit import Note, Task, Document, BackgroundJob, TimelineEvent
from app.services.auth_service import (
    utcnow, new_id, make_token, decode_token,
    get_current_user, is_ops, require, require_writer,
    audit, timeline, notify, ops_and_lead_ids,
)
from app.services.authorization import (
    candidate_scope_filters, get_candidate_or_404, edit_level, redact,
    candidate_to_dict, group_role,
)
from app.services.storage import get_object, put_object

router = APIRouter(prefix="/api")


# ── Request schemas ────────────────────────────────────────────

class CandidateIn(BaseModel):
    first_name: str
    last_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    primary_skill: Optional[str] = None
    skills: list[str] = []
    experience_years: Optional[float] = None
    visa_status: Optional[str] = None
    work_authorization: Optional[str] = None
    availability_date: Optional[str] = None
    source: Optional[str] = None
    linkedin_url: Optional[str] = None
    pay_rate: Optional[float] = None
    bill_rate: Optional[float] = None
    target_rate: Optional[float] = None
    summary: Optional[str] = None
    relocation: Optional[bool] = None
    timezone: Optional[str] = None
    group_id: Optional[str] = None
    override_duplicate_reason: Optional[str] = None

class DupIn(BaseModel):
    email: Optional[str] = None
    phone: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    exclude_id: Optional[str] = None

class VersionIn(BaseModel):
    version: int
    reason: Optional[str] = None

class TransitionIn(VersionIn):
    to_status: str

class AssignIn(VersionIn):
    group_id: str

class TransferIn(VersionIn):
    to_group_id: str
    acknowledge_active_offer: bool = False

class UnassignIn(VersionIn):
    target_status: Optional[str] = None

class OwnerIn(VersionIn):
    owner_id: Optional[str] = None

class NoteIn(BaseModel):
    body: str
    visibility: str = "STANDARD"

class TaskIn(BaseModel):
    title: str
    candidate_id: Optional[str] = None
    assignee_id: Optional[str] = None
    due_date: Optional[str] = None
    priority: str = "MEDIUM"

class TaskPatch(BaseModel):
    status: Optional[str] = None
    title: Optional[str] = None
    due_date: Optional[str] = None
    assignee_id: Optional[str] = None


# ── Helpers ────────────────────────────────────────────────────

def norm_email(e: str | None) -> str | None:
    return (e or "").strip().lower() or None

def norm_phone(p: str | None) -> str | None:
    d = re.sub(r"\D", "", p or "")
    return d[-10:] if len(d) >= 7 else None

def view(user: dict, c: dict) -> dict:
    d = redact(user, c)
    d["full_name"] = f"{c['first_name']} {c['last_name']}"
    return d


async def claim(db: AsyncSession, user: dict, cand_id: str, version: int, extra: dict | None = None):
    """Atomically bumps version — acts as optimistic lock; loser gets 409."""
    result = await db.execute(
        select(Candidate).where(
            Candidate.id == cand_id,
            Candidate.organization_id == user["organization_id"],
            Candidate.version == version,
        ).with_for_update()
    )
    cand = result.scalar_one_or_none()
    if not cand:
        raise ConflictError()
    cand.version += 1
    cand.updated_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    cand.updated_by = user["id"]
    if extra:
        for k, v in extra.items():
            setattr(cand, k, v)
    await db.flush()
    await db.refresh(cand)
    return candidate_to_dict(cand)


async def find_duplicates(db: AsyncSession, org_id: str, email: str | None, phone: str | None,
                          first: str | None, last: str | None, exclude_id: str | None = None):
    exact, possible = [], []
    ne = norm_email(email)
    np = norm_phone(phone)
    base_filter = Candidate.organization_id == org_id
    if exclude_id:
        base_filter = and_(base_filter, Candidate.id != exclude_id)

    conditions = []
    if ne:
        conditions.append(Candidate.email_norm == ne)
    if np:
        conditions.append(Candidate.phone_norm == np)

    if conditions:
        result = await db.execute(
            select(Candidate).where(base_filter, or_(*conditions))
        )
        for c in result.scalars().all():
            match = "email" if (c.email or "").lower() == ne else "phone"
            exact.append({
                "id": c.id, "first_name": c.first_name, "last_name": c.last_name,
                "email": c.email, "phone": c.phone, "status": c.status,
                "current_group_id": c.current_group_id, "match": match,
            })

    if first and last:
        ex_ids = {e["id"] for e in exact}
        result = await db.execute(
            select(Candidate).where(
                base_filter,
                func.lower(Candidate.first_name) == first.strip().lower(),
                func.lower(Candidate.last_name) == last.strip().lower(),
            )
        )
        for c in result.scalars().all():
            if c.id not in ex_ids:
                possible.append({
                    "id": c.id, "first_name": c.first_name, "last_name": c.last_name,
                    "email": c.email, "phone": c.phone, "status": c.status,
                    "current_group_id": c.current_group_id, "match": "name",
                })

    return exact, possible


def permissions(user: dict, c: dict) -> dict:
    lvl = edit_level(user, c)
    ops = is_ops(user)
    st = c["status"]
    return {
        "edit_level": lvl,
        "can_edit": lvl is not None and st != "ARCHIVED",
        "allowed_transitions": [
            t for t in TRANSITIONS.get(st, [])
            if lvl and t != "PLACED" and (t != "MARKETING" or c.get("current_group_id"))
        ],
        "can_assign": ops and not c.get("current_group_id") and st != "ARCHIVED",
        "can_transfer": (
            ops or (lvl == "full" and user.get("_groups", {}).get(c.get("current_group_id")) == "LEAD")
        ) and bool(c.get("current_group_id")),
        "can_unassign": ops and bool(c.get("current_group_id")),
        "can_archive": ops and st != "ARCHIVED",
        "can_restore": ops and st == "ARCHIVED",
        "can_set_owner": (
            ops or user.get("_groups", {}).get(c.get("current_group_id")) == "LEAD"
        ) and bool(c.get("current_group_id")),
        "can_view_ops_notes": ops or (user["role"] == AUDITOR and user.get("can_view_ops_only")),
        "can_upload": lvl is not None,
    }


async def assign_service(db: AsyncSession, user: dict, cand: dict, group_id: str,
                         version: int, reason: str | None = None, event: str = "ASSIGNED"):
    result = await db.execute(
        select(Group).where(
            Group.id == group_id,
            Group.organization_id == user["organization_id"],
            Group.active == True,
        )
    )
    grp = result.scalar_one_or_none()
    if not grp:
        raise NotFoundError("Group not found or inactive")

    prev_group = cand.get("current_group_id")
    doc = await claim(db, user, cand["id"], version, {"current_group_id": group_id, "owner_id": None})

    # End old active assignments
    await db.execute(
        update(CandidateGroupAssignment).where(
            CandidateGroupAssignment.candidate_id == cand["id"],
            CandidateGroupAssignment.active == True,
        ).values(active=False, ended_at=utcnow(), ended_by=user["id"], end_reason=reason or event)
    )

    # Create new assignment
    db.add(CandidateGroupAssignment(
        id=new_id(), organization_id=user["organization_id"], candidate_id=cand["id"],
        group_id=group_id, active=True, started_at=utcnow(), started_by=user["id"], reason=reason,
    ))
    await db.flush()

    await audit(db, user, f"CANDIDATE_{event}", "candidate", cand["id"],
                {"current_group_id": prev_group}, {"current_group_id": group_id}, reason)
    label = "Transferred" if prev_group else "Assigned"
    await timeline(db, user, cand["id"], event,
                   f"{label} to group {grp.name}" + (f" — {reason}" if reason else ""),
                   {"from": prev_group, "to": group_id})
    await notify(db, user["organization_id"],
                 await ops_and_lead_ids(db, user["organization_id"], group_id),
                 f"Candidate {event.lower()}: {cand['first_name']} {cand['last_name']}",
                 f"Now in group {grp.name}", f"/candidates/{cand['id']}")
    return doc


async def set_status(db: AsyncSession, user: dict, c: dict, to: str, version: int,
                     reason: str | None = None, event: str = "STATUS_CHANGED"):
    extra = {"status": to}
    if to in ("BENCH", "ON_HOLD") and c["status"] not in ("BENCH", "ON_HOLD"):
        extra["bench_since"] = utcnow()
    doc = await claim(db, user, c["id"], version, extra)
    await audit(db, user, "CANDIDATE_STATUS_CHANGED", "candidate", c["id"],
                {"status": c["status"]}, {"status": to}, reason)
    await timeline(db, user, c["id"], event,
                   f"{c['status']} → {to}" + (f" — {reason}" if reason else ""),
                   {"from": c["status"], "to": to})
    return doc


# ── Routes ─────────────────────────────────────────────────────

@router.post("/candidates/duplicate-check")
async def duplicate_check(body: DupIn, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    exact, possible = await find_duplicates(db, user["organization_id"], body.email, body.phone, body.first_name, body.last_name, body.exclude_id)
    return {"exact": exact, "possible": possible, "can_override": is_ops(user)}


@router.get("/candidates")
async def list_candidates(
    q: str = "", status: str = "", group_id: str = "", owner_id: str = "",
    skill: str = "", unassigned: bool = False, page: int = 1, page_size: int = 25,
    sort: str = "-updated_at", include_archived: bool = False,
    user=Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    page_size = max(1, min(page_size, 200))
    page = max(1, page)
    filters = candidate_scope_filters(user)

    if q:
        like = f"%{q}%"
        filters.append(or_(
            Candidate.first_name.ilike(like), Candidate.last_name.ilike(like),
            Candidate.email.ilike(like), Candidate.primary_skill.ilike(like),
            Candidate.phone.ilike(like),
        ))
    if status:
        filters.append(Candidate.status.in_(status.split(",")))
    elif not include_archived:
        filters.append(Candidate.status != "ARCHIVED")
    if group_id:
        filters.append(Candidate.current_group_id == group_id)
    if unassigned:
        filters.append(Candidate.current_group_id == None)
    if owner_id:
        filters.append(Candidate.owner_id == owner_id)
    if skill:
        filters.append(or_(
            Candidate.primary_skill.ilike(f"%{skill}%"),
            Candidate.skills.any(skill),
        ))

    # Sorting
    key = sort.lstrip("-")
    if key not in ("updated_at", "created_at", "last_name", "status", "bench_since", "experience_years"):
        key = "updated_at"
    sort_col = getattr(Candidate, key)
    order = sort_col.desc() if sort.startswith("-") else sort_col.asc()

    # Count
    count_q = select(func.count()).select_from(Candidate).where(*filters)
    total = (await db.execute(count_q)).scalar() or 0

    # Fetch
    result = await db.execute(
        select(Candidate).where(*filters).order_by(order)
        .offset((page - 1) * page_size).limit(page_size)
    )
    candidates = result.scalars().all()

    # Enrich with group/owner names
    grp_result = await db.execute(
        select(Group.id, Group.name).where(Group.organization_id == user["organization_id"])
    )
    groups = {r.id: r.name for r in grp_result.all()}

    usr_result = await db.execute(
        select(User.id, User.name).where(User.organization_id == user["organization_id"])
    )
    owners = {r.id: r.name for r in usr_result.all()}

    items = []
    for c in candidates:
        d = view(user, candidate_to_dict(c))
        d["group_name"] = groups.get(c.current_group_id)
        d["owner_name"] = owners.get(c.owner_id)
        items.append(d)

    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post("/candidates")
async def create_candidate(body: CandidateIn, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require(user, ADMIN, OPERATIONS)
    exact, possible = await find_duplicates(db, user["organization_id"], body.email, body.phone, body.first_name, body.last_name)
    if exact:
        if not body.override_duplicate_reason or not body.override_duplicate_reason.strip():
            raise ConflictError({"code": "DUPLICATE", "message": "Exact duplicate email/phone exists.", "exact": exact})

    data = body.model_dump(exclude={"group_id", "override_duplicate_reason"})
    data["skills"] = [s.strip() for s in data["skills"] if s and s.strip()]
    cid = new_id()

    cand = Candidate(
        id=cid, organization_id=user["organization_id"], status="NEW",
        current_group_id=None, owner_id=None,
        email_norm=norm_email(body.email), phone_norm=norm_phone(body.phone),
        version=1, created_by=user["id"], bench_since=None, **data,
    )
    db.add(cand)
    await db.flush()

    doc = candidate_to_dict(cand)
    await audit(db, user, "CANDIDATE_CREATED", "candidate", cid, None, doc,
                body.override_duplicate_reason if exact else None)
    await timeline(db, user, cid, "CREATED", "Candidate created" + (" (duplicate override)" if exact else ""))
    if exact:
        await timeline(db, user, cid, "DUPLICATE_OVERRIDE", f"Override reason: {body.override_duplicate_reason}")

    if body.group_id:
        doc = await assign_service(db, user, doc, body.group_id, 1)
        doc = await set_status(db, user, doc, "BENCH", doc["version"], "Auto: assigned to group")

    return view(user, doc)


@router.get("/candidates/{cid}")
async def get_candidate(cid: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    c = await get_candidate_or_404(db, user, cid)
    cd = candidate_to_dict(c)

    grp = None
    if c.current_group_id:
        r = await db.execute(select(Group).where(Group.id == c.current_group_id))
        g = r.scalar_one_or_none()
        grp = {"id": g.id, "name": g.name, "description": g.description} if g else None

    owner = None
    if c.owner_id:
        r = await db.execute(select(User.id, User.name).where(User.id == c.owner_id))
        o = r.one_or_none()
        owner = {"id": o.id, "name": o.name} if o else None

    # Assignment history
    hist_result = await db.execute(
        select(CandidateGroupAssignment).where(
            CandidateGroupAssignment.candidate_id == cid
        ).order_by(CandidateGroupAssignment.started_at.desc())
    )
    grp_names = {}
    all_grps = await db.execute(
        select(Group.id, Group.name).where(Group.organization_id == user["organization_id"])
    )
    grp_names = {r.id: r.name for r in all_grps.all()}

    history = []
    for h in hist_result.scalars().all():
        history.append({
            "id": h.id, "group_id": h.group_id, "active": h.active,
            "started_at": h.started_at, "ended_at": h.ended_at,
            "reason": h.reason, "end_reason": h.end_reason,
            "group_name": grp_names.get(h.group_id),
        })

    active_offer = None
    r = await db.execute(
        select(Offer.id, Offer.status).where(
            Offer.candidate_id == cid,
            Offer.status.in_(["EXTENDED", "ACCEPTED"]),
        )
    )
    o = r.one_or_none()
    if o:
        active_offer = {"id": o.id, "status": o.status}

    return {
        "candidate": view(user, cd),
        "group": grp, "owner": owner,
        "assignment_history": history,
        "active_offer": active_offer,
        "permissions": permissions(user, cd),
    }


@router.patch("/candidates/{cid}")
async def update_candidate(cid: str, body: dict, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require_writer(user)
    c = await get_candidate_or_404(db, user, cid)
    cd = candidate_to_dict(c)
    lvl = edit_level(user, cd)
    if not lvl or cd["status"] == "ARCHIVED":
        raise ForbiddenError("You cannot edit this candidate")
    if "version" not in body:
        raise ValidationError("version is required")
    for forbidden in ("current_group_id", "status", "owner_id", "organization_id", "id"):
        if forbidden in body:
            raise ValidationError(f"'{forbidden}' cannot be changed through generic update; use the dedicated workflow")
    allowed = FULL_FIELDS if lvl == "full" else MARKETING_FIELDS
    if not is_ops(user):
        allowed = [a for a in allowed if a != "pay_rate"]
    upd = {k: v for k, v in body.items() if k in allowed}
    bad = [k for k in body if k not in allowed and k != "version" and k != "override_duplicate_reason"]
    if bad:
        raise ForbiddenError(f"Not permitted to edit: {', '.join(bad)}")
    if "email" in upd or "phone" in upd:
        exact, _ = await find_duplicates(db, user["organization_id"], upd.get("email"), upd.get("phone"), None, None, cid)
        if exact and not (is_ops(user) and body.get("override_duplicate_reason")):
            raise ConflictError({"code": "DUPLICATE", "message": "Another candidate has this email/phone", "exact": exact})
        if "email" in upd:
            upd["email_norm"] = norm_email(upd["email"])
        if "phone" in upd:
            upd["phone_norm"] = norm_phone(upd["phone"])

    doc = await claim(db, user, cid, int(body["version"]), upd)
    before = {k: cd.get(k) for k in upd}
    await audit(db, user, "CANDIDATE_UPDATED", "candidate", cid, before, upd)
    changed = [k for k in upd if not k.endswith("_norm")]
    await timeline(db, user, cid, "UPDATED", f"Updated {', '.join(changed)}")
    return view(user, doc)


async def guard_transition(db: AsyncSession, user: dict, c: dict, to: str):
    if to not in TRANSITIONS.get(c["status"], []):
        raise ValidationError(f"Transition {c['status']} → {to} is not allowed")
    if to == "MARKETING" and not c.get("current_group_id"):
        raise ValidationError("Candidate must be assigned to a group before marketing")
    if to == "SUBMITTED":
        r = await db.execute(select(Submission).where(Submission.candidate_id == c["id"]).limit(1))
        if not r.scalar_one_or_none():
            raise ValidationError("Create a submission first")
    if to == "INTERVIEWING":
        r = await db.execute(select(InterviewModel).where(
            InterviewModel.candidate_id == c["id"], InterviewModel.status == "SCHEDULED"
        ).limit(1))
        if not r.scalar_one_or_none():
            raise ValidationError("Schedule an interview first")
    if to == "OFFERED":
        r = await db.execute(select(Offer).where(
            Offer.candidate_id == c["id"], Offer.status.in_(["EXTENDED", "ACCEPTED"])
        ).limit(1))
        if not r.scalar_one_or_none():
            raise ValidationError("Record an offer first")
    if to == "PLACED":
        raise ValidationError("Use the placement workflow to place a candidate")


@router.post("/candidates/{cid}/transition")
async def transition(cid: str, body: TransitionIn, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require_writer(user)
    c = await get_candidate_or_404(db, user, cid)
    cd = candidate_to_dict(c)
    if not edit_level(user, cd):
        raise ForbiddenError("You cannot change this candidate's status")
    if cd["version"] != body.version:
        raise ConflictError()
    await guard_transition(db, user, cd, body.to_status)
    return view(user, await set_status(db, user, cd, body.to_status, body.version, body.reason))


@router.post("/candidates/{cid}/assign")
async def assign(cid: str, body: AssignIn, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require(user, ADMIN, OPERATIONS)
    c = await get_candidate_or_404(db, user, cid)
    cd = candidate_to_dict(c)
    if cd.get("current_group_id"):
        raise ValidationError("Candidate already has an active group. Use transfer.")
    if cd["status"] == "ARCHIVED":
        raise ValidationError("Restore the candidate first")
    doc = await assign_service(db, user, cd, body.group_id, body.version, body.reason)
    if doc["status"] == "NEW":
        doc = await set_status(db, user, doc, "BENCH", doc["version"], "Auto: assigned to group")
    return view(user, doc)


@router.post("/candidates/{cid}/transfer")
async def transfer(cid: str, body: TransferIn, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require_writer(user)
    c = await get_candidate_or_404(db, user, cid)
    cd = candidate_to_dict(c)
    if not cd.get("current_group_id"):
        raise ValidationError("Candidate has no active group. Use assign.")
    if not (is_ops(user) or user.get("_groups", {}).get(cd["current_group_id"]) == "LEAD"):
        raise ForbiddenError("Only Admin, Operations or the current group Lead can transfer")
    if body.to_group_id == cd["current_group_id"]:
        raise ValidationError("Candidate is already in this group")
    if not body.reason or not body.reason.strip():
        raise ValidationError("A reason is required for transfers")
    # Check active offer
    r = await db.execute(select(Offer).where(
        Offer.candidate_id == cid, Offer.status.in_(["EXTENDED", "ACCEPTED"])
    ).limit(1))
    active_offer = r.scalar_one_or_none()
    if active_offer or cd["status"] == "OFFERED":
        if not is_ops(user):
            raise ForbiddenError("Candidate has an active offer — only Admin/Operations may transfer")
        if not body.acknowledge_active_offer:
            raise ConflictError({"code": "ACTIVE_OFFER", "message": "Candidate has an active offer. Explicit acknowledgment required."})
    doc = await assign_service(db, user, cd, body.to_group_id, body.version, body.reason, "TRANSFERRED")
    await notify(db, user["organization_id"],
                 await ops_and_lead_ids(db, user["organization_id"], cd["current_group_id"]),
                 f"Candidate transferred out: {cd['first_name']} {cd['last_name']}", body.reason, f"/candidates/{cid}")
    return view(user, doc)


@router.post("/candidates/{cid}/unassign")
async def unassign(cid: str, body: UnassignIn, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require(user, ADMIN, OPERATIONS)
    c = await get_candidate_or_404(db, user, cid)
    cd = candidate_to_dict(c)
    if not cd.get("current_group_id"):
        raise ValidationError("Candidate has no active group")
    if not body.reason or not body.reason.strip():
        raise ValidationError("A reason is required")
    extra = {"current_group_id": None, "owner_id": None}
    if cd["status"] in MARKETING_STATES:
        if body.target_status not in ("BENCH", "ON_HOLD"):
            raise ValidationError("Choose BENCH or ON_HOLD explicitly when unassigning from marketing")
        extra["status"] = body.target_status
        extra["bench_since"] = utcnow()
    doc = await claim(db, user, cid, body.version, extra)
    await db.execute(
        update(CandidateGroupAssignment).where(
            CandidateGroupAssignment.candidate_id == cid, CandidateGroupAssignment.active == True,
        ).values(active=False, ended_at=utcnow(), ended_by=user["id"], end_reason=body.reason)
    )
    await db.flush()
    await audit(db, user, "CANDIDATE_UNASSIGNED", "candidate", cid,
                {"current_group_id": cd["current_group_id"], "status": cd["status"]},
                {"current_group_id": None, "status": doc["status"]}, body.reason)
    await timeline(db, user, cid, "UNASSIGNED",
                   f"Removed from group — {body.reason}" + (f" (status → {body.target_status})" if "status" in extra else ""))
    await notify(db, user["organization_id"],
                 await ops_and_lead_ids(db, user["organization_id"], cd["current_group_id"]),
                 f"Candidate unassigned: {cd['first_name']} {cd['last_name']}", body.reason, f"/candidates/{cid}")
    return view(user, doc)


@router.post("/candidates/{cid}/owner")
async def set_owner(cid: str, body: OwnerIn, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require_writer(user)
    c = await get_candidate_or_404(db, user, cid)
    cd = candidate_to_dict(c)
    if not (is_ops(user) or user.get("_groups", {}).get(cd.get("current_group_id")) == "LEAD"):
        raise ForbiddenError("Only Admin, Operations or group Lead can set owner")
    if body.owner_id:
        r = await db.execute(select(Membership).where(
            Membership.group_id == cd.get("current_group_id"),
            Membership.user_id == body.owner_id,
            Membership.active == True,
        ).limit(1))
        if not r.scalar_one_or_none():
            raise ValidationError("Owner must be an active member of the candidate's current group")
    doc = await claim(db, user, cid, body.version, {"owner_id": body.owner_id})
    await audit(db, user, "CANDIDATE_OWNER_SET", "candidate", cid,
                {"owner_id": cd.get("owner_id")}, {"owner_id": body.owner_id})
    await timeline(db, user, cid, "OWNER_CHANGED", "Owner updated")
    return view(user, doc)


@router.post("/candidates/{cid}/archive")
async def archive(cid: str, body: VersionIn, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require(user, ADMIN, OPERATIONS)
    c = await get_candidate_or_404(db, user, cid)
    cd = candidate_to_dict(c)
    if not body.reason:
        raise ValidationError("A reason is required")
    doc = await claim(db, user, cid, body.version, {
        "status": "ARCHIVED", "prior_status": cd["status"],
        "current_group_id": None, "owner_id": None, "archived_at": utcnow(),
    })
    await db.execute(
        update(CandidateGroupAssignment).where(
            CandidateGroupAssignment.candidate_id == cid, CandidateGroupAssignment.active == True,
        ).values(active=False, ended_at=utcnow(), ended_by=user["id"], end_reason="ARCHIVED")
    )
    await audit(db, user, "CANDIDATE_ARCHIVED", "candidate", cid,
                {"status": cd["status"], "current_group_id": cd.get("current_group_id")},
                {"status": "ARCHIVED"}, body.reason)
    await timeline(db, user, cid, "ARCHIVED", body.reason)
    return view(user, doc)


@router.post("/candidates/{cid}/restore")
async def restore(cid: str, body: VersionIn, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require(user, ADMIN, OPERATIONS)
    c = await get_candidate_or_404(db, user, cid)
    cd = candidate_to_dict(c)
    if cd["status"] != "ARCHIVED":
        raise ValidationError("Candidate is not archived")
    doc = await claim(db, user, cid, body.version, {"status": "BENCH", "bench_since": utcnow()})
    await audit(db, user, "CANDIDATE_RESTORED", "candidate", cid,
                {"status": "ARCHIVED"}, {"status": "BENCH", "current_group_id": None}, body.reason)
    await timeline(db, user, cid, "RESTORED", "Restored to BENCH without group access — assign a group explicitly")
    return view(user, doc)


@router.get("/candidates/{cid}/timeline")
async def get_timeline(cid: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await get_candidate_or_404(db, user, cid)
    result = await db.execute(
        select(TimelineEvent).where(
            TimelineEvent.candidate_id == cid,
            TimelineEvent.organization_id == user["organization_id"],
        ).order_by(TimelineEvent.created_at.desc()).limit(500)
    )
    return [
        {"id": t.id, "event": t.event, "detail": t.detail, "meta": t.meta,
         "actor_name": t.actor_name, "created_at": str(t.created_at)}
        for t in result.scalars().all()
    ]


@router.get("/candidates/{cid}/notes")
async def list_notes(cid: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    c = await get_candidate_or_404(db, user, cid)
    cd = candidate_to_dict(c)
    filters = [Note.candidate_id == cid]
    if not permissions(user, cd)["can_view_ops_notes"]:
        filters.append(Note.visibility != "OPERATIONS_ONLY")
    result = await db.execute(
        select(Note).where(*filters).order_by(Note.created_at.desc()).limit(500)
    )
    return [
        {"id": n.id, "body": n.body, "visibility": n.visibility,
         "author_id": n.author_id, "author_name": n.author_name, "created_at": str(n.created_at)}
        for n in result.scalars().all()
    ]


@router.post("/candidates/{cid}/notes")
async def add_note(cid: str, body: NoteIn, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require_writer(user)
    c = await get_candidate_or_404(db, user, cid)
    cd = candidate_to_dict(c)
    if not edit_level(user, cd):
        raise ForbiddenError("Not permitted")
    if body.visibility == "OPERATIONS_ONLY" and not is_ops(user):
        raise ForbiddenError("Only Admin/Operations can write operations-only notes")
    if not body.body.strip():
        raise ValidationError("Note cannot be empty")
    note = Note(
        id=new_id(), organization_id=user["organization_id"], candidate_id=cid,
        body=body.body, visibility=body.visibility,
        author_id=user["id"], author_name=user["name"],
    )
    db.add(note)
    await db.flush()
    await timeline(db, user, cid, "NOTE_ADDED",
                   "Note added" + (" (operations-only)" if body.visibility == "OPERATIONS_ONLY" else ""))
    return {"id": note.id, "body": note.body, "visibility": note.visibility,
            "author_id": note.author_id, "author_name": note.author_name, "created_at": str(note.created_at)}


@router.get("/tasks")
async def list_tasks(
    candidate_id: str = "", mine: bool = False, status: str = "",
    user=Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    filters = [Task.organization_id == user["organization_id"]]
    if candidate_id:
        await get_candidate_or_404(db, user, candidate_id)
        filters.append(Task.candidate_id == candidate_id)
    if mine or (user["role"] == EMPLOYEE and not candidate_id):
        filters.append(Task.assignee_id == user["id"])
    if status:
        filters.append(Task.status == status)
    result = await db.execute(select(Task).where(*filters).order_by(Task.due_date.asc()).limit(500))
    names_r = await db.execute(
        select(User.id, User.name).where(User.organization_id == user["organization_id"])
    )
    names = {r.id: r.name for r in names_r.all()}
    return [
        {"id": t.id, "title": t.title, "candidate_id": t.candidate_id,
         "assignee_id": t.assignee_id, "assignee_name": names.get(t.assignee_id),
         "due_date": t.due_date, "priority": t.priority, "status": t.status,
         "created_at": str(t.created_at)}
        for t in result.scalars().all()
    ]


@router.post("/tasks")
async def create_task(body: TaskIn, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require_writer(user)
    if body.candidate_id:
        await get_candidate_or_404(db, user, body.candidate_id)
    t = Task(
        id=new_id(), organization_id=user["organization_id"],
        title=body.title, candidate_id=body.candidate_id,
        assignee_id=body.assignee_id or user["id"],
        due_date=body.due_date, priority=body.priority,
        status="OPEN", created_by=user["id"],
    )
    db.add(t)
    await db.flush()
    if body.candidate_id:
        await timeline(db, user, body.candidate_id, "TASK_CREATED", body.title)
    if t.assignee_id != user["id"]:
        await notify(db, user["organization_id"], [t.assignee_id], "New task assigned", body.title)
    return {"id": t.id, "title": t.title, "candidate_id": t.candidate_id,
            "assignee_id": t.assignee_id, "due_date": t.due_date,
            "priority": t.priority, "status": t.status, "created_at": str(t.created_at)}


@router.patch("/tasks/{tid}")
async def update_task(tid: str, body: TaskPatch, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require_writer(user)
    result = await db.execute(
        select(Task).where(Task.id == tid, Task.organization_id == user["organization_id"])
    )
    t = result.scalar_one_or_none()
    if not t:
        raise NotFoundError("Task not found")
    if not is_ops(user) and user["id"] not in (t.assignee_id, t.created_by):
        raise ForbiddenError("Not your task")
    upd = {k: v for k, v in body.model_dump().items() if v is not None}
    if upd.get("status") and upd["status"] not in ("OPEN", "DONE"):
        raise ValidationError("Invalid task status")
    for k, v in upd.items():
        setattr(t, k, v)
    await db.flush()
    if t.candidate_id and upd.get("status") == "DONE":
        await timeline(db, user, t.candidate_id, "TASK_COMPLETED", t.title)
    return {"id": t.id, "title": t.title, "status": t.status}


@router.get("/candidates/{cid}/documents")
async def list_documents(cid: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await get_candidate_or_404(db, user, cid)
    result = await db.execute(
        select(Document).where(Document.candidate_id == cid, Document.is_deleted == False)
        .order_by(Document.doc_type, Document.version.desc())
    )
    return [
        {"id": d.id, "doc_type": d.doc_type, "version": d.version,
         "original_filename": d.original_filename, "content_type": d.content_type,
         "size": d.size, "scan_status": d.scan_status, "scan_reason": d.scan_reason,
         "uploaded_by_name": d.uploaded_by_name, "created_at": str(d.created_at)}
        for d in result.scalars().all()
    ]


@router.post("/candidates/{cid}/documents")
async def upload_document(
    cid: str, file: UploadFile = File(...), doc_type: str = Form("RESUME"),
    user=Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    require_writer(user)
    c = await get_candidate_or_404(db, user, cid)
    cd = candidate_to_dict(c)
    if not edit_level(user, cd):
        raise ForbiddenError("Not permitted to upload")
    data = await file.read()
    if len(data) > MAX_UPLOAD_SIZE:
        from app.exceptions import ValidationError
        raise ValidationError("File exceeds 10MB")
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "bin"
    # Get latest version
    result = await db.execute(
        select(func.max(Document.version)).where(
            Document.candidate_id == cid, Document.doc_type == doc_type
        )
    )
    last_ver = result.scalar() or 0
    version = last_ver + 1
    path = f"benchos/{user['organization_id']}/quarantine/{new_id()}.{ext}"

    doc = Document(
        id=new_id(), organization_id=user["organization_id"], candidate_id=cid,
        doc_type=doc_type, version=version, original_filename=file.filename,
        content_type=file.content_type, size=len(data), storage_path=path,
        scan_status="PENDING", scan_engine="SIMULATED", is_deleted=False,
        uploaded_by=user["id"], uploaded_by_name=user["name"],
    )
    db.add(doc)
    # Queue scan job
    db.add(BackgroundJob(
        id=new_id(), organization_id=user["organization_id"], type="SCAN",
        status="PENDING", payload={"document_id": doc.id}, created_by=user["id"],
    ))
    await db.flush()
    await audit(db, user, "DOCUMENT_UPLOADED", "document", doc.id, None,
                {"candidate_id": cid, "doc_type": doc_type, "version": version, "filename": file.filename})
    await timeline(db, user, cid, "DOCUMENT_UPLOADED",
                   f"{doc_type} v{version}: {file.filename} (quarantined, scanning)")
    await put_object(path, data, file.content_type or "application/octet-stream")
    return {"id": doc.id, "doc_type": doc.doc_type, "version": version,
            "original_filename": doc.original_filename, "scan_status": doc.scan_status,
            "created_at": str(doc.created_at)}


@router.get("/documents/{did}/signed-url")
async def signed_url(did: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Document).where(
            Document.id == did, Document.organization_id == user["organization_id"],
            Document.is_deleted == False,
        )
    )
    d = result.scalar_one_or_none()
    if not d:
        raise NotFoundError("Document not found")
    await get_candidate_or_404(db, user, d.candidate_id)
    if d.scan_status != "PASSED":
        raise LockedError(f"Download blocked: scan status is {d.scan_status}")
    token = make_token(user["id"], "download", 5, {"doc": did})
    await audit(db, user, "DOCUMENT_URL_ISSUED", "document", did)
    return {"url": f"/api/documents/download?token={token}", "expires_in": 300}


@router.get("/documents/download")
async def download_document(token: str, db: AsyncSession = Depends(get_db)):
    claims = decode_token(token, "download")
    document = await db.get(Document, claims.get("doc"))
    if not document or document.is_deleted or document.scan_status != "PASSED":
        raise LockedError("Download blocked")
    data, content_type = await get_object(document.storage_path)
    filename = quote(document.original_filename, safe="")
    return FileResponse(
        content=data,
        media_type=document.content_type or content_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


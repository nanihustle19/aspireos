"""Candidate authorization and redaction helpers."""
from sqlalchemy import select, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import (
    ADMIN, OPERATIONS, AUDITOR, EMPLOYEE, MARKETING_STATES,
    PAY_FIELDS, BILL_FIELDS,
)
from app.exceptions import NotFoundError
from app.models.candidate import Candidate
from app.services.auth_service import is_ops, can_see_bill


def candidate_scope_filters(user: dict) -> list:
    """Build SQLAlchemy WHERE clauses to scope candidate access by user role/groups."""
    org_filter = Candidate.organization_id == user["organization_id"]

    if user["role"] in (ADMIN, OPERATIONS, AUDITOR):
        return [org_filter]

    groups = user.get("_groups", {})
    full_groups = [g for g, r in groups.items() if r != "MARKETING"]
    mkt_groups = [g for g, r in groups.items() if r == "MARKETING"]

    conditions = []
    if full_groups:
        conditions.append(Candidate.current_group_id.in_(full_groups))
    if mkt_groups:
        conditions.append(
            and_(
                Candidate.current_group_id.in_(mkt_groups),
                Candidate.status.in_(MARKETING_STATES),
            )
        )
        conditions.append(
            and_(
                Candidate.current_group_id.in_(mkt_groups),
                Candidate.status.in_(["BENCH", "ON_HOLD"]),
                Candidate.owner_id == user["id"],
            )
        )

    if not conditions:
        # No group access — return impossible filter
        return [org_filter, Candidate.id == "__none__"]

    return [org_filter, or_(*conditions)]


async def get_candidate_or_404(db: AsyncSession, user: dict, cid: str) -> Candidate:
    """Fetch a candidate scoped by user access, or raise 404."""
    filters = candidate_scope_filters(user)
    result = await db.execute(
        select(Candidate).where(*filters, Candidate.id == cid)
    )
    c = result.scalar_one_or_none()
    if not c:
        raise NotFoundError("Candidate not found or not accessible")
    return c


def group_role(user: dict, cand_dict: dict) -> str | None:
    return user.get("_groups", {}).get(cand_dict.get("current_group_id"))


def edit_level(user: dict, cand_dict: dict) -> str | None:
    """Returns 'full', 'marketing', or None."""
    if is_ops(user):
        return "full"
    if user["role"] != EMPLOYEE:
        return None
    r = group_role(user, cand_dict)
    if r in ("LEAD", "RECRUITER"):
        return "full"
    if r == "MARKETING":
        return "marketing"
    return None


def redact(user: dict, doc: dict, group_id: str | None = None) -> dict:
    """Redact rate fields based on user role/group access."""
    if not doc:
        return doc
    d = dict(doc)
    gid = group_id if group_id is not None else d.get("current_group_id")
    if not is_ops(user):
        for f in PAY_FIELDS:
            if f in d:
                d[f] = None
                d.setdefault("_redacted", []).append(f)
    if not can_see_bill(user, gid):
        for f in BILL_FIELDS:
            if f in d:
                d[f] = None
                d.setdefault("_redacted", []).append(f)
    return d


def candidate_to_dict(c: Candidate) -> dict:
    """Convert SQLAlchemy Candidate to dict."""
    return {
        "id": c.id, "organization_id": c.organization_id,
        "first_name": c.first_name, "last_name": c.last_name,
        "email": c.email, "phone": c.phone, "location": c.location,
        "primary_skill": c.primary_skill, "skills": c.skills or [],
        "experience_years": c.experience_years,
        "visa_status": c.visa_status, "work_authorization": c.work_authorization,
        "availability_date": c.availability_date, "source": c.source,
        "linkedin_url": c.linkedin_url,
        "pay_rate": c.pay_rate, "bill_rate": c.bill_rate, "target_rate": c.target_rate,
        "summary": c.summary, "relocation": c.relocation, "timezone": c.timezone,
        "status": c.status, "prior_status": c.prior_status,
        "current_group_id": c.current_group_id, "owner_id": c.owner_id,
        "version": c.version, "bench_since": c.bench_since,
        "created_at": str(c.created_at) if c.created_at else None,
        "updated_at": str(c.updated_at) if c.updated_at else None,
        "created_by": c.created_by,
    }


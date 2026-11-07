"""Pipeline routes — submissions, interviews, offers, placements + directory CRUD — /api"""
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.constants import (
    ADMIN, OPERATIONS, EMPLOYEE,
    SUBMISSION_STATUSES, INTERVIEW_STATUSES, OFFER_STATUSES,
)
from app.exceptions import NotFoundError, ForbiddenError, ConflictError, ValidationError
from app.models.candidate import Candidate
from app.models.group import Group
from app.models.user import User
from app.models.pipeline import Vendor, Client, Job, Submission, Interview, Offer, Placement
from app.services.auth_service import (
    utcnow, new_id, get_current_user, is_ops, require, require_writer,
    audit, timeline, notify, ops_and_lead_ids,
)
from app.services.authorization import (
    get_candidate_or_404, edit_level, redact, candidate_to_dict,
    candidate_scope_filters,
)

router = APIRouter(prefix="/api")

ENTITY_FIELDS = {
    "vendors": ["name", "contact_name", "contact_email", "phone", "tier", "notes", "status"],
    "clients": ["name", "industry", "location", "contact_name", "contact_email", "notes", "status"],
    "jobs": ["title", "client_id", "vendor_id", "location", "work_mode", "rate", "skills", "description", "status", "openings"],
}
ENTITY_MODELS = {"vendors": Vendor, "clients": Client, "jobs": Job}


# ── Schemas ────────────────────────────────────────────────────

class SubmissionIn(BaseModel):
    candidate_id: str
    job_id: str
    submission_rate: Optional[float] = None
    notes: Optional[str] = None

class StatusIn(BaseModel):
    status: str
    note: Optional[str] = None
    version: int

class InterviewIn(BaseModel):
    submission_id: str
    scheduled_at: str
    timezone: str = "America/New_York"
    duration_minutes: int = 60
    mode: str = "VIDEO"
    round: str = "Round 1"
    interviewer: Optional[str] = None

class RescheduleIn(BaseModel):
    scheduled_at: str
    timezone: str
    reason: str
    version: int

class OfferIn(BaseModel):
    submission_id: str
    bill_rate: Optional[float] = None
    pay_rate: Optional[float] = None
    start_date: Optional[str] = None
    notes: Optional[str] = None

class PlacementIn(BaseModel):
    offer_id: str
    start_date: str
    end_date: Optional[str] = None
    confirm: bool = False


# ── Helpers ────────────────────────────────────────────────────

def can_write_pipeline(user: dict, cand_dict: dict):
    require_writer(user)
    if not edit_level(user, cand_dict):
        raise ForbiddenError("You cannot work this candidate")


def entity_to_dict(e) -> dict:
    d = {}
    for col in e.__table__.columns:
        val = getattr(e, col.name)
        if col.name in ("created_at", "updated_at") and val:
            val = str(val)
        d[col.name] = val
    return d


async def enrich(db: AsyncSession, user: dict, items: list[dict]) -> list[dict]:
    if not items:
        return items
    org_id = user["organization_id"]
    cids = list({i["candidate_id"] for i in items})
    cr = await db.execute(select(Candidate).where(Candidate.id.in_(cids)))
    cands = {c.id: c for c in cr.scalars().all()}
    jr = await db.execute(select(Job).where(Job.organization_id == org_id))
    jobs = {j.id: j for j in jr.scalars().all()}
    clr = await db.execute(select(Client.id, Client.name).where(Client.organization_id == org_id))
    clients = {r.id: r.name for r in clr.all()}
    grr = await db.execute(select(Group.id, Group.name).where(Group.organization_id == org_id))
    groups = {r.id: r.name for r in grr.all()}

    out = []
    for i in items:
        c = cands.get(i["candidate_id"])
        j = jobs.get(i.get("job_id"))
        enriched = redact(user, i, i.get("group_id"))
        enriched["candidate_name"] = f"{c.first_name} {c.last_name}".strip() if c else ""
        enriched["candidate_status"] = c.status if c else None
        enriched["job_title"] = j.title if j else None
        enriched["client_name"] = clients.get(j.client_id) if j else None
        enriched["group_name"] = groups.get(i.get("group_id"))
        out.append(enriched)
    return out


async def versioned_update(db: AsyncSession, model, user: dict, eid: str, version: int,
                           upd: dict, push_field: str | None = None, push_value=None):
    r = await db.execute(
        select(model).where(
            model.id == eid, model.organization_id == user["organization_id"], model.version == version
        ).with_for_update()
    )
    entity = r.scalar_one_or_none()
    if not entity:
        raise ConflictError()
    for k, v in upd.items():
        setattr(entity, k, v)
    entity.version += 1
    if push_field and push_value:
        current = getattr(entity, push_field) or []
        setattr(entity, push_field, current + [push_value])
    await db.flush()
    return entity_to_dict(entity)


async def get_scoped_entity(db: AsyncSession, model, user: dict, eid: str):
    filters = [model.id == eid, model.organization_id == user["organization_id"]]
    if user["role"] == EMPLOYEE:
        # Scope by group access
        group_ids = list(user.get("_groups", {}).keys())
        if hasattr(model, "group_id") and group_ids:
            filters.append(model.group_id.in_(group_ids))
        elif hasattr(model, "group_id"):
            filters.append(model.group_id == "__none__")
    r = await db.execute(select(model).where(*filters))
    entity = r.scalar_one_or_none()
    if not entity:
        raise NotFoundError("Not found")
    return entity


# ── Directory CRUD (vendors, clients, jobs) ────────────────────

@router.get("/{entity}")
async def list_entities(entity: str, q: str = "", status: str = "",
                        user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if entity not in ENTITY_MODELS:
        raise NotFoundError()
    model = ENTITY_MODELS[entity]
    filters = [model.organization_id == user["organization_id"]]
    if q:
        if hasattr(model, "name"):
            filters.append(model.name.ilike(f"%{q}%"))
    if status:
        filters.append(model.status == status)
    r = await db.execute(select(model).where(*filters).order_by(model.created_at.desc()).limit(1000))
    items = [entity_to_dict(e) for e in r.scalars().all()]

    if entity == "jobs":
        clr = await db.execute(select(Client.id, Client.name).where(Client.organization_id == user["organization_id"]))
        cl = {r.id: r.name for r in clr.all()}
        vnr = await db.execute(select(Vendor.id, Vendor.name).where(Vendor.organization_id == user["organization_id"]))
        vn = {r.id: r.name for r in vnr.all()}
        for j in items:
            j["client_name"] = cl.get(j.get("client_id"))
            j["vendor_name"] = vn.get(j.get("vendor_id"))
            if not is_ops(user) and not any(r in ("LEAD", "MARKETING") for r in user.get("_groups", {}).values()):
                j["rate"] = None
    return items


@router.post("/{entity}")
async def create_entity(entity: str, body: dict, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if entity not in ENTITY_MODELS:
        raise NotFoundError()
    require_writer(user)
    model = ENTITY_MODELS[entity]
    fields = ENTITY_FIELDS[entity]
    data = {k: body.get(k) for k in fields if k in body}
    if not (data.get("name") or data.get("title")):
        raise ValidationError("Name/title is required")
    eid = new_id()
    kwargs = {
        "id": eid, "organization_id": user["organization_id"],
        "status": data.get("status") or ("OPEN" if entity == "jobs" else "ACTIVE"),
        "version": 1, "created_by": user["id"], **data,
    }
    e = model(**kwargs)
    db.add(e)
    await db.flush()
    await audit(db, user, f"{entity.upper()[:-1]}_CREATED", entity[:-1], eid, None, data)
    return entity_to_dict(e)


@router.patch("/{entity}/{eid}")
async def update_entity(entity: str, eid: str, body: dict,
                        user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if entity not in ENTITY_MODELS:
        raise NotFoundError()
    require_writer(user)
    model = ENTITY_MODELS[entity]
    fields = ENTITY_FIELDS[entity]
    data = {k: body[k] for k in fields if k in body}
    if "version" not in body:
        raise ValidationError("version is required")
    r = await db.execute(select(model).where(model.id == eid, model.organization_id == user["organization_id"]))
    before = r.scalar_one_or_none()
    if not before:
        raise NotFoundError()
    before_dict = entity_to_dict(before)
    res = await versioned_update(db, model, user, eid, body["version"], data)
    await audit(db, user, f"{entity.upper()[:-1]}_UPDATED", entity[:-1], eid,
                {k: before_dict.get(k) for k in data}, data)
    return res


# ── Submissions ────────────────────────────────────────────────

@router.get("/pipeline/submissions")
async def list_submissions(candidate_id: str = "", status: str = "",
                           user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    filters = [Submission.organization_id == user["organization_id"]]
    if user["role"] == EMPLOYEE:
        group_ids = list(user.get("_groups", {}).keys())
        if group_ids:
            filters.append(Submission.group_id.in_(group_ids))
        else:
            filters.append(Submission.group_id == "__none__")
    if candidate_id:
        filters.append(Submission.candidate_id == candidate_id)
    if status:
        filters.append(Submission.status == status)
    r = await db.execute(select(Submission).where(*filters).order_by(Submission.created_at.desc()).limit(1000))
    items = [entity_to_dict(s) for s in r.scalars().all()]
    return await enrich(db, user, items)


@router.post("/pipeline/submissions")
async def create_submission(body: SubmissionIn, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    c = await get_candidate_or_404(db, user, body.candidate_id)
    cd = candidate_to_dict(c)
    can_write_pipeline(user, cd)
    if cd["status"] not in ("MARKETING", "SUBMITTED", "INTERVIEWING"):
        raise ValidationError("Candidate must be in MARKETING (or later) to be submitted")
    jr = await db.execute(select(Job).where(Job.id == body.job_id, Job.organization_id == user["organization_id"]))
    job = jr.scalar_one_or_none()
    if not job:
        raise NotFoundError("Job not found")
    # Check for active submission
    sr = await db.execute(select(Submission).where(
        Submission.candidate_id == c.id, Submission.job_id == job.id,
        Submission.status.not_in(["REJECTED", "WITHDRAWN"]),
    ).limit(1))
    if sr.scalar_one_or_none():
        raise ConflictError("Candidate already has an active submission for this job")

    sid = new_id()
    s = Submission(
        id=sid, organization_id=user["organization_id"], candidate_id=c.id, job_id=job.id,
        client_id=job.client_id, vendor_id=job.vendor_id, group_id=cd["current_group_id"],
        submission_rate=body.submission_rate, notes=body.notes, status="SUBMITTED", version=1,
        status_history=[{"status": "SUBMITTED", "at": utcnow(), "by": user["name"], "note": body.notes}],
        submitted_by=user["id"], submitted_by_name=user["name"],
    )
    db.add(s)
    await db.flush()
    await audit(db, user, "SUBMISSION_CREATED", "submission", sid, None,
                {"candidate_id": c.id, "job_id": job.id, "submission_rate": body.submission_rate})
    await timeline(db, user, c.id, "SUBMITTED", f"Submitted to {job.title}")
    if cd["status"] == "MARKETING":
        from app.routes.candidates import set_status
        await set_status(db, user, cd, "SUBMITTED", cd["version"], "Auto: submission created")
    return (await enrich(db, user, [entity_to_dict(s)]))[0]


@router.patch("/pipeline/submissions/{sid}/status")
async def submission_status(sid: str, body: StatusIn, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    s = await get_scoped_entity(db, Submission, user, sid)
    c = await get_candidate_or_404(db, user, s.candidate_id)
    cd = candidate_to_dict(c)
    can_write_pipeline(user, cd)
    if body.status not in SUBMISSION_STATUSES or body.status == "PLACED":
        raise ValidationError("Invalid status")
    res = await versioned_update(db, Submission, user, sid, body.version, {"status": body.status},
                                 "status_history", {"status": body.status, "at": utcnow(), "by": user["name"], "note": body.note})
    await audit(db, user, "SUBMISSION_STATUS_CHANGED", "submission", sid,
                {"status": s.status}, {"status": body.status}, body.note, candidate_id=c.id)
    await timeline(db, user, c.id, "SUBMISSION_STATUS", f"Submission → {body.status}")
    if body.status in ("REJECTED", "WITHDRAWN") and cd["status"] == "SUBMITTED":
        sr = await db.execute(select(Submission).where(
            Submission.candidate_id == c.id, Submission.status.not_in(["REJECTED", "WITHDRAWN"])
        ).limit(1))
        if not sr.scalar_one_or_none():
            from app.routes.candidates import set_status
            await set_status(db, user, cd, "MARKETING", cd["version"], "Auto: no active submissions")
    return (await enrich(db, user, [res]))[0]


# ── Interviews ─────────────────────────────────────────────────

@router.get("/pipeline/interviews")
async def list_interviews(candidate_id: str = "", upcoming: bool = False,
                          user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    filters = [Interview.organization_id == user["organization_id"]]
    if user["role"] == EMPLOYEE:
        group_ids = list(user.get("_groups", {}).keys())
        if group_ids:
            filters.append(Interview.group_id.in_(group_ids))
        else:
            filters.append(Interview.group_id == "__none__")
    if candidate_id:
        filters.append(Interview.candidate_id == candidate_id)
    if upcoming:
        filters.extend([Interview.scheduled_at >= utcnow(), Interview.status == "SCHEDULED"])
    order = Interview.scheduled_at.asc() if upcoming else Interview.scheduled_at.desc()
    r = await db.execute(select(Interview).where(*filters).order_by(order).limit(1000))
    return await enrich(db, user, [entity_to_dict(i) for i in r.scalars().all()])


@router.post("/pipeline/interviews")
async def create_interview(body: InterviewIn, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    s = await get_scoped_entity(db, Submission, user, body.submission_id)
    c = await get_candidate_or_404(db, user, s.candidate_id)
    cd = candidate_to_dict(c)
    can_write_pipeline(user, cd)
    iid = new_id()
    i = Interview(
        id=iid, organization_id=user["organization_id"], candidate_id=c.id,
        submission_id=s.id, job_id=s.job_id, group_id=s.group_id,
        scheduled_at=body.scheduled_at, timezone=body.timezone,
        duration_minutes=body.duration_minutes, mode=body.mode, round=body.round,
        interviewer=body.interviewer, status="SCHEDULED", version=1, created_by=user["id"],
        reschedule_history=[],
    )
    db.add(i)
    await db.flush()
    if s.status in ("SUBMITTED", "CLIENT_REVIEW"):
        await versioned_update(db, Submission, user, s.id, s.version, {"status": "INTERVIEW"},
                               "status_history", {"status": "INTERVIEW", "at": utcnow(), "by": user["name"], "note": "Auto: interview scheduled"})
    await audit(db, user, "INTERVIEW_SCHEDULED", "interview", iid, None,
                {"candidate_id": c.id, "scheduled_at": body.scheduled_at, "timezone": body.timezone})
    await timeline(db, user, c.id, "INTERVIEW_SCHEDULED", f"{body.round} on {body.scheduled_at} ({body.timezone})")
    if cd["status"] == "SUBMITTED":
        from app.routes.candidates import set_status
        await set_status(db, user, cd, "INTERVIEWING", cd["version"], "Auto: interview scheduled")
    return (await enrich(db, user, [entity_to_dict(i)]))[0]


@router.post("/pipeline/interviews/{iid}/reschedule")
async def reschedule(iid: str, body: RescheduleIn, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    i = await get_scoped_entity(db, Interview, user, iid)
    c = await get_candidate_or_404(db, user, i.candidate_id)
    cd = candidate_to_dict(c)
    can_write_pipeline(user, cd)
    if i.status != "SCHEDULED":
        raise ValidationError("Only scheduled interviews can be rescheduled")
    if not body.reason.strip():
        raise ValidationError("Reason required")
    res = await versioned_update(
        db, Interview, user, iid, body.version,
        {"scheduled_at": body.scheduled_at, "timezone": body.timezone},
        "reschedule_history", {
            "from": i.scheduled_at, "from_tz": i.timezone,
            "to": body.scheduled_at, "to_tz": body.timezone,
            "reason": body.reason, "by": user["name"], "at": utcnow(),
        },
    )
    await audit(db, user, "INTERVIEW_RESCHEDULED", "interview", iid,
                {"scheduled_at": i.scheduled_at}, {"scheduled_at": body.scheduled_at},
                body.reason, candidate_id=c.id)
    await timeline(db, user, c.id, "INTERVIEW_RESCHEDULED",
                   f"{i.scheduled_at} → {body.scheduled_at} — {body.reason}")
    return (await enrich(db, user, [res]))[0]


@router.patch("/pipeline/interviews/{iid}/status")
async def interview_status(iid: str, body: StatusIn, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    i = await get_scoped_entity(db, Interview, user, iid)
    c = await get_candidate_or_404(db, user, i.candidate_id)
    cd = candidate_to_dict(c)
    can_write_pipeline(user, cd)
    if body.status not in INTERVIEW_STATUSES:
        raise ValidationError("Invalid status")
    res = await versioned_update(db, Interview, user, iid, body.version,
                                 {"status": body.status, "feedback": body.note})
    await audit(db, user, "INTERVIEW_STATUS_CHANGED", "interview", iid,
                {"status": i.status}, {"status": body.status}, body.note, candidate_id=c.id)
    await timeline(db, user, c.id, "INTERVIEW_" + body.status, body.note or "")
    return (await enrich(db, user, [res]))[0]


# ── Offers ─────────────────────────────────────────────────────

@router.get("/pipeline/offers")
async def list_offers(candidate_id: str = "", user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    filters = [Offer.organization_id == user["organization_id"]]
    if user["role"] == EMPLOYEE:
        group_ids = list(user.get("_groups", {}).keys())
        if group_ids:
            filters.append(Offer.group_id.in_(group_ids))
        else:
            filters.append(Offer.group_id == "__none__")
    if candidate_id:
        filters.append(Offer.candidate_id == candidate_id)
    r = await db.execute(select(Offer).where(*filters).order_by(Offer.created_at.desc()).limit(1000))
    return await enrich(db, user, [entity_to_dict(o) for o in r.scalars().all()])


@router.post("/pipeline/offers")
async def create_offer(body: OfferIn, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    s = await get_scoped_entity(db, Submission, user, body.submission_id)
    c = await get_candidate_or_404(db, user, s.candidate_id)
    cd = candidate_to_dict(c)
    can_write_pipeline(user, cd)
    if cd["status"] not in ("SUBMITTED", "INTERVIEWING", "OFFERED"):
        raise ValidationError("Candidate must be submitted or interviewing to receive an offer")
    oid = new_id()
    o = Offer(
        id=oid, organization_id=user["organization_id"], candidate_id=c.id,
        submission_id=s.id, job_id=s.job_id, group_id=s.group_id,
        bill_rate=body.bill_rate, pay_rate=body.pay_rate if is_ops(user) else None,
        start_date=body.start_date, notes=body.notes, status="EXTENDED", version=1, created_by=user["id"],
    )
    db.add(o)
    await db.flush()
    await versioned_update(db, Submission, user, s.id, s.version, {"status": "OFFER"},
                           "status_history", {"status": "OFFER", "at": utcnow(), "by": user["name"], "note": "Offer extended"})
    await audit(db, user, "OFFER_CREATED", "offer", oid, None,
                {"candidate_id": c.id, "bill_rate": body.bill_rate, "start_date": body.start_date})
    await timeline(db, user, c.id, "OFFER_EXTENDED", "Offer extended")
    if cd["status"] != "OFFERED":
        from app.routes.candidates import set_status
        await set_status(db, user, cd, "OFFERED", cd["version"], "Auto: offer extended")
    await notify(db, user["organization_id"],
                 await ops_and_lead_ids(db, user["organization_id"], s.group_id),
                 f"Offer extended: {cd['first_name']} {cd['last_name']}", "Review the offer",
                 f"/candidates/{c.id}")
    return (await enrich(db, user, [entity_to_dict(o)]))[0]


@router.patch("/pipeline/offers/{oid}/status")
async def offer_status(oid: str, body: StatusIn, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    o = await get_scoped_entity(db, Offer, user, oid)
    c = await get_candidate_or_404(db, user, o.candidate_id)
    cd = candidate_to_dict(c)
    can_write_pipeline(user, cd)
    if body.status not in OFFER_STATUSES:
        raise ValidationError("Invalid status")
    if body.status == "ACCEPTED" and not is_ops(user) and user.get("_groups", {}).get(o.group_id) != "LEAD":
        raise ForbiddenError("Only Admin, Operations or group Lead can mark offer accepted")
    res = await versioned_update(db, Offer, user, oid, body.version, {"status": body.status})
    await audit(db, user, "OFFER_STATUS_CHANGED", "offer", oid,
                {"status": o.status}, {"status": body.status}, body.note, candidate_id=c.id)
    await timeline(db, user, c.id, "OFFER_" + body.status, body.note or "")
    if body.status in ("DECLINED", "WITHDRAWN") and cd["status"] == "OFFERED":
        or2 = await db.execute(select(Offer).where(
            Offer.candidate_id == c.id, Offer.status.in_(["EXTENDED", "ACCEPTED"])
        ).limit(1))
        if not or2.scalar_one_or_none():
            from app.routes.candidates import set_status
            await set_status(db, user, cd, "MARKETING", cd["version"], f"Auto: offer {body.status.lower()}")
    return (await enrich(db, user, [res]))[0]


# ── Placements ─────────────────────────────────────────────────

@router.get("/pipeline/placements")
async def list_placements(candidate_id: str = "", user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    filters = [Placement.organization_id == user["organization_id"]]
    if user["role"] == EMPLOYEE:
        group_ids = list(user.get("_groups", {}).keys())
        if group_ids:
            filters.append(Placement.group_id.in_(group_ids))
        else:
            filters.append(Placement.group_id == "__none__")
    if candidate_id:
        filters.append(Placement.candidate_id == candidate_id)
    r = await db.execute(select(Placement).where(*filters).order_by(Placement.created_at.desc()).limit(1000))
    return await enrich(db, user, [entity_to_dict(p) for p in r.scalars().all()])


@router.post("/pipeline/placements")
async def create_placement(body: PlacementIn, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require(user, ADMIN, OPERATIONS)
    if not body.confirm:
        raise ValidationError("Explicit confirmation required to create a placement")
    o = await get_scoped_entity(db, Offer, user, body.offer_id)
    if o.status != "ACCEPTED":
        raise ValidationError("Offer must be ACCEPTED before placement")
    pr = await db.execute(select(Placement).where(Placement.offer_id == o.id).limit(1))
    if pr.scalar_one_or_none():
        raise ConflictError("Placement already exists for this offer")
    c = await get_candidate_or_404(db, user, o.candidate_id)
    cd = candidate_to_dict(c)
    if cd["status"] != "OFFERED":
        raise ValidationError("Candidate must be in OFFERED status")

    pid = new_id()
    p = Placement(
        id=pid, organization_id=user["organization_id"], candidate_id=c.id,
        offer_id=o.id, job_id=o.job_id, group_id=o.group_id,
        bill_rate=o.bill_rate, pay_rate=o.pay_rate,
        start_date=body.start_date, end_date=body.end_date,
        status="ACTIVE", version=1, created_by=user["id"],
    )
    db.add(p)
    # Update all related submissions to PLACED
    await db.execute(
        update(Submission).where(
            Submission.candidate_id == c.id, Submission.job_id == o.job_id
        ).values(status="PLACED")
    )
    # Place the candidate
    from app.routes.candidates import claim
    await claim(db, user_to_dict_compat(user), c.id, cd["version"], {"status": "PLACED", "bench_since": None})
    await db.flush()
    await audit(db, user, "CANDIDATE_PLACED", "placement", pid,
                {"status": cd["status"]}, {"candidate_id": c.id, "status": "PLACED"})
    await timeline(db, user, c.id, "PLACED", f"Placed — start {body.start_date}")
    await notify(db, user["organization_id"],
                 await ops_and_lead_ids(db, user["organization_id"], o.group_id),
                 f"Placement: {cd['first_name']} {cd['last_name']}", f"Starts {body.start_date}",
                 f"/candidates/{c.id}")
    return (await enrich(db, user, [entity_to_dict(p)]))[0]


@router.post("/pipeline/placements/{pid}/end")
async def end_placement(pid: str, body: StatusIn, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require(user, ADMIN, OPERATIONS)
    p = await get_scoped_entity(db, Placement, user, pid)
    if p.status != "ACTIVE":
        raise ValidationError("Placement not active")
    res = await versioned_update(db, Placement, user, pid, body.version,
                                 {"status": "ENDED", "ended_at": utcnow(), "end_reason": body.note})
    c = await get_candidate_or_404(db, user, p.candidate_id)
    cd = candidate_to_dict(c)
    if cd["status"] == "PLACED":
        from app.routes.candidates import set_status
        await set_status(db, user, cd, "BENCH", cd["version"], "Placement ended")
    await audit(db, user, "PLACEMENT_ENDED", "placement", pid,
                {"status": "ACTIVE"}, {"status": "ENDED"}, body.note, candidate_id=p.candidate_id)
    return (await enrich(db, user, [res]))[0]


def user_to_dict_compat(user: dict) -> dict:
    """Ensure user dict has needed fields for claim()."""
    return user


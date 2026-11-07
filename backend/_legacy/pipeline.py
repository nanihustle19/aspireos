from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core import (db, ADMIN, OPS, EMP, candidate_scope, now, new_id, get_current_user, is_ops, require, require_writer,
                  edit_level, redact, get_candidate_or_404, audit, timeline, notify, ops_and_lead_ids, rx)
from candidates import set_status

router = APIRouter(prefix="/api")

ENTITY_FIELDS = {
    "vendors": ["name", "contact_name", "contact_email", "phone", "tier", "notes", "status"],
    "clients": ["name", "industry", "location", "contact_name", "contact_email", "notes", "status"],
    "jobs": ["title", "client_id", "vendor_id", "location", "work_mode", "rate", "skills", "description", "status", "openings"],
}


async def scope_filter(user):
    f = {"organization_id": user["organization_id"]}
    if user["role"] == EMP:
        f["group_id"] = {"$in": list(user.get("_groups", {}).keys())}
        f["candidate_id"] = {"$in": await db.candidates.distinct("id", candidate_scope(user))}
    return f


def can_write_pipeline(user, cand):
    require_writer(user)
    if not edit_level(user, cand):
        raise HTTPException(403, "You cannot work this candidate")


@router.get("/{entity}")
async def list_entities(entity: str, q: str = "", status: str = "", user=Depends(get_current_user)):
    if entity not in ENTITY_FIELDS:
        raise HTTPException(404, "Not found")
    f = {"organization_id": user["organization_id"]}
    if q:
        f["$or"] = [{"name": rx(q)}, {"title": rx(q)}]
    if status:
        f["status"] = status
    items = await db[entity].find(f, {"_id": 0}).sort("created_at", -1).to_list(1000)
    if entity == "jobs":
        cl = {c["id"]: c["name"] for c in await db.clients.find({"organization_id": user["organization_id"]}, {"_id": 0}).to_list(1000)}
        vn = {c["id"]: c["name"] for c in await db.vendors.find({"organization_id": user["organization_id"]}, {"_id": 0}).to_list(1000)}
        for j in items:
            j["client_name"], j["vendor_name"] = cl.get(j.get("client_id")), vn.get(j.get("vendor_id"))
            if not is_ops(user) and not any(r in ("LEAD", "MARKETING") for r in user.get("_groups", {}).values()):
                j["rate"] = None
    return items


@router.post("/{entity}")
async def create_entity(entity: str, body: dict, user=Depends(get_current_user)):
    if entity not in ENTITY_FIELDS:
        raise HTTPException(404, "Not found")
    require_writer(user)
    data = {k: body.get(k) for k in ENTITY_FIELDS[entity] if k in body}
    if not (data.get("name") or data.get("title")):
        raise HTTPException(422, "Name/title is required")
    doc = data | {"id": new_id(), "organization_id": user["organization_id"], "status": data.get("status") or ("OPEN" if entity == "jobs" else "ACTIVE"),
                  "version": 1, "created_by": user["id"], "created_at": now()}
    await db[entity].insert_one(dict(doc))
    await audit(user, f"{entity.upper()[:-1]}_CREATED", entity[:-1], doc["id"], None, data)
    return doc


@router.patch("/{entity}/{eid}")
async def update_entity(entity: str, eid: str, body: dict, user=Depends(get_current_user)):
    if entity not in ENTITY_FIELDS:
        raise HTTPException(404, "Not found")
    require_writer(user)
    data = {k: body[k] for k in ENTITY_FIELDS[entity] if k in body}
    before = await db[entity].find_one({"id": eid, "organization_id": user["organization_id"]}, {"_id": 0})
    if not before:
        raise HTTPException(404, "Not found")
    if "version" not in body:
        raise HTTPException(422, "version is required")
    res = await db[entity].find_one_and_update({"id": eid, "organization_id": user["organization_id"], "version": body["version"]},
                                               {"$set": data | {"updated_at": now()}, "$inc": {"version": 1}}, projection={"_id": 0}, return_document=True)
    if not res:
        raise HTTPException(409, "Record changed by someone else. Reload.")
    await audit(user, f"{entity.upper()[:-1]}_UPDATED", entity[:-1], eid, {k: before.get(k) for k in data}, data)
    return res


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


SUB_STATUSES = ["SUBMITTED", "CLIENT_REVIEW", "INTERVIEW", "OFFER", "REJECTED", "WITHDRAWN", "PLACED"]
INT_STATUSES = ["SCHEDULED", "COMPLETED", "CANCELLED", "NO_SHOW"]
OFFER_STATUSES = ["EXTENDED", "ACCEPTED", "DECLINED", "WITHDRAWN"]


async def enrich(user, items):
    oid = user["organization_id"]
    cids = list({i["candidate_id"] for i in items})
    cands = {c["id"]: c for c in await db.candidates.find({"id": {"$in": cids}}, {"_id": 0, "id": 1, "first_name": 1, "last_name": 1, "status": 1}).to_list(2000)}
    jobs = {j["id"]: j for j in await db.jobs.find({"organization_id": oid}, {"_id": 0}).to_list(2000)}
    clients = {c["id"]: c["name"] for c in await db.clients.find({"organization_id": oid}, {"_id": 0}).to_list(2000)}
    groups = {g["id"]: g["name"] for g in await db.groups.find({"organization_id": oid}, {"_id": 0}).to_list(500)}
    out = []
    for i in items:
        c = cands.get(i["candidate_id"], {})
        j = jobs.get(i.get("job_id"), {})
        out.append(redact(user, i, i.get("group_id")) | {
            "candidate_name": f"{c.get('first_name', '')} {c.get('last_name', '')}".strip(), "candidate_status": c.get("status"),
            "job_title": j.get("title"), "client_name": clients.get(j.get("client_id")), "group_name": groups.get(i.get("group_id"))})
    return out


async def versioned(coll, user, eid, version, upd, push=None):
    u = {"$set": upd | {"updated_at": now()}, "$inc": {"version": 1}}
    if push:
        u["$push"] = push
    res = await db[coll].find_one_and_update({"id": eid, "organization_id": user["organization_id"], "version": version}, u, projection={"_id": 0}, return_document=True)
    if not res:
        raise HTTPException(409, "Record changed by someone else. Reload.")
    return res


async def get_scoped(coll, user, eid):
    d = await db[coll].find_one((await scope_filter(user)) | {"id": eid}, {"_id": 0})
    if not d:
        raise HTTPException(404, "Not found")
    return d


@router.get("/pipeline/submissions")
async def list_submissions(candidate_id: str = "", status: str = "", user=Depends(get_current_user)):
    f = await scope_filter(user)
    if candidate_id:
        f["candidate_id"] = candidate_id if user["role"] != EMP or candidate_id in f["candidate_id"]["$in"] else "__none__"
    if status:
        f["status"] = status
    return await enrich(user, await db.submissions.find(f, {"_id": 0}).sort("created_at", -1).to_list(1000))


@router.post("/pipeline/submissions")
async def create_submission(body: SubmissionIn, user=Depends(get_current_user)):
    c = await get_candidate_or_404(user, body.candidate_id)
    can_write_pipeline(user, c)
    if c["status"] not in ("MARKETING", "SUBMITTED", "INTERVIEWING"):
        raise HTTPException(422, "Candidate must be in MARKETING (or later) to be submitted")
    job = await db.jobs.find_one({"id": body.job_id, "organization_id": user["organization_id"]}, {"_id": 0})
    if not job:
        raise HTTPException(404, "Job not found")
    if await db.submissions.find_one({"candidate_id": c["id"], "job_id": job["id"], "status": {"$nin": ["REJECTED", "WITHDRAWN"]}}):
        raise HTTPException(409, "Candidate already has an active submission for this job")
    s = {"id": new_id(), "organization_id": user["organization_id"], "candidate_id": c["id"], "job_id": job["id"],
         "client_id": job.get("client_id"), "vendor_id": job.get("vendor_id"), "group_id": c["current_group_id"],
         "submission_rate": body.submission_rate, "notes": body.notes, "status": "SUBMITTED", "version": 1,
         "status_history": [{"status": "SUBMITTED", "at": now(), "by": user["name"], "note": body.notes}],
         "submitted_by": user["id"], "submitted_by_name": user["name"], "created_at": now()}
    await db.submissions.insert_one(dict(s))
    await audit(user, "SUBMISSION_CREATED", "submission", s["id"], None, {"candidate_id": c["id"], "job_id": job["id"], "submission_rate": body.submission_rate})
    await timeline(user, c["id"], "SUBMITTED", f"Submitted to {job['title']}")
    if c["status"] == "MARKETING":
        await set_status(user, c, "SUBMITTED", c["version"], "Auto: submission created")
    return (await enrich(user, [s]))[0]


@router.patch("/pipeline/submissions/{sid}/status")
async def submission_status(sid: str, body: StatusIn, user=Depends(get_current_user)):
    s = await get_scoped("submissions", user, sid)
    c = await get_candidate_or_404(user, s["candidate_id"])
    can_write_pipeline(user, c)
    if body.status not in SUB_STATUSES or body.status == "PLACED":
        raise HTTPException(422, "Invalid status")
    res = await versioned("submissions", user, sid, body.version, {"status": body.status},
                          {"status_history": {"status": body.status, "at": now(), "by": user["name"], "note": body.note}})
    await audit(user, "SUBMISSION_STATUS_CHANGED", "submission", sid, {"status": s["status"]}, {"status": body.status}, body.note, candidate_id=c["id"])
    await timeline(user, c["id"], "SUBMISSION_STATUS", f"Submission → {body.status}")
    if body.status in ("REJECTED", "WITHDRAWN") and c["status"] == "SUBMITTED":
        if not await db.submissions.find_one({"candidate_id": c["id"], "status": {"$nin": ["REJECTED", "WITHDRAWN"]}}):
            await set_status(user, c, "MARKETING", c["version"], "Auto: no active submissions")
    return (await enrich(user, [res]))[0]


@router.get("/pipeline/interviews")
async def list_interviews(candidate_id: str = "", upcoming: bool = False, user=Depends(get_current_user)):
    f = await scope_filter(user)
    if candidate_id:
        f["candidate_id"] = candidate_id if user["role"] != EMP or candidate_id in f["candidate_id"]["$in"] else "__none__"
    if upcoming:
        f |= {"scheduled_at": {"$gte": now()}, "status": "SCHEDULED"}
    return await enrich(user, await db.interviews.find(f, {"_id": 0}).sort("scheduled_at", 1 if upcoming else -1).to_list(1000))


@router.post("/pipeline/interviews")
async def create_interview(body: InterviewIn, user=Depends(get_current_user)):
    s = await get_scoped("submissions", user, body.submission_id)
    c = await get_candidate_or_404(user, s["candidate_id"])
    can_write_pipeline(user, c)
    i = body.model_dump() | {"id": new_id(), "organization_id": user["organization_id"], "candidate_id": c["id"],
                             "job_id": s["job_id"], "group_id": s["group_id"], "status": "SCHEDULED", "version": 1,
                             "reschedule_history": [], "feedback": None, "created_by": user["id"], "created_at": now()}
    await db.interviews.insert_one(dict(i))
    if s["status"] in ("SUBMITTED", "CLIENT_REVIEW"):
        await versioned("submissions", user, s["id"], s["version"], {"status": "INTERVIEW"}, {"status_history": {"status": "INTERVIEW", "at": now(), "by": user["name"], "note": "Auto: interview scheduled"}})
    await audit(user, "INTERVIEW_SCHEDULED", "interview", i["id"], None, {"candidate_id": c["id"], "scheduled_at": body.scheduled_at, "timezone": body.timezone})
    await timeline(user, c["id"], "INTERVIEW_SCHEDULED", f"{body.round} on {body.scheduled_at} ({body.timezone})")
    if c["status"] == "SUBMITTED":
        await set_status(user, c, "INTERVIEWING", c["version"], "Auto: interview scheduled")
    return (await enrich(user, [i]))[0]


@router.post("/pipeline/interviews/{iid}/reschedule")
async def reschedule(iid: str, body: RescheduleIn, user=Depends(get_current_user)):
    i = await get_scoped("interviews", user, iid)
    c = await get_candidate_or_404(user, i["candidate_id"])
    can_write_pipeline(user, c)
    if i["status"] != "SCHEDULED":
        raise HTTPException(422, "Only scheduled interviews can be rescheduled")
    if not body.reason.strip():
        raise HTTPException(422, "Reason required")
    res = await versioned("interviews", user, iid, body.version, {"scheduled_at": body.scheduled_at, "timezone": body.timezone},
                          {"reschedule_history": {"from": i["scheduled_at"], "from_tz": i["timezone"], "to": body.scheduled_at, "to_tz": body.timezone, "reason": body.reason, "by": user["name"], "at": now()}})
    await audit(user, "INTERVIEW_RESCHEDULED", "interview", iid, {"scheduled_at": i["scheduled_at"]}, {"scheduled_at": body.scheduled_at}, body.reason, candidate_id=c["id"])
    await timeline(user, c["id"], "INTERVIEW_RESCHEDULED", f"{i['scheduled_at']} → {body.scheduled_at} — {body.reason}")
    return (await enrich(user, [res]))[0]


@router.patch("/pipeline/interviews/{iid}/status")
async def interview_status(iid: str, body: StatusIn, user=Depends(get_current_user)):
    i = await get_scoped("interviews", user, iid)
    c = await get_candidate_or_404(user, i["candidate_id"])
    can_write_pipeline(user, c)
    if body.status not in INT_STATUSES:
        raise HTTPException(422, "Invalid status")
    res = await versioned("interviews", user, iid, body.version, {"status": body.status, "feedback": body.note})
    await audit(user, "INTERVIEW_STATUS_CHANGED", "interview", iid, {"status": i["status"]}, {"status": body.status}, body.note, candidate_id=c["id"])
    await timeline(user, c["id"], "INTERVIEW_" + body.status, body.note or "")
    return (await enrich(user, [res]))[0]


@router.get("/pipeline/offers")
async def list_offers(candidate_id: str = "", user=Depends(get_current_user)):
    f = await scope_filter(user)
    if candidate_id:
        f["candidate_id"] = candidate_id if user["role"] != EMP or candidate_id in f["candidate_id"]["$in"] else "__none__"
    return await enrich(user, await db.offers.find(f, {"_id": 0}).sort("created_at", -1).to_list(1000))


@router.post("/pipeline/offers")
async def create_offer(body: OfferIn, user=Depends(get_current_user)):
    s = await get_scoped("submissions", user, body.submission_id)
    c = await get_candidate_or_404(user, s["candidate_id"])
    can_write_pipeline(user, c)
    if c["status"] not in ("SUBMITTED", "INTERVIEWING", "OFFERED"):
        raise HTTPException(422, "Candidate must be submitted or interviewing to receive an offer")
    o = body.model_dump() | {"id": new_id(), "organization_id": user["organization_id"], "candidate_id": c["id"], "job_id": s["job_id"],
                             "group_id": s["group_id"], "status": "EXTENDED", "version": 1, "created_by": user["id"], "created_at": now()}
    if not is_ops(user):
        o["pay_rate"] = None
    await db.offers.insert_one(dict(o))
    await versioned("submissions", user, s["id"], s["version"], {"status": "OFFER"}, {"status_history": {"status": "OFFER", "at": now(), "by": user["name"], "note": "Offer extended"}})
    await audit(user, "OFFER_CREATED", "offer", o["id"], None, {"candidate_id": c["id"], "bill_rate": body.bill_rate, "pay_rate": o["pay_rate"], "start_date": body.start_date})
    await timeline(user, c["id"], "OFFER_EXTENDED", "Offer extended")
    if c["status"] != "OFFERED":
        await set_status(user, c, "OFFERED", c["version"], "Auto: offer extended")
    await notify(user["organization_id"], await ops_and_lead_ids(user["organization_id"], s["group_id"]), f"Offer extended: {c['first_name']} {c['last_name']}", "Review the offer", f"/candidates/{c['id']}")
    return (await enrich(user, [o]))[0]


@router.patch("/pipeline/offers/{oid}/status")
async def offer_status(oid: str, body: StatusIn, user=Depends(get_current_user)):
    o = await get_scoped("offers", user, oid)
    c = await get_candidate_or_404(user, o["candidate_id"])
    can_write_pipeline(user, c)
    if body.status not in OFFER_STATUSES:
        raise HTTPException(422, "Invalid status")
    if body.status == "ACCEPTED" and not is_ops(user) and user.get("_groups", {}).get(o["group_id"]) != "LEAD":
        raise HTTPException(403, "Only Admin, Operations or group Lead can mark offer accepted")
    res = await versioned("offers", user, oid, body.version, {"status": body.status})
    await audit(user, "OFFER_STATUS_CHANGED", "offer", oid, {"status": o["status"]}, {"status": body.status}, body.note, candidate_id=c["id"])
    await timeline(user, c["id"], "OFFER_" + body.status, body.note or "")
    if body.status in ("DECLINED", "WITHDRAWN") and c["status"] == "OFFERED":
        if not await db.offers.find_one({"candidate_id": c["id"], "status": {"$in": ["EXTENDED", "ACCEPTED"]}}):
            await set_status(user, c, "MARKETING", c["version"], f"Auto: offer {body.status.lower()}")
    return (await enrich(user, [res]))[0]


@router.get("/pipeline/placements")
async def list_placements(candidate_id: str = "", user=Depends(get_current_user)):
    f = await scope_filter(user)
    if candidate_id:
        f["candidate_id"] = candidate_id if user["role"] != EMP or candidate_id in f["candidate_id"]["$in"] else "__none__"
    return await enrich(user, await db.placements.find(f, {"_id": 0}).sort("created_at", -1).to_list(1000))


@router.post("/pipeline/placements")
async def create_placement(body: PlacementIn, user=Depends(get_current_user)):
    require(user, ADMIN, OPS)
    if not body.confirm:
        raise HTTPException(422, "Explicit confirmation required to create a placement")
    o = await get_scoped("offers", user, body.offer_id)
    if o["status"] != "ACCEPTED":
        raise HTTPException(422, "Offer must be ACCEPTED before placement")
    if await db.placements.find_one({"offer_id": o["id"]}):
        raise HTTPException(409, "Placement already exists for this offer")
    c = await get_candidate_or_404(user, o["candidate_id"])
    if c["status"] != "OFFERED":
        raise HTTPException(422, "Candidate must be in OFFERED status")
    p = {"id": new_id(), "organization_id": user["organization_id"], "candidate_id": c["id"], "offer_id": o["id"], "job_id": o["job_id"],
         "group_id": o["group_id"], "bill_rate": o.get("bill_rate"), "pay_rate": o.get("pay_rate"), "start_date": body.start_date,
         "end_date": body.end_date, "status": "ACTIVE", "version": 1, "created_by": user["id"], "created_at": now()}
    await db.placements.insert_one(dict(p))
    await db.submissions.update_many({"candidate_id": c["id"], "job_id": o["job_id"]}, {"$set": {"status": "PLACED"}, "$push": {"status_history": {"status": "PLACED", "at": now(), "by": user["name"]}}})
    from candidates import claim
    await claim(user, c["id"], c["version"], {"status": "PLACED", "bench_since": None})
    await audit(user, "CANDIDATE_PLACED", "placement", p["id"], {"status": c["status"]}, {"candidate_id": c["id"], "status": "PLACED", "bill_rate": p["bill_rate"], "pay_rate": p["pay_rate"]})
    await timeline(user, c["id"], "PLACED", f"Placed — start {body.start_date}")
    await notify(user["organization_id"], await ops_and_lead_ids(user["organization_id"], o["group_id"]), f"Placement: {c['first_name']} {c['last_name']}", f"Starts {body.start_date}", f"/candidates/{c['id']}")
    return (await enrich(user, [p]))[0]


@router.post("/pipeline/placements/{pid}/end")
async def end_placement(pid: str, body: StatusIn, user=Depends(get_current_user)):
    require(user, ADMIN, OPS)
    p = await get_scoped("placements", user, pid)
    if p["status"] != "ACTIVE":
        raise HTTPException(422, "Placement not active")
    res = await versioned("placements", user, pid, body.version, {"status": "ENDED", "ended_at": now(), "end_reason": body.note})
    c = await get_candidate_or_404(user, p["candidate_id"])
    if c["status"] == "PLACED":
        await set_status(user, c, "BENCH", c["version"], "Placement ended")
    await audit(user, "PLACEMENT_ENDED", "placement", pid, {"status": "ACTIVE"}, {"status": "ENDED"}, body.note, candidate_id=p["candidate_id"])
    return (await enrich(user, [res]))[0]

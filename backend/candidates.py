import re
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import Response
from pydantic import BaseModel
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from core import (db, ADMIN, OPS, EMP, AUDITOR, STATUSES, MARKETING_STATES, TRANSITIONS, now, new_id,
                  get_current_user, is_ops, require, require_writer, candidate_scope, edit_level, redact,
                  get_candidate_or_404, audit, timeline, notify, ops_and_lead_ids, paginate_params, rx,
                  make_token, decode_token)
from storage import put_object, get_object, APP_NAME

router = APIRouter(prefix="/api")

FULL_FIELDS = ["first_name", "last_name", "email", "phone", "location", "primary_skill", "skills", "experience_years",
               "visa_status", "work_authorization", "availability_date", "source", "linkedin_url", "pay_rate",
               "bill_rate", "target_rate", "summary", "relocation", "timezone"]
MARKETING_FIELDS = ["skills", "availability_date", "target_rate", "summary", "relocation", "location"]


def norm_email(e):
    return (e or "").strip().lower() or None


def norm_phone(p):
    d = re.sub(r"\D", "", p or "")
    return d[-10:] if len(d) >= 7 else None


class CandidateIn(BaseModel):
    first_name: str
    last_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    primary_skill: Optional[str] = None
    skills: List[str] = []
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


def conflict():
    raise HTTPException(409, "This candidate was changed by someone else. Reload to see the latest version.")


async def claim(user, cand_id, version, extra_set=None, extra_filter=None):
    """Atomically bumps version — acts as the candidate lock; loser gets 409."""
    f = {"id": cand_id, "organization_id": user["organization_id"], "version": version} | (extra_filter or {})
    doc = await db.candidates.find_one_and_update(
        f, {"$inc": {"version": 1}, "$set": {"updated_at": now(), "updated_by": user["id"]} | (extra_set or {})},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER)
    if not doc:
        conflict()
    return doc


def view(user, c):
    d = redact(user, c)
    d["full_name"] = f"{c['first_name']} {c['last_name']}"
    return d


async def find_duplicates(org_id, email, phone, first, last, exclude_id=None):
    exact, possible = [], []
    proj = {"_id": 0, "id": 1, "first_name": 1, "last_name": 1, "email": 1, "phone": 1, "status": 1, "current_group_id": 1}
    base = {"organization_id": org_id}
    if exclude_id:
        base["id"] = {"$ne": exclude_id}
    ors = []
    if norm_email(email):
        ors.append({"email_norm": norm_email(email)})
    if norm_phone(phone):
        ors.append({"phone_norm": norm_phone(phone)})
    if ors:
        for c in await db.candidates.find(base | {"$or": ors}, proj).to_list(20):
            match = "email" if (c.get("email") or "").lower() == norm_email(email) else "phone"
            exact.append(c | {"match": match})
    if first and last:
        ex = {c["id"] for c in exact}
        q = base | {"first_name": {"$regex": f"^{re.escape(first.strip())}$", "$options": "i"},
                    "last_name": {"$regex": f"^{re.escape(last.strip())}$", "$options": "i"}}
        for c in await db.candidates.find(q, proj).to_list(20):
            if c["id"] not in ex:
                possible.append(c | {"match": "name"})
    return exact, possible


@router.post("/candidates/duplicate-check")
async def duplicate_check(body: DupIn, user=Depends(get_current_user)):
    exact, possible = await find_duplicates(user["organization_id"], body.email, body.phone, body.first_name, body.last_name, body.exclude_id)
    return {"exact": exact, "possible": possible, "can_override": is_ops(user)}


@router.get("/candidates")
async def list_candidates(q: str = "", status: str = "", group_id: str = "", owner_id: str = "", skill: str = "",
                          unassigned: bool = False, page: int = 1, page_size: int = 25, sort: str = "-updated_at",
                          include_archived: bool = False, user=Depends(get_current_user)):
    page, page_size = paginate_params(page, page_size)
    f = candidate_scope(user)
    ands = []
    if q:
        ands.append({"$or": [{"first_name": rx(q)}, {"last_name": rx(q)}, {"email": rx(q)}, {"primary_skill": rx(q)}, {"skills": rx(q)}, {"phone": rx(q)}]})
    if status:
        ands.append({"status": {"$in": status.split(",")}})
    elif not include_archived:
        ands.append({"status": {"$ne": "ARCHIVED"}})
    if group_id:
        ands.append({"current_group_id": group_id})
    if unassigned:
        ands.append({"current_group_id": None})
    if owner_id:
        ands.append({"owner_id": owner_id})
    if skill:
        ands.append({"$or": [{"skills": rx(skill)}, {"primary_skill": rx(skill)}]})
    if ands:
        f = {"$and": [f] + ands}
    key = sort.lstrip("-")
    if key not in ("updated_at", "created_at", "last_name", "status", "bench_since", "experience_years"):
        key = "updated_at"
    total = await db.candidates.count_documents(f)
    docs = await db.candidates.find(f, {"_id": 0}).sort(key, -1 if sort.startswith("-") else 1).skip((page - 1) * page_size).limit(page_size).to_list(page_size)
    groups = {g["id"]: g["name"] for g in await db.groups.find({"organization_id": user["organization_id"]}, {"_id": 0}).to_list(200)}
    owners = {u["id"]: u["name"] for u in await db.users.find({"organization_id": user["organization_id"]}, {"_id": 0, "id": 1, "name": 1}).to_list(1000)}
    items = [view(user, d) | {"group_name": groups.get(d.get("current_group_id")), "owner_name": owners.get(d.get("owner_id"))} for d in docs]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


async def assign_service(user, cand, group_id, version, reason=None, event="ASSIGNED"):
    grp = await db.groups.find_one({"id": group_id, "organization_id": user["organization_id"], "active": True}, {"_id": 0})
    if not grp:
        raise HTTPException(404, "Group not found or inactive")
    prev_group = cand.get("current_group_id")
    doc = await claim(user, cand["id"], version, {"current_group_id": group_id, "owner_id": None})
    await db.assignments.update_many({"candidate_id": cand["id"], "active": True},
                                     {"$set": {"active": False, "ended_at": now(), "ended_by": user["id"], "end_reason": reason or event}})
    try:
        await db.assignments.insert_one({"id": new_id(), "organization_id": user["organization_id"], "candidate_id": cand["id"],
                                         "group_id": group_id, "active": True, "started_at": now(), "started_by": user["id"], "reason": reason})
    except DuplicateKeyError:
        conflict()
    await audit(user, f"CANDIDATE_{event}", "candidate", cand["id"], {"current_group_id": prev_group}, {"current_group_id": group_id}, reason)
    await timeline(user, cand["id"], event, f"{'Transferred' if prev_group else 'Assigned'} to group {grp['name']}" + (f" — {reason}" if reason else ""), {"from": prev_group, "to": group_id})
    await notify(user["organization_id"], await ops_and_lead_ids(user["organization_id"], group_id),
                 f"Candidate {event.lower()}: {cand['first_name']} {cand['last_name']}", f"Now in group {grp['name']}", f"/candidates/{cand['id']}")
    return doc


@router.post("/candidates")
async def create_candidate(body: CandidateIn, user=Depends(get_current_user)):
    require(user, ADMIN, OPS)
    exact, possible = await find_duplicates(user["organization_id"], body.email, body.phone, body.first_name, body.last_name)
    if exact:
        if not body.override_duplicate_reason or not body.override_duplicate_reason.strip():
            raise HTTPException(409, {"code": "DUPLICATE", "message": "Exact duplicate email/phone exists. Admin/Operations may override with a reason.", "exact": exact})
    data = body.model_dump(exclude={"group_id", "override_duplicate_reason"})
    data["skills"] = [s.strip() for s in data["skills"] if s and s.strip()]
    cid = new_id()
    doc = data | {"id": cid, "organization_id": user["organization_id"], "status": "NEW", "current_group_id": None,
                  "owner_id": None, "email_norm": norm_email(body.email), "phone_norm": norm_phone(body.phone),
                  "version": 1, "created_at": now(), "updated_at": now(), "created_by": user["id"], "bench_since": None}
    await db.candidates.insert_one(dict(doc))
    await audit(user, "CANDIDATE_CREATED", "candidate", cid, None, {k: v for k, v in doc.items() if k != "_id"},
                body.override_duplicate_reason if exact else None)
    await timeline(user, cid, "CREATED", "Candidate created" + (" (duplicate override)" if exact else ""))
    if exact:
        await timeline(user, cid, "DUPLICATE_OVERRIDE", f"Override reason: {body.override_duplicate_reason}")
    if body.group_id:
        doc = await assign_service(user, doc, body.group_id, 1)
        doc = await set_status(user, doc, "BENCH", doc["version"], "Auto: assigned to group")
    return view(user, doc)


def permissions(user, c):
    lvl = edit_level(user, c)
    ops = is_ops(user)
    st = c["status"]
    return {
        "edit_level": lvl,
        "can_edit": lvl is not None and st != "ARCHIVED",
        "allowed_transitions": [t for t in TRANSITIONS.get(st, []) if lvl and t != "PLACED" and (t != "MARKETING" or c.get("current_group_id"))],
        "can_assign": ops and not c.get("current_group_id") and st != "ARCHIVED",
        "can_transfer": (ops or (lvl == "full" and user.get("_groups", {}).get(c.get("current_group_id")) == "LEAD")) and bool(c.get("current_group_id")),
        "can_unassign": ops and bool(c.get("current_group_id")),
        "can_archive": ops and st != "ARCHIVED",
        "can_restore": ops and st == "ARCHIVED",
        "can_set_owner": (ops or user.get("_groups", {}).get(c.get("current_group_id")) == "LEAD") and bool(c.get("current_group_id")),
        "can_view_ops_notes": ops or (user["role"] == AUDITOR and user.get("can_view_ops_only")),
        "can_upload": lvl is not None,
    }


@router.get("/candidates/{cid}")
async def get_candidate(cid: str, user=Depends(get_current_user)):
    c = await get_candidate_or_404(user, cid)
    grp = await db.groups.find_one({"id": c.get("current_group_id")}, {"_id": 0}) if c.get("current_group_id") else None
    owner = await db.users.find_one({"id": c.get("owner_id")}, {"_id": 0, "id": 1, "name": 1}) if c.get("owner_id") else None
    history = await db.assignments.find({"candidate_id": cid}, {"_id": 0}).sort("started_at", -1).to_list(50)
    gnames = {g["id"]: g["name"] for g in await db.groups.find({"organization_id": user["organization_id"]}, {"_id": 0}).to_list(200)}
    for h in history:
        h["group_name"] = gnames.get(h["group_id"])
    active_offer = await db.offers.find_one({"candidate_id": cid, "status": {"$in": ["EXTENDED", "ACCEPTED"]}}, {"_id": 0, "id": 1, "status": 1})
    return {"candidate": view(user, c), "group": grp, "owner": owner, "assignment_history": history,
            "active_offer": active_offer, "permissions": permissions(user, c)}


@router.patch("/candidates/{cid}")
async def update_candidate(cid: str, body: dict, user=Depends(get_current_user)):
    require_writer(user)
    c = await get_candidate_or_404(user, cid)
    lvl = edit_level(user, c)
    if not lvl or c["status"] == "ARCHIVED":
        raise HTTPException(403, "You cannot edit this candidate")
    if "version" not in body:
        raise HTTPException(422, "version is required")
    for forbidden in ("current_group_id", "status", "owner_id", "organization_id", "id"):
        if forbidden in body:
            raise HTTPException(422, f"'{forbidden}' cannot be changed through generic update; use the dedicated workflow")
    allowed = FULL_FIELDS if lvl == "full" else MARKETING_FIELDS
    if not is_ops(user):
        allowed = [a for a in allowed if a != "pay_rate"]
    upd = {k: v for k, v in body.items() if k in allowed}
    bad = [k for k in body if k not in allowed and k != "version"]
    if bad:
        raise HTTPException(403, f"Not permitted to edit: {', '.join(bad)}")
    if "email" in upd or "phone" in upd:
        exact, _ = await find_duplicates(user["organization_id"], upd.get("email"), upd.get("phone"), None, None, cid)
        if exact and not (is_ops(user) and body.get("override_duplicate_reason")):
            raise HTTPException(409, {"code": "DUPLICATE", "message": "Another candidate has this email/phone", "exact": exact})
        if "email" in upd:
            upd["email_norm"] = norm_email(upd["email"])
        if "phone" in upd:
            upd["phone_norm"] = norm_phone(upd["phone"])
    doc = await claim(user, cid, int(body["version"]), upd)
    before = {k: c.get(k) for k in upd}
    await audit(user, "CANDIDATE_UPDATED", "candidate", cid, before, upd)
    changed = [k for k in upd if not k.endswith("_norm")]
    await timeline(user, cid, "UPDATED", f"Updated {', '.join(changed)}")
    return view(user, doc)


async def guard_transition(user, c, to):
    if to not in TRANSITIONS.get(c["status"], []):
        raise HTTPException(422, f"Transition {c['status']} → {to} is not allowed")
    if to == "MARKETING" and not c.get("current_group_id"):
        raise HTTPException(422, "Candidate must be assigned to a group before marketing")
    if to == "SUBMITTED" and not await db.submissions.find_one({"candidate_id": c["id"]}):
        raise HTTPException(422, "Create a submission first")
    if to == "INTERVIEWING" and not await db.interviews.find_one({"candidate_id": c["id"], "status": "SCHEDULED"}):
        raise HTTPException(422, "Schedule an interview first")
    if to == "OFFERED" and not await db.offers.find_one({"candidate_id": c["id"], "status": {"$in": ["EXTENDED", "ACCEPTED"]}}):
        raise HTTPException(422, "Record an offer first")
    if to == "PLACED":
        raise HTTPException(422, "Use the placement workflow to place a candidate")


async def set_status(user, c, to, version, reason=None, event="STATUS_CHANGED"):
    extra = {"status": to}
    if to in ("BENCH", "ON_HOLD") and c["status"] not in ("BENCH", "ON_HOLD"):
        extra["bench_since"] = now()
    doc = await claim(user, c["id"], version, extra)
    await audit(user, "CANDIDATE_STATUS_CHANGED", "candidate", c["id"], {"status": c["status"]}, {"status": to}, reason)
    await timeline(user, c["id"], event, f"{c['status']} → {to}" + (f" — {reason}" if reason else ""), {"from": c["status"], "to": to})
    return doc


@router.post("/candidates/{cid}/transition")
async def transition(cid: str, body: TransitionIn, user=Depends(get_current_user)):
    require_writer(user)
    c = await get_candidate_or_404(user, cid)
    if not edit_level(user, c):
        raise HTTPException(403, "You cannot change this candidate's status")
    if c["version"] != body.version:
        conflict()
    await guard_transition(user, c, body.to_status)
    return view(user, await set_status(user, c, body.to_status, body.version, body.reason))


@router.post("/candidates/{cid}/assign")
async def assign(cid: str, body: AssignIn, user=Depends(get_current_user)):
    require(user, ADMIN, OPS)
    c = await get_candidate_or_404(user, cid)
    if c.get("current_group_id"):
        raise HTTPException(422, "Candidate already has an active group. Use transfer.")
    if c["status"] == "ARCHIVED":
        raise HTTPException(422, "Restore the candidate first")
    doc = await assign_service(user, c, body.group_id, body.version, body.reason)
    if doc["status"] == "NEW":
        doc = await set_status(user, doc, "BENCH", doc["version"], "Auto: assigned to group")
    return view(user, doc)


@router.post("/candidates/{cid}/transfer")
async def transfer(cid: str, body: TransferIn, user=Depends(get_current_user)):
    require_writer(user)
    c = await get_candidate_or_404(user, cid)
    if not c.get("current_group_id"):
        raise HTTPException(422, "Candidate has no active group. Use assign.")
    if not (is_ops(user) or user.get("_groups", {}).get(c["current_group_id"]) == "LEAD"):
        raise HTTPException(403, "Only Admin, Operations or the current group Lead can transfer")
    if body.to_group_id == c["current_group_id"]:
        raise HTTPException(422, "Candidate is already in this group")
    if not body.reason or not body.reason.strip():
        raise HTTPException(422, "A reason is required for transfers")
    active_offer = await db.offers.find_one({"candidate_id": cid, "status": {"$in": ["EXTENDED", "ACCEPTED"]}})
    if active_offer or c["status"] == "OFFERED":
        if not is_ops(user):
            raise HTTPException(403, "Candidate has an active offer — only Admin/Operations may transfer")
        if not body.acknowledge_active_offer:
            raise HTTPException(409, {"code": "ACTIVE_OFFER", "message": "Candidate has an active offer. Explicit acknowledgment required."})
    doc = await assign_service(user, c, body.to_group_id, body.version, body.reason, "TRANSFERRED")
    await notify(user["organization_id"], await ops_and_lead_ids(user["organization_id"], c["current_group_id"]),
                 f"Candidate transferred out: {c['first_name']} {c['last_name']}", body.reason, f"/candidates/{cid}")
    return view(user, doc)


@router.post("/candidates/{cid}/unassign")
async def unassign(cid: str, body: UnassignIn, user=Depends(get_current_user)):
    require(user, ADMIN, OPS)
    c = await get_candidate_or_404(user, cid)
    if not c.get("current_group_id"):
        raise HTTPException(422, "Candidate has no active group")
    if not body.reason or not body.reason.strip():
        raise HTTPException(422, "A reason is required")
    extra = {"current_group_id": None, "owner_id": None}
    if c["status"] in MARKETING_STATES:
        if body.target_status not in ("BENCH", "ON_HOLD"):
            raise HTTPException(422, {"code": "TARGET_STATUS_REQUIRED", "message": "Choose BENCH or ON_HOLD explicitly when unassigning from marketing"})
        extra |= {"status": body.target_status, "bench_since": now()}
    doc = await claim(user, cid, body.version, extra)
    await db.assignments.update_many({"candidate_id": cid, "active": True}, {"$set": {"active": False, "ended_at": now(), "ended_by": user["id"], "end_reason": body.reason}})
    await audit(user, "CANDIDATE_UNASSIGNED", "candidate", cid, {"current_group_id": c["current_group_id"], "status": c["status"]}, {"current_group_id": None, "status": doc["status"]}, body.reason)
    await timeline(user, cid, "UNASSIGNED", f"Removed from group — {body.reason}" + (f" (status → {body.target_status})" if "status" in extra else ""))
    await notify(user["organization_id"], await ops_and_lead_ids(user["organization_id"], c["current_group_id"]),
                 f"Candidate unassigned: {c['first_name']} {c['last_name']}", body.reason, f"/candidates/{cid}")
    return view(user, doc)


@router.post("/candidates/{cid}/owner")
async def set_owner(cid: str, body: OwnerIn, user=Depends(get_current_user)):
    require_writer(user)
    c = await get_candidate_or_404(user, cid)
    if not (is_ops(user) or user.get("_groups", {}).get(c.get("current_group_id")) == "LEAD"):
        raise HTTPException(403, "Only Admin, Operations or group Lead can set owner")
    if body.owner_id and not await db.memberships.find_one({"group_id": c.get("current_group_id"), "user_id": body.owner_id, "active": True}):
        raise HTTPException(422, "Owner must be an active member of the candidate's current group")
    doc = await claim(user, cid, body.version, {"owner_id": body.owner_id})
    await audit(user, "CANDIDATE_OWNER_SET", "candidate", cid, {"owner_id": c.get("owner_id")}, {"owner_id": body.owner_id})
    await timeline(user, cid, "OWNER_CHANGED", "Owner updated")
    return view(user, doc)


@router.post("/candidates/{cid}/archive")
async def archive(cid: str, body: VersionIn, user=Depends(get_current_user)):
    require(user, ADMIN, OPS)
    c = await get_candidate_or_404(user, cid)
    if not body.reason:
        raise HTTPException(422, "A reason is required")
    doc = await claim(user, cid, body.version, {"status": "ARCHIVED", "prior_status": c["status"], "current_group_id": None, "owner_id": None, "archived_at": now()})
    await db.assignments.update_many({"candidate_id": cid, "active": True}, {"$set": {"active": False, "ended_at": now(), "ended_by": user["id"], "end_reason": "ARCHIVED"}})
    await audit(user, "CANDIDATE_ARCHIVED", "candidate", cid, {"status": c["status"], "current_group_id": c.get("current_group_id")}, {"status": "ARCHIVED"}, body.reason)
    await timeline(user, cid, "ARCHIVED", body.reason)
    return view(user, doc)


@router.post("/candidates/{cid}/restore")
async def restore(cid: str, body: VersionIn, user=Depends(get_current_user)):
    require(user, ADMIN, OPS)
    c = await get_candidate_or_404(user, cid)
    if c["status"] != "ARCHIVED":
        raise HTTPException(422, "Candidate is not archived")
    doc = await claim(user, cid, body.version, {"status": "BENCH", "bench_since": now()})
    await audit(user, "CANDIDATE_RESTORED", "candidate", cid, {"status": "ARCHIVED"}, {"status": "BENCH", "current_group_id": None}, body.reason)
    await timeline(user, cid, "RESTORED", "Restored to BENCH without group access — assign a group explicitly")
    return view(user, doc)


@router.get("/candidates/{cid}/timeline")
async def get_timeline(cid: str, user=Depends(get_current_user)):
    await get_candidate_or_404(user, cid)
    return await db.timeline.find({"candidate_id": cid, "organization_id": user["organization_id"]}, {"_id": 0}).sort("created_at", -1).to_list(500)


@router.get("/candidates/{cid}/audit")
async def get_candidate_audit(cid: str, user=Depends(get_current_user)):
    require(user, ADMIN, OPS, AUDITOR)
    await get_candidate_or_404(user, cid)
    from admin_routes import redact_audit
    logs = await db.audit_logs.find({"organization_id": user["organization_id"], "$or": [{"entity_id": cid}, {"candidate_id": cid}]}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return [redact_audit(user, a) for a in logs]


@router.get("/candidates/{cid}/notes")
async def list_notes(cid: str, user=Depends(get_current_user)):
    c = await get_candidate_or_404(user, cid)
    f = {"candidate_id": cid}
    if not permissions(user, c)["can_view_ops_notes"]:
        f["visibility"] = {"$ne": "OPERATIONS_ONLY"}
    return await db.notes.find(f, {"_id": 0}).sort("created_at", -1).to_list(500)


@router.post("/candidates/{cid}/notes")
async def add_note(cid: str, body: NoteIn, user=Depends(get_current_user)):
    require_writer(user)
    c = await get_candidate_or_404(user, cid)
    if not edit_level(user, c):
        raise HTTPException(403, "Not permitted")
    if body.visibility == "OPERATIONS_ONLY" and not is_ops(user):
        raise HTTPException(403, "Only Admin/Operations can write operations-only notes")
    if not body.body.strip():
        raise HTTPException(422, "Note cannot be empty")
    note = {"id": new_id(), "organization_id": user["organization_id"], "candidate_id": cid, "body": body.body,
            "visibility": body.visibility, "author_id": user["id"], "author_name": user["name"], "created_at": now()}
    await db.notes.insert_one(dict(note))
    await timeline(user, cid, "NOTE_ADDED", "Note added" + (" (operations-only)" if body.visibility == "OPERATIONS_ONLY" else ""))
    return note


@router.get("/tasks")
async def list_tasks(candidate_id: str = "", mine: bool = False, status: str = "", user=Depends(get_current_user)):
    f = {"organization_id": user["organization_id"]}
    if candidate_id:
        await get_candidate_or_404(user, candidate_id)
        f["candidate_id"] = candidate_id
    if mine or user["role"] == EMP and not candidate_id:
        f["assignee_id"] = user["id"]
    if status:
        f["status"] = status
    tasks = await db.tasks.find(f, {"_id": 0}).sort("due_date", 1).to_list(500)
    names = {u["id"]: u["name"] for u in await db.users.find({"organization_id": user["organization_id"]}, {"_id": 0, "id": 1, "name": 1}).to_list(1000)}
    for t in tasks:
        t["assignee_name"] = names.get(t.get("assignee_id"))
    return tasks


@router.post("/tasks")
async def create_task(body: TaskIn, user=Depends(get_current_user)):
    require_writer(user)
    if body.candidate_id:
        await get_candidate_or_404(user, body.candidate_id)
    t = body.model_dump() | {"id": new_id(), "organization_id": user["organization_id"], "status": "OPEN",
                             "assignee_id": body.assignee_id or user["id"], "created_by": user["id"], "created_at": now()}
    await db.tasks.insert_one(dict(t))
    if body.candidate_id:
        await timeline(user, body.candidate_id, "TASK_CREATED", body.title)
    if t["assignee_id"] != user["id"]:
        await notify(user["organization_id"], [t["assignee_id"]], "New task assigned", body.title)
    return t


@router.patch("/tasks/{tid}")
async def update_task(tid: str, body: TaskPatch, user=Depends(get_current_user)):
    require_writer(user)
    t = await db.tasks.find_one({"id": tid, "organization_id": user["organization_id"]}, {"_id": 0})
    if not t:
        raise HTTPException(404, "Task not found")
    if not is_ops(user) and user["id"] not in (t["assignee_id"], t["created_by"]):
        raise HTTPException(403, "Not your task")
    upd = {k: v for k, v in body.model_dump().items() if v is not None}
    if upd.get("status") and upd["status"] not in ("OPEN", "DONE"):
        raise HTTPException(422, "Invalid task status")
    await db.tasks.update_one({"id": tid}, {"$set": upd | {"updated_at": now()}})
    if t.get("candidate_id") and upd.get("status") == "DONE":
        await timeline(user, t["candidate_id"], "TASK_COMPLETED", t["title"])
    return t | upd


ALLOWED_EXT = {"pdf", "doc", "docx", "txt", "rtf", "png", "jpg", "jpeg"}
MAX_SIZE = 10 * 1024 * 1024


@router.get("/candidates/{cid}/documents")
async def list_documents(cid: str, user=Depends(get_current_user)):
    await get_candidate_or_404(user, cid)
    return await db.documents.find({"candidate_id": cid, "is_deleted": False}, {"_id": 0, "storage_path": 0}).sort([("doc_type", 1), ("version", -1)]).to_list(500)


@router.post("/candidates/{cid}/documents")
async def upload_document(cid: str, file: UploadFile = File(...), doc_type: str = Form("RESUME"), user=Depends(get_current_user)):
    require_writer(user)
    c = await get_candidate_or_404(user, cid)
    if not edit_level(user, c):
        raise HTTPException(403, "Not permitted to upload")
    data = await file.read()
    if len(data) > MAX_SIZE:
        raise HTTPException(413, "File exceeds 10MB")
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "bin"
    last = await db.documents.find_one({"candidate_id": cid, "doc_type": doc_type}, sort=[("version", -1)])
    version = (last["version"] + 1) if last else 1
    path = f"{APP_NAME}/{user['organization_id']}/quarantine/{new_id()}.{ext}"
    res = put_object(path, data, file.content_type or "application/octet-stream")
    doc = {"id": new_id(), "organization_id": user["organization_id"], "candidate_id": cid, "doc_type": doc_type,
           "version": version, "original_filename": file.filename, "content_type": file.content_type, "size": len(data),
           "storage_path": res["path"], "scan_status": "PENDING", "scan_engine": "SIMULATED", "is_deleted": False,
           "uploaded_by": user["id"], "uploaded_by_name": user["name"], "created_at": now()}
    await db.documents.insert_one(dict(doc))
    await db.bg_jobs.insert_one({"id": new_id(), "organization_id": user["organization_id"], "type": "SCAN", "status": "PENDING",
                                 "payload": {"document_id": doc["id"]}, "created_by": user["id"], "created_at": now()})
    await audit(user, "DOCUMENT_UPLOADED", "document", doc["id"], None, {"candidate_id": cid, "doc_type": doc_type, "version": version, "filename": file.filename})
    await timeline(user, cid, "DOCUMENT_UPLOADED", f"{doc_type} v{version}: {file.filename} (quarantined, scanning)")
    doc.pop("storage_path")
    return doc


@router.get("/documents/{did}/signed-url")
async def signed_url(did: str, user=Depends(get_current_user)):
    d = await db.documents.find_one({"id": did, "organization_id": user["organization_id"], "is_deleted": False}, {"_id": 0})
    if not d:
        raise HTTPException(404, "Document not found")
    await get_candidate_or_404(user, d["candidate_id"])
    if d["scan_status"] != "PASSED":
        raise HTTPException(423, f"Download blocked: scan status is {d['scan_status']}")
    token = make_token(user["id"], "download", 5, {"doc": did})
    await audit(user, "DOCUMENT_URL_ISSUED", "document", did)
    return {"url": f"/api/documents/download?token={token}", "expires_in": 300}


@router.get("/documents/download")
async def download(token: str = Query(...)):
    p = decode_token(token, "download")
    d = await db.documents.find_one({"id": p["doc"], "is_deleted": False}, {"_id": 0})
    if not d or d["scan_status"] != "PASSED":
        raise HTTPException(423, "Download blocked")
    data, ct = get_object(d["storage_path"])
    return Response(content=data, media_type=d.get("content_type") or ct,
                    headers={"Content-Disposition": f'attachment; filename="{d["original_filename"]}"'})

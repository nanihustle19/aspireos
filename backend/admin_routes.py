import csv
import io
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response
from pydantic import BaseModel

from core import (db, ADMIN, OPS, EMP, AUDITOR, ORG_ROLES, GROUP_ROLES, STATUSES, MARKETING_STATES, BILL_FIELDS, PAY_FIELDS,
                  now, new_id, get_current_user, is_ops, require, require_writer, candidate_scope, can_see_bill,
                  audit, timeline, notify, ops_and_lead_ids, public_user)

router = APIRouter(prefix="/api")


def redact_audit(user, a):
    a = dict(a)
    for k in ("before", "after"):
        snap = a.get(k)
        if isinstance(snap, dict):
            snap = dict(snap)
            for f in PAY_FIELDS:
                if f in snap and not is_ops(user):
                    snap[f] = "•••"
            for f in BILL_FIELDS:
                if f in snap and not is_ops(user):
                    snap[f] = "•••"
            a[k] = snap
    return a


class InviteIn(BaseModel):
    email: str
    name: str
    role: str = EMP
    group_id: Optional[str] = None
    group_role: Optional[str] = None


class UserPatch(BaseModel):
    role: Optional[str] = None
    status: Optional[str] = None
    can_view_ops_only: Optional[bool] = None


class GroupIn(BaseModel):
    name: str
    description: Optional[str] = None


class MemberIn(BaseModel):
    user_id: str
    role: str


class SavedViewIn(BaseModel):
    name: str
    page: str = "candidates"
    filters: dict = {}


@router.get("/organization")
async def get_org(user=Depends(get_current_user)):
    return await db.organizations.find_one({"id": user["organization_id"]}, {"_id": 0})


@router.get("/users")
async def list_users(user=Depends(get_current_user)):
    users = await db.users.find({"organization_id": user["organization_id"]}, {"_id": 0, "password_hash": 0, "mfa_secret": 0, "pending_mfa_secret": 0}).sort("name", 1).to_list(1000)
    ms = await db.memberships.find({"organization_id": user["organization_id"], "active": True}, {"_id": 0}).to_list(5000)
    groups = {g["id"]: g["name"] for g in await db.groups.find({"organization_id": user["organization_id"]}, {"_id": 0}).to_list(500)}
    for u in users:
        u["groups"] = [{"group_id": m["group_id"], "group_name": groups.get(m["group_id"]), "role": m["role"]} for m in ms if m["user_id"] == u["id"]]
    return users


async def revoke_membership(user, m, reason):
    await db.memberships.update_one({"id": m["id"]}, {"$set": {"active": False, "ended_at": now(), "ended_by": user["id"], "end_reason": reason}})
    cleared = await db.candidates.find({"current_group_id": m["group_id"], "owner_id": m["user_id"]}, {"_id": 0, "id": 1}).to_list(5000)
    if cleared:
        await db.candidates.update_many({"current_group_id": m["group_id"], "owner_id": m["user_id"]}, {"$set": {"owner_id": None, "updated_at": now()}, "$inc": {"version": 1}})
        for c in cleared:
            await timeline(user, c["id"], "OWNER_CLEARED", f"Owner removed from group ({reason})")
    member = await db.users.find_one({"id": m["user_id"]}, {"_id": 0, "name": 1})
    grp = await db.groups.find_one({"id": m["group_id"]}, {"_id": 0, "name": 1})
    await audit(user, "MEMBERSHIP_REMOVED", "group", m["group_id"], {"user_id": m["user_id"], "role": m["role"]}, None, reason)
    await notify(user["organization_id"], await ops_and_lead_ids(user["organization_id"], m["group_id"]),
                 f"Member removed: {member and member['name']}", f"Removed from {grp and grp['name']}. {len(cleared)} candidate owner(s) cleared.")
    return len(cleared)


@router.patch("/users/{uid}")
async def update_user(uid: str, body: UserPatch, user=Depends(get_current_user)):
    require(user, ADMIN)
    target = await db.users.find_one({"id": uid, "organization_id": user["organization_id"]}, {"_id": 0})
    if not target:
        raise HTTPException(404, "User not found")
    upd = {k: v for k, v in body.model_dump().items() if v is not None}
    if "role" in upd and upd["role"] not in ORG_ROLES:
        raise HTTPException(422, "Invalid role")
    if uid == user["id"] and ("role" in upd or upd.get("status") == "DEACTIVATED"):
        raise HTTPException(422, "You cannot change your own role or deactivate yourself")
    inc = {}
    if upd.get("status") == "DEACTIVATED" or "role" in upd:
        inc = {"session_version": 1}
    await db.users.update_one({"id": uid}, {"$set": upd | {"updated_at": now()}, **({"$inc": inc} if inc else {})})
    if upd.get("status") == "DEACTIVATED":
        for m in await db.memberships.find({"user_id": uid, "active": True}, {"_id": 0}).to_list(100):
            await revoke_membership(user, m, "User deactivated")
    await audit(user, "USER_UPDATED", "user", uid, {k: target.get(k) for k in upd}, upd)
    return {"ok": True}


@router.get("/invitations")
async def list_invitations(user=Depends(get_current_user)):
    require(user, ADMIN, OPS)
    return await db.invitations.find({"organization_id": user["organization_id"]}, {"_id": 0}).sort("created_at", -1).to_list(500)


@router.post("/invitations")
async def create_invitation(body: InviteIn, user=Depends(get_current_user)):
    require(user, ADMIN, OPS)
    if body.role not in ORG_ROLES or (body.role == ADMIN and user["role"] != ADMIN):
        raise HTTPException(422, "Invalid role")
    email = body.email.strip().lower()
    if "@" not in email:
        raise HTTPException(422, "Invalid email")
    if await db.users.find_one({"email": email}):
        raise HTTPException(409, "A user with this email already exists")
    if body.group_id:
        if body.role != EMP or body.group_role not in GROUP_ROLES:
            raise HTTPException(422, "Group membership requires EMPLOYEE role and a valid group role")
        if not await db.groups.find_one({"id": body.group_id, "organization_id": user["organization_id"], "active": True}):
            raise HTTPException(422, "Group not found or inactive")
    uid = new_id()
    await db.users.insert_one({"id": uid, "organization_id": user["organization_id"], "email": email, "name": body.name, "role": body.role,
                               "status": "INVITED", "auth_methods": [], "mfa_enabled": False, "session_version": 0, "created_at": now()})
    if body.group_id:
        await db.memberships.insert_one({"id": new_id(), "organization_id": user["organization_id"], "group_id": body.group_id, "user_id": uid,
                                         "role": body.group_role, "active": True, "created_at": now()})
    token = secrets.token_urlsafe(32)
    inv = {"id": new_id(), "organization_id": user["organization_id"], "user_id": uid, "email": email, "name": body.name, "role": body.role,
           "token": token, "status": "PENDING", "invited_by": user["id"], "invited_by_name": user["name"], "created_at": now(),
           "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()}
    await db.invitations.insert_one(dict(inv))
    await db.outbox.insert_one({"id": new_id(), "organization_id": user["organization_id"], "to": email, "subject": "You're invited to BenchOS",
                                "body": f"Activate your account: /activate?token={token}", "status": "PENDING", "attempts": 0, "created_at": now()})
    await audit(user, "USER_INVITED", "user", uid, None, {"email": email, "role": body.role})
    return inv | {"activation_path": f"/activate?token={token}"}


@router.post("/invitations/{iid}/revoke")
async def revoke_invitation(iid: str, user=Depends(get_current_user)):
    require(user, ADMIN, OPS)
    inv = await db.invitations.find_one({"id": iid, "organization_id": user["organization_id"], "status": "PENDING"}, {"_id": 0})
    if not inv:
        raise HTTPException(404, "Pending invitation not found")
    await db.invitations.update_one({"id": iid}, {"$set": {"status": "REVOKED"}})
    await db.users.update_one({"id": inv["user_id"], "status": "INVITED"}, {"$set": {"status": "DEACTIVATED"}})
    await audit(user, "INVITATION_REVOKED", "user", inv["user_id"])
    return {"ok": True}


@router.get("/groups")
async def list_groups(user=Depends(get_current_user)):
    f = {"organization_id": user["organization_id"]}
    groups = await db.groups.find(f, {"_id": 0}).sort("name", 1).to_list(500)
    for g in groups:
        g["member_count"] = await db.memberships.count_documents({"group_id": g["id"], "active": True})
        g["candidate_count"] = await db.candidates.count_documents({"current_group_id": g["id"]})
        g["my_role"] = user.get("_groups", {}).get(g["id"])
    return groups


@router.post("/groups")
async def create_group(body: GroupIn, user=Depends(get_current_user)):
    require(user, ADMIN, OPS)
    if await db.groups.find_one({"organization_id": user["organization_id"], "name": body.name}):
        raise HTTPException(409, "Group name already exists")
    g = {"id": new_id(), "organization_id": user["organization_id"], "name": body.name, "description": body.description, "active": True, "created_at": now()}
    await db.groups.insert_one(dict(g))
    await audit(user, "GROUP_CREATED", "group", g["id"], None, {"name": body.name})
    return g


@router.get("/groups/{gid}")
async def get_group(gid: str, user=Depends(get_current_user)):
    g = await db.groups.find_one({"id": gid, "organization_id": user["organization_id"]}, {"_id": 0})
    if not g:
        raise HTTPException(404, "Group not found")
    ms = await db.memberships.find({"group_id": gid, "active": True}, {"_id": 0}).to_list(500)
    users = {u["id"]: u for u in await db.users.find({"id": {"$in": [m["user_id"] for m in ms]}}, {"_id": 0, "id": 1, "name": 1, "email": 1, "status": 1}).to_list(500)}
    g["members"] = [m | {"user": users.get(m["user_id"])} for m in ms]
    g["can_manage"] = is_ops(user) or user.get("_groups", {}).get(gid) == "LEAD"
    return g


@router.patch("/groups/{gid}")
async def update_group(gid: str, body: dict, user=Depends(get_current_user)):
    require(user, ADMIN, OPS)
    upd = {k: body[k] for k in ("name", "description", "active") if k in body}
    if upd.get("active") is False and await db.candidates.count_documents({"current_group_id": gid}):
        raise HTTPException(422, "Transfer or unassign all candidates before deactivating the group")
    await db.groups.update_one({"id": gid, "organization_id": user["organization_id"]}, {"$set": upd})
    await audit(user, "GROUP_UPDATED", "group", gid, None, upd)
    return {"ok": True}


@router.post("/groups/{gid}/members")
async def add_member(gid: str, body: MemberIn, user=Depends(get_current_user)):
    if not (is_ops(user) or user.get("_groups", {}).get(gid) == "LEAD"):
        raise HTTPException(403, "Only Admin, Operations or group Lead can manage members")
    if body.role not in GROUP_ROLES:
        raise HTTPException(422, "Invalid group role")
    target = await db.users.find_one({"id": body.user_id, "organization_id": user["organization_id"]}, {"_id": 0})
    if not target or target["role"] != EMP:
        raise HTTPException(422, "Only standard employees can be group members")
    if await db.memberships.find_one({"group_id": gid, "user_id": body.user_id, "active": True}):
        raise HTTPException(409, "User is already a member")
    m = {"id": new_id(), "organization_id": user["organization_id"], "group_id": gid, "user_id": body.user_id, "role": body.role, "active": True, "created_at": now()}
    await db.memberships.insert_one(dict(m))
    await audit(user, "MEMBERSHIP_ADDED", "group", gid, None, {"user_id": body.user_id, "role": body.role})
    await notify(user["organization_id"], [body.user_id], "Added to group", f"You were added as {body.role}")
    return m


@router.patch("/groups/{gid}/members/{mid}")
async def change_member_role(gid: str, mid: str, body: dict, user=Depends(get_current_user)):
    if not (is_ops(user) or user.get("_groups", {}).get(gid) == "LEAD"):
        raise HTTPException(403, "Not permitted")
    if body.get("role") not in GROUP_ROLES:
        raise HTTPException(422, "Invalid group role")
    m = await db.memberships.find_one({"id": mid, "group_id": gid, "active": True}, {"_id": 0})
    if not m:
        raise HTTPException(404, "Membership not found")
    await db.memberships.update_one({"id": mid}, {"$set": {"role": body["role"]}})
    await audit(user, "MEMBERSHIP_ROLE_CHANGED", "group", gid, {"role": m["role"]}, {"role": body["role"], "user_id": m["user_id"]})
    return {"ok": True}


@router.delete("/groups/{gid}/members/{mid}")
async def remove_member(gid: str, mid: str, reason: str = "Removed", user=Depends(get_current_user)):
    if not (is_ops(user) or user.get("_groups", {}).get(gid) == "LEAD"):
        raise HTTPException(403, "Not permitted")
    m = await db.memberships.find_one({"id": mid, "group_id": gid, "active": True}, {"_id": 0})
    if not m:
        raise HTTPException(404, "Membership not found")
    cleared = await revoke_membership(user, m, reason)
    return {"ok": True, "owners_cleared": cleared}


DEFAULT_SETTINGS = {"bench_aging_warning_days": 14, "bench_aging_critical_days": 30, "weekly_submission_target": 5,
                    "interview_default_timezone": "America/New_York", "mfa_required_for_admin": True}


@router.get("/settings")
async def get_settings(user=Depends(get_current_user)):
    s = await db.settings.find_one({"organization_id": user["organization_id"]}, {"_id": 0}) or {}
    return DEFAULT_SETTINGS | s


@router.put("/settings")
async def put_settings(body: dict, user=Depends(get_current_user)):
    require(user, ADMIN)
    upd = {k: body[k] for k in DEFAULT_SETTINGS if k in body and k != "mfa_required_for_admin"}
    before = await get_settings(user)
    for k in ("bench_aging_warning_days", "bench_aging_critical_days", "weekly_submission_target"):
        if k in upd:
            if not isinstance(upd[k], int) or isinstance(upd[k], bool) or not 1 <= upd[k] <= 365:
                raise HTTPException(422, f"{k} must be an integer between 1 and 365")
    merged = before | upd
    if merged["bench_aging_warning_days"] >= merged["bench_aging_critical_days"]:
        raise HTTPException(422, "Warning threshold must be lower than critical threshold")
    if "interview_default_timezone" in upd:
        from zoneinfo import ZoneInfo
        try:
            ZoneInfo(upd["interview_default_timezone"])
        except Exception:
            raise HTTPException(422, "Invalid timezone")
    await db.settings.update_one({"organization_id": user["organization_id"]}, {"$set": upd | {"organization_id": user["organization_id"]}}, upsert=True)
    await audit(user, "SETTINGS_UPDATED", "settings", user["organization_id"], {k: before.get(k) for k in upd}, upd)
    return await get_settings(user)


@router.get("/saved-views")
async def list_views(page: str = "candidates", user=Depends(get_current_user)):
    return await db.saved_views.find({"user_id": user["id"], "page": page}, {"_id": 0}).to_list(100)


@router.post("/saved-views")
async def create_view(body: SavedViewIn, user=Depends(get_current_user)):
    v = body.model_dump() | {"id": new_id(), "organization_id": user["organization_id"], "user_id": user["id"], "created_at": now()}
    await db.saved_views.insert_one(dict(v))
    return v


@router.delete("/saved-views/{vid}")
async def delete_view(vid: str, user=Depends(get_current_user)):
    await db.saved_views.delete_one({"id": vid, "user_id": user["id"]})
    return {"ok": True}


@router.get("/audit")
async def list_audit(entity_type: str = "", action: str = "", actor_id: str = "", page: int = 1, page_size: int = 50, user=Depends(get_current_user)):
    require(user, ADMIN, OPS, AUDITOR)
    f = {"organization_id": user["organization_id"]}
    if entity_type:
        f["entity_type"] = entity_type
    if action:
        f["action"] = {"$regex": action, "$options": "i"}
    if actor_id:
        f["actor_id"] = actor_id
    page_size = min(page_size, 200)
    total = await db.audit_logs.count_documents(f)
    items = await db.audit_logs.find(f, {"_id": 0}).sort("created_at", -1).skip((page - 1) * page_size).limit(page_size).to_list(page_size)
    return {"items": [redact_audit(user, a) for a in items], "total": total, "page": page}


@router.get("/notifications")
async def list_notifications(user=Depends(get_current_user)):
    items = await db.notifications.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {"items": items, "unread": await db.notifications.count_documents({"user_id": user["id"], "read": False})}


@router.post("/notifications/read-all")
async def read_all(user=Depends(get_current_user)):
    await db.notifications.update_many({"user_id": user["id"]}, {"$set": {"read": True}})
    return {"ok": True}


@router.post("/notifications/{nid}/read")
async def read_one(nid: str, user=Depends(get_current_user)):
    await db.notifications.update_one({"id": nid, "user_id": user["id"]}, {"$set": {"read": True}})
    return {"ok": True}


@router.get("/outbox")
async def list_outbox(user=Depends(get_current_user)):
    require(user, ADMIN)
    return await db.outbox.find({"organization_id": user["organization_id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)


def days_since(iso):
    if not iso:
        return None
    return (datetime.now(timezone.utc) - datetime.fromisoformat(iso)).days


@router.get("/dashboard")
async def dashboard(user=Depends(get_current_user)):
    scope = candidate_scope(user)
    settings = await get_settings(user)
    by_status = {s: 0 for s in STATUSES}
    async for r in db.candidates.aggregate([{"$match": scope}, {"$group": {"_id": "$status", "n": {"$sum": 1}}}]):
        by_status[r["_id"]] = r["n"]
    bench = await db.candidates.find(scope | {"status": {"$in": ["BENCH", "ON_HOLD"]}}, {"_id": 0, "bench_since": 1}).to_list(5000)
    aging = {"0-7": 0, "8-14": 0, "15-30": 0, "30+": 0}
    critical = 0
    for b in bench:
        d = days_since(b.get("bench_since")) or 0
        aging["0-7" if d <= 7 else "8-14" if d <= 14 else "15-30" if d <= 30 else "30+"] += 1
        critical += d > settings["bench_aging_critical_days"]
    sf = {"organization_id": user["organization_id"]}
    if user["role"] == EMP:
        sf["group_id"] = {"$in": list(user.get("_groups", {}).keys())}
    week = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0).isoformat()
    daily = []
    for i in range(13, -1, -1):
        d0 = (datetime.now(timezone.utc) - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        d1 = d0 + timedelta(days=1)
        daily.append({"date": d0.strftime("%b %d"), "submissions": await db.submissions.count_documents(sf | {"created_at": {"$gte": d0.isoformat(), "$lt": d1.isoformat()}})})
    upcoming = await db.interviews.find(sf | {"status": "SCHEDULED", "scheduled_at": {"$gte": now()}}, {"_id": 0}).sort("scheduled_at", 1).limit(6).to_list(6)
    cands = {c["id"]: f"{c['first_name']} {c['last_name']}" for c in await db.candidates.find({"id": {"$in": [u["candidate_id"] for u in upcoming]}}, {"_id": 0}).to_list(10)}
    for u in upcoming:
        u["candidate_name"] = cands.get(u["candidate_id"])
    return {
        "by_status": by_status, "bench_aging": aging, "bench_critical": critical, "settings": settings,
        "submissions_7d": await db.submissions.count_documents(sf | {"created_at": {"$gte": week}}),
        "interviews_upcoming": await db.interviews.count_documents(sf | {"status": "SCHEDULED", "scheduled_at": {"$gte": now()}}),
        "offers_open": await db.offers.count_documents(sf | {"status": "EXTENDED"}),
        "placements_month": await db.placements.count_documents(sf | {"created_at": {"$gte": month_start}}),
        "placements_active": await db.placements.count_documents(sf | {"status": "ACTIVE"}),
        "my_open_tasks": await db.tasks.count_documents({"assignee_id": user["id"], "status": "OPEN"}),
        "submissions_daily": daily, "upcoming_interviews": upcoming,
    }


@router.get("/reports/summary")
async def reports(user=Depends(get_current_user)):
    require(user, ADMIN, OPS, AUDITOR, EMP)
    oid = user["organization_id"]
    sf = {"organization_id": oid}
    if user["role"] == EMP:
        sf["group_id"] = {"$in": list(user.get("_groups", {}).keys())}
    groups = await db.groups.find({"organization_id": oid}, {"_id": 0}).to_list(500)
    by_group = []
    for g in groups:
        if user["role"] == EMP and g["id"] not in user.get("_groups", {}):
            continue
        by_group.append({"group": g["name"],
                         "candidates": await db.candidates.count_documents({"current_group_id": g["id"]}),
                         "bench": await db.candidates.count_documents({"current_group_id": g["id"], "status": {"$in": ["BENCH", "ON_HOLD"]}}),
                         "marketing": await db.candidates.count_documents({"current_group_id": g["id"], "status": {"$in": MARKETING_STATES}}),
                         "submissions": await db.submissions.count_documents({"group_id": g["id"]}),
                         "interviews": await db.interviews.count_documents({"group_id": g["id"]}),
                         "placements": await db.placements.count_documents({"group_id": g["id"]})})
    funnel = [{"stage": k, "count": await db[c].count_documents(sf)} for k, c in
              [("Submissions", "submissions"), ("Interviews", "interviews"), ("Offers", "offers"), ("Placements", "placements")]]
    scope = candidate_scope(user)
    bench = await db.candidates.find(scope | {"status": {"$in": ["BENCH", "ON_HOLD"]}}, {"_id": 0, "id": 1, "first_name": 1, "last_name": 1, "status": 1, "primary_skill": 1, "bench_since": 1, "current_group_id": 1}).to_list(2000)
    gn = {g["id"]: g["name"] for g in groups}
    for b in bench:
        b["days_on_bench"] = days_since(b.get("bench_since"))
        b["group_name"] = gn.get(b.get("current_group_id"))
    bench.sort(key=lambda b: -(b["days_on_bench"] or 0))
    recruiters = []
    async for r in db.submissions.aggregate([{"$match": sf}, {"$group": {"_id": "$submitted_by_name", "n": {"$sum": 1}}}, {"$sort": {"n": -1}}]):
        recruiters.append({"name": r["_id"], "submissions": r["n"]})
    return {"by_group": by_group, "funnel": funnel, "bench_aging": bench[:50], "recruiter_activity": recruiters}


@router.post("/exports/candidates")
async def export_candidates(body: dict = None, user=Depends(get_current_user)):
    require(user, ADMIN, OPS, AUDITOR)
    j = {"id": new_id(), "organization_id": user["organization_id"], "type": "EXPORT_CANDIDATES", "status": "PENDING",
         "payload": {"filters": (body or {}).get("filters", {})}, "created_by": user["id"], "created_by_name": user["name"], "created_at": now()}
    await db.bg_jobs.insert_one(dict(j))
    await audit(user, "EXPORT_REQUESTED", "export", j["id"], None, j["payload"])
    return j


@router.post("/imports/candidates")
async def import_candidates(file: UploadFile = File(...), user=Depends(get_current_user)):
    require(user, ADMIN, OPS)
    text = (await file.read()).decode("utf-8-sig", errors="replace")
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        raise HTTPException(422, "CSV is empty or missing header row")
    if not {"first_name", "last_name"} <= set(rows[0].keys()):
        raise HTTPException(422, "CSV must include first_name and last_name columns")
    j = {"id": new_id(), "organization_id": user["organization_id"], "type": "IMPORT_CANDIDATES", "status": "PENDING",
         "payload": {"rows": rows[:5000], "filename": file.filename}, "created_by": user["id"], "created_by_name": user["name"], "created_at": now()}
    await db.bg_jobs.insert_one(dict(j))
    await audit(user, "IMPORT_REQUESTED", "import", j["id"], None, {"filename": file.filename, "rows": len(rows)})
    return {k: v for k, v in j.items() if k != "payload"} | {"rows": len(rows)}


@router.get("/bg-jobs")
async def list_jobs(user=Depends(get_current_user)):
    f = {"organization_id": user["organization_id"], "type": {"$in": ["EXPORT_CANDIDATES", "IMPORT_CANDIDATES"]}}
    if not is_ops(user):
        f["created_by"] = user["id"]
    return await db.bg_jobs.find(f, {"_id": 0, "payload": 0, "result_csv": 0}).sort("created_at", -1).to_list(100)


@router.get("/bg-jobs/{jid}/download")
async def download_job(jid: str, user=Depends(get_current_user)):
    require(user, ADMIN, OPS, AUDITOR)
    j = await db.bg_jobs.find_one({"id": jid, "organization_id": user["organization_id"], "created_by": user["id"]}, {"_id": 0})
    if not j or j["status"] != "COMPLETED" or not j.get("result_csv"):
        raise HTTPException(404, "Export not ready")
    await audit(user, "EXPORT_DOWNLOADED", "export", jid)
    return Response(j["result_csv"], media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="candidates-{jid[:8]}.csv"'})

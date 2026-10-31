import os
import uuid
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

import bcrypt
import jwt
from dotenv import load_dotenv
from fastapi import HTTPException, Request
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv(Path(__file__).parent / ".env")

logger = logging.getLogger("benchmgr")
client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]
JWT_ALGORITHM = "HS256"

ADMIN, OPS, EMP, AUDITOR = "ADMIN", "OPERATIONS", "EMPLOYEE", "AUDITOR"
ORG_ROLES = [ADMIN, OPS, EMP, AUDITOR]
GROUP_ROLES = ["LEAD", "RECRUITER", "MARKETING", "VIEWER"]
STATUSES = ["NEW", "BENCH", "MARKETING", "SUBMITTED", "INTERVIEWING", "OFFERED", "PLACED", "ON_HOLD", "ARCHIVED"]
MARKETING_STATES = ["MARKETING", "SUBMITTED", "INTERVIEWING", "OFFERED"]
TRANSITIONS = {
    "NEW": ["BENCH", "ON_HOLD"],
    "BENCH": ["MARKETING", "ON_HOLD"],
    "MARKETING": ["SUBMITTED", "BENCH", "ON_HOLD"],
    "SUBMITTED": ["INTERVIEWING", "MARKETING"],
    "INTERVIEWING": ["OFFERED", "MARKETING"],
    "OFFERED": ["PLACED", "MARKETING"],
    "PLACED": ["BENCH"],
    "ON_HOLD": ["BENCH"],
    "ARCHIVED": [],
}
PAY_FIELDS = ["pay_rate"]
BILL_FIELDS = ["bill_rate", "target_rate", "submission_rate", "rate"]


def now():
    return datetime.now(timezone.utc).isoformat()


def new_id():
    return str(uuid.uuid4())


def hash_password(p: str) -> str:
    return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()


def verify_password(p: str, h: str) -> bool:
    return bool(h) and bcrypt.checkpw(p.encode(), h.encode())


def make_token(user_id: str, kind: str, minutes: int, extra: dict = None) -> str:
    payload = {"sub": user_id, "type": kind, "exp": datetime.now(timezone.utc) + timedelta(minutes=minutes)}
    payload.update(extra or {})
    return jwt.encode(payload, os.environ["JWT_SECRET"], algorithm=JWT_ALGORITHM)


def decode_token(token: str, kind: str) -> dict:
    try:
        payload = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")
    if payload.get("type") != kind:
        raise HTTPException(401, "Invalid token type")
    return payload


def public_user(u: dict) -> dict:
    return {k: v for k, v in u.items() if k not in ("_id", "password_hash", "mfa_secret", "pending_mfa_secret")}


async def load_groups(user: dict) -> dict:
    ms = await db.memberships.find({"user_id": user["id"], "active": True}, {"_id": 0}).to_list(500)
    return {m["group_id"]: m["role"] for m in ms}


async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
    if not token:
        raise HTTPException(401, "Not authenticated")
    payload = decode_token(token, "access")
    user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0})
    if not user or user.get("status") != "ACTIVE":
        raise HTTPException(401, "User inactive or not found")
    if payload.get("sv", 0) != user.get("session_version", 0):
        raise HTTPException(401, "Session revoked")
    user["_groups"] = await load_groups(user) if user["role"] == EMP else {}
    return public_user(user) | {"_groups": user["_groups"]}


def is_ops(user) -> bool:
    return user["role"] in (ADMIN, OPS)


def require(user, *roles):
    if user["role"] not in roles:
        raise HTTPException(403, "You do not have permission for this action")


def require_writer(user):
    if user["role"] == AUDITOR:
        raise HTTPException(403, "Auditors have read-only access")


def candidate_scope(user) -> dict:
    org = {"organization_id": user["organization_id"]}
    if user["role"] in (ADMIN, OPS, AUDITOR):
        return org
    groups = user.get("_groups", {})
    full = [g for g, r in groups.items() if r != "MARKETING"]
    mkt = [g for g, r in groups.items() if r == "MARKETING"]
    ors = []
    if full:
        ors.append({"current_group_id": {"$in": full}})
    if mkt:
        ors.append({"current_group_id": {"$in": mkt}, "status": {"$in": MARKETING_STATES}})
        ors.append({"current_group_id": {"$in": mkt}, "status": {"$in": ["BENCH", "ON_HOLD"]}, "owner_id": user["id"]})
    if not ors:
        return org | {"id": "__none__"}
    return org | {"$or": ors}


def group_role(user, cand) -> str:
    return user.get("_groups", {}).get(cand.get("current_group_id"))


def edit_level(user, cand) -> str:
    if is_ops(user):
        return "full"
    if user["role"] != EMP:
        return None
    r = group_role(user, cand)
    if r in ("LEAD", "RECRUITER"):
        return "full"
    if r == "MARKETING":
        return "marketing"
    return None


def can_see_bill(user, group_id) -> bool:
    return is_ops(user) or user.get("_groups", {}).get(group_id) in ("LEAD", "MARKETING")


def redact(user, doc: dict, group_id=None) -> dict:
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


async def get_candidate_or_404(user, cid: str) -> dict:
    c = await db.candidates.find_one(candidate_scope(user) | {"id": cid}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Candidate not found or not accessible")
    return c


async def audit(user, action, entity_type, entity_id, before=None, after=None, reason=None, candidate_id=None):
    await db.audit_logs.insert_one({
        "candidate_id": candidate_id or (after or {}).get("candidate_id") or (before or {}).get("candidate_id"),
        "id": new_id(), "organization_id": user["organization_id"], "actor_id": user["id"],
        "actor_name": user.get("name"), "action": action, "entity_type": entity_type,
        "entity_id": entity_id, "before": before, "after": after, "reason": reason, "created_at": now(),
    })


async def timeline(user, candidate_id, event, detail="", meta=None):
    await db.timeline.insert_one({
        "id": new_id(), "organization_id": user["organization_id"], "candidate_id": candidate_id,
        "event": event, "detail": detail, "meta": meta or {}, "actor_id": user["id"],
        "actor_name": user.get("name"), "created_at": now(),
    })


async def notify(org_id, user_ids, title, body, link=None):
    users = await db.users.find({"id": {"$in": list(set(user_ids))}, "status": "ACTIVE"}, {"_id": 0, "id": 1, "email": 1}).to_list(500)
    for u in users:
        await db.notifications.insert_one({
            "id": new_id(), "organization_id": org_id, "user_id": u["id"], "title": title,
            "body": body, "link": link, "read": False, "created_at": now(),
        })
        await db.outbox.insert_one({
            "id": new_id(), "organization_id": org_id, "to": u["email"], "subject": title,
            "body": body, "status": "PENDING", "attempts": 0, "created_at": now(),
        })


async def ops_and_lead_ids(org_id, group_id=None):
    ids = [u["id"] for u in await db.users.find({"organization_id": org_id, "role": {"$in": [ADMIN, OPS]}, "status": "ACTIVE"}, {"id": 1, "_id": 0}).to_list(200)]
    if group_id:
        ids += [m["user_id"] for m in await db.memberships.find({"group_id": group_id, "role": "LEAD", "active": True}, {"_id": 0}).to_list(50)]
    return ids


def paginate_params(page: int, page_size: int):
    page_size = max(1, min(page_size, 200))
    return max(1, page), page_size


def rx(q: str):
    import re
    return {"$regex": re.escape(q), "$options": "i"}

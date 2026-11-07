"""Admin routes — users, groups, settings, audit, dashboard, exports, platform — /api"""
import csv
import io
import secrets
import re
from base64 import b64decode
from binascii import Error as Base64Error
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, UploadFile, File
from fastapi.responses import Response as FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from sqlalchemy import DateTime, select, update, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.constants import (
    ADMIN, OPERATIONS, EMPLOYEE, AUDITOR, ORG_ROLES, GROUP_ROLES,
    STATUSES, MARKETING_STATES, PAY_FIELDS, BILL_FIELDS, DEFAULT_SETTINGS,
)
from app.exceptions import NotFoundError, ForbiddenError, ConflictError, ValidationError
from app.models.user import User, Invitation
from app.models.organization import Organization
from app.models.group import Group, Membership
from app.models.candidate import Candidate
from app.models.pipeline import Submission, Interview, Offer, Placement
from app.models.audit import (
    AuditLog, TimelineEvent, Notification, EmailOutbox,
    Note, Task, Document, BackgroundJob, SavedView, Settings,
)
from app.services.auth_service import (
    utcnow, new_id, hash_password, get_current_user, user_to_dict,
    is_ops, require, require_writer, audit, timeline, notify, ops_and_lead_ids, clear_attempts,
)
from app.services.authorization import candidate_scope_filters, candidate_to_dict

router = APIRouter(prefix="/api")


# ── Schemas ────────────────────────────────────────────────────

class InviteIn(BaseModel):
    email: str
    name: str
    role: str = EMPLOYEE
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

class ResetMfaIn(BaseModel):
    reason: str = Field(max_length=1000)


class OrgIn(BaseModel):
    name: str = Field(max_length=255)
    slug: str
    admin_name: str = Field(max_length=255)
    admin_email: str = Field(max_length=320)
    plan: str = "Professional"
    default_groups: list[str] = Field(default_factory=lambda: ["Core Bench"], max_length=10)
    industry: str | None = Field(default=None, max_length=100)
    size: str | None = Field(default=None, max_length=20)
    logo_data: str | None = Field(default=None, max_length=175000)
    temporary_password: str | None = Field(default=None, max_length=72)


# ── Helpers ────────────────────────────────────────────────────

def redact_audit(user: dict, a: dict) -> dict:
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


async def revoke_membership(db: AsyncSession, user: dict, m, reason: str) -> int:
    """Revoke a membership, clear candidate ownership, notify."""
    m.active = False
    m.ended_at = utcnow()
    m.ended_by = user["id"]
    m.end_reason = reason
    await db.flush()

    # Clear candidate owners
    result = await db.execute(
        select(Candidate).where(
            Candidate.current_group_id == m.group_id, Candidate.owner_id == m.user_id
        )
    )
    cleared = result.scalars().all()
    if cleared:
        await db.execute(
            update(Candidate).where(
                Candidate.current_group_id == m.group_id, Candidate.owner_id == m.user_id
            ).values(owner_id=None, version=Candidate.version + 1)
        )
        for c in cleared:
            await timeline(db, user, c.id, "OWNER_CLEARED", f"Owner removed from group ({reason})")

    member_r = await db.execute(select(User.name).where(User.id == m.user_id))
    member_name = (member_r.scalar_one_or_none() or "Unknown")
    grp_r = await db.execute(select(Group.name).where(Group.id == m.group_id))
    grp_name = (grp_r.scalar_one_or_none() or "Unknown")

    await audit(db, user, "MEMBERSHIP_REMOVED", "group", m.group_id,
                {"user_id": m.user_id, "role": m.role}, None, reason)
    await notify(db, user["organization_id"],
                 await ops_and_lead_ids(db, user["organization_id"], m.group_id),
                 f"Member removed: {member_name}",
                 f"Removed from {grp_name}. {len(cleared)} candidate owner(s) cleared.")
    return len(cleared)


async def get_org_settings(db: AsyncSession, org_id: str) -> dict:
    result = await db.execute(select(Settings).where(Settings.organization_id == org_id))
    s = result.scalar_one_or_none()
    if s:
        return DEFAULT_SETTINGS | {
            "bench_aging_warning_days": s.bench_aging_warning_days,
            "bench_aging_critical_days": s.bench_aging_critical_days,
            "weekly_submission_target": s.weekly_submission_target,
            "interview_default_timezone": s.interview_default_timezone,
        }
    return dict(DEFAULT_SETTINGS)


# ── Organization ───────────────────────────────────────────────

@router.get("/organization")
async def get_org(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(Organization).where(Organization.id == user["organization_id"]))
    org = r.scalar_one_or_none()
    if not org:
        raise NotFoundError("Organization not found")
    return {"id": org.id, "name": org.name, "slug": org.slug, "plan": org.plan}


# ── Users ──────────────────────────────────────────────────────

@router.get("/users")
async def list_users(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(User).where(User.organization_id == user["organization_id"]).order_by(User.name)
    )
    users = result.scalars().all()
    ms_result = await db.execute(
        select(Membership).where(
            Membership.organization_id == user["organization_id"], Membership.active == True
        )
    )
    memberships = ms_result.scalars().all()
    grp_r = await db.execute(
        select(Group.id, Group.name).where(Group.organization_id == user["organization_id"])
    )
    groups = {r.id: r.name for r in grp_r.all()}

    out = []
    for u in users:
        ud = user_to_dict(u)
        ud.pop("password_hash", None)
        ud["groups"] = [
            {"group_id": m.group_id, "group_name": groups.get(m.group_id), "role": m.role}
            for m in memberships if m.user_id == u.id
        ]
        out.append(ud)
    return out


@router.patch("/users/{uid}")
async def update_user(uid: str, body: UserPatch, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require(user, ADMIN)
    r = await db.execute(
        select(User).where(User.id == uid, User.organization_id == user["organization_id"]).with_for_update()
    )
    target = r.scalar_one_or_none()
    if not target:
        raise NotFoundError("User not found")
    upd = {k: v for k, v in body.model_dump().items() if v is not None}
    if "role" in upd and upd["role"] not in ORG_ROLES:
        raise ValidationError("Invalid role")
    if uid == user["id"] and ("role" in upd or upd.get("status") == "DEACTIVATED"):
        raise ValidationError("You cannot change your own role or deactivate yourself")
    for k, v in upd.items():
        setattr(target, k, v)
    if upd.get("status") == "DEACTIVATED" or "role" in upd:
        target.session_version = (target.session_version or 0) + 1
    if upd.get("status") == "DEACTIVATED":
        ms_r = await db.execute(
            select(Membership).where(Membership.user_id == uid, Membership.active == True)
        )
        for m in ms_r.scalars().all():
            await revoke_membership(db, user, m, "User deactivated")
    await db.flush()
    before = {k: getattr(target, k) for k in upd}
    await audit(db, user, "USER_UPDATED", "user", uid, before, upd)
    return {"ok": True}


@router.post("/users/{uid}/reset-mfa")
async def reset_mfa(uid: str, body: ResetMfaIn, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require(user, ADMIN)
    if uid == user["id"]:
        raise ValidationError("Another administrator must reset your authenticator")
    r = await db.execute(
        select(User).where(User.id == uid, User.organization_id == user["organization_id"]).with_for_update()
    )
    target = r.scalar_one_or_none()
    if not target:
        raise NotFoundError("User not found")
    if not target.mfa_enabled:
        raise ValidationError("User has no authenticator enrolled")
    reason = body.reason.strip()
    if not reason.strip():
        raise ValidationError("A reason is required")
    target.mfa_enabled = False
    target.mfa_secret = None
    target.pending_mfa_secret = None
    target.session_version = (target.session_version or 0) + 1
    await clear_attempts(db, f"mfa:{uid}")
    await audit(db, user, "MFA_RESET", "user", uid, {"mfa_enabled": True}, {"mfa_enabled": False}, reason)
    await notify(db, user["organization_id"], [uid], "Your authenticator was reset",
                 "Sign in again to enroll a new authenticator app.")
    return {"ok": True}


# ── Invitations ────────────────────────────────────────────────

@router.get("/invitations")
async def list_invitations(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require(user, ADMIN, OPERATIONS)
    r = await db.execute(
        select(Invitation).where(Invitation.organization_id == user["organization_id"])
        .order_by(Invitation.created_at.desc())
    )
    return [
        {"id": i.id, "email": i.email, "name": i.name, "role": i.role,
         "status": i.status, "invited_by_name": i.invited_by_name,
         "created_at": str(i.created_at), "expires_at": i.expires_at}
        for i in r.scalars().all()
    ]


@router.post("/invitations")
async def create_invitation(body: InviteIn, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require(user, ADMIN, OPERATIONS)
    if body.role not in ORG_ROLES or (body.role == ADMIN and user["role"] != ADMIN):
        raise ValidationError("Invalid role")
    email = body.email.strip().lower()
    if "@" not in email:
        raise ValidationError("Invalid email")
    r = await db.execute(select(User).where(User.email == email))
    if r.scalar_one_or_none():
        raise ConflictError("A user with this email already exists")
    if body.group_id:
        if body.role != EMPLOYEE or body.group_role not in GROUP_ROLES:
            raise ValidationError("Group membership requires EMPLOYEE role and a valid group role")
        gr = await db.execute(select(Group).where(
            Group.id == body.group_id, Group.organization_id == user["organization_id"], Group.active == True
        ))
        if not gr.scalar_one_or_none():
            raise ValidationError("Group not found or inactive")

    uid = new_id()
    new_user = User(
        id=uid, organization_id=user["organization_id"], email=email, name=body.name,
        role=body.role, status="INVITED", auth_methods=[], mfa_enabled=False, session_version=0,
    )
    db.add(new_user)
    await db.flush()

    if body.group_id:
        db.add(Membership(
            id=new_id(), organization_id=user["organization_id"],
            group_id=body.group_id, user_id=uid, role=body.group_role, active=True,
        ))

    token = secrets.token_urlsafe(32)
    inv = Invitation(
        id=new_id(), organization_id=user["organization_id"], user_id=uid, email=email,
        name=body.name, role=body.role, token=token, status="PENDING",
        invited_by=user["id"], invited_by_name=user["name"],
        expires_at=(datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
    )
    db.add(inv)
    db.add(EmailOutbox(
        id=new_id(), organization_id=user["organization_id"], to=email,
        subject="You're invited to BenchOS",
        body=f"Activate your account: {get_settings().FRONTEND_URL.rstrip('/')}/activate?token={token}",
        status="PENDING", attempts=0,
    ))
    await db.flush()
    await audit(db, user, "USER_INVITED", "user", uid, None, {"email": email, "role": body.role})
    return {"id": inv.id, "email": email, "token": token, "activation_path": f"/activate?token={token}"}


@router.post("/invitations/{iid}/revoke")
async def revoke_invitation(iid: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require(user, ADMIN, OPERATIONS)
    r = await db.execute(select(Invitation).where(
        Invitation.id == iid, Invitation.organization_id == user["organization_id"], Invitation.status == "PENDING"
    ))
    inv = r.scalar_one_or_none()
    if not inv:
        raise NotFoundError("Pending invitation not found")
    inv.status = "REVOKED"
    await db.execute(
        update(User).where(User.id == inv.user_id, User.status == "INVITED").values(status="DEACTIVATED")
    )
    await db.flush()
    await audit(db, user, "INVITATION_REVOKED", "user", inv.user_id)
    return {"ok": True}


# ── Groups ─────────────────────────────────────────────────────

@router.get("/groups")
async def list_groups(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    r = await db.execute(
        select(Group).where(Group.organization_id == user["organization_id"]).order_by(Group.name)
    )
    groups = r.scalars().all()
    out = []
    for g in groups:
        mc = await db.execute(select(func.count()).select_from(Membership).where(
            Membership.group_id == g.id, Membership.active == True
        ))
        cc = await db.execute(select(func.count()).select_from(Candidate).where(
            Candidate.current_group_id == g.id
        ))
        out.append({
            "id": g.id, "name": g.name, "description": g.description, "active": g.active,
            "member_count": mc.scalar() or 0, "candidate_count": cc.scalar() or 0,
            "my_role": user.get("_groups", {}).get(g.id),
            "created_at": str(g.created_at),
        })
    return out


@router.post("/groups")
async def create_group(body: GroupIn, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require(user, ADMIN, OPERATIONS)
    r = await db.execute(select(Group).where(
        Group.organization_id == user["organization_id"], Group.name == body.name
    ))
    if r.scalar_one_or_none():
        raise ConflictError("Group name already exists")
    g = Group(id=new_id(), organization_id=user["organization_id"], name=body.name,
              description=body.description, active=True)
    db.add(g)
    await db.flush()
    await audit(db, user, "GROUP_CREATED", "group", g.id, None, {"name": body.name})
    return {"id": g.id, "name": g.name, "description": g.description, "active": g.active}


@router.get("/groups/{gid}")
async def get_group(gid: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(Group).where(Group.id == gid, Group.organization_id == user["organization_id"]))
    g = r.scalar_one_or_none()
    if not g:
        raise NotFoundError("Group not found")
    ms_r = await db.execute(select(Membership).where(Membership.group_id == gid, Membership.active == True))
    members = ms_r.scalars().all()
    user_ids = [m.user_id for m in members]
    users_r = await db.execute(select(User).where(User.id.in_(user_ids))) if user_ids else None
    users_map = {u.id: {"id": u.id, "name": u.name, "email": u.email, "status": u.status}
                 for u in (users_r.scalars().all() if users_r else [])}
    return {
        "id": g.id, "name": g.name, "description": g.description, "active": g.active,
        "members": [{"id": m.id, "user_id": m.user_id, "role": m.role, "user": users_map.get(m.user_id)}
                     for m in members],
        "can_manage": is_ops(user) or user.get("_groups", {}).get(gid) == "LEAD",
    }


@router.patch("/groups/{gid}")
async def update_group(gid: str, body: dict, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require(user, ADMIN, OPERATIONS)
    r = await db.execute(select(Group).where(Group.id == gid, Group.organization_id == user["organization_id"]))
    g = r.scalar_one_or_none()
    if not g:
        raise NotFoundError("Group not found")
    if body.get("active") is False:
        cc = await db.execute(select(func.count()).select_from(Candidate).where(Candidate.current_group_id == gid))
        if (cc.scalar() or 0) > 0:
            raise ValidationError("Transfer or unassign all candidates before deactivating the group")
    for k in ("name", "description", "active"):
        if k in body:
            setattr(g, k, body[k])
    await db.flush()
    await audit(db, user, "GROUP_UPDATED", "group", gid, None, {k: body[k] for k in ("name", "description", "active") if k in body})
    return {"ok": True}


@router.post("/groups/{gid}/members")
async def add_member(gid: str, body: MemberIn, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not (is_ops(user) or user.get("_groups", {}).get(gid) == "LEAD"):
        raise ForbiddenError("Only Admin, Operations or group Lead can manage members")
    if body.role not in GROUP_ROLES:
        raise ValidationError("Invalid group role")
    tr = await db.execute(select(User).where(User.id == body.user_id, User.organization_id == user["organization_id"]))
    target = tr.scalar_one_or_none()
    if not target or target.role != EMPLOYEE:
        raise ValidationError("Only standard employees can be group members")
    mr = await db.execute(select(Membership).where(
        Membership.group_id == gid, Membership.user_id == body.user_id, Membership.active == True
    ))
    if mr.scalar_one_or_none():
        raise ConflictError("User is already a member")
    m = Membership(id=new_id(), organization_id=user["organization_id"], group_id=gid,
                   user_id=body.user_id, role=body.role, active=True)
    db.add(m)
    await db.flush()
    await audit(db, user, "MEMBERSHIP_ADDED", "group", gid, None, {"user_id": body.user_id, "role": body.role})
    await notify(db, user["organization_id"], [body.user_id], "Added to group", f"You were added as {body.role}")
    return {"id": m.id, "group_id": gid, "user_id": body.user_id, "role": body.role}


@router.patch("/groups/{gid}/members/{mid}")
async def change_member_role(gid: str, mid: str, body: dict, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not (is_ops(user) or user.get("_groups", {}).get(gid) == "LEAD"):
        raise ForbiddenError("Not permitted")
    if body.get("role") not in GROUP_ROLES:
        raise ValidationError("Invalid group role")
    mr = await db.execute(select(Membership).where(Membership.id == mid, Membership.group_id == gid, Membership.active == True))
    m = mr.scalar_one_or_none()
    if not m:
        raise NotFoundError("Membership not found")
    old_role = m.role
    m.role = body["role"]
    await db.flush()
    await audit(db, user, "MEMBERSHIP_ROLE_CHANGED", "group", gid, {"role": old_role}, {"role": body["role"], "user_id": m.user_id})
    return {"ok": True}


@router.delete("/groups/{gid}/members/{mid}")
async def remove_member(gid: str, mid: str, reason: str = "Removed", user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not (is_ops(user) or user.get("_groups", {}).get(gid) == "LEAD"):
        raise ForbiddenError("Not permitted")
    mr = await db.execute(select(Membership).where(Membership.id == mid, Membership.group_id == gid, Membership.active == True))
    m = mr.scalar_one_or_none()
    if not m:
        raise NotFoundError("Membership not found")
    cleared = await revoke_membership(db, user, m, reason)
    return {"ok": True, "owners_cleared": cleared}


# ── Settings ───────────────────────────────────────────────────

@router.get("/settings")
async def get_settings_route(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await get_org_settings(db, user["organization_id"])


@router.put("/settings")
async def put_settings(body: dict, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require(user, ADMIN)
    before = await get_org_settings(db, user["organization_id"])
    upd = {k: body[k] for k in DEFAULT_SETTINGS if k in body and k != "mfa_required_for_admin"}
    for k in ("bench_aging_warning_days", "bench_aging_critical_days", "weekly_submission_target"):
        if k in upd:
            if not isinstance(upd[k], int) or isinstance(upd[k], bool) or not 1 <= upd[k] <= 365:
                raise ValidationError(f"{k} must be an integer between 1 and 365")
    merged = before | upd
    if merged["bench_aging_warning_days"] >= merged["bench_aging_critical_days"]:
        raise ValidationError("Warning threshold must be lower than critical threshold")
    if "interview_default_timezone" in upd:
        from zoneinfo import ZoneInfo
        try:
            ZoneInfo(upd["interview_default_timezone"])
        except Exception:
            raise ValidationError("Invalid timezone")

    r = await db.execute(select(Settings).where(Settings.organization_id == user["organization_id"]))
    s = r.scalar_one_or_none()
    if s:
        for k, v in upd.items():
            setattr(s, k, v)
    else:
        db.add(Settings(id=new_id(), organization_id=user["organization_id"], **upd))
    await db.flush()
    await audit(db, user, "SETTINGS_UPDATED", "settings", user["organization_id"],
                {k: before.get(k) for k in upd}, upd)
    return await get_org_settings(db, user["organization_id"])


# ── Saved views ────────────────────────────────────────────────

@router.get("/saved-views")
async def list_views(page: str = "candidates", user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(SavedView).where(SavedView.user_id == user["id"], SavedView.page == page))
    return [{"id": v.id, "name": v.name, "page": v.page, "filters": v.filters} for v in r.scalars().all()]


@router.post("/saved-views")
async def create_view(body: SavedViewIn, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    v = SavedView(id=new_id(), organization_id=user["organization_id"], user_id=user["id"],
                  name=body.name, page=body.page, filters=body.filters)
    db.add(v)
    await db.flush()
    return {"id": v.id, "name": v.name, "page": v.page, "filters": v.filters}


@router.delete("/saved-views/{vid}")
async def delete_view(vid: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await db.execute(delete(SavedView).where(SavedView.id == vid, SavedView.user_id == user["id"]))
    return {"ok": True}


# ── Audit log ──────────────────────────────────────────────────

@router.get("/audit")
async def list_audit(entity_type: str = "", action: str = "", actor_id: str = "",
                     page: int = 1, page_size: int = 50,
                     user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require(user, ADMIN, OPERATIONS, AUDITOR)
    filters = [AuditLog.organization_id == user["organization_id"]]
    if entity_type:
        filters.append(AuditLog.entity_type == entity_type)
    if action:
        filters.append(AuditLog.action.ilike(f"%{action}%"))
    if actor_id:
        filters.append(AuditLog.actor_id == actor_id)
    page_size = min(page_size, 200)
    total_r = await db.execute(select(func.count()).select_from(AuditLog).where(*filters))
    total = total_r.scalar() or 0
    items_r = await db.execute(
        select(AuditLog).where(*filters).order_by(AuditLog.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )
    items = [
        redact_audit(user, {
            "id": a.id, "action": a.action, "entity_type": a.entity_type,
            "entity_id": a.entity_id, "actor_id": a.actor_id, "actor_name": a.actor_name,
            "before": a.before, "after": a.after, "reason": a.reason,
            "created_at": str(a.created_at),
        })
        for a in items_r.scalars().all()
    ]
    return {"items": items, "total": total, "page": page}


# ── Notifications ──────────────────────────────────────────────

@router.get("/notifications")
async def list_notifications(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    r = await db.execute(
        select(Notification).where(Notification.user_id == user["id"])
        .order_by(Notification.created_at.desc()).limit(100)
    )
    items = [{"id": n.id, "title": n.title, "body": n.body, "link": n.link,
              "read": n.read, "created_at": str(n.created_at)} for n in r.scalars().all()]
    ur = await db.execute(select(func.count()).select_from(Notification).where(
        Notification.user_id == user["id"], Notification.read == False
    ))
    return {"items": items, "unread": ur.scalar() or 0}


@router.post("/notifications/read-all")
async def read_all(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await db.execute(update(Notification).where(Notification.user_id == user["id"]).values(read=True))
    return {"ok": True}


@router.post("/notifications/{nid}/read")
async def read_one(nid: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await db.execute(update(Notification).where(Notification.id == nid, Notification.user_id == user["id"]).values(read=True))
    return {"ok": True}


# ── Outbox ─────────────────────────────────────────────────────

@router.get("/outbox")
async def list_outbox(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require(user, ADMIN)
    r = await db.execute(
        select(EmailOutbox).where(EmailOutbox.organization_id == user["organization_id"])
        .order_by(EmailOutbox.created_at.desc()).limit(200)
    )
    return [{"id": e.id, "to": e.to, "subject": e.subject, "status": e.status,
             "attempts": e.attempts, "created_at": str(e.created_at)} for e in r.scalars().all()]


# ── Dashboard ──────────────────────────────────────────────────

@router.get("/dashboard")
async def dashboard(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    scope = candidate_scope_filters(user)
    settings = await get_org_settings(db, user["organization_id"])

    # By status
    by_status = {s: 0 for s in STATUSES}
    r = await db.execute(
        select(Candidate.status, func.count()).where(*scope).group_by(Candidate.status)
    )
    for row in r.all():
        by_status[row[0]] = row[1]

    # Bench aging
    bench_r = await db.execute(
        select(Candidate.bench_since).where(*scope, Candidate.status.in_(["BENCH", "ON_HOLD"]))
    )
    aging = {"0-7": 0, "8-14": 0, "15-30": 0, "30+": 0}
    critical = 0
    now_dt = datetime.now(timezone.utc)
    for row in bench_r.all():
        bs = row[0]
        if bs:
            try:
                dt = datetime.fromisoformat(bs.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                d = max(0, (now_dt - dt).days)
            except Exception:
                d = 0
        else:
            d = 0
        bucket = "0-7" if d <= 7 else "8-14" if d <= 14 else "15-30" if d <= 30 else "30+"
        aging[bucket] += 1
        if d > settings["bench_aging_critical_days"]:
            critical += 1

    # Scoped pipeline filter
    org_id = user["organization_id"]
    week_ago = now_dt - timedelta(days=7)
    month_start = now_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    today = now_dt.date()
    first_day = today - timedelta(days=13)
    submission_day = func.date(func.timezone("UTC", Submission.created_at))
    daily_rows = await db.execute(
        select(submission_day, func.count()).join(Candidate, Candidate.id == Submission.candidate_id)
        .where(*scope, Submission.organization_id == org_id, submission_day.between(first_day, today))
        .group_by(submission_day)
    )
    daily_counts = dict(daily_rows.all())
    days = [first_day + timedelta(days=offset) for offset in range(14)]
    interview_time = func.cast(Interview.scheduled_at, DateTime(timezone=True))
    upcoming = await db.execute(
        select(Interview, Candidate.first_name, Candidate.last_name)
        .join(Candidate, Candidate.id == Interview.candidate_id)
        .where(*scope, Interview.organization_id == org_id, Interview.status == "SCHEDULED",
               interview_time >= now_dt)
        .order_by(interview_time, Interview.id).limit(5)
    )

    sub_count = await db.execute(select(func.count()).select_from(Submission).where(
        Submission.organization_id == org_id, Submission.created_at >= week_ago
    ))
    int_count = await db.execute(select(func.count()).select_from(Interview).where(
        Interview.organization_id == org_id, Interview.status == "SCHEDULED"
    ))
    offer_count = await db.execute(select(func.count()).select_from(Offer).where(
        Offer.organization_id == org_id, Offer.status == "EXTENDED"
    ))
    place_month = await db.execute(select(func.count()).select_from(Placement).where(
        Placement.organization_id == org_id, Placement.created_at >= month_start
    ))
    place_active = await db.execute(select(func.count()).select_from(Placement).where(
        Placement.organization_id == org_id, Placement.status == "ACTIVE"
    ))
    task_count = await db.execute(select(func.count()).select_from(Task).where(
        Task.assignee_id == user["id"], Task.status == "OPEN"
    ))

    return {
        "by_status": by_status, "bench_aging": aging, "bench_critical": critical, "settings": settings,
        "submissions_7d": sub_count.scalar() or 0,
        "interviews_upcoming": int_count.scalar() or 0,
        "offers_open": offer_count.scalar() or 0,
        "placements_month": place_month.scalar() or 0,
        "placements_active": place_active.scalar() or 0,
        "my_open_tasks": task_count.scalar() or 0,
        "submissions_daily": [{"date": day.isoformat(), "submissions": daily_counts.get(day, 0)} for day in days],
        "upcoming_interviews": [
            {"id": interview.id, "candidate_id": interview.candidate_id,
             "candidate_name": f"{first} {last}".strip(), "round": interview.round,
             "mode": interview.mode, "scheduled_at": interview.scheduled_at,
             "timezone": interview.timezone, "status": interview.status}
            for interview, first, last in upcoming.all()
        ],
    }


# ── Reports ────────────────────────────────────────────────────

@router.get("/reports/summary")
async def reports(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require(user, ADMIN, OPERATIONS, AUDITOR, EMPLOYEE)
    org_id = user["organization_id"]
    employee_groups = list(user.get("_groups", {})) if user["role"] == EMPLOYEE else None
    gr = await db.execute(select(Group).where(Group.organization_id == org_id))
    groups = gr.scalars().all()
    by_group = []
    for g in groups:
        if employee_groups is not None and g.id not in employee_groups:
            continue
        cc = await db.execute(select(func.count()).select_from(Candidate).where(Candidate.current_group_id == g.id))
        bc = await db.execute(select(func.count()).select_from(Candidate).where(
            Candidate.current_group_id == g.id, Candidate.status.in_(["BENCH", "ON_HOLD"])
        ))
        mc = await db.execute(select(func.count()).select_from(Candidate).where(
            Candidate.current_group_id == g.id, Candidate.status.in_(MARKETING_STATES)
        ))
        sc = await db.execute(select(func.count()).select_from(Submission).where(Submission.group_id == g.id))
        ic = await db.execute(select(func.count()).select_from(Interview).where(Interview.group_id == g.id))
        pc = await db.execute(select(func.count()).select_from(Placement).where(Placement.group_id == g.id))
        by_group.append({
            "group": g.name, "candidates": cc.scalar() or 0, "bench": bc.scalar() or 0,
            "marketing": mc.scalar() or 0, "submissions": sc.scalar() or 0,
            "interviews": ic.scalar() or 0, "placements": pc.scalar() or 0,
        })
    funnel = []
    for name, model in [("Submissions", Submission), ("Interviews", Interview), ("Offers", Offer), ("Placements", Placement)]:
        counts = select(func.count()).select_from(model).where(model.organization_id == org_id)
        if employee_groups is not None:
            counts = counts.where(model.group_id.in_(employee_groups))
        fc = await db.execute(counts)
        funnel.append({"stage": name, "count": fc.scalar() or 0})

    bench = await db.scalars(select(Candidate).where(
        *candidate_scope_filters(user), Candidate.status.in_(["BENCH", "ON_HOLD"]),
    ).order_by(Candidate.bench_since.asc().nulls_last(), Candidate.id).limit(50))
    group_names = {group.id: group.name for group in groups}
    today = datetime.now(timezone.utc).date()
    bench_aging = []
    for candidate in bench:
        try:
            since = datetime.fromisoformat(candidate.bench_since or "").date()
            days = max(0, (today - since).days)
        except ValueError:
            days = None
        bench_aging.append({
            "id": candidate.id, "first_name": candidate.first_name, "last_name": candidate.last_name,
            "primary_skill": candidate.primary_skill, "status": candidate.status,
            "group_name": group_names.get(candidate.current_group_id), "days_on_bench": days,
        })

    submissions = func.count()
    recruiter_name = func.coalesce(Submission.submitted_by_name, "Unknown")
    activity = select(recruiter_name, submissions).where(Submission.organization_id == org_id)
    if employee_groups is not None:
        activity = activity.where(Submission.group_id.in_(employee_groups))
    recruiters = await db.execute(activity.group_by(recruiter_name).order_by(submissions.desc(), recruiter_name))
    return {
        "by_group": by_group, "funnel": funnel, "bench_aging": bench_aging,
        "recruiter_activity": [{"name": name, "submissions": count} for name, count in recruiters],
    }


# ── Exports / Imports ──────────────────────────────────────────

@router.post("/exports/candidates")
async def export_candidates(body: dict = None, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require(user, ADMIN, OPERATIONS, AUDITOR)
    j = BackgroundJob(
        id=new_id(), organization_id=user["organization_id"], type="EXPORT_CANDIDATES",
        status="PENDING", payload=(body or {}).get("filters", {}),
        created_by=user["id"], created_by_name=user["name"],
    )
    db.add(j)
    await db.flush()
    await audit(db, user, "EXPORT_REQUESTED", "export", j.id, None, j.payload)
    return {"id": j.id, "type": j.type, "status": j.status}


@router.post("/imports/candidates")
async def import_candidates(file: UploadFile = File(...), user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require(user, ADMIN, OPERATIONS)
    text = (await file.read()).decode("utf-8-sig", errors="replace")
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        raise ValidationError("CSV is empty or missing header row")
    if not {"first_name", "last_name"} <= set(rows[0].keys()):
        raise ValidationError("CSV must include first_name and last_name columns")
    j = BackgroundJob(
        id=new_id(), organization_id=user["organization_id"], type="IMPORT_CANDIDATES",
        status="PENDING", payload={"rows": rows[:5000], "filename": file.filename},
        created_by=user["id"], created_by_name=user["name"],
    )
    db.add(j)
    await db.flush()
    await audit(db, user, "IMPORT_REQUESTED", "import", j.id, None, {"filename": file.filename, "rows": len(rows)})
    return {"id": j.id, "type": j.type, "status": j.status, "rows": len(rows)}


@router.get("/bg-jobs")
async def list_jobs(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    filters = [
        BackgroundJob.organization_id == user["organization_id"],
        BackgroundJob.type.in_(["EXPORT_CANDIDATES", "IMPORT_CANDIDATES"]),
    ]
    if not is_ops(user):
        filters.append(BackgroundJob.created_by == user["id"])
    r = await db.execute(select(BackgroundJob).where(*filters).order_by(BackgroundJob.created_at.desc()).limit(100))
    return [
        {"id": j.id, "type": j.type, "status": j.status,
         "created_by_name": j.created_by_name, "created_at": str(j.created_at),
         "finished_at": j.finished_at, "result": j.result, "error": j.error}
        for j in r.scalars().all()
    ]


@router.get("/bg-jobs/{jid}/download")
async def download_job(jid: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require(user, ADMIN, OPERATIONS, AUDITOR)
    r = await db.execute(select(BackgroundJob).where(
        BackgroundJob.id == jid, BackgroundJob.organization_id == user["organization_id"],
    ))
    j = r.scalar_one_or_none()
    if not j or j.status != "COMPLETED" or not j.result_csv:
        raise NotFoundError("Export not ready")
    await audit(db, user, "EXPORT_DOWNLOADED", "export", jid)
    return FileResponse(j.result_csv, media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="candidates-{jid[:8]}.csv"'})


# ── Platform Admin ─────────────────────────────────────────────

def require_platform(user: dict):
    if not user.get("is_platform_admin"):
        raise ForbiddenError("Platform administrator access required")


@router.get("/platform/organizations/slug-availability")
async def organization_slug_availability(slug: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require_platform(user)
    slug = slug.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,40}", slug):
        raise ValidationError("Use 2–41 lowercase letters, numbers, or hyphens, starting with a letter or number.")
    return {"available": await db.scalar(select(Organization.id).where(Organization.slug == slug)) is None}


def delivery_status(status: str | None) -> str | None:
    if status == "PENDING" and not get_settings().SMTP_HOST:
        return "NOT_CONFIGURED"
    return status


@router.post("/platform/organizations/{oid}/retry-invite")
async def retry_organization_invite(oid: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require_platform(user)
    message = await db.scalar(
        select(EmailOutbox).join(Invitation, Invitation.delivery_id == EmailOutbox.id)
        .where(Invitation.organization_id == oid, Invitation.status == "PENDING", Invitation.expires_at > utcnow())
        .order_by(Invitation.created_at.desc()).limit(1).with_for_update(of=EmailOutbox)
    )
    if not message:
        raise NotFoundError("No active email invitation to retry.")
    if message.status == "FAILED":
        message.status = "PENDING"
        message.attempts = 0
        await audit(db, user, "ORGANIZATION_INVITE_RETRIED", "organization", oid)
    return {"invite_status": delivery_status(message.status)}


@router.get("/platform/organizations")
async def list_orgs(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require_platform(user)
    r = await db.execute(select(Organization).order_by(Organization.created_at.desc()))
    orgs = r.scalars().all()
    out = []
    for o in orgs:
        uc = await db.execute(select(func.count()).select_from(User).where(User.organization_id == o.id))
        cc = await db.execute(select(func.count()).select_from(Candidate).where(Candidate.organization_id == o.id))
        admin_r = await db.execute(
            select(User).where(User.organization_id == o.id, User.role == ADMIN)
            .order_by(User.created_at).limit(1)
        )
        admin = admin_r.scalar_one_or_none()
        status = await db.scalar(
            select(EmailOutbox.status).join(Invitation, Invitation.delivery_id == EmailOutbox.id)
            .where(Invitation.organization_id == o.id, Invitation.status == "PENDING", Invitation.expires_at > utcnow())
            .order_by(Invitation.created_at.desc()).limit(1)
        )
        out.append({
            "id": o.id, "name": o.name, "slug": o.slug, "plan": o.plan,
            "industry": o.industry, "size": o.size, "logo_data": o.logo_data,
            "invite_status": delivery_status(status),
            "user_count": uc.scalar() or 0, "candidate_count": cc.scalar() or 0,
            "primary_admin": {"email": admin.email, "name": admin.name, "status": admin.status} if admin else None,
            "created_at": str(o.created_at),
        })
    return out


@router.post("/platform/organizations")
async def create_org(body: OrgIn, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require_platform(user)
    slug = body.slug.strip().lower()
    email = body.admin_email.strip().lower()
    if not body.name.strip() or not body.admin_name.strip():
        raise ValidationError("Organization name and admin name are required")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,40}", slug):
        raise ValidationError("Slug must be 2-41 chars: lowercase letters, numbers, hyphens")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise ValidationError("Invalid admin email")
    if body.plan not in ("Starter", "Professional", "Enterprise"):
        raise ValidationError("Invalid plan")
    if body.size and body.size not in {"1–10", "11–50", "51–200", "201+"}:
        raise ValidationError("Choose a valid organization size")
    if body.temporary_password is not None and (
        len(body.temporary_password) < 12 or len(body.temporary_password.encode()) > 72
    ):
        raise ValidationError("Temporary passwords must have at least 12 characters and fit within 72 bytes")
    if body.logo_data:
        header, separator, encoded = body.logo_data.partition(",")
        signatures = {"data:image/png;base64": b"\x89PNG\r\n\x1a\n", "data:image/jpeg;base64": b"\xff\xd8\xff"}
        try:
            logo = b64decode(encoded, validate=True)
        except (Base64Error, ValueError) as exc:
            raise ValidationError("Choose a PNG or JPEG logo up to 128 KB") from exc
        if not separator or header not in signatures or not logo.startswith(signatures[header]) or len(logo) > 131072:
            raise ValidationError("Choose a PNG or JPEG logo up to 128 KB")
    sr = await db.execute(select(Organization).where(Organization.slug == slug))
    if sr.scalar_one_or_none():
        raise ConflictError("An organization with this slug already exists")
    ur = await db.execute(select(User).where(User.email == email))
    if ur.scalar_one_or_none():
        raise ConflictError("A user with this email already exists")

    groups = dict.fromkeys(name.strip() for name in body.default_groups if name.strip())
    if any(len(name) > 255 for name in groups):
        raise ValidationError("Group names must be at most 255 characters")
    oid, uid = new_id(), new_id()
    token = secrets.token_urlsafe(32)
    db.add(Organization(id=oid, name=body.name.strip(), slug=slug, plan=body.plan, created_by=user["id"],
                        industry=(body.industry or "").strip() or None, size=body.size, logo_data=body.logo_data))
    try:
        await db.flush()
    except IntegrityError as exc:
        raise ConflictError("An organization with this slug already exists") from exc
    db.add(Settings(id=new_id(), organization_id=oid, **{k: v for k, v in DEFAULT_SETTINGS.items() if k != "mfa_required_for_admin"}))
    for g in groups:
        db.add(Group(id=new_id(), organization_id=oid, name=g, description="", active=True))
    db.add(User(id=uid, organization_id=oid, email=email, name=body.admin_name.strip(),
                role=ADMIN, status="INVITED", auth_methods=[], mfa_enabled=False, session_version=0))
    try:
        await db.flush()
    except IntegrityError as exc:
        raise ConflictError("A user with this email already exists") from exc
    delivery_id = new_id() if body.temporary_password is None else None
    if delivery_id:
        db.add(EmailOutbox(
            id=delivery_id, organization_id=oid, to=email,
            subject=f"Your BenchOS workspace for {body.name.strip()} is ready",
            body=f"Activate your administrator account: {get_settings().FRONTEND_URL.rstrip('/')}/activate?token={token}",
            status="PENDING", attempts=0,
        ))
        await db.flush()
    db.add(Invitation(
        id=new_id(), organization_id=oid, user_id=uid, email=email, name=body.admin_name.strip(),
        role=ADMIN, token=token, status="PENDING", invited_by=user["id"], invited_by_name=user["name"],
        expires_at=(datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        delivery_id=delivery_id,
        temporary_password_hash=hash_password(body.temporary_password) if body.temporary_password else None,
    ))
    await db.flush()
    await audit(db, user, "ORGANIZATION_CREATED", "organization", oid, None,
                {"name": body.name, "slug": slug, "admin_email": email})
    return {"id": oid, "name": body.name.strip(), "slug": slug, "admin_email": email,
            "activation_path": f"/activate?token={token}",
            "invite_status": delivery_status("PENDING") if delivery_id else None}


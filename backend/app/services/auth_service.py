"""Authentication dependencies, Supabase Auth adapter, and helpers for FastAPI."""
import re
import uuid
import hashlib
import secrets
import logging
from base64 import b64encode
from datetime import datetime, timezone, timedelta
from typing import Optional

import bcrypt
import httpx
import jwt
import pyotp
import qrcode
from qrcode.image.svg import SvgPathFillImage
from fastapi import Depends, Request, Response
from sqlalchemy import select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.constants import ADMIN, OPERATIONS, EMPLOYEE, AUDITOR
from app.exceptions import UnauthorizedError, ForbiddenError, TooManyRequestsError, ValidationError
from app.models.user import User, LoginAttempt, PasswordResetToken, Invitation
from app.models.group import Membership
from app.models.audit import Notification, EmailOutbox, AuditLog, TimelineEvent

logger = logging.getLogger("benchos.auth")


# ── Utility Functions ──────────────────────────────────────────

def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


def hash_password(p: str) -> str:
    return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()


def verify_password(p: str, h: str) -> bool:
    return bool(h) and bcrypt.checkpw(p.encode(), h.encode())


# ── Auth Adapter (Native JWT + Supabase Auth) ───────────────────

class AuthAdapter:
    """Authentication adapter supporting native JWT and Supabase Auth delegation."""

    @staticmethod
    def is_supabase_enabled() -> bool:
        settings = get_settings()
        return bool(settings.SUPABASE_URL and settings.SUPABASE_KEY)

    @staticmethod
    async def verify_supabase_token(token: str) -> dict:
        """Verify token against Supabase Auth service."""
        settings = get_settings()
        url = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/user"
        headers = {
            "apikey": settings.SUPABASE_KEY,
            "Authorization": f"Bearer {token}",
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    return {
                        "sub": data.get("id"),
                        "email": data.get("email"),
                        "type": "access",
                        "adapter": "supabase",
                    }
                raise UnauthorizedError("Invalid Supabase token")
        except httpx.HTTPError:
            raise UnauthorizedError("Supabase Auth service unreachable")

    @staticmethod
    def encode_native_token(user_id: str, kind: str, minutes: int, extra: dict | None = None) -> str:
        settings = get_settings()
        payload = {
            "sub": user_id,
            "type": kind,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=minutes),
        }
        payload.update(extra or {})
        return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

    @staticmethod
    def decode_native_token(token: str, kind: str) -> dict:
        settings = get_settings()
        try:
            payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        except jwt.ExpiredSignatureError:
            raise UnauthorizedError("Token expired")
        except jwt.InvalidTokenError:
            raise UnauthorizedError("Invalid token")
        if payload.get("type") != kind:
            raise UnauthorizedError("Invalid token type")
        return payload


def make_token(user_id: str, kind: str, minutes: int, extra: dict | None = None) -> str:
    return AuthAdapter.encode_native_token(user_id, kind, minutes, extra)


def decode_token(token: str, kind: str) -> dict:
    return AuthAdapter.decode_native_token(token, kind)


def token_hash(t: str) -> str:
    return hashlib.sha256(t.encode()).hexdigest()


def set_cookies(resp: Response, access: str, refresh: str):
    resp.set_cookie("access_token", access, httponly=True, secure=True, samesite="none", max_age=3600, path="/")
    resp.set_cookie("refresh_token", refresh, httponly=True, secure=True, samesite="none", max_age=604800, path="/")


# ── User dict helpers ──────────────────────────────────────────

def public_user(u: dict) -> dict:
    """Strip sensitive fields from user dict."""
    return {k: v for k, v in u.items() if k not in ("password_hash", "mfa_secret", "pending_mfa_secret")}


def user_to_dict(u: User) -> dict:
    """Convert SQLAlchemy User to dict."""
    return {
        "id": u.id, "organization_id": u.organization_id, "email": u.email,
        "name": u.name, "role": u.role, "status": u.status,
        "mfa_enabled": u.mfa_enabled, "session_version": u.session_version,
        "picture": u.picture, "is_platform_admin": u.is_platform_admin,
        "can_view_ops_only": u.can_view_ops_only, "auth_methods": u.auth_methods or [],
        "last_login_at": str(u.last_login_at) if u.last_login_at else None,
        "created_at": str(u.created_at) if u.created_at else None,
    }


# ── Group loading ──────────────────────────────────────────────

async def load_groups(db: AsyncSession, user_id: str) -> dict[str, str]:
    """Load active group memberships for a user. Returns {group_id: role}."""
    result = await db.execute(
        select(Membership.group_id, Membership.role).where(
            Membership.user_id == user_id, Membership.active == True
        )
    )
    return {row.group_id: row.role for row in result.all()}


# ── Auth dependency ────────────────────────────────────────────

async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    """FastAPI dependency: resolves current authenticated user from token (Native or Supabase)."""
    token = request.cookies.get("access_token")
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
    if not token:
        raise UnauthorizedError("Authentication required")

    # If Supabase is enabled, attempt Supabase verification first, fallback to native JWT
    payload = None
    if AuthAdapter.is_supabase_enabled():
        try:
            payload = await AuthAdapter.verify_supabase_token(token)
        except Exception:
            payload = None

    if not payload:
        payload = decode_token(token, "access")

    # Look up user in PostgreSQL
    if payload.get("adapter") == "supabase" and payload.get("email"):
        result = await db.execute(select(User).where(User.email == payload["email"].lower()))
    else:
        result = await db.execute(select(User).where(User.id == payload["sub"]))

    user = result.scalar_one_or_none()

    if not user or user.status != "ACTIVE":
        raise UnauthorizedError("User inactive or not found")
    if payload.get("adapter") != "supabase" and payload.get("sv", 0) != (user.session_version or 0):
        raise UnauthorizedError("Session revoked")

    user_dict = user_to_dict(user)
    user_dict["_groups"] = await load_groups(db, user.id) if user.role == EMPLOYEE else {}
    return public_user(user_dict) | {"_groups": user_dict["_groups"]}


# ── Authorization helpers ──────────────────────────────────────

def is_ops(user: dict) -> bool:
    return user["role"] in (ADMIN, OPERATIONS)


def require(user: dict, *roles: str):
    if user["role"] not in roles:
        raise ForbiddenError("Access restricted")


def require_writer(user: dict):
    if user["role"] == AUDITOR:
        raise ForbiddenError("Auditors have read-only access")


# ── Rate checking ──────────────────────────────────────────────

def can_see_bill(user: dict, group_id: str | None) -> bool:
    return is_ops(user) or user.get("_groups", {}).get(group_id) in ("LEAD", "MARKETING")


# ── Audit / Timeline / Notification helpers ────────────────────

async def audit(
    db: AsyncSession, user: dict, action: str, entity_type: str, entity_id: str,
    before: dict | None = None, after: dict | None = None,
    reason: str | None = None, candidate_id: str | None = None,
):
    entry = AuditLog(
        id=new_id(),
        organization_id=user["organization_id"],
        actor_id=user["id"],
        actor_name=user.get("name"),
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        candidate_id=candidate_id or (after or {}).get("candidate_id") or (before or {}).get("candidate_id"),
        before=before,
        after=after,
        reason=reason,
    )
    db.add(entry)
    await db.flush()


async def timeline(
    db: AsyncSession, user: dict, candidate_id: str, event: str,
    detail: str, meta: dict | None = None,
):
    entry = TimelineEvent(
        id=new_id(),
        organization_id=user["organization_id"],
        candidate_id=candidate_id,
        event=event,
        detail=detail,
        meta=meta or {},
        actor_id=user["id"],
        actor_name=user.get("name"),
    )
    db.add(entry)
    await db.flush()


async def notify(
    db: AsyncSession, org_id: str, user_ids: list[str],
    title: str, body: str, link: str | None = None,
):
    result = await db.execute(
        select(User.id, User.email).where(
            User.id.in_(list(set(user_ids))), User.status == "ACTIVE"
        )
    )
    for row in result.all():
        db.add(Notification(
            id=new_id(), organization_id=org_id, user_id=row.id,
            title=title, body=body, link=link, read=False,
        ))
        db.add(EmailOutbox(
            id=new_id(), organization_id=org_id, to=row.email,
            subject=title, body=body, status="PENDING", attempts=0,
        ))
    await db.flush()


async def ops_and_lead_ids(db: AsyncSession, org_id: str, group_id: str | None = None) -> list[str]:
    result = await db.execute(
        select(User.id).where(
            User.organization_id == org_id,
            User.role.in_([ADMIN, OPERATIONS]),
            User.status == "ACTIVE",
        )
    )
    ids = [row.id for row in result.all()]
    if group_id:
        result2 = await db.execute(
            select(Membership.user_id).where(
                Membership.group_id == group_id,
                Membership.role == "LEAD",
                Membership.active == True,
            )
        )
        ids += [row.user_id for row in result2.all()]
    return ids


# ── Login rate limiter ─────────────────────────────────────────

async def check_lock(db: AsyncSession, identifier: str):
    result = await db.execute(
        select(LoginAttempt).where(LoginAttempt.identifier == identifier)
    )
    rec = result.scalar_one_or_none()
    if rec and rec.count >= 5:
        if rec.last:
            locked = datetime.fromisoformat(rec.last) + timedelta(minutes=15)
            if locked > datetime.now(timezone.utc):
                raise TooManyRequestsError("Too many failed attempts. Try again in 15 minutes.")
        await db.execute(delete(LoginAttempt).where(LoginAttempt.identifier == identifier))
        await db.flush()


async def record_attempt(db: AsyncSession, identifier: str):
    result = await db.execute(
        select(LoginAttempt).where(LoginAttempt.identifier == identifier)
    )
    rec = result.scalar_one_or_none()
    if rec:
        rec.count = (rec.count or 0) + 1
        rec.last = utcnow()
    else:
        db.add(LoginAttempt(id=new_id(), identifier=identifier, count=1, last=utcnow()))
    await db.flush()


async def clear_attempts(db: AsyncSession, identifier: str):
    await db.execute(delete(LoginAttempt).where(LoginAttempt.identifier == identifier))
    await db.flush()


# ── Session issuance ───────────────────────────────────────────

async def issue_session(db: AsyncSession, user_dict: dict, resp: Response) -> dict:
    sv = user_dict.get("session_version", 0)
    access = make_token(user_dict["id"], "access", 60, {"sv": sv})
    refresh = make_token(user_dict["id"], "refresh", 60 * 24 * 7, {"sv": sv})
    set_cookies(resp, access, refresh)
    await db.execute(
        update(User).where(User.id == user_dict["id"]).values(last_login_at=datetime.now(timezone.utc))
    )
    await db.flush()
    return {"user": public_user(user_dict), "access_token": access, "refresh_token": refresh}


async def mfa_gate(db: AsyncSession, user_dict: dict, user_obj: User, resp: Response) -> dict:
    if user_dict["role"] != ADMIN:
        return await issue_session(db, user_dict, resp)
    mfa_token = make_token(user_dict["id"], "mfa", 10, {"sv": user_obj.session_version})
    if user_obj.mfa_enabled:
        return {"mfa_required": True, "mfa_token": mfa_token}
    secret = pyotp.random_base32()
    user_obj.pending_mfa_secret = secret
    await db.flush()
    uri = pyotp.TOTP(secret).provisioning_uri(name=user_dict["email"], issuer_name="BenchOS")
    qr = qrcode.make(uri, image_factory=SvgPathFillImage).to_string()
    return {
        "mfa_setup_required": True, "mfa_token": mfa_token, "secret": secret, "otpauth_uri": uri,
        "qr_image": "data:image/svg+xml;base64," + b64encode(qr).decode("ascii"),
    }

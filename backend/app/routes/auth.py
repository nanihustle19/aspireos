"""Authentication routes — /api/auth"""
import secrets
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode, urlsplit

import httpx
import pyotp
from fastapi import APIRouter, Depends, Response, Request, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import case, select, update, delete, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.constants import ADMIN
from app.exceptions import UnauthorizedError, ForbiddenError, ValidationError
from app.models.audit import EmailOutbox
from app.models.user import User, Invitation, LoginAttempt, PasswordResetToken
from app.models.organization import Organization
from app.models.group import Group, Membership
from app.services.auth_service import (
    utcnow, new_id, hash_password, verify_password, make_token, decode_token,
    token_hash, public_user, user_to_dict, load_groups, get_current_user,
    check_lock, record_attempt, clear_attempts, set_cookies,
    issue_session, mfa_gate, audit, notify,
)

router = APIRouter(prefix="/api/auth")


# ── Request schemas ────────────────────────────────────────────

class LoginIn(BaseModel):
    email: str
    password: str

class MfaIn(BaseModel):
    mfa_token: str
    code: str

class ActivateIn(BaseModel):
    token: str
    password: str
    name: str | None = None
    temporary_password: str | None = None

class ForgotIn(BaseModel):
    email: str

class ResetTokenIn(BaseModel):
    token: str

class ResetIn(ResetTokenIn):
    password: str

class GoogleIn(BaseModel):
    session_id: str | None = None
    credential: str | None = None
    access_token: str | None = None


# ── Routes ─────────────────────────────────────────────────────

async def requires_temporary_password(db: AsyncSession, user_id: str) -> bool:
    return bool(await db.scalar(select(Invitation.id).where(
        Invitation.user_id == user_id, Invitation.status == "PENDING",
        Invitation.temporary_password_hash.is_not(None),
    ).limit(1)))

@router.post("/login")
async def login(body: LoginIn, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    email = body.email.strip().lower()
    ident = f"{request.client.host if request.client else 'x'}:{email}"
    await check_lock(db, ident)

    result = await db.execute(select(User).where(User.email == email).with_for_update())
    user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.password_hash or ""):
        await record_attempt(db, ident)
        await db.commit()
        raise UnauthorizedError("Invalid email or password")
    if user.status != "ACTIVE":
        raise ForbiddenError("Account is not active")

    await clear_attempts(db, ident)
    user_dict = user_to_dict(user)
    return await mfa_gate(db, user_dict, user, response)


@router.post("/mfa/verify")
async def mfa_verify(body: MfaIn, response: Response, db: AsyncSession = Depends(get_db)):
    p = decode_token(body.mfa_token, "mfa")
    result = await db.execute(select(User).where(User.id == p["sub"]).with_for_update())
    user = result.scalar_one_or_none()
    if not user or user.status != "ACTIVE" or user.role != ADMIN or p.get("sv") != user.session_version:
        raise UnauthorizedError("Sign-in challenge expired. Sign in again.")

    ident = f"mfa:{user.id}"
    await check_lock(db, ident)

    secret = user.mfa_secret if user.mfa_enabled else user.pending_mfa_secret
    if not secret or not pyotp.TOTP(secret).verify(body.code.strip(), valid_window=1):
        await record_attempt(db, ident)
        await db.commit()
        raise UnauthorizedError("Invalid authenticator code")

    await clear_attempts(db, ident)

    if not user.mfa_enabled:
        user.mfa_enabled = True
        user.mfa_secret = secret
        user.pending_mfa_secret = None
        await db.flush()
        user_dict = user_to_dict(user)
        await audit(db, user_dict, "MFA_ENROLLED", "user", user.id)

    user_dict = user_to_dict(user)
    return await issue_session(db, user_dict, response)


# ── Google OAuth & Session ─────────────────────────────────────

@router.get("/google/redirect")
async def google_redirect(redirect_url: str = Query(default="")):
    settings = get_settings()
    frontend = redirect_url or f"{settings.FRONTEND_URL}/dashboard"

    if not settings.GOOGLE_CLIENT_ID:
        # If Google client ID is not configured, inform the user via redirect
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/login?error=" + urlencode({"msg": "Google OAuth is not configured on this server."})
        )

    scope = "openid email profile"
    callback_uri = f"{settings.FRONTEND_URL}/api/auth/google/callback"
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": callback_uri,
        "response_type": "code",
        "scope": scope,
        "state": frontend,
        "access_type": "offline",
        "prompt": "consent",
    }
    google_auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    return RedirectResponse(url=google_auth_url)


@router.get("/google/callback")
async def google_callback(
    code: str = Query(...), state: str = Query(default=""),
    response: Response = None, db: AsyncSession = Depends(get_db),
):
    settings = get_settings()
    token_url = "https://oauth2.googleapis.com/token"
    callback_uri = f"{settings.FRONTEND_URL}/api/auth/google/callback"

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            token_resp = await client.post(token_url, data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": callback_uri,
                "grant_type": "authorization_code",
            })
            token_data = token_resp.json()
            access_tok = token_data.get("access_token")

            userinfo_resp = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_tok}"},
            )
            profile = userinfo_resp.json()
    except Exception:
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/login?error=Google+auth+failed")

    email = (profile.get("email") or "").lower()
    if not email:
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/login?error=No+email+returned+from+Google")

    result = await db.execute(select(User).where(User.email == email).with_for_update())
    user = result.scalar_one_or_none()
    if not user:
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/login?error=Invitation+required+for+access")

    if user.status == "INVITED":
        if await requires_temporary_password(db, user.id):
            return RedirectResponse(url=f"{settings.FRONTEND_URL}/login?error=Use+your+activation+link")
        user.status = "ACTIVE"
        user.picture = profile.get("picture")
        user.activated_at = datetime.now(timezone.utc)
        if "google" not in (user.auth_methods or []):
            user.auth_methods = (user.auth_methods or []) + ["google"]
        await db.flush()

        await db.execute(
            update(Invitation).where(
                Invitation.user_id == user.id, Invitation.status == "PENDING"
            ).values(status="ACCEPTED", accepted_at=utcnow())
        )
        await db.flush()
        await audit(db, user_to_dict(user), "USER_ACTIVATED_GOOGLE", "user", user.id)

    if user.status != "ACTIVE":
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/login?error=Account+deactivated")

    # The frontend exchanges this short-lived proof through the normal MFA gate.
    target = f"{settings.FRONTEND_URL.rstrip('/')}/dashboard"
    allowed = urlsplit(settings.FRONTEND_URL)
    requested = urlsplit(state)
    if (requested.scheme, requested.netloc, requested.path) == (allowed.scheme, allowed.netloc, "/dashboard"):
        target = requested._replace(query="", fragment="").geturl()
    proof = make_token(user.id, "google-callback", 1, {"sv": user.session_version})
    return RedirectResponse(url=f"{target}#session_id={proof}")


@router.post("/google/session")
async def google_session(body: GoogleIn, response: Response, db: AsyncSession = Depends(get_db)):
    """Verifies a Google OAuth token or Supabase Auth session token."""
    email = None
    picture = None
    session_claims = None

    token = body.credential or body.access_token
    if token:
        # Verify via Google TokenInfo API
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(f"https://oauth2.googleapis.com/tokeninfo?id_token={token}")
                if r.status_code == 200:
                    info = r.json()
                    email = info.get("email")
                    picture = info.get("picture")
        except httpx.HTTPError:
            pass

    if not email and body.session_id:
        try:
            try:
                p = decode_token(body.session_id, "google-callback")
            except UnauthorizedError:
                p = decode_token(body.session_id, "access")
            u = await db.get(User, p["sub"])
            if u and u.status == "ACTIVE" and p.get("sv", 0) == u.session_version:
                email = u.email
                session_claims = p
        except (UnauthorizedError, KeyError):
            pass

    if not email:
        raise UnauthorizedError("Google authentication could not be verified")

    email = email.lower()
    result = await db.execute(select(User).where(User.email == email).with_for_update().execution_options(populate_existing=True))
    user = result.scalar_one_or_none()

    if not user:
        raise ForbiddenError("Access is invitation-only. Ask your administrator for an invite.")
    if session_claims and (
        user.id != session_claims["sub"] or user.status != "ACTIVE"
        or user.session_version != session_claims.get("sv", 0)
    ):
        raise UnauthorizedError("Sign-in expired. Try again.")

    if user.status == "INVITED":
        if await requires_temporary_password(db, user.id):
            raise ForbiddenError("Use your activation link and temporary password to continue.")
        user.status = "ACTIVE"
        user.picture = picture or user.picture
        user.activated_at = datetime.now(timezone.utc)
        if "google" not in (user.auth_methods or []):
            user.auth_methods = (user.auth_methods or []) + ["google"]
        await db.flush()
        await db.execute(
            update(Invitation).where(
                Invitation.user_id == user.id, Invitation.status == "PENDING"
            ).values(status="ACCEPTED", accepted_at=utcnow())
        )
        await db.flush()
        await audit(db, user_to_dict(user), "USER_ACTIVATED_GOOGLE", "user", user.id)

    if user.status != "ACTIVE":
        raise ForbiddenError("Account is deactivated")

    user_dict = user_to_dict(user)
    return await mfa_gate(db, user_dict, user, response)


@router.get("/invitations/{token}")
async def invitation_info(token: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Invitation).where(Invitation.token == token, Invitation.status == "PENDING")
    )
    inv = result.scalar_one_or_none()
    if not inv or inv.expires_at < utcnow():
        raise ValidationError("Invitation is invalid or expired")

    org_result = await db.execute(select(Organization).where(Organization.id == inv.organization_id))
    org = org_result.scalar_one_or_none()
    return {"email": inv.email, "name": inv.name, "role": inv.role, "organization": org.name if org else None,
            "temporary_password_required": bool(inv.temporary_password_hash)}


@router.post("/activate")
async def activate(body: ActivateIn, response: Response, db: AsyncSession = Depends(get_db)):
    user_id = await db.scalar(select(Invitation.user_id).where(Invitation.token == body.token))
    user = await db.scalar(select(User).where(User.id == user_id).with_for_update())
    if not user or user.status != "INVITED":
        raise ValidationError("Invitation is invalid or expired")
    result = await db.execute(
        select(Invitation).where(Invitation.token == body.token, Invitation.status == "PENDING").with_for_update()
    )
    inv = result.scalar_one_or_none()
    if not inv or inv.expires_at < utcnow():
        raise ValidationError("Invitation is invalid or expired")
    if len(body.password) < 8 or len(body.password.encode()) > 72:
        raise ValidationError("Password must be at least 8 characters and at most 72 bytes")
    if inv.temporary_password_hash:
        identifier = f"activation:{inv.id}"
        await check_lock(db, identifier)
        temporary = body.temporary_password or ""
        if len(temporary.encode()) > 72 or not verify_password(temporary, inv.temporary_password_hash):
            await record_attempt(db, identifier)
            await db.commit()
            raise ValidationError("The temporary password is incorrect. Check it with the person who invited you.")
        if temporary == body.password:
            raise ValidationError("Choose a password different from your temporary password.")
        await clear_attempts(db, identifier)
        inv.temporary_password_hash = None

    user.status = "ACTIVE"
    user.password_hash = hash_password(body.password)
    user.activated_at = datetime.now(timezone.utc)
    if body.name:
        user.name = body.name
    if "password" not in (user.auth_methods or []):
        user.auth_methods = (user.auth_methods or []) + ["password"]

    inv.status = "ACCEPTED"
    inv.accepted_at = utcnow()
    await db.flush()

    user_dict = user_to_dict(user)
    await audit(db, user_dict, "USER_ACTIVATED_PASSWORD", "user", user.id)
    return await mfa_gate(db, user_dict, user, response)


@router.post("/refresh")
async def refresh(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    token = request.cookies.get("refresh_token") or request.headers.get("X-Refresh-Token")
    if not token:
        raise UnauthorizedError("No refresh token")

    p = decode_token(token, "refresh")
    result = await db.execute(select(User).where(User.id == p["sub"]))
    user = result.scalar_one_or_none()

    if not user or user.status != "ACTIVE" or p.get("sv", 0) != (user.session_version or 0):
        raise UnauthorizedError("Session revoked")

    return await issue_session(db, user_to_dict(user), response)


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/", samesite="none", secure=True)
    response.delete_cookie("refresh_token", path="/", samesite="none", secure=True)
    return {"ok": True}


@router.post("/logout-all")
async def logout_all(response: Response, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await db.execute(
        update(User).where(User.id == user["id"]).values(
            session_version=User.session_version + 1
        )
    )
    await db.flush()
    await logout(response)
    return {"ok": True}


@router.get("/me")
async def me(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    org_result = await db.execute(select(Organization).where(Organization.id == user["organization_id"]))
    org = org_result.scalar_one_or_none()

    groups = []
    if user.get("_groups"):
        result = await db.execute(
            select(Group).where(Group.id.in_(list(user["_groups"].keys())))
        )
        for g in result.scalars().all():
            groups.append({"id": g.id, "name": g.name, "role": user["_groups"][g.id]})

    u = {k: v for k, v in user.items() if k != "_groups"}
    return {
        "user": u,
        "organization": {"id": org.id, "name": org.name, "slug": org.slug, "plan": org.plan} if org else None,
        "groups": groups,
    }


# ── Password reset ─────────────────────────────────────────────

@router.post("/forgot-password")
async def forgot_password(body: ForgotIn, request: Request, db: AsyncSession = Depends(get_db)):
    settings = get_settings()
    email = body.email.strip().lower()
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(minutes=1)).isoformat()
    address = request.client.host if request.client else "unknown"
    # Apply the same limits before looking up known and unknown addresses.
    for identifier, limit in ((f"reset:ip:{address}", 15), (f"reset:email:{token_hash(email)}", 1)):
        expired = LoginAttempt.last < cutoff
        allowed = await db.scalar(
            insert(LoginAttempt).values(identifier=identifier, count=1, last=now.isoformat())
            .on_conflict_do_update(
                index_elements=[LoginAttempt.identifier],
                set_={"count": case((expired, 1), else_=LoginAttempt.count + 1),
                      "last": case((expired, now.isoformat()), else_=LoginAttempt.last)},
                where=expired | (LoginAttempt.count < limit),
            ).returning(LoginAttempt.id)
        )
        if not allowed:
            return {"ok": True}
    result = await db.execute(select(User).where(User.email == email, User.status == "ACTIVE").with_for_update())
    user = result.scalar_one_or_none()
    # Always return 200 to prevent user enumeration
    if not user:
        return {"ok": True}

    raw = secrets.token_urlsafe(32)
    th = token_hash(raw)
    exp = datetime.now(timezone.utc) + timedelta(hours=1)
    db.add(PasswordResetToken(
        id=new_id(), user_id=user.id, token_hash=th,
        used=False, expires_at=exp,
    ))
    link = f"{settings.FRONTEND_URL}/reset-password?token={raw}"
    db.add(EmailOutbox(
        id=new_id(), organization_id=user.organization_id, to=user.email,
        subject="Reset your AspireOs password",
        body=f"Click the link to reset your password within 1 hour: {link}",
        status="PENDING", attempts=0,
    ))
    await db.flush()
    return {"ok": True}


async def valid_reset(db: AsyncSession, token: str) -> PasswordResetToken:
    result = await db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == token_hash(token),
            PasswordResetToken.used == False,
        )
    )
    rec = result.scalar_one_or_none()
    if not rec:
        raise ValidationError("Reset link is invalid or already used")
    exp = rec.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < datetime.now(timezone.utc):
        raise ValidationError("Reset link has expired")
    return rec


@router.get("/reset-password/{token}")
async def check_reset(token: str, db: AsyncSession = Depends(get_db)):
    rec = await valid_reset(db, token)
    result = await db.execute(select(User.email).where(User.id == rec.user_id))
    row = result.one_or_none()
    return {"email": row.email if row else None}


@router.post("/reset-password/check")
async def check_reset_body(body: ResetTokenIn, db: AsyncSession = Depends(get_db)):
    return await check_reset(body.token, db)


@router.post("/reset-password")
async def reset_password(body: ResetIn, db: AsyncSession = Depends(get_db)):
    rec = await valid_reset(db, body.token)
    if len(body.password) < 8 or len(body.password.encode()) > 72:
        raise ValidationError("Password must be at least 8 characters and at most 72 bytes")

    result = await db.execute(
        select(User).where(User.id == rec.user_id, User.status == "ACTIVE").with_for_update()
    )
    user = result.scalar_one_or_none()
    if not user:
        raise ForbiddenError("Account is not active")

    await valid_reset(db, body.token)
    await db.execute(
        update(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id, PasswordResetToken.used == False,
        ).values(used=True, used_at=datetime.now(timezone.utc))
    )
    user.pending_mfa_secret = None
    user.password_hash = hash_password(body.password)
    user.session_version = (user.session_version or 0) + 1
    if "password" not in (user.auth_methods or []):
        user.auth_methods = (user.auth_methods or []) + ["password"]

    # Clear login attempts for this email
    await db.execute(
        delete(LoginAttempt).where(func.right(LoginAttempt.identifier, len(user.email) + 1) == f":{user.email}")
    )
    await db.flush()

    user_dict = user_to_dict(user)
    await audit(db, user_dict, "PASSWORD_RESET_COMPLETED", "user", user.id)
    return {"ok": True}

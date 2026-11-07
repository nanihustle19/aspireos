from datetime import datetime, timezone, timedelta

import hashlib
import os
import re
import secrets

import httpx
import pyotp
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from core import (db, ADMIN, now, new_id, hash_password, verify_password, make_token, decode_token,
                  public_user, get_current_user, load_groups, audit)

router = APIRouter(prefix="/api/auth")
EMERGENT_SESSION_URL = "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data"


class LoginIn(BaseModel):
    email: str
    password: str


class MfaIn(BaseModel):
    mfa_token: str
    code: str


class ActivateIn(BaseModel):
    token: str
    password: str
    name: str = None


class ForgotIn(BaseModel):
    email: str


class ResetIn(BaseModel):
    token: str
    password: str


class GoogleIn(BaseModel):
    session_id: str


def set_cookies(resp: Response, access: str, refresh: str):
    resp.set_cookie("access_token", access, httponly=True, secure=True, samesite="none", max_age=3600, path="/")
    resp.set_cookie("refresh_token", refresh, httponly=True, secure=True, samesite="none", max_age=604800, path="/")


async def issue_session(user: dict, resp: Response) -> dict:
    sv = user.get("session_version", 0)
    access = make_token(user["id"], "access", 60, {"sv": sv})
    refresh = make_token(user["id"], "refresh", 60 * 24 * 7, {"sv": sv})
    set_cookies(resp, access, refresh)
    await db.users.update_one({"id": user["id"]}, {"$set": {"last_login_at": now()}})
    return {"user": public_user(user), "access_token": access, "refresh_token": refresh}


async def mfa_gate(user: dict, resp: Response) -> dict:
    if user["role"] != ADMIN:
        return await issue_session(user, resp)
    mfa_token = make_token(user["id"], "mfa", 10)
    if user.get("mfa_enabled"):
        return {"mfa_required": True, "mfa_token": mfa_token}
    secret = pyotp.random_base32()
    await db.users.update_one({"id": user["id"]}, {"$set": {"pending_mfa_secret": secret}})
    uri = pyotp.TOTP(secret).provisioning_uri(name=user["email"], issuer_name="BenchOS")
    return {"mfa_setup_required": True, "mfa_token": mfa_token, "secret": secret, "otpauth_uri": uri}


async def check_lock(identifier: str):
    rec = await db.login_attempts.find_one({"identifier": identifier})
    if rec and rec.get("count", 0) >= 5:
        locked = datetime.fromisoformat(rec["last"]) + timedelta(minutes=15)
        if locked > datetime.now(timezone.utc):
            raise HTTPException(429, "Too many failed attempts. Try again in 15 minutes.")
        await db.login_attempts.delete_one({"identifier": identifier})


@router.post("/login")
async def login(body: LoginIn, request: Request, response: Response):
    email = body.email.strip().lower()
    ident = f"{request.client.host if request.client else 'x'}:{email}"
    await check_lock(ident)
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if not user or not verify_password(body.password, user.get("password_hash")):
        await db.login_attempts.update_one({"identifier": ident}, {"$inc": {"count": 1}, "$set": {"last": now()}}, upsert=True)
        raise HTTPException(401, "Invalid email or password")
    if user["status"] != "ACTIVE":
        raise HTTPException(403, "Account is not active")
    await db.login_attempts.delete_one({"identifier": ident})
    return await mfa_gate(user, response)


@router.post("/mfa/verify")
async def mfa_verify(body: MfaIn, response: Response):
    p = decode_token(body.mfa_token, "mfa")
    user = await db.users.find_one({"id": p["sub"]}, {"_id": 0})
    if not user:
        raise HTTPException(401, "User not found")
    ident = f"mfa:{user['id']}"
    await check_lock(ident)
    secret = user.get("mfa_secret") if user.get("mfa_enabled") else user.get("pending_mfa_secret")
    if not secret or not pyotp.TOTP(secret).verify(body.code.strip(), valid_window=1):
        await db.login_attempts.update_one({"identifier": ident}, {"$inc": {"count": 1}, "$set": {"last": now()}}, upsert=True)
        raise HTTPException(401, "Invalid authenticator code")
    await db.login_attempts.delete_one({"identifier": ident})
    if not user.get("mfa_enabled"):
        await db.users.update_one({"id": user["id"]}, {"$set": {"mfa_enabled": True, "mfa_secret": secret}, "$unset": {"pending_mfa_secret": ""}})
        await audit(user, "MFA_ENROLLED", "user", user["id"])
    return await issue_session(user, response)


@router.post("/google/session")
async def google_session(body: GoogleIn, response: Response):
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(EMERGENT_SESSION_URL, headers={"X-Session-ID": body.session_id})
    except httpx.HTTPError:
        raise HTTPException(502, "Google sign-in service unavailable. Try again.")
    data = r.json() if r.status_code == 200 else {}
    if not data.get("email"):
        raise HTTPException(401, "Google session could not be verified")
    email = data["email"].lower()
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if not user:
        raise HTTPException(403, "Access is invitation-only. Ask your administrator for an invite.")
    if user["status"] == "INVITED":
        await db.users.update_one({"id": user["id"]}, {"$set": {"status": "ACTIVE", "picture": data.get("picture"), "activated_at": now()}, "$addToSet": {"auth_methods": "google"}})
        await db.invitations.update_many({"user_id": user["id"], "status": "PENDING"}, {"$set": {"status": "ACCEPTED", "accepted_at": now()}})
        await audit(user, "USER_ACTIVATED_GOOGLE", "user", user["id"])
        user = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    if user["status"] != "ACTIVE":
        raise HTTPException(403, "Account is deactivated")
    return await mfa_gate(user, response)


@router.get("/invitations/{token}")
async def invitation_info(token: str):
    inv = await db.invitations.find_one({"token": token, "status": "PENDING"}, {"_id": 0})
    if not inv or inv["expires_at"] < now():
        raise HTTPException(404, "Invitation is invalid or expired")
    org = await db.organizations.find_one({"id": inv["organization_id"]}, {"_id": 0})
    return {"email": inv["email"], "name": inv.get("name"), "role": inv["role"], "organization": org["name"]}


@router.post("/activate")
async def activate(body: ActivateIn, response: Response):
    inv = await db.invitations.find_one({"token": body.token, "status": "PENDING"}, {"_id": 0})
    if not inv or inv["expires_at"] < now():
        raise HTTPException(404, "Invitation is invalid or expired")
    if len(body.password) < 8:
        raise HTTPException(422, "Password must be at least 8 characters")
    upd = {"status": "ACTIVE", "password_hash": hash_password(body.password), "activated_at": now()}
    if body.name:
        upd["name"] = body.name
    await db.users.update_one({"id": inv["user_id"]}, {"$set": upd, "$addToSet": {"auth_methods": "password"}})
    await db.invitations.update_one({"id": inv["id"]}, {"$set": {"status": "ACCEPTED", "accepted_at": now()}})
    user = await db.users.find_one({"id": inv["user_id"]}, {"_id": 0})
    await audit(user, "USER_ACTIVATED_PASSWORD", "user", user["id"])
    return await mfa_gate(user, response)


@router.post("/refresh")
async def refresh(request: Request, response: Response):
    token = request.cookies.get("refresh_token") or request.headers.get("X-Refresh-Token")
    if not token:
        raise HTTPException(401, "No refresh token")
    p = decode_token(token, "refresh")
    user = await db.users.find_one({"id": p["sub"]}, {"_id": 0})
    if not user or user["status"] != "ACTIVE" or p.get("sv", 0) != user.get("session_version", 0):
        raise HTTPException(401, "Session revoked")
    return await issue_session(user, response)


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/", samesite="none", secure=True)
    response.delete_cookie("refresh_token", path="/", samesite="none", secure=True)
    return {"ok": True}


@router.post("/logout-all")
async def logout_all(response: Response, user=Depends(get_current_user)):
    await db.users.update_one({"id": user["id"]}, {"$inc": {"session_version": 1}})
    await logout(response)
    return {"ok": True}


@router.get("/me")
async def me(user=Depends(get_current_user)):
    org = await db.organizations.find_one({"id": user["organization_id"]}, {"_id": 0})
    groups = []
    if user["_groups"]:
        gs = await db.groups.find({"id": {"$in": list(user["_groups"].keys())}}, {"_id": 0}).to_list(100)
        groups = [{"id": g["id"], "name": g["name"], "role": user["_groups"][g["id"]]} for g in gs]
    u = {k: v for k, v in user.items() if k != "_groups"}
    return {"user": u, "organization": org, "groups": groups}


def token_hash(t: str) -> str:
    return hashlib.sha256(t.encode()).hexdigest()


@router.post("/forgot-password")
async def forgot_password(body: ForgotIn, request: Request):
    email = body.email.strip().lower()
    user = await db.users.find_one({"email": email, "status": "ACTIVE"}, {"_id": 0})
    if user:
        recent = await db.password_reset_tokens.count_documents({"user_id": user["id"], "created_at": {"$gte": datetime.now(timezone.utc) - timedelta(minutes=15)}})
        if recent < 3:
            token = secrets.token_urlsafe(32)
            await db.password_reset_tokens.update_many({"user_id": user["id"], "used": False}, {"$set": {"used": True}})
            await db.password_reset_tokens.insert_one({"token_hash": token_hash(token), "user_id": user["id"], "used": False,
                                                       "created_at": datetime.now(timezone.utc), "expires_at": datetime.now(timezone.utc) + timedelta(hours=1)})
            origin = os.environ["FRONTEND_URL"].rstrip("/")
            await db.outbox.insert_one({"id": new_id(), "organization_id": user["organization_id"], "to": email, "subject": "Reset your BenchOS password",
                                        "body": f"Reset link (valid 1 hour): {origin}/reset-password?token={token}", "status": "PENDING", "attempts": 0, "created_at": now()})
            await audit(user, "PASSWORD_RESET_REQUESTED", "user", user["id"])
    return {"ok": True, "message": "If an active account exists for that email, a reset link has been sent."}


async def valid_reset(token: str):
    rec = await db.password_reset_tokens.find_one({"token_hash": token_hash(token), "used": False})
    if not rec:
        raise HTTPException(400, "Reset link is invalid or already used")
    exp = rec["expires_at"]
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < datetime.now(timezone.utc):
        raise HTTPException(400, "Reset link has expired")
    return rec


@router.get("/reset-password/{token}")
async def check_reset(token: str):
    rec = await valid_reset(token)
    u = await db.users.find_one({"id": rec["user_id"]}, {"_id": 0, "email": 1})
    return {"email": u["email"]}


@router.post("/reset-password")
async def reset_password(body: ResetIn):
    rec = await valid_reset(body.token)
    if len(body.password) < 8:
        raise HTTPException(422, "Password must be at least 8 characters")
    await db.password_reset_tokens.update_one({"token_hash": rec["token_hash"]}, {"$set": {"used": True, "used_at": datetime.now(timezone.utc)}})
    if not await db.users.find_one({"id": rec["user_id"], "status": "ACTIVE"}):
        raise HTTPException(403, "Account is not active")
    user = await db.users.find_one_and_update({"id": rec["user_id"]}, {"$set": {"password_hash": hash_password(body.password)}, "$inc": {"session_version": 1},
                                                                      "$addToSet": {"auth_methods": "password"}}, projection={"_id": 0})
    await db.login_attempts.delete_many({"identifier": {"$regex": f":{re.escape(user['email'])}$"}})
    await audit(user, "PASSWORD_RESET_COMPLETED", "user", user["id"])
    return {"ok": True}

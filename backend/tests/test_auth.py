"""Integration tests for Authentication, MFA, Session and Invitations."""
import uuid
import pytest
import requests
from conftest import API, TOTP


def test_login_invalid_password():
    r = requests.post(f"{API}/auth/login", json={"email": "ops@acme.test", "password": "WrongPassword"})
    assert r.status_code == 401


def test_login_nonexistent_user():
    r = requests.post(f"{API}/auth/login", json={"email": "nobody@nowhere.test", "password": "AnyPassword"})
    assert r.status_code == 401


def test_auth_me_returns_profile(H):
    r = requests.get(f"{API}/auth/me", headers=H["ops"])
    assert r.status_code == 200
    data = r.json()
    assert "user" in data
    assert data["user"]["email"] == "ops@acme.test"
    assert data["user"]["role"] == "OPERATIONS"
    assert "organization" in data
    assert data["organization"]["slug"] == "acme"


def test_auditor_read_only_access(H):
    r = requests.get(f"{API}/auth/me", headers=H["auditor"])
    assert r.status_code == 200
    data = r.json()
    assert data["user"]["role"] == "AUDITOR"


def test_admin_mfa_flow():
    r = requests.post(f"{API}/auth/login", json={"email": "admin@acme.test", "password": "Admin@12345"})
    assert r.status_code == 200
    data = r.json()
    assert data.get("mfa_required") is True
    assert "mfa_token" in data

    # Wrong code should fail
    r_bad = requests.post(f"{API}/auth/mfa/verify", json={"mfa_token": data["mfa_token"], "code": "000000"})
    assert r_bad.status_code == 401

    # Correct TOTP code should succeed
    import pyotp
    code = pyotp.TOTP(TOTP).now()
    r_good = requests.post(f"{API}/auth/mfa/verify", json={"mfa_token": data["mfa_token"], "code": code})
    assert r_good.status_code == 200
    res_data = r_good.json()
    assert "access_token" in res_data
    assert "refresh_token" in res_data


def test_invite_and_activate(H):
    # Ops invites new employee
    email = f"test.user.{uuid.uuid4().hex[:8]}@acme.test"
    r_invite = requests.post(
        f"{API}/users/invite",
        headers=H["ops"],
        json={"email": email, "name": "Test Candidate Recruiter", "role": "EMPLOYEE"},
    )
    assert r_invite.status_code == 200
    inv = r_invite.json()
    token = inv["token"]

    # Verify invitation info endpoint
    r_info = requests.get(f"{API}/auth/invitations/{token}")
    assert r_info.status_code == 200
    info_data = r_info.json()
    assert info_data["email"] == email

    # Activate account with new password
    r_act = requests.post(
        f"{API}/auth/activate",
        json={"token": token, "password": "NewSecurePassword123", "name": "Activated Recruiter"},
    )
    assert r_act.status_code == 200
    act_data = r_act.json()
    assert "access_token" in act_data

    # Now login with the activated password
    r_login = requests.post(
        f"{API}/auth/login",
        json={"email": email, "password": "NewSecurePassword123"},
    )
    assert r_login.status_code == 200


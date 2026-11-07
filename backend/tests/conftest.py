import os
from pathlib import Path
import pyotp
import pytest
import requests

# Resolve backend URL flexibly (environment variable, local .env, or localhost)
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL") or os.environ.get("BACKEND_URL")

if not BASE_URL:
    env_paths = [
        Path(__file__).parent.parent / ".env",
        Path(__file__).parent.parent.parent / "frontend" / ".env",
        Path("/app/frontend/.env"),
    ]
    for p in env_paths:
        if p.exists():
            try:
                for line in p.read_text(encoding="utf-8").splitlines():
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        BASE_URL = line.split("=", 1)[1].strip()
                        break
                if BASE_URL:
                    break
            except Exception:
                pass

BASE_URL = (BASE_URL or "http://localhost:8000").rstrip("/")
API = BASE_URL + "/api"
TOTP = "B3ES4OQPDKPZ452SAHMCNNB3FOL2RRXU"
_cache = {}


def login(email: str, pw: str = "Demo@12345") -> dict[str, str]:
    if email in _cache:
        return _cache[email]
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, f"Login failed for {email}: {r.text}"
    d = r.json()
    if d.get("mfa_required"):
        r = requests.post(
            f"{API}/auth/mfa/verify",
            json={"mfa_token": d["mfa_token"], "code": pyotp.TOTP(TOTP).now()},
        )
        assert r.status_code == 200, f"MFA failed for {email}: {r.text}"
        d = r.json()
    h = {"Authorization": "Bearer " + d["access_token"]}
    _cache[email] = h
    return h


@pytest.fixture(scope="session")
def api_url():
    return API


@pytest.fixture(scope="session")
def H():
    """Authenticated headers for all core personas in the seed database."""
    return {
        "admin": login("admin@acme.test", "Admin@12345"),
        "ops": login("ops@acme.test"),
        "lead": login("lead@acme.test"),
        "recruiter": login("recruiter@acme.test"),
        "marketing": login("marketing@acme.test"),
        "viewer": login("viewer@acme.test"),
        "auditor": login("auditor@acme.test"),
        "nw": login("admin@northwind.test", "Demo@12345"),
    }


@pytest.fixture(scope="session")
def groups(H):
    """Returns mapping of group name -> group id."""
    gs = requests.get(f"{API}/groups", headers=H["ops"]).json()
    return {g["name"]: g["id"] for g in gs}

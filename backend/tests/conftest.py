import os
import pyotp
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    for line in open("/app/frontend/.env"):
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip()
BASE_URL = BASE_URL.rstrip("/")
API = BASE_URL + "/api"
TOTP = "B3ES4OQPDKPZ452SAHMCNNB3FOL2RRXU"
_cache = {}


def login(email, pw="Demo@12345"):
    if email in _cache:
        return _cache[email]
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    d = r.json()
    if d.get("mfa_required"):
        r = requests.post(f"{API}/auth/mfa/verify", json={"mfa_token": d["mfa_token"], "code": pyotp.TOTP(TOTP).now()})
        assert r.status_code == 200, r.text
        d = r.json()
    h = {"Authorization": "Bearer " + d["access_token"]}
    _cache[email] = h
    return h


@pytest.fixture(scope="session")
def H():
    return {
        "admin": login("admin@acme.test", "Admin@12345"), "ops": login("ops@acme.test"), "lead": login("lead@acme.test"),
        "recruiter": login("recruiter@acme.test"), "marketing": login("marketing@acme.test"), "viewer": login("viewer@acme.test"),
        "auditor": login("auditor@acme.test"), "nw": login("admin@northwind.test", "Demo@12345"),
    }


@pytest.fixture(scope="session")
def groups(H):
    gs = requests.get(f"{API}/groups", headers=H["ops"]).json()
    return {g["name"]: g["id"] for g in gs}

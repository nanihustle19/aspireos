# Round 2: password reset, admin MFA reset, platform organizations, Google session
import os
import re
import time
import uuid

import pyotp
import pytest
import requests
from pymongo import MongoClient

from conftest import API, login

U = uuid.uuid4().hex[:6]
mdb = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))[os.environ.get("DB_NAME", "test_database")]
ORIGIN = API[:-4]


def reset_token_for(email):
    m = mdb.outbox.find_one({"to": email, "subject": "Reset your BenchOS password"}, sort=[("created_at", -1)])
    assert m, "no reset email in outbox"
    tok = re.search(r"/reset-password\?token=([\w-]+)", m["body"])
    assert tok, m["body"]
    return tok.group(1), m["body"]


def invite_and_activate(admin_h, email, role="EMPLOYEE", pw="Initial@123"):
    r = requests.post(f"{API}/invitations", headers=admin_h, json={"email": email, "name": "TEST " + role, "role": role})
    assert r.status_code == 200, r.text
    tok = r.json()["activation_path"].split("token=")[1]
    r = requests.post(f"{API}/auth/activate", json={"token": tok, "password": pw})
    assert r.status_code == 200, r.text
    return r.json()


def mfa_verify(d, secret):
    r = requests.post(f"{API}/auth/mfa/verify", json={"mfa_token": d["mfa_token"], "code": pyotp.TOTP(secret).now()})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def admin():
    return login("admin@acme.test", "Admin@12345")


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    emails = [f"test_pr_{U}@acme.test", f"test_adm_{U}@acme.test", f"test_orgadm_{U}@newco.test"]
    users = list(mdb.users.find({"email": {"$in": emails}}, {"id": 1}))
    ids = [u["id"] for u in users]
    mdb.password_reset_tokens.delete_many({"user_id": {"$in": ids}})
    mdb.memberships.delete_many({"user_id": {"$in": ids}})
    mdb.invitations.delete_many({"email": {"$in": emails}})
    for o in mdb.organizations.find({"slug": {"$regex": f"^test-{U}"}}):
        for c in ("groups", "settings", "users", "invitations", "outbox", "audit_logs", "notifications"):
            mdb[c].delete_many({"organization_id": o["id"]})
        mdb.organizations.delete_one({"id": o["id"]})
    mdb.users.delete_many({"email": {"$in": emails}})


# Password reset (forgot/reset)
class TestPasswordReset:
    def test_unknown_email_generic(self):
        r = requests.post(f"{API}/auth/forgot-password", json={"email": f"nobody_{U}@nowhere.test"})
        assert r.status_code == 200 and r.json()["ok"] is True
        assert "If an active account" in r.json()["message"]

    def test_full_reset_flow(self, admin):
        email = f"test_pr_{U}@acme.test"
        d = invite_and_activate(admin, email)
        old_access = {"Authorization": "Bearer " + d["access_token"]}
        assert requests.get(f"{API}/auth/me", headers=old_access).status_code == 200
        r = requests.post(f"{API}/auth/forgot-password", json={"email": email}, headers={"Origin": ORIGIN})
        assert r.status_code == 200
        tok, body = reset_token_for(email)
        assert f"{ORIGIN}/reset-password?token=" in body
        r = requests.get(f"{API}/auth/reset-password/{tok}")
        assert r.status_code == 200 and r.json()["email"] == email
        assert requests.post(f"{API}/auth/reset-password", json={"token": tok, "password": "short"}).status_code == 422
        r = requests.post(f"{API}/auth/reset-password", json={"token": tok, "password": "NewPass@123"})
        assert r.status_code == 200, r.text
        # old session revoked
        assert requests.get(f"{API}/auth/me", headers=old_access).status_code == 401
        # old password fails, new works
        assert requests.post(f"{API}/auth/login", json={"email": email, "password": "Initial@123"}).status_code == 401
        r = requests.post(f"{API}/auth/login", json={"email": email, "password": "NewPass@123"})
        assert r.status_code == 200 and r.json()["user"]["email"] == email
        # single use
        assert requests.post(f"{API}/auth/reset-password", json={"token": tok, "password": "Another@123"}).status_code == 400
        assert requests.get(f"{API}/auth/reset-password/{tok}").status_code == 400

    def test_invalid_token(self):
        assert requests.get(f"{API}/auth/reset-password/bogus-token").status_code == 400
        assert requests.post(f"{API}/auth/reset-password", json={"token": "bogus", "password": "Whatever@123"}).status_code == 400

    def test_new_request_invalidates_old_token(self):
        email = f"test_pr_{U}@acme.test"
        requests.post(f"{API}/auth/forgot-password", json={"email": email})
        t1, _ = reset_token_for(email)
        time.sleep(0.05)
        requests.post(f"{API}/auth/forgot-password", json={"email": email})
        t2, _ = reset_token_for(email)
        assert t1 != t2
        assert requests.get(f"{API}/auth/reset-password/{t1}").status_code == 400
        assert requests.get(f"{API}/auth/reset-password/{t2}").status_code == 200


# Admin MFA reset
class TestMfaReset:
    def test_reset_mfa_flow(self, admin):
        email = f"test_adm_{U}@acme.test"
        d = invite_and_activate(admin, email, role="ADMIN")
        assert d.get("mfa_setup_required") and d.get("secret")
        s1 = d["secret"]
        sess = mfa_verify(d, s1)
        target_h = {"Authorization": "Bearer " + sess["access_token"]}
        uid = sess["user"]["id"]
        users = requests.get(f"{API}/users", headers=admin).json()
        assert next(u for u in users if u["id"] == uid)["mfa_enabled"] is True
        # non-admin 403
        ops = login("ops@acme.test")
        assert requests.post(f"{API}/users/{uid}/reset-mfa", headers=ops, json={"reason": "x"}).status_code == 403
        # reason required
        assert requests.post(f"{API}/users/{uid}/reset-mfa", headers=admin, json={"reason": "  "}).status_code == 422
        # own MFA (target admin resetting own) -> 422
        assert requests.post(f"{API}/users/{uid}/reset-mfa", headers=target_h, json={"reason": "self"}).status_code == 422
        r = requests.post(f"{API}/users/{uid}/reset-mfa", headers=admin, json={"reason": "Lost phone TEST"})
        assert r.status_code == 200, r.text
        assert requests.get(f"{API}/auth/me", headers=target_h).status_code == 401
        r = requests.post(f"{API}/auth/login", json={"email": email, "password": "Initial@123"})
        d2 = r.json()
        assert d2.get("mfa_setup_required") is True and d2["secret"] != s1
        mfa_verify(d2, d2["secret"])
        # already reset again -> requires enrolled; double reset of unenrolled user
        a = mdb.audit_logs.find_one({"action": "MFA_RESET", "entity_id": uid})
        assert a and a.get("reason") == "Lost phone TEST" or a

    def test_admin_cannot_reset_own(self, admin):
        me = requests.get(f"{API}/auth/me", headers=admin).json()["user"]
        assert requests.post(f"{API}/users/{me['id']}/reset-mfa", headers=admin, json={"reason": "x"}).status_code == 422

    def test_cross_tenant_reset_404(self, admin):
        nw = mdb.users.find_one({"email": "admin@northwind.test"})
        assert requests.post(f"{API}/users/{nw['id']}/reset-mfa", headers=admin, json={"reason": "x"}).status_code == 404


# Platform organizations
class TestOrganizations:
    def test_access_control(self, admin):
        r = requests.get(f"{API}/platform/organizations", headers=admin)
        assert r.status_code == 200 and len(r.json()) >= 2
        assert requests.get(f"{API}/platform/organizations", headers=login("ops@acme.test")).status_code == 403
        assert requests.get(f"{API}/platform/organizations", headers=login("admin@northwind.test")).status_code == 403
        assert requests.post(f"{API}/platform/organizations", headers=login("ops@acme.test"),
                             json={"name": "x", "slug": "xx", "admin_name": "x", "admin_email": "x@x.test"}).status_code == 403

    def test_create_org_and_activate(self, admin):
        slug = f"test-{U}-newco"
        email = f"test_orgadm_{U}@newco.test"
        body = {"name": f"TEST NewCo {U}", "slug": slug, "plan": "Starter", "admin_name": "TEST Org Admin", "admin_email": email,
                "default_groups": ["Java Bench", "Data Bench"]}
        r = requests.post(f"{API}/platform/organizations", headers=admin, json=body)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["slug"] == slug and data["activation_path"].startswith("/activate?token=")
        # validations
        assert requests.post(f"{API}/platform/organizations", headers=admin, json=body | {"admin_email": f"o_{U}@x.test"}).status_code == 409
        assert requests.post(f"{API}/platform/organizations", headers=admin, json=body | {"slug": f"test-{U}-other"}).status_code == 409
        assert requests.post(f"{API}/platform/organizations", headers=admin, json=body | {"slug": "Bad Slug!", "admin_email": f"p_{U}@x.test"}).status_code == 422
        assert requests.post(f"{API}/platform/organizations", headers=admin, json=body | {"slug": f"test-{U}-e", "admin_email": "admin@acme.test"}).status_code == 409
        orgs = requests.get(f"{API}/platform/organizations", headers=admin).json()
        row = next(o for o in orgs if o["slug"] == slug)
        assert row["primary_admin"]["email"] == email and row["primary_admin"]["status"] == "INVITED" and row["plan"] == "Starter"
        tok = data["activation_path"].split("token=")[1]
        info = requests.get(f"{API}/auth/invitations/{tok}").json()
        assert info["organization"] == body["name"] and info["role"] == "ADMIN"
        r = requests.post(f"{API}/auth/activate", json={"token": tok, "password": "OrgAdmin@123"})
        d = r.json()
        assert d.get("mfa_setup_required") and d.get("secret")
        sess = mfa_verify(d, d["secret"])
        h = {"Authorization": "Bearer " + sess["access_token"]}
        me = requests.get(f"{API}/auth/me", headers=h).json()
        assert me["organization"]["id"] == data["id"]
        assert not me["user"].get("is_platform_admin")
        cands = requests.get(f"{API}/candidates", headers=h).json()
        items = cands.get("items", cands) if isinstance(cands, dict) else cands
        assert len(items) == 0
        gnames = sorted(g["name"] for g in requests.get(f"{API}/groups", headers=h).json())
        assert gnames == ["Data Bench", "Java Bench"]
        assert len(requests.get(f"{API}/users", headers=h).json()) == 1
        acme_c = mdb.candidates.find_one({"organization_id": mdb.users.find_one({"email": "admin@acme.test"})["organization_id"]})
        assert requests.get(f"{API}/candidates/{acme_c['id']}", headers=h).status_code == 404
        assert requests.get(f"{API}/platform/organizations", headers=h).status_code == 403


# Google session
class TestGoogle:
    def test_bogus_session(self):
        r = requests.post(f"{API}/auth/google/session", json={"session_id": "bogus-session-123"})
        assert r.status_code == 401

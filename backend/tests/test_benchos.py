"""BenchOS backend regression tests: auth, scope, redaction, candidate workflows, pipeline, docs, admin, data jobs."""
import time
import uuid
import requests
import pytest
from conftest import API, BASE_URL, login

U = uuid.uuid4().hex[:6]


def mk(H, **kw):
    body = {"first_name": "TEST_" + U, "last_name": kw.pop("ln", "Cand"), "email": f"test_{uuid.uuid4().hex[:8]}@x.test"} | kw
    r = requests.post(f"{API}/candidates", headers=H["ops"], json=body)
    assert r.status_code == 200, r.text
    return r.json()


def det(H, cid, who="ops"):
    return requests.get(f"{API}/candidates/{cid}", headers=H[who]).json()


# --- Auth ---
class TestAuth:
    def test_admin_mfa_required(self):
        r = requests.post(f"{API}/auth/login", json={"email": "admin@acme.test", "password": "Admin@12345"})
        assert r.status_code == 200 and r.json().get("mfa_required") is True and r.json().get("mfa_token")

    def test_ops_login_cookies_httponly(self):
        r = requests.post(f"{API}/auth/login", json={"email": "ops@acme.test", "password": "Demo@12345"})
        assert r.status_code == 200
        sc = r.headers.get("set-cookie", "")
        assert "access_token" in sc and "HttpOnly" in sc
        assert r.json()["user"]["role"] == "OPERATIONS"

    def test_me(self, H):
        r = requests.get(f"{API}/auth/me", headers=H["lead"])
        assert r.status_code == 200 and (r.json().get("user") or r.json())["email"] == "lead@acme.test"

    def test_pending_user_cannot_login(self):
        r = requests.post(f"{API}/auth/login", json={"email": "pending@acme.test", "password": "Demo@12345"})
        assert r.status_code in (401, 403)

    def test_cors_credentials(self):
        r = requests.options(f"{API}/auth/me", headers={"Origin": BASE_URL, "Access-Control-Request-Method": "GET"})
        assert r.headers.get("access-control-allow-credentials") == "true"
        assert r.headers.get("access-control-allow-origin") == BASE_URL


# --- Scope & redaction ---
class TestScope:
    def test_lead_only_java(self, H, groups):
        items = requests.get(f"{API}/candidates?page_size=200", headers=H["lead"]).json()["items"]
        assert items and all(i["current_group_id"] == groups["Java & Cloud"] for i in items)
        assert all(i.get("pay_rate") is None for i in items)
        assert any(i.get("bill_rate") is not None for i in items)

    def test_marketing_scope(self, H):
        me = requests.get(f"{API}/auth/me", headers=H["marketing"]).json(); me = me.get("user") or me
        items = requests.get(f"{API}/candidates?page_size=200", headers=H["marketing"]).json()["items"]
        assert items
        for i in items:
            assert i["status"] in ("MARKETING", "SUBMITTED", "INTERVIEWING", "OFFERED") or (i["status"] in ("BENCH", "ON_HOLD") and i["owner_id"] == me["id"])

    def test_recruiter_viewer_auditor_bill_redacted(self, H):
        for who in ("recruiter", "viewer", "auditor"):
            items = requests.get(f"{API}/candidates?page_size=50", headers=H[who]).json()["items"]
            assert items, who
            assert all(i.get("bill_rate") is None and i.get("target_rate") is None and i.get("pay_rate") is None for i in items), who

    def test_ops_sees_pay(self, H):
        items = requests.get(f"{API}/candidates?page_size=50", headers=H["ops"]).json()["items"]
        assert any(i.get("pay_rate") is not None for i in items)

    def test_tenant_isolation(self, H):
        acme = requests.get(f"{API}/candidates?page_size=1", headers=H["ops"]).json()["items"][0]
        assert requests.get(f"{API}/candidates/{acme['id']}", headers=H["nw"]).status_code == 404
        nw = requests.get(f"{API}/candidates?page_size=200", headers=H["nw"]).json()["items"]
        assert all(i["organization_id"] != acme["organization_id"] for i in nw)

    def test_auditor_read_only(self, H):
        c = requests.get(f"{API}/candidates?page_size=1", headers=H["auditor"]).json()["items"][0]
        assert requests.post(f"{API}/candidates/{c['id']}/notes", headers=H["auditor"], json={"body": "x"}).status_code == 403
        assert requests.patch(f"{API}/candidates/{c['id']}", headers=H["auditor"], json={"version": c["version"], "summary": "x"}).status_code == 403
        notes = requests.get(f"{API}/candidates/{c['id']}/notes", headers=H["auditor"]).json()
        assert all(n["visibility"] != "OPERATIONS_ONLY" for n in notes)
        p = det(H, c["id"], "auditor")["permissions"]
        assert not p["can_edit"] and not p["can_transfer"] and not p["can_archive"]

    def test_ops_only_notes_hidden_from_lead(self, H):
        c = mk(H)
        requests.post(f"{API}/candidates/{c['id']}/notes", headers=H["ops"], json={"body": "secret", "visibility": "OPERATIONS_ONLY"})
        ns = requests.get(f"{API}/candidates/{c['id']}/notes", headers=H["ops"]).json()
        assert any(n["visibility"] == "OPERATIONS_ONLY" for n in ns)


# --- Duplicates ---
class TestDuplicates:
    def test_exact_email_blocked_and_override(self, H):
        c = mk(H)
        r = requests.post(f"{API}/candidates", headers=H["ops"], json={"first_name": "X", "last_name": "Y", "email": c["email"].upper()})
        assert r.status_code == 409
        r = requests.post(f"{API}/candidates", headers=H["ops"], json={"first_name": "X", "last_name": "Y", "email": c["email"], "override_duplicate_reason": "TEST override"})
        assert r.status_code == 200

    def test_lead_cannot_create(self, H):
        assert requests.post(f"{API}/candidates", headers=H["lead"], json={"first_name": "a", "last_name": "b"}).status_code == 403

    def test_phone_dup_with_null_email_candidate(self, H):
        # existing candidate WITHOUT email, matched by phone -> must not 500
        ph = "555" + str(uuid.uuid4().int)[:7]
        r = requests.post(f"{API}/candidates", headers=H["ops"], json={"first_name": "TEST_np", "last_name": "NoEmail", "phone": ph})
        assert r.status_code == 200
        d = requests.post(f"{API}/candidates/duplicate-check", headers=H["ops"], json={"phone": ph, "email": "zz@zz.test"})
        assert d.status_code == 200, f"duplicate-check crashed: {d.status_code} {d.text[:200]}"
        assert d.json()["exact"]


# --- Assign/transfer/unassign/concurrency ---
class TestWorkflow:
    def test_assign_transfer_concurrency(self, H, groups):
        c = mk(H)
        a = requests.post(f"{API}/candidates/{c['id']}/assign", headers=H["ops"], json={"group_id": groups["Java & Cloud"], "version": c["version"]})
        assert a.status_code == 200 and a.json()["status"] == "BENCH"
        v = a.json()["version"]
        body = {"to_group_id": groups["Data & Analytics"], "version": v, "reason": "TEST"}
        r1 = requests.post(f"{API}/candidates/{c['id']}/transfer", headers=H["ops"], json=body)
        r2 = requests.post(f"{API}/candidates/{c['id']}/transfer", headers=H["ops"], json=body)
        assert r1.status_code == 200 and r2.status_code in (409, 422)
        stale = requests.patch(f"{API}/candidates/{c['id']}", headers=H["ops"], json={"version": v, "summary": "x"})
        assert stale.status_code == 409
        cur = det(H, c["id"])["candidate"]["version"]
        assert requests.patch(f"{API}/candidates/{c['id']}", headers=H["ops"], json={"version": cur, "current_group_id": groups["Java & Cloud"]}).status_code == 422
        hist = det(H, c["id"])["assignment_history"]
        assert sum(1 for h in hist if h["active"]) == 1

    def test_transfer_requires_reason(self, H, groups):
        c = mk(H, group_id=groups["Java & Cloud"])
        r = requests.post(f"{API}/candidates/{c['id']}/transfer", headers=H["ops"], json={"to_group_id": groups["Data & Analytics"], "version": c["version"]})
        assert r.status_code == 422

    def test_unassign_marketing_requires_target_and_archive_restore(self, H, groups):
        c = mk(H)
        a = requests.post(f"{API}/candidates/{c['id']}/assign", headers=H["ops"], json={"group_id": groups["Java & Cloud"], "version": c["version"]}).json()
        t = requests.post(f"{API}/candidates/{c['id']}/transition", headers=H["ops"], json={"to_status": "MARKETING", "version": a["version"]}).json()
        assert t["status"] == "MARKETING"
        u = requests.post(f"{API}/candidates/{c['id']}/unassign", headers=H["ops"], json={"version": t["version"], "reason": "x"})
        assert u.status_code == 422
        u = requests.post(f"{API}/candidates/{c['id']}/unassign", headers=H["ops"], json={"version": t["version"], "reason": "x", "target_status": "BENCH"}).json()
        assert u["status"] == "BENCH" and u["current_group_id"] is None
        ar = requests.post(f"{API}/candidates/{c['id']}/archive", headers=H["ops"], json={"version": u["version"], "reason": "TEST"}).json()
        assert ar["status"] == "ARCHIVED"
        rs = requests.post(f"{API}/candidates/{c['id']}/restore", headers=H["ops"], json={"version": ar["version"], "reason": "TEST"}).json()
        assert rs["status"] == "BENCH" and rs["current_group_id"] is None

    def test_invalid_transition(self, H):
        c = mk(H)
        r = requests.post(f"{API}/candidates/{c['id']}/transition", headers=H["ops"], json={"to_status": "PLACED", "version": c["version"]})
        assert r.status_code == 422


# --- Pipeline ---
class TestPipeline:
    def test_full_pipeline(self, H, groups):
        c = mk(H, group_id=groups["Java & Cloud"])
        v = det(H, c["id"])["candidate"]["version"]
        if det(H, c["id"])["candidate"]["status"] == "NEW":
            v = requests.post(f"{API}/candidates/{c['id']}/transition", headers=H["ops"], json={"to_status": "BENCH", "version": v}).json()["version"]
        m = requests.post(f"{API}/candidates/{c['id']}/transition", headers=H["ops"], json={"to_status": "MARKETING", "version": v})
        assert m.status_code == 200, m.text
        job = requests.get(f"{API}/jobs", headers=H["ops"]).json()[0]
        s = requests.post(f"{API}/pipeline/submissions", headers=H["lead"], json={"candidate_id": c["id"], "job_id": job["id"], "submission_rate": 90})
        assert s.status_code == 200, s.text
        assert det(H, c["id"])["candidate"]["status"] == "SUBMITTED"
        i = requests.post(f"{API}/pipeline/interviews", headers=H["lead"], json={"submission_id": s.json()["id"], "scheduled_at": "2026-03-01T15:00:00Z", "timezone": "Asia/Kolkata"})
        assert i.status_code == 200 and det(H, c["id"])["candidate"]["status"] == "INTERVIEWING"
        rs = requests.post(f"{API}/pipeline/interviews/{i.json()['id']}/reschedule", headers=H["lead"], json={"scheduled_at": "2026-03-02T15:00:00Z", "timezone": "Europe/London", "reason": "TEST", "version": 1})
        assert rs.status_code == 200 and len(rs.json()["reschedule_history"]) == 1
        o = requests.post(f"{API}/pipeline/offers", headers=H["ops"], json={"submission_id": s.json()["id"], "bill_rate": 100, "pay_rate": 70})
        assert o.status_code == 200 and det(H, c["id"])["candidate"]["status"] == "OFFERED"
        # active offer transfer requires ack
        cv = det(H, c["id"])["candidate"]["version"]
        t = requests.post(f"{API}/candidates/{c['id']}/transfer", headers=H["ops"], json={"to_group_id": groups["Data & Analytics"], "version": cv, "reason": "x"})
        assert t.status_code == 409
        acc = requests.patch(f"{API}/pipeline/offers/{o.json()['id']}/status", headers=H["ops"], json={"status": "ACCEPTED", "version": 1})
        assert acc.status_code == 200
        assert requests.post(f"{API}/pipeline/placements", headers=H["lead"], json={"offer_id": o.json()["id"], "start_date": "2026-04-01", "confirm": True}).status_code == 403
        p = requests.post(f"{API}/pipeline/placements", headers=H["ops"], json={"offer_id": o.json()["id"], "start_date": "2026-04-01", "confirm": True})
        assert p.status_code == 200 and det(H, c["id"])["candidate"]["status"] == "PLACED"
        e = requests.post(f"{API}/pipeline/placements/{p.json()['id']}/end", headers=H["ops"], json={"status": "ENDED", "note": "TEST", "version": 1})
        assert e.status_code == 200 and det(H, c["id"])["candidate"]["status"] == "BENCH"


# --- Documents ---
class TestDocuments:
    def test_scan_pass_and_eicar(self, H):
        c = mk(H)
        d = requests.post(f"{API}/candidates/{c['id']}/documents", headers=H["ops"], files={"file": ("cv.txt", b"resume", "text/plain")}, data={"doc_type": "RESUME"}).json()
        assert d["scan_status"] == "PENDING"
        assert requests.get(f"{API}/documents/{d['id']}/signed-url", headers=H["ops"]).status_code == 423
        eic = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!H+H*"
        bad = requests.post(f"{API}/candidates/{c['id']}/documents", headers=H["ops"], files={"file": ("bad.txt", eic, "text/plain")}, data={"doc_type": "OTHER"}).json()
        st = {}
        for _ in range(15):
            time.sleep(1)
            st = {x["id"]: x["scan_status"] for x in requests.get(f"{API}/candidates/{c['id']}/documents", headers=H["ops"]).json()}
            if st.get(d["id"]) != "PENDING" and st.get(bad["id"]) != "PENDING":
                break
        assert st[d["id"]] == "PASSED" and st[bad["id"]] == "FAILED"
        su = requests.get(f"{API}/documents/{d['id']}/signed-url", headers=H["ops"]).json()
        dl = requests.get(BASE_URL + su["url"])
        assert dl.status_code == 200 and dl.content == b"resume"
        assert requests.get(f"{API}/documents/{bad['id']}/signed-url", headers=H["ops"]).status_code == 423


# --- Admin / users / groups ---
class TestAdmin:
    def test_invite_activate_deactivate(self, H, groups):
        email = f"test_inv_{U}@acme.test"
        inv = requests.post(f"{API}/invitations", headers=H["ops"], json={"email": email, "name": "TEST Inv", "role": "EMPLOYEE", "group_id": groups["Java & Cloud"], "group_role": "RECRUITER"})
        assert inv.status_code == 200, inv.text
        tok = inv.json()["activation_path"].split("token=")[1]
        assert requests.get(f"{API}/auth/invitations/{tok}").json()["email"] == email
        a = requests.post(f"{API}/auth/activate", json={"token": tok, "password": "Test@12345", "name": "TEST Inv"})
        assert a.status_code == 200 and a.json().get("access_token")
        h = {"Authorization": "Bearer " + a.json()["access_token"]}
        assert requests.get(f"{API}/auth/me", headers=h).status_code == 200
        uid = a.json()["user"]["id"]
        r = requests.patch(f"{API}/users/{uid}", headers=H["admin"], json={"status": "DEACTIVATED"})
        assert r.status_code == 200, r.text
        assert requests.get(f"{API}/auth/me", headers=h).status_code == 401

    def test_group_member_add_remove(self, H, groups):
        users = requests.get(f"{API}/users", headers=H["ops"]).json()
        viewer = next(u for u in users if u["email"] == "viewer@acme.test")
        gid = groups["DevOps & SRE"] if "DevOps & SRE" in groups else [g for n, g in groups.items() if "DevOps" in n][0]
        m = requests.post(f"{API}/groups/{gid}/members", headers=H["ops"], json={"user_id": viewer["id"], "role": "VIEWER"})
        assert m.status_code == 200, m.text
        r = requests.delete(f"{API}/groups/{gid}/members/{m.json()['id']}", headers=H["ops"])
        assert r.status_code == 200

    def test_settings_admin_only(self, H):
        s = requests.get(f"{API}/settings", headers=H["admin"]).json()
        assert requests.put(f"{API}/settings", headers=H["ops"], json=s).status_code == 403
        assert requests.put(f"{API}/settings", headers=H["admin"], json=s).status_code == 200

    def test_audit_and_dashboards(self, H):
        assert requests.get(f"{API}/audit?entity_type=candidate", headers=H["auditor"]).status_code == 200
        assert requests.get(f"{API}/audit", headers=H["lead"]).status_code == 403
        for who in ("ops", "lead", "marketing", "auditor"):
            assert requests.get(f"{API}/dashboard", headers=H[who]).status_code == 200, who
            assert requests.get(f"{API}/reports/summary", headers=H[who]).status_code == 200, who
        assert requests.get(f"{API}/notifications", headers=H["ops"]).status_code == 200


# --- Imports / exports ---
class TestDataJobs:
    def wait(self, H, jid):
        for _ in range(20):
            time.sleep(1)
            j = next((x for x in requests.get(f"{API}/bg-jobs", headers=H["ops"]).json() if x["id"] == jid), None)
            if j and j["status"] in ("COMPLETED", "FAILED"):
                return j
        return j

    def test_export(self, H):
        assert requests.post(f"{API}/exports/candidates", headers=H["lead"], json={}).status_code == 403
        j = requests.post(f"{API}/exports/candidates", headers=H["ops"], json={}).json()
        j = self.wait(H, j["id"])
        assert j["status"] == "COMPLETED"
        csv = requests.get(f"{API}/bg-jobs/{j['id']}/download", headers=H["ops"])
        assert csv.status_code == 200 and csv.text.startswith("id,first_name")

    def test_import_skips_dupes(self, H):
        e = f"test_imp_{U}@x.test"
        existing = requests.get(f"{API}/candidates?page_size=1", headers=H["ops"]).json()["items"][0]
        csv = f"first_name,last_name,email,phone\nTEST_Imp,One,{e},\nTEST_Imp,Dup,{existing['email']},\n"
        j = requests.post(f"{API}/imports/candidates", headers=H["ops"], files={"file": ("t.csv", csv.encode(), "text/csv")}).json()
        j = self.wait(H, j["id"])
        assert j["status"] == "COMPLETED" and j["result"]["created"] == 1 and j["result"]["skipped"] == 1

    def test_import_dupes_within_file(self, H):
        e = f"test_imp2_{U}@x.test"
        csv = f"first_name,last_name,email\nTEST_A,A,{e}\nTEST_B,B,{e}\n"
        j = requests.post(f"{API}/imports/candidates", headers=H["ops"], files={"file": ("t.csv", csv.encode(), "text/csv")}).json()
        j = self.wait(H, j["id"])
        assert j["status"] == "COMPLETED" and j["result"]["created"] == 1, f"in-file duplicate not skipped: {j.get('result')}"


# --- Additional role-guard and create-with-group checks ---
class TestRoleGuards:
    def test_create_with_group_sets_bench(self, H, groups):
        c = mk(H, group_id=groups["Java & Cloud"])
        assert c["current_group_id"] == groups["Java & Cloud"]
        assert c["status"] == "BENCH", f"create with group_id left status={c['status']} (expected BENCH like /assign)"

    def test_recruiter_cannot_transfer(self, H, groups):
        items = requests.get(f"{API}/candidates?page_size=5", headers=H["recruiter"]).json()["items"]
        c = items[0]
        r = requests.post(f"{API}/candidates/{c['id']}/transfer", headers=H["recruiter"], json={"to_group_id": groups["Data & Analytics"], "version": c["version"], "reason": "x"})
        assert r.status_code == 403

    def test_marketing_cannot_edit_restricted_fields(self, H):
        c = requests.get(f"{API}/candidates?status=MARKETING&page_size=1", headers=H["marketing"]).json()["items"][0]
        r = requests.patch(f"{API}/candidates/{c['id']}", headers=H["marketing"], json={"version": c["version"], "email": "hack@x.test"})
        assert r.status_code == 403
        assert requests.post(f"{API}/candidates/{c['id']}/notes", headers=H["marketing"], json={"body": "x", "visibility": "OPERATIONS_ONLY"}).status_code == 403

    def test_auditor_cannot_import_but_can_export(self, H):
        assert requests.post(f"{API}/imports/candidates", headers=H["auditor"], files={"file": ("t.csv", b"first_name,last_name\na,b\n", "text/csv")}).status_code == 403
        assert requests.post(f"{API}/exports/candidates", headers=H["auditor"], json={}).status_code == 200

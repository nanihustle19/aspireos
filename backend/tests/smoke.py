import pyotp, requests, sys
API = sys.argv[1] + "/api"
def login(email, pw="Demo@12345"):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}).json()
    if r.get("mfa_required"):
        r = requests.post(f"{API}/auth/mfa/verify", json={"mfa_token": r["mfa_token"], "code": pyotp.TOTP("B3ES4OQPDKPZ452SAHMCNNB3FOL2RRXU").now()}).json()
    return {"Authorization": "Bearer " + r["access_token"]}
A = login("admin@acme.test", "Admin@12345"); O = login("ops@acme.test"); L = login("lead@acme.test"); M = login("marketing@acme.test"); AU = login("auditor@acme.test"); N = login("admin@northwind.test")
cnt = lambda h: requests.get(f"{API}/candidates", headers=h).json()["total"]
print("scope admin/ops/lead/mkt/auditor/northwind", cnt(A), cnt(O), cnt(L), cnt(M), cnt(AU), cnt(N))
c = requests.post(f"{API}/candidates", headers=O, json={"first_name": "Test", "last_name": "Person", "email": "tp@x.test", "phone": "5551234567"}).json()
print("create", c["status"], c["version"])
d = requests.post(f"{API}/candidates", headers=O, json={"first_name": "T2", "last_name": "P2", "email": "TP@x.test"})
print("dup", d.status_code)
groups = requests.get(f"{API}/groups", headers=O).json()
g1, g2 = groups[0]["id"], groups[1]["id"]
a = requests.post(f"{API}/candidates/{c['id']}/assign", headers=O, json={"group_id": g1, "version": 1}).json()
print("assign", a["status"], a["version"])
v = a["version"]
r1 = requests.post(f"{API}/candidates/{c['id']}/transfer", headers=O, json={"to_group_id": g2, "version": v, "reason": "x"})
r2 = requests.post(f"{API}/candidates/{c['id']}/transfer", headers=O, json={"to_group_id": g2, "version": v, "reason": "x"})
print("concurrent transfer", r1.status_code, r2.status_code)
p = requests.patch(f"{API}/candidates/{c['id']}", headers=O, json={"version": 1, "current_group_id": g1})
print("generic group edit", p.status_code)
lc = requests.get(f"{API}/candidates", headers=L).json()["items"][0]
print("lead pay redacted", lc["pay_rate"], lc.get("bill_rate"))
print("lead export", requests.post(f"{API}/exports/candidates", headers=L, json={}).status_code, "auditor export", requests.post(f"{API}/exports/candidates", headers=AU, json={}).status_code)
det = requests.get(f"{API}/candidates/{c['id']}", headers=O).json()["candidate"]
t = requests.post(f"{API}/candidates/{c['id']}/transition", headers=O, json={"to_status": "MARKETING", "version": det["version"]}).json()
u = requests.post(f"{API}/candidates/{c['id']}/unassign", headers=O, json={"version": t["version"], "reason": "test"})
print("unassign no target", u.status_code, u.json()["detail"])
u = requests.post(f"{API}/candidates/{c['id']}/unassign", headers=O, json={"version": t["version"], "reason": "test", "target_status": "ON_HOLD"}).json()
print("unassign ok", u["status"], u["current_group_id"])
print("northwind access acme cand", requests.get(f"{API}/candidates/{c['id']}", headers=N).status_code)
print("dashboard", requests.get(f"{API}/dashboard", headers=L).status_code, "reports", requests.get(f"{API}/reports/summary", headers=M).status_code)
files = {"file": ("cv.txt", b"hello resume", "text/plain")}
doc = requests.post(f"{API}/candidates/{c['id']}/documents", headers=O, files=files, data={"doc_type": "RESUME"}).json()
print("upload", doc.get("scan_status"), doc.get("detail"))
print("signed before scan", requests.get(f"{API}/documents/{doc['id']}/signed-url", headers=O).status_code)
import time; time.sleep(6)
s = requests.get(f"{API}/documents/{doc['id']}/signed-url", headers=O)
print("signed after", s.status_code)
if s.ok: print("download", requests.get(sys.argv[1] + s.json()["url"]).content)

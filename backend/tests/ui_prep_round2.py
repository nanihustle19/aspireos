# Prep data for round-2 UI tests: user with reset token + Acme admin with MFA enrolled
import json, re, sys, uuid, pyotp, requests
sys.path.insert(0, "/app/backend/tests")
from conftest import API, login
from pymongo import MongoClient
mdb = MongoClient("mongodb://localhost:27017")["test_database"]
U = uuid.uuid4().hex[:6]
admin = login("admin@acme.test", "Admin@12345")
out = {}
e = f"test_uipr_{U}@acme.test"
tok = requests.post(f"{API}/invitations", headers=admin, json={"email": e, "name": "TEST UI Reset", "role": "EMPLOYEE"}).json()["activation_path"].split("token=")[1]
requests.post(f"{API}/auth/activate", json={"token": tok, "password": "Initial@123"})
requests.post(f"{API}/auth/forgot-password", json={"email": e}, headers={"Origin": API[:-4]})
m = mdb.outbox.find_one({"to": e, "subject": "Reset your BenchOS password"})
out["reset_email"] = e
out["reset_url"] = re.search(r"(https?://\S+/reset-password\?token=[\w-]+)", m["body"]).group(1)
a = f"test_uiadm_{U}@acme.test"
tok = requests.post(f"{API}/invitations", headers=admin, json={"email": a, "name": "TEST UI Admin2", "role": "ADMIN"}).json()["activation_path"].split("token=")[1]
d = requests.post(f"{API}/auth/activate", json={"token": tok, "password": "Initial@123"}).json()
s = requests.post(f"{API}/auth/mfa/verify", json={"mfa_token": d["mfa_token"], "code": pyotp.TOTP(d["secret"]).now()}).json()
out["mfa_admin_email"] = a
out["mfa_admin_id"] = s["user"]["id"]
print(json.dumps(out))

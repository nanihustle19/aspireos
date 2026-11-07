"""Integration tests for RBAC, Group Scoping, Rate Redaction, and Auditor read-only enforcement."""
import uuid
import pytest
import requests
from conftest import API


def test_rate_redaction(H, groups):
    core_gid = list(groups.values())[0]

    cand = requests.post(f"{API}/candidates", headers=H["ops"], json={
        "first_name": "Confidential",
        "last_name": f"Rate-{uuid.uuid4().hex[:6]}",
        "pay_rate": 80.0,
        "bill_rate": 130.0,
        "target_rate": 140.0,
        "group_id": core_gid,
    }).json()
    cid = cand["id"]

    # 1. Operations can see pay_rate and bill_rate
    r_ops = requests.get(f"{API}/candidates/{cid}", headers=H["ops"])
    assert r_ops.status_code == 200
    ops_cand = r_ops.json()["candidate"]
    assert ops_cand["pay_rate"] == 80.0
    assert ops_cand["bill_rate"] == 130.0
    assert ops_cand["target_rate"] == 140.0

    # 2. Recruiter cannot see pay_rate or bill_rate
    r_recruiter = requests.get(f"{API}/candidates/{cid}", headers=H["recruiter"])
    if r_recruiter.status_code == 200:
        rec_cand = r_recruiter.json()["candidate"]
        assert rec_cand.get("pay_rate") is None
        assert rec_cand.get("bill_rate") is None
        assert rec_cand.get("target_rate") == 140.0


def test_auditor_cannot_mutate(H):
    # Auditor attempting to create a candidate MUST be rejected with 403
    r = requests.post(f"{API}/candidates", headers=H["auditor"], json={
        "first_name": "Auditor",
        "last_name": "IllegalWrite",
    })
    assert r.status_code == 403

    # Auditor attempting to create a job MUST be rejected with 403
    r_job = requests.post(f"{API}/jobs", headers=H["auditor"], json={
        "title": "Illegal Auditor Job",
    })
    assert r_job.status_code == 403


def test_tenant_isolation(H):
    # Acme Operations lists candidates
    acme_list = requests.get(f"{API}/candidates", headers=H["ops"]).json()
    acme_ids = {c["id"] for c in acme_list["items"]}

    # Northwind admin cannot fetch an Acme candidate ID
    if acme_ids:
        sample_acme_id = next(iter(acme_ids))
        r_cross = requests.get(f"{API}/candidates/{sample_acme_id}", headers=H["nw"])
        assert r_cross.status_code == 404


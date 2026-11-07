"""Integration tests for Pipeline: Vendors, Clients, Jobs, Submissions, Interviews, Offers, and Placements."""
import uuid
import pytest
import requests
from conftest import API


def test_full_pipeline_flow(H, groups):
    core_gid = list(groups.values())[0]
    unique_suffix = uuid.uuid4().hex[:6]

    # 1. Create Vendor & Client
    client = requests.post(f"{API}/clients", headers=H["ops"], json={
        "name": f"Enterprise Bank-{unique_suffix}",
        "industry": "Financial Services",
    }).json()

    # 2. Create Job
    job = requests.post(f"{API}/jobs", headers=H["ops"], json={
        "title": f"Lead Python Architect-{unique_suffix}",
        "client_id": client["id"],
        "rate": 125.0,
        "skills": ["Python", "FastAPI", "Docker"],
    }).json()

    # 3. Create Candidate and assign to group
    cand = requests.post(f"{API}/candidates", headers=H["ops"], json={
        "first_name": "Pipeline",
        "last_name": f"Specialist-{unique_suffix}",
        "primary_skill": "Python",
        "group_id": core_gid,
    }).json()
    cid = cand["id"]

    # 4. Create Submission
    sub = requests.post(f"{API}/pipeline/submissions", headers=H["ops"], json={
        "candidate_id": cid,
        "job_id": job["id"],
        "submission_rate": 120.0,
        "notes": "Direct client submission",
    }).json()
    assert sub["status"] == "SUBMITTED"

    # Candidate status auto-advances to SUBMITTED
    c_sub = requests.get(f"{API}/candidates/{cid}", headers=H["ops"]).json()["candidate"]
    assert c_sub["status"] == "SUBMITTED"

    # 5. Schedule Interview
    interview = requests.post(f"{API}/pipeline/interviews", headers=H["ops"], json={
        "submission_id": sub["id"],
        "scheduled_at": "2026-12-01T15:00:00Z",
        "timezone": "America/New_York",
        "duration_minutes": 45,
        "mode": "VIDEO",
        "round": "Technical Screening",
    }).json()
    assert interview["status"] == "SCHEDULED"

    # Candidate status auto-advances to INTERVIEWING
    c_int = requests.get(f"{API}/candidates/{cid}", headers=H["ops"]).json()["candidate"]
    assert c_int["status"] == "INTERVIEWING"

    # 6. Extend Offer
    offer = requests.post(f"{API}/pipeline/offers", headers=H["ops"], json={
        "submission_id": sub["id"],
        "bill_rate": 125.0,
        "pay_rate": 85.0,
        "notes": "Contract approved",
    }).json()
    assert offer["status"] == "EXTENDED"

    # Candidate status auto-advances to OFFERED
    c_off = requests.get(f"{API}/candidates/{cid}", headers=H["ops"]).json()["candidate"]
    assert c_off["status"] == "OFFERED"

    # 7. Execute Placement
    placement = requests.post(f"{API}/pipeline/offers/{offer['id']}/place", headers=H["ops"], json={
        "start_date": "2026-12-15",
    }).json()
    assert placement["status"] == "ACTIVE"

    # Candidate status auto-advances to PLACED
    c_plc = requests.get(f"{API}/candidates/{cid}", headers=H["ops"]).json()["candidate"]
    assert c_plc["status"] == "PLACED"


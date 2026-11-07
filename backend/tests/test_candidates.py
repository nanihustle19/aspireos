"""Integration tests for Candidate intake, duplicate checks, generic update restrictions."""
import uuid
import pytest
import requests
from conftest import API


def test_create_candidate_basics(H):
    unique_suffix = uuid.uuid4().hex[:6]
    payload = {
        "first_name": "Jane",
        "last_name": f"Doe-{unique_suffix}",
        "email": f"jane.{unique_suffix}@example.test",
        "phone": f"555{unique_suffix[:7]}",
        "primary_skill": "Python / FastAPI",
        "skills": ["Python", "FastAPI", "PostgreSQL"],
        "experience_years": 5.5,
        "pay_rate": 65.0,
        "bill_rate": 95.0,
        "target_rate": 105.0,
    }
    r = requests.post(f"{API}/candidates", headers=H["ops"], json=payload)
    assert r.status_code == 200, r.text
    cand = r.json()
    assert cand["first_name"] == "Jane"
    assert cand["status"] == "NEW"
    assert cand["version"] == 1
    return cand


def test_duplicate_intake_hard_block(H):
    unique_suffix = uuid.uuid4().hex[:6]
    email = f"dup.{unique_suffix}@example.test"
    payload = {
        "first_name": "Alice",
        "last_name": "Smith",
        "email": email,
        "phone": "5551234567",
        "primary_skill": "React",
    }
    # Create first candidate
    r1 = requests.post(f"{API}/candidates", headers=H["ops"], json=payload)
    assert r1.status_code == 200

    # Attempt second candidate with exact same email -> should be blocked with 409
    r2 = requests.post(f"{API}/candidates", headers=H["recruiter"], json=payload)
    assert r2.status_code == 409
    assert "DUPLICATE" in r2.text

    # Admin/Ops can override duplicate with documented reason
    override_payload = {**payload, "override_duplicate_reason": "Verified different individual, same household"}
    r3 = requests.post(f"{API}/candidates", headers=H["ops"], json=override_payload)
    assert r3.status_code == 200


def test_forbidden_generic_field_update(H):
    # Create candidate
    unique_suffix = uuid.uuid4().hex[:6]
    cand = requests.post(f"{API}/candidates", headers=H["ops"], json={
        "first_name": "Bob",
        "last_name": f"Tester-{unique_suffix}",
        "email": f"bob.{unique_suffix}@example.test",
    }).json()

    cid = cand["id"]
    version = cand["version"]

    # Attempt to change current_group_id via generic PATCH -> MUST FAIL
    r_bad_group = requests.patch(
        f"{API}/candidates/{cid}",
        headers=H["ops"],
        json={"version": version, "current_group_id": str(uuid.uuid4())},
    )
    assert r_bad_group.status_code == 422
    assert "current_group_id" in r_bad_group.text

    # Attempt to change status via generic PATCH -> MUST FAIL
    r_bad_status = requests.patch(
        f"{API}/candidates/{cid}",
        headers=H["ops"],
        json={"version": version, "status": "BENCH"},
    )
    assert r_bad_status.status_code == 422
    assert "status" in r_bad_status.text

    # Attempt to change owner_id via generic PATCH -> MUST FAIL
    r_bad_owner = requests.patch(
        f"{API}/candidates/{cid}",
        headers=H["ops"],
        json={"version": version, "owner_id": str(uuid.uuid4())},
    )
    assert r_bad_owner.status_code == 422
    assert "owner_id" in r_bad_owner.text


def test_optimistic_locking_conflict(H):
    cand = requests.post(f"{API}/candidates", headers=H["ops"], json={
        "first_name": "Optimistic",
        "last_name": "Locking",
    }).json()

    cid = cand["id"]
    version = cand["version"]

    # First update succeeds
    r1 = requests.patch(
        f"{API}/candidates/{cid}",
        headers=H["ops"],
        json={"version": version, "location": "New York, NY"},
    )
    assert r1.status_code == 200
    new_version = r1.json()["version"]
    assert new_version == version + 1

    # Second update using the old stale version -> 409 Conflict
    r2 = requests.patch(
        f"{API}/candidates/{cid}",
        headers=H["ops"],
        json={"version": version, "location": "San Francisco, CA"},
    )
    assert r2.status_code == 409


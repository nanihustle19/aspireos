"""Integration tests for Group Assignment, Transfer transactions, and One-Active-Group constraint."""
import uuid
import pytest
import requests
from conftest import API


def test_assign_and_auto_transition_to_bench(H, groups):
    core_bench_gid = list(groups.values())[0]

    cand = requests.post(f"{API}/candidates", headers=H["ops"], json={
        "first_name": "Assignee",
        "last_name": f"Test-{uuid.uuid4().hex[:6]}",
    }).json()

    assert cand["status"] == "NEW"
    assert cand["current_group_id"] is None

    # Assign to group
    r_assign = requests.post(
        f"{API}/candidates/{cand['id']}/assign",
        headers=H["ops"],
        json={"group_id": core_bench_gid, "version": cand["version"], "reason": "Initial team desk assignment"},
    )
    assert r_assign.status_code == 200, r_assign.text
    updated = r_assign.json()
    assert updated["current_group_id"] == core_bench_gid
    # Auto-transitions to BENCH upon assignment
    assert updated["status"] == "BENCH"
    assert updated["version"] == cand["version"] + 2  # assign bump + bench bump


def test_transfer_transaction(H, groups):
    gids = list(groups.values())
    if len(gids) < 2:
        pytest.skip("Requires at least two groups to test transfer")

    from_gid, to_gid = gids[0], gids[1]

    # Create candidate assigned to from_gid
    cand = requests.post(f"{API}/candidates", headers=H["ops"], json={
        "first_name": "Transferable",
        "last_name": f"Consultant-{uuid.uuid4().hex[:6]}",
        "group_id": from_gid,
    }).json()

    cid = cand["id"]
    version = cand["version"]

    # Transfer candidate to to_gid
    r_transfer = requests.post(
        f"{API}/candidates/{cid}/transfer",
        headers=H["ops"],
        json={"to_group_id": to_gid, "version": version, "reason": "Reassigned to specialized cloud desk"},
    )
    assert r_transfer.status_code == 200, r_transfer.text
    transferred = r_transfer.json()
    assert transferred["current_group_id"] == to_gid

    # Candidate detail history should show exactly 1 active assignment
    r_detail = requests.get(f"{API}/candidates/{cid}", headers=H["ops"])
    assert r_detail.status_code == 200
    detail = r_detail.json()
    active_assignments = [h for h in detail["assignment_history"] if h["active"]]
    assert len(active_assignments) == 1
    assert active_assignments[0]["group_id"] == to_gid


def test_unassign_from_marketing_requires_explicit_status(H, groups):
    gid = list(groups.values())[0]

    cand = requests.post(f"{API}/candidates", headers=H["ops"], json={
        "first_name": "MarketingUnassign",
        "last_name": f"Test-{uuid.uuid4().hex[:6]}",
        "group_id": gid,
    }).json()
    cid = cand["id"]

    # Transition to MARKETING
    r_mkt = requests.post(
        f"{API}/candidates/{cid}/transition",
        headers=H["ops"],
        json={"to_status": "MARKETING", "version": cand["version"], "reason": "Ready for client submissions"},
    )
    assert r_mkt.status_code == 200
    mkt_version = r_mkt.json()["version"]

    # Attempting to unassign without choosing target_status (BENCH vs ON_HOLD) MUST FAIL
    r_fail = requests.post(
        f"{API}/candidates/{cid}/unassign",
        headers=H["ops"],
        json={"version": mkt_version, "reason": "Removing from desk"},
    )
    assert r_fail.status_code == 422

    # Providing explicit target_status succeeds
    r_ok = requests.post(
        f"{API}/candidates/{cid}/unassign",
        headers=H["ops"],
        json={"version": mkt_version, "target_status": "BENCH", "reason": "Removing from marketing back to bench"},
    )
    assert r_ok.status_code == 200
    res = r_ok.json()
    assert res["status"] == "BENCH"
    assert res["current_group_id"] is None


import asyncio
import csv
import io

from core import db, logger, now, new_id, redact, candidate_scope, notify, load_groups, EMP
from storage import get_object

EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!H+H*"
SAFE_EXT = {"pdf", "doc", "docx", "txt", "rtf", "png", "jpg", "jpeg"}
EXPORT_COLS = ["id", "first_name", "last_name", "email", "phone", "status", "primary_skill", "skills", "experience_years",
               "location", "visa_status", "group_name", "pay_rate", "bill_rate", "target_rate", "created_at"]


async def run_scan(job):
    """SIMULATED malware scan: extension allowlist, size and EICAR signature check."""
    d = await db.documents.find_one({"id": job["payload"]["document_id"]}, {"_id": 0})
    if not d:
        return {"error": "document missing"}
    await asyncio.sleep(2)
    ext = d["original_filename"].rsplit(".", 1)[-1].lower() if "." in d["original_filename"] else ""
    reason = None
    try:
        data, _ = get_object(d["storage_path"])
        if EICAR in data:
            reason = "Malware signature detected (EICAR test)"
        elif data[:2] == b"MZ":
            reason = "Executable content detected"
    except Exception as e:
        reason = f"Unable to read object: {e}"
    if not reason and ext not in SAFE_EXT:
        reason = f"File type .{ext} not allowed"
    status = "FAILED" if reason else "PASSED"
    await db.documents.update_one({"id": d["id"]}, {"$set": {"scan_status": status, "scan_reason": reason, "scanned_at": now()}})
    await db.timeline.insert_one({"id": new_id(), "organization_id": d["organization_id"], "candidate_id": d["candidate_id"],
                                  "event": "DOCUMENT_SCAN_" + status, "detail": f"{d['original_filename']}: {reason or 'clean'} (simulated scanner)",
                                  "actor_name": "System", "created_at": now(), "meta": {}})
    await notify(d["organization_id"], [d["uploaded_by"]], f"Document scan {status.lower()}", f"{d['original_filename']}: {reason or 'clean'}", f"/candidates/{d['candidate_id']}")
    return {"scan_status": status, "reason": reason}


async def run_export(job):
    user = await db.users.find_one({"id": job["created_by"]}, {"_id": 0})
    user["_groups"] = await load_groups(user) if user["role"] == EMP else {}
    groups = {g["id"]: g["name"] for g in await db.groups.find({"organization_id": user["organization_id"]}, {"_id": 0}).to_list(500)}
    f = candidate_scope(user)
    flt = job["payload"].get("filters") or {}
    if flt.get("status"):
        f["status"] = {"$in": flt["status"].split(",")}
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=EXPORT_COLS, extrasaction="ignore")
    w.writeheader()
    n = 0
    async for c in db.candidates.find(f, {"_id": 0}):
        r = redact(user, c)
        r["skills"] = "; ".join(r.get("skills") or [])
        r["group_name"] = groups.get(c.get("current_group_id"))
        for k in ("pay_rate", "bill_rate", "target_rate"):
            if r.get(k) is None and k in (r.get("_redacted") or []):
                r[k] = "REDACTED"
        w.writerow(r)
        n += 1
    await db.bg_jobs.update_one({"id": job["id"]}, {"$set": {"result_csv": out.getvalue()}})
    await notify(user["organization_id"], [user["id"]], "Export ready", f"{n} candidates exported")
    return {"rows": n}


async def run_import(job):
    from candidates import norm_email, norm_phone, find_duplicates
    created, skipped, errors = 0, 0, []
    for i, row in enumerate(job["payload"]["rows"], start=2):
        fn, ln = (row.get("first_name") or "").strip(), (row.get("last_name") or "").strip()
        if not fn or not ln:
            errors.append(f"Row {i}: missing name")
            skipped += 1
            continue
        exact, _ = await find_duplicates(job["organization_id"], row.get("email"), row.get("phone"), None, None)
        if exact:
            errors.append(f"Row {i}: duplicate of {exact[0]['first_name']} {exact[0]['last_name']} ({exact[0]['match']})")
            skipped += 1
            continue
        cid = new_id()
        try:
            exp = float(row.get("experience_years") or 0) or None
        except ValueError:
            exp = None
        await db.candidates.insert_one({
            "id": cid, "organization_id": job["organization_id"], "first_name": fn, "last_name": ln, "email": row.get("email") or None,
            "phone": row.get("phone") or None, "email_norm": norm_email(row.get("email")), "phone_norm": norm_phone(row.get("phone")),
            "primary_skill": row.get("primary_skill") or None, "skills": [s.strip() for s in (row.get("skills") or "").split(";") if s.strip()],
            "experience_years": exp, "location": row.get("location") or None, "visa_status": row.get("visa_status") or None,
            "status": "NEW", "current_group_id": None, "owner_id": None, "version": 1, "source": "CSV Import",
            "created_by": job["created_by"], "created_at": now(), "updated_at": now(), "bench_since": None})
        await db.timeline.insert_one({"id": new_id(), "organization_id": job["organization_id"], "candidate_id": cid, "event": "CREATED",
                                      "detail": f"Imported from {job['payload'].get('filename')}", "actor_name": job.get("created_by_name"), "created_at": now(), "meta": {}})
        created += 1
    await notify(job["organization_id"], [job["created_by"]], "Import finished", f"{created} created, {skipped} skipped")
    return {"created": created, "skipped": skipped, "errors": errors[:200]}


HANDLERS = {"SCAN": run_scan, "EXPORT_CANDIDATES": run_export, "IMPORT_CANDIDATES": run_import}


async def process_outbox():
    async for m in db.outbox.find({"status": "PENDING"}).limit(50):
        logger.info(f"[MOCKED EMAIL] to={m['to']} subject={m['subject']!r}")
        await db.outbox.update_one({"id": m["id"]}, {"$set": {"status": "SENT_MOCK", "sent_at": now()}, "$inc": {"attempts": 1}})


async def worker_loop(types, outbox=False):
    while True:
        try:
            job = await db.bg_jobs.find_one_and_update({"status": "PENDING", "type": {"$in": types}}, {"$set": {"status": "RUNNING", "started_at": now()}}, sort=[("created_at", 1)])
            if job:
                try:
                    result = await HANDLERS[job["type"]](job)
                    await db.bg_jobs.update_one({"id": job["id"]}, {"$set": {"status": "COMPLETED", "result": result, "finished_at": now()}})
                except Exception as e:
                    logger.exception("job failed")
                    await db.bg_jobs.update_one({"id": job["id"]}, {"$set": {"status": "FAILED", "error": str(e), "finished_at": now()}})
                continue
            if outbox:
                await process_outbox()
        except Exception:
            logger.exception("worker loop error")
        await asyncio.sleep(1.5)

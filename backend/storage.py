import os
import requests

STORAGE_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
STORAGE_URL = STORAGE_BASE.rstrip("/") + "/objstore/api/v1/storage"
APP_NAME = "benchos"
storage_key = None


def init_storage(force: bool = False):
    global storage_key
    if storage_key and not force:
        return storage_key
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": os.environ.get("EMERGENT_LLM_KEY")}, timeout=30)
    resp.raise_for_status()
    storage_key = resp.json()["storage_key"]
    return storage_key


def put_object(path: str, data: bytes, content_type: str) -> dict:
    for attempt in (0, 1):
        resp = requests.put(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": init_storage(force=attempt == 1), "Content-Type": content_type}, data=data, timeout=120)
        if resp.status_code != 404:
            break
    resp.raise_for_status()
    return resp.json()


def get_object(path: str):
    for attempt in (0, 1):
        resp = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": init_storage(force=attempt == 1)}, timeout=60)
        if resp.status_code != 404:
            break
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")

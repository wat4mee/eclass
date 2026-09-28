"""State of the latest sync run, shared by sync.py (writer) and the dashboard (reader).

data/sync_status.json:
    {"state": "running" | "done" | "error", "started": ISO, "finished": ISO,
     "code": "login" | "network" | "other" | "stopped",       # only when state == "error"
     "new": [{"kind": "material" | "assignment" | "grade", "course": str, "name": str}],
     "counts": {...}}
"""
import fcntl
import json
import os
from pathlib import Path

STATUS_FILE = "sync_status.json"
LOCK_FILE = ".run.lock"


def read(data_dir):
    try:
        return json.loads((Path(data_dir) / STATUS_FILE).read_text())
    except (FileNotFoundError, ValueError):
        return {"state": "none"}


def write(data_dir, status):
    path = Path(data_dir) / STATUS_FILE
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(status, ensure_ascii=False))
    os.replace(tmp, path)  # atomic: readers never see half a file


def busy(data_dir):
    """True while a sync/analyze run holds the run lock."""
    path = Path(data_dir) / LOCK_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(f, fcntl.LOCK_UN)
        return False

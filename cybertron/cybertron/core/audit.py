#!/usr/bin/env python3
"""Cybertron Audit Logger — Every action, command, approval, and result."""
import json
import time
from pathlib import Path
from typing import Optional

AUDIT_DIR = Path.home() / ".cybertron" / "audit"
AUDIT_FILE = AUDIT_DIR / "audit.log"

def ensure_dir():
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)

def log(event_type: str, details: dict, session_id: Optional[str] = None, user: str = "local"):
    ensure_dir()
    entry = {
        "timestamp": int(time.time() * 1000),
        "type": event_type,
        "session_id": session_id,
        "user": user,
        "details": details,
    }
    with open(AUDIT_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")

def read_audit(limit: int = 100) -> list:
    if not AUDIT_FILE.exists():
        return []
    with open(AUDIT_FILE) as f:
        lines = f.readlines()
    entries = [json.loads(line) for line in lines if line.strip()]
    return entries[-limit:]

def export_audit(format: str = "json") -> str:
    entries = read_audit(limit=10000)
    if format == "json":
        return json.dumps(entries, indent=2)
    md = "# Cybertron Audit Log\n\n"
    for e in entries:
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(e["timestamp"] / 1000))
        md += f"## {e['type']} — {ts}\n\n"
        md += f"- **Session**: {e.get('session_id', 'N/A')}\n"
        md += f"- **User**: {e.get('user', 'N/A')}\n"
        md += f"- **Details**: \n```json\n{json.dumps(e['details'], indent=2)}\n```\n\n"
    return md

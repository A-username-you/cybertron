"""Audit Logger."""
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

CYBERTRON_HOME = Path.home() / ".cybertron"
AUDIT_LOG = CYBERTRON_HOME / "audit.log"


class AuditLogger:
    """Immutable audit log for all operations."""

    def __init__(self):
        CYBERTRON_HOME.mkdir(exist_ok=True)

    def log(self, event: str, user: str = "system", details: Dict[str, Any] = None):
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "event": event,
            "user": user,
            "details": details or {}
        }
        with open(AUDIT_LOG, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def get_logs(self, limit: int = 100) -> list:
        if not AUDIT_LOG.exists():
            return []
        with open(AUDIT_LOG) as f:
            lines = f.readlines()
        return [json.loads(l) for l in lines[-limit:]]

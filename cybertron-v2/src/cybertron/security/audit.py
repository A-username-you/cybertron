"""Audit Logger"""
import json
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
import structlog

logger = structlog.get_logger()


@dataclass
class AuditEvent:
    timestamp: str
    event_type: str
    actor: str
    target: str
    action: str
    result: str
    metadata: Dict[str, Any]
    hash_chain: str = ""

    def compute_hash(self, previous_hash: str = "") -> str:
        data = json.dumps(asdict(self), sort_keys=True, default=str)
        return hashlib.sha256(f"{previous_hash}{data}".encode()).hexdigest()


class AuditLogger:
    def __init__(self, log_path: Path):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._last_hash = self._load_last_hash()

    def _load_last_hash(self) -> str:
        if not self.log_path.exists():
            return "0" * 64
        try:
            with open(self.log_path, "r") as f:
                lines = f.readlines()
                if lines:
                    last = json.loads(lines[-1])
                    return last.get("hash_chain", "")
        except:
            pass
        return "0" * 64

    def log(self, event_type: str, actor: str, target: str, action: str,
            result: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        event = AuditEvent(
            timestamp=datetime.utcnow().isoformat(),
            event_type=event_type, actor=actor, target=target,
            action=action, result=result, metadata=metadata or {}
        )
        event.hash_chain = event.compute_hash(self._last_hash)
        self._last_hash = event.hash_chain
        with open(self.log_path, "a") as f:
            f.write(json.dumps(asdict(event), default=str) + "
")

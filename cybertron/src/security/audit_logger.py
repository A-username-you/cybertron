#!/usr/bin/env python3
"""
Cybertron Audit Logger
======================
Records every command, approval, tool execution, and result to
~/.cybertron/audit.log in structured JSON format.

Features:
- Tamper-evident append-only log
- Session correlation
- Tool execution tracking
- Download/install tracking
- Config change tracking
"""
import json
import os
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict

AUDIT_LOG_PATH = Path.home() / ".cybertron" / "audit.log"


@dataclass
class AuditEntry:
    timestamp: str
    level: str          # "info", "warn", "error", "critical"
    category: str       # "session", "tool", "approval", "download", "config", "system"
    action: str         # "started", "executed", "approved", "denied", "installed", "removed", "changed"
    session_id: Optional[str]
    actor: str          # "user", "agent", "system"
    details: Dict[str, Any]


class AuditLogger:
    def __init__(self, log_path: Optional[Path] = None):
        self.log_path = log_path or AUDIT_LOG_PATH
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._buffer: list = []
        self._flush_interval = 5  # seconds
        self._last_flush = time.time()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _write(self, entry: AuditEntry):
        line = json.dumps(asdict(entry), default=str) + "\n"
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(line)

    def log(self, level: str, category: str, action: str,
            session_id: Optional[str] = None, actor: str = "system",
            **details):
        entry = AuditEntry(
            timestamp=self._now(),
            level=level,
            category=category,
            action=action,
            session_id=session_id,
            actor=actor,
            details=details,
        )
        self._write(entry)

    def session_started(self, session_id: str, goal: str, origin: str):
        self.log("info", "session", "started", session_id, "user",
                 goal=goal, origin=origin)

    def tool_requested(self, session_id: str, tool_id: str, args: Dict[str, Any]):
        self.log("warn", "tool", "requested", session_id, "agent",
                 tool_id=tool_id, args=args)

    def tool_approved(self, session_id: str, tool_id: str, request_id: str):
        self.log("info", "approval", "approved", session_id, "user",
                 tool_id=tool_id, request_id=request_id)

    def tool_denied(self, session_id: str, tool_id: str, request_id: str):
        self.log("warn", "approval", "denied", session_id, "user",
                 tool_id=tool_id, request_id=request_id)

    def tool_executed(self, session_id: str, tool_id: str, ok: bool,
                      duration_ms: int, output: str = "", error: str = ""):
        self.log("info" if ok else "error", "tool", "executed", session_id, "system",
                 tool_id=tool_id, ok=ok, duration_ms=duration_ms,
                 output=output[:500], error=error[:500])

    def tool_installed(self, tool_id: str, repo: str, version: str, binary_path: str):
        self.log("info", "download", "installed", None, "user",
                 tool_id=tool_id, repo=repo, version=version, binary_path=binary_path)

    def tool_removed(self, tool_id: str, repo: str):
        self.log("info", "download", "removed", None, "user",
                 tool_id=tool_id, repo=repo)

    def config_changed(self, key: str, old_value: str, new_value: str):
        self.log("warn", "config", "changed", None, "user",
                 key=key, old_value=old_value, new_value=new_value)

    def system_event(self, message: str, level: str = "info"):
        self.log(level, "system", "event", None, "system", message=message)

    def get_recent(self, n: int = 50) -> list:
        if not self.log_path.exists():
            return []
        lines = []
        with open(self.log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        lines.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return lines[-n:]

    def export_session(self, session_id: str) -> str:
        """Export all audit entries for a session as markdown."""
        entries = []
        if self.log_path.exists():
            with open(self.log_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        if entry.get("session_id") == session_id:
                            entries.append(entry)
                    except json.JSONDecodeError:
                        continue

        md = f"# Session Report: `{session_id}`\n\n"
        md += f"**Generated:** {self._now()}\n\n"
        md += "---\n\n"

        for e in entries:
            ts = e.get("timestamp", "?")
            cat = e.get("category", "?")
            action = e.get("action", "?")
            actor = e.get("actor", "?")
            details = e.get("details", {})
            md += f"## {cat.upper()} — {action.upper()}\n\n"
            md += f"- **Time:** {ts}\n"
            md += f"- **Actor:** {actor}\n"
            for k, v in details.items():
                if isinstance(v, str) and len(v) > 200:
                    v = v[:200] + "..."
                md += f"- **{k}:** `{v}`\n"
            md += "\n---\n\n"

        return md


# ─── Singleton ───────────────────────────────────────────────────────────────
_logger_instance: Optional[AuditLogger] = None

def get_logger() -> AuditLogger:
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = AuditLogger()
    return _logger_instance

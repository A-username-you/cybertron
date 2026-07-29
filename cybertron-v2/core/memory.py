#!/usr/bin/env python3
"""
Cybertron Memory — Session persistence, target recall, finding history.
"""
import json
import time
from pathlib import Path
from typing import Dict, List, Optional

MEMORY_DIR = Path.home() / ".cybertron" / "memory"
SESSIONS_FILE = MEMORY_DIR / "sessions.json"
FINDINGS_FILE = MEMORY_DIR / "findings.json"
TARGETS_FILE = MEMORY_DIR / "targets.json"

def ensure_dir():
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)

def save_session(session: dict):
    ensure_dir()
    sessions = load_sessions()
    sessions.append(session)
    # Keep last 200
    sessions = sessions[-200:]
    with open(SESSIONS_FILE, "w") as f:
        json.dump(sessions, f, indent=2)

def load_sessions() -> List[dict]:
    if not SESSIONS_FILE.exists():
        return []
    with open(SESSIONS_FILE) as f:
        return json.load(f)

def save_finding(session_id: str, tool: str, finding: dict):
    ensure_dir()
    findings = load_findings()
    findings.append({
        "timestamp": int(time.time() * 1000),
        "session_id": session_id,
        "tool": tool,
        **finding,
    })
    with open(FINDINGS_FILE, "w") as f:
        json.dump(findings[-500:], f, indent=2)

def load_findings() -> List[dict]:
    if not FINDINGS_FILE.exists():
        return []
    with open(FINDINGS_FILE) as f:
        return json.load(f)

def save_target(target: str, metadata: Optional[dict] = None):
    ensure_dir()
    targets = load_targets()
    targets[target] = {
        "last_seen": int(time.time() * 1000),
        "metadata": metadata or {},
    }
    with open(TARGETS_FILE, "w") as f:
        json.dump(targets, f, indent=2)

def load_targets() -> Dict[str, dict]:
    if not TARGETS_FILE.exists():
        return {}
    with open(TARGETS_FILE) as f:
        return json.load(f)

def get_target_history(target: str) -> List[dict]:
    """Get all past sessions and findings for a target."""
    sessions = [s for s in load_sessions() if target in s.get("goal", "")]
    findings = [f for f in load_findings() if f.get("session_id") in [s["id"] for s in sessions]]
    return {"sessions": sessions, "findings": findings}

def generate_context(target: str) -> str:
    """Generate memory context for the agent about a target."""
    history = get_target_history(target)
    if not history["sessions"]:
        return ""

    context = f"Previous activity on target '{target}':\n"
    for s in history["sessions"][-5:]:
        ts = time.strftime("%Y-%m-%d", time.localtime(s.get("startedAt", 0) / 1000))
        context += f"- [{ts}] {s.get('goal', '')} → {s.get('state', 'unknown')}\n"

    if history["findings"]:
        context += "\nPast findings:\n"
        for f in history["findings"][-10:]:
            context += f"- [{f.get('tool', '?')}] {f.get('summary', 'finding')}\n"

    return context

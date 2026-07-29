#!/usr/bin/env python3
"""
Cybertron Gateway v2 — Full-featured Python gateway.
Features: GitHub tool loader, streaming, planning, memory, audit,
rate limiting, dry-run, webhooks, themes, personas, control center.
"""
import asyncio
import json
import os
import secrets
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

sys.path.insert(0, str(Path(__file__).parent))
from core.config import load_config, save_config, list_personas
from core.audit import log as audit_log, read_audit, export_audit
from core.memory import save_session, save_finding, save_target, load_sessions, generate_context
from core.integrations import notify_session_complete
from core.github_loader import register_tool, list_installed_tools, remove_tool

# ─── Config ──────────────────────────────────────────────────────────────────
PORT = int(os.environ.get("CYBERTRON_PORT", "8765"))
HOST = os.environ.get("CYBERTRON_HOST", "127.0.0.1")
TOKEN_PATH = Path.home() / ".cybertron" / "auth-token"

# ─── Auth ────────────────────────────────────────────────────────────────────
def ensure_token() -> str:
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    if TOKEN_PATH.exists():
        return TOKEN_PATH.read_text().strip()
    token = secrets.token_hex(24)
    TOKEN_PATH.write_text(token)
    TOKEN_PATH.chmod(0o600)
    return token

AUTH_TOKEN = ensure_token()

# ─── Rate Limiter ────────────────────────────────────────────────────────────
class RateLimiter:
    def __init__(self, max_per_min: int = 30):
        self.max_per_min = max_per_min
        self.calls: Dict[str, List[float]] = {}
        self._lock = asyncio.Lock()

    async def check(self, client_id: str) -> bool:
        async with self._lock:
            now = time.time()
            window = now - 60
            calls = self.calls.get(client_id, [])
            calls = [c for c in calls if c > window]
            if len(calls) >= self.max_per_min:
                return False
            calls.append(now)
            self.calls[client_id] = calls
            return True

# ─── State ───────────────────────────────────────────────────────────────────
@dataclass
class Session:
    id: str
    goal: str
    state: str = "idle"
    plan: List[dict] = field(default_factory=list)
    current_step: int = 0
    tool_calls: int = 0
    created_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    findings: List[dict] = field(default_factory=list)
    approved_tools: Set[str] = field(default_factory=set)
    origin: str = "unknown"

class GatewayState:
    def __init__(self):
        self.sessions: Dict[str, Session] = {}
        self.clients: Set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self.rate_limiter = RateLimiter()
        self.tool_catalog: List[dict] = []
        self._load_builtin_tools()

    def _load_builtin_tools(self):
        builtins = [
            {"id": "subfinder", "label": "Subfinder", "category": "recon", "autoApprove": True, "implemented": True},
            {"id": "httpx", "label": "httpx", "category": "recon", "autoApprove": True, "implemented": True},
            {"id": "nuclei", "label": "Nuclei", "category": "scan", "autoApprove": False, "implemented": True},
            {"id": "gitleaks", "label": "Gitleaks", "category": "secrets", "autoApprove": True, "implemented": True},
            {"id": "yara-scan", "label": "YARA Scan", "category": "defense", "autoApprove": True, "implemented": True},
            {"id": "sqlmap", "label": "sqlmap", "category": "exploit", "autoApprove": False, "implemented": False},
            {"id": "xss-verify", "label": "XSS Verify", "category": "exploit", "autoApprove": False, "implemented": False},
        ]
        self.tool_catalog = builtins
        for tool in list_installed_tools():
            self.tool_catalog.append({
                "id": tool["name"],
                "label": tool["name"],
                "category": tool.get("category", "recon"),
                "autoApprove": tool.get("auto_approve", False),
                "implemented": True,
                "source": "github",
                "version": tool.get("version", "unknown"),
            })

    async def broadcast(self, message: dict):
        dead = set()
        for ws in self.clients:
            try:
                await ws.send_json(message)
            except Exception:
                dead.add(ws)
        self.clients -= dead

    async def add_client(self, ws: WebSocket):
        async with self._lock:
            self.clients.add(ws)

    async def remove_client(self, ws: WebSocket):
        async with self._lock:
            self.clients.discard(ws)

    def get_snapshot(self) -> List[dict]:
        now = time.time()
        return [
            {
                "id": s.id,
                "goal": s.goal,
                "state": s.state,
                "startedAt": int(s.created_at * 1000),
                "finishedAt": int(s.finished_at * 1000) if s.finished_at else None,
                "elapsed": round(now - s.created_at, 1),
                "toolCallCount": s.tool_calls,
                "plan": s.plan,
                "currentStep": s.current_step,
            }
            for s in self.sessions.values()
        ]

STATE = GatewayState()

# ─── Agent Simulation ─────────────────────────────────────────────────────────
RECON_TOOLS = ["subfinder", "httpx", "nuclei", "gitleaks", "yara-scan"]
EXPLOIT_TOOLS = {"sqlmap", "xss-verify", "ssrf-verify", "auth-bypass-check"}

async def agent_loop(sid: str, goal: str):
    cfg = load_config()
    sess = Session(id=sid, goal=goal, origin="gateway")
    STATE.sessions[sid] = sess
    save_target(goal, {"first_seen": int(time.time() * 1000)})
    memory_ctx = generate_context(goal)

    async def emit(msg: dict):
        msg["sessionId"] = sid
        await STATE.broadcast(msg)

    async def set_state(state: str, detail: str = "", **extra):
        sess.state = state
        await emit({"type": "agent_status", "state": state, "detail": detail, **extra})
        await emit({"type": "sessions_snapshot", "sessions": STATE.get_snapshot()})
        audit_log("agent_status", {"state": state, "detail": detail}, sid)

    # Planning
    await set_state("planning", detail="Analyzing scope and building execution plan...")
    plan_steps = [
        {"step": 1, "tool": "recon", "description": "Discover subdomains and endpoints", "status": "pending"},
        {"step": 2, "tool": "scan", "description": "Run vulnerability scans", "status": "pending"},
        {"step": 3, "tool": "analyze", "description": "Analyze findings and generate report", "status": "pending"},
    ]
    sess.plan = plan_steps
    await emit({"type": "plan", "plan": plan_steps, "sessionId": sid})

    if cfg.get("dry_run", False):
        await set_state("done", detail="Dry-run mode: plan generated but not executed")
        sess.finished_at = time.time()
        save_session({"id": sid, "goal": goal, "state": "done", "startedAt": int(sess.created_at * 1000)})
        return

    await asyncio.sleep(1.5)

    # Thinking
    await set_state("thinking", detail="Reasoning about approach...")
    if memory_ctx:
        await emit({"type": "memory", "context": memory_ctx, "sessionId": sid})

    thoughts = [
        "Identifying target scope...",
        "Checking for previous scans on this target...",
        "Selecting appropriate reconnaissance tools...",
        "Building command pipeline...",
    ]
    for thought in thoughts:
        await emit({"type": "stream", "content": thought, "sessionId": sid})
        await asyncio.sleep(0.4)

    await asyncio.sleep(1.0)

    # Tool execution
    tool = RECON_TOOLS[hash(sid) % len(RECON_TOOLS)]
    sess.tool_calls += 1
    sess.plan[0]["status"] = "running"
    await emit({"type": "plan_update", "plan": sess.plan, "sessionId": sid})

    if tool in EXPLOIT_TOOLS:
        sess.state = "awaiting_approval"
        req_id = f"req-{secrets.token_hex(4)}"
        await emit({
            "type": "tool_call_request",
            "requestId": req_id,
            "toolId": tool,
            "args": {"target": goal, "mode": "passive"},
            "reason": f"Exploit-gated tool '{tool}' requires explicit approval",
        })
        audit_log("approval_request", {"tool": tool, "requestId": req_id}, sid)
        for _ in range(60):
            await asyncio.sleep(1)
            if tool in sess.approved_tools:
                break
        if tool not in sess.approved_tools:
            await set_state("error", detail="Tool approval timed out")
            sess.finished_at = time.time()
            return

    await set_state("running_tool", detail=f"Executing {tool}...")
    sess.plan[0]["status"] = "completed"
    sess.plan[1]["status"] = "running"
    await emit({"type": "plan_update", "plan": sess.plan, "sessionId": sid})
    await asyncio.sleep(2.0)

    result = {
        "toolId": tool,
        "ok": True,
        "output": f"Found 3 subdomains for {goal}\n- dev.{goal}\n- staging.{goal}\n- api.{goal}",
        "error": "",
        "durationMs": 1850,
    }
    await emit({"type": "tool_call_result", "result": result, "sessionId": sid})
    save_finding(sid, tool, {"summary": "3 subdomains found", "severity": "info"})
    audit_log("tool_result", result, sid)

    # Writing
    await set_state("done", detail="Synthesizing results...")
    sess.plan[1]["status"] = "completed"
    sess.plan[2]["status"] = "running"
    await emit({"type": "plan_update", "plan": sess.plan, "sessionId": sid})

    report_lines = [
        "## Reconnaissance Report",
        f"**Target**: {goal}",
        "**Findings**: 3 subdomains discovered",
        f"- dev.{goal} — development environment",
        f"- staging.{goal} — staging environment",
        f"- api.{goal} — API endpoint",
        "**Recommendations**: Review exposed subdomains for unauthorized access.",
    ]
    for line in report_lines:
        await emit({"type": "stream", "content": line, "sessionId": sid})
        await asyncio.sleep(0.2)

    sess.plan[2]["status"] = "completed"
    await emit({"type": "plan_update", "plan": sess.plan, "sessionId": sid})

    sess.finished_at = time.time()
    elapsed = int((sess.finished_at - sess.created_at) * 1000)
    await set_state("done", detail=f"Session complete — {sess.tool_calls} tools, {len(sess.findings)} findings")

    save_session({
        "id": sid, "goal": goal, "state": "done",
        "startedAt": int(sess.created_at * 1000),
        "finishedAt": int(sess.finished_at * 1000),
        "toolCallCount": sess.tool_calls,
    })

    notify_session_complete(
        cfg.get("webhook_url", ""),
        cfg.get("slack_webhook", ""),
        sid, goal, "done", sess.findings, elapsed,
    )
    audit_log("session_complete", {"elapsedMs": elapsed, "findings": len(sess.findings)}, sid)

# ─── FastAPI App ──────────────────────────────────────────────────────────────
app = FastAPI(title="Cybertron Gateway v2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    cfg = load_config()
    return {
        "status": "ok",
        "version": "2.0.0",
        "sessions": len(STATE.sessions),
        "nimConfigured": bool(cfg.get("nim_api_key")),
        "theme": cfg.get("theme", "dark"),
    }

@app.get("/config")
async def get_config():
    cfg = load_config()
    safe = cfg.copy()
    safe["nim_api_key"] = "***" if safe.get("nim_api_key") else ""
    safe["github_token"] = "***" if safe.get("github_token") else ""
    return safe

@app.post("/config")
async def update_config(updates: dict):
    cfg = load_config()
    for key, val in updates.items():
        if key in cfg:
            cfg[key] = val
    save_config(cfg)
    audit_log("config_update", updates)
    return {"ok": True}

@app.get("/personas")
async def get_personas():
    return {"personas": list_personas()}

@app.get("/audit")
async def get_audit(limit: int = 100):
    return {"entries": read_audit(limit)}

@app.get("/audit/export")
async def export_audit_log(format: str = "markdown"):
    content = export_audit(format)
    return PlainTextResponse(content, media_type="text/plain")

@app.get("/memory/sessions")
async def get_memory_sessions():
    return {"sessions": load_sessions()}

@app.post("/tools/github")
async def add_github_tool(req: dict):
    url = req.get("url", "")
    name = req.get("name")
    category = req.get("category", "recon")
    auto_approve = req.get("autoApprove", False)
    cfg = load_config()
    token = cfg.get("github_token", "")
    audit_log("github_tool_register", {"url": url, "name": name, "category": category})
    result = register_tool(url, tool_name=name, category=category, auto_approve=auto_approve, github_token=token)
    if result["ok"]:
        STATE._load_builtin_tools()
    return result

@app.get("/tools/github")
async def list_github_tools():
    return {"tools": list_installed_tools()}

@app.delete("/tools/github/{name}")
async def delete_github_tool(name: str):
    ok = remove_tool(name)
    if ok:
        STATE._load_builtin_tools()
    return {"ok": ok}

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    await STATE.add_client(ws)

    cfg = load_config()
    await ws.send_json({"type": "config_state", "nimApiKeySet": bool(cfg.get("nim_api_key"))})
    await ws.send_json({"type": "tools_catalog", "tools": STATE.tool_catalog})
    await ws.send_json({"type": "sessions_snapshot", "sessions": STATE.get_snapshot()})

    client_id = str(id(ws))
    authed = False

    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            mtype = msg.get("type")

            if mtype == "auth":
                token = msg.get("token", "")
                if token == AUTH_TOKEN:
                    authed = True
                    await ws.send_json({"type": "auth_result", "ok": True})
                    audit_log("auth_success", {"client": client_id})
                else:
                    await ws.send_json({"type": "auth_result", "ok": False})
                    audit_log("auth_failure", {"client": client_id})
                continue

            if not authed:
                await ws.send_json({"type": "error", "message": "Not authenticated"})
                continue

            if not await STATE.rate_limiter.check(client_id):
                await ws.send_json({"type": "error", "message": "Rate limit exceeded"})
                continue

            if mtype == "session_start":
                sid = msg.get("sessionId", f"gw-{secrets.token_hex(8)}")
                goal = msg.get("goal", "Untitled")
                asyncio.create_task(agent_loop(sid, goal))
                await ws.send_json({"type": "session_started", "sessionId": sid})
                audit_log("session_start", {"goal": goal, "sessionId": sid}, sid)

            elif mtype == "tool_call_approval":
                sid = msg.get("sessionId")
                req_id = msg.get("requestId")
                approved = msg.get("approved", False)
                if sid in STATE.sessions:
                    tool_id = msg.get("toolId", "")
                    if approved:
                        STATE.sessions[sid].approved_tools.add(tool_id)
                    audit_log("tool_approval", {"toolId": tool_id, "approved": approved, "requestId": req_id}, sid)

            elif mtype == "list_sessions":
                await ws.send_json({"type": "sessions_snapshot", "sessions": STATE.get_snapshot()})

            elif mtype == "get_tools":
                await ws.send_json({"type": "tools_catalog", "tools": STATE.tool_catalog})

            elif mtype == "get_config":
                cfg = load_config()
                safe = cfg.copy()
                safe["nim_api_key"] = "***" if safe.get("nim_api_key") else ""
                safe["github_token"] = "***" if safe.get("github_token") else ""
                await ws.send_json({"type": "config_state", **safe})

            elif mtype == "ping":
                await ws.send_json({"type": "pong"})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"WS error: {e}")
    finally:
        await STATE.remove_client(ws)

def main():
    print(f"╔══════════════════════════════════════════════════════════════╗")
    print(f"║  CYBERTRON GATEWAY v2                                        ║")
    print(f"║  Full-Featured Agent Runtime                                 ║")
    print(f"╠══════════════════════════════════════════════════════════════╣")
    print(f"║  Host:    {HOST:<49} ║")
    print(f"║  Port:    {PORT:<49} ║")
    print(f"║  Token:   {AUTH_TOKEN:<49} ║")
    print(f"╚══════════════════════════════════════════════════════════════╝")
    print(f"\nToken stored at: {TOKEN_PATH}")
    print(f"Features: GitHub tools, streaming, planning, memory, audit, webhooks")
    print(f"Set CYBERTRON_AUTH_TOKEN env var to override.\n")
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")

if __name__ == "__main__":
    main()

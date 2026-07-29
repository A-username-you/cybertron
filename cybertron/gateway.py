#!/usr/bin/env python3
"""
Cybertron Runtime Gateway
Red + Blue Team Agent — HTTP + WebSocket gateway
"""
import asyncio
import json
import os
import secrets
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Set
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# ─── Config ──────────────────────────────────────────────────────────────────
PORT = int(os.environ.get("CYBERTRON_PORT", "8765"))
HOST = os.environ.get("CYBERTRON_HOST", "127.0.0.1")
TOKEN_PATH = Path.home() / ".cybertron" / "auth-token"
SIMULATE_DELAYS = True  # Set False for instant responses

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

# ─── Data Models ─────────────────────────────────────────────────────────────
@dataclass
class Session:
    id: str
    goal: str
    state: str = "idle"          # idle | thinking | writing | result | awaiting_approval
    elapsed: float = 0.0
    tool_calls: int = 0
    created_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    current_tool: Optional[str] = None
    tool_args: Optional[dict] = None
    approved: bool = False

# ─── State ───────────────────────────────────────────────────────────────────
class GatewayState:
    def __init__(self):
        self.sessions: Dict[str, Session] = {}
        self.clients: Set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self._tasks: Dict[str, asyncio.Task] = {}

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

    def start_session(self, sid: str, goal: str) -> Session:
        sess = Session(id=sid, goal=goal)
        self.sessions[sid] = sess
        return sess

    def get_snapshot(self) -> List[dict]:
        now = time.time()
        return [
            {
                "id": s.id,
                "goal": s.goal,
                "state": s.state,
                "elapsed": round(now - s.created_at, 1),
                "toolCalls": s.tool_calls,
                "finishedAt": s.finished_at,
            }
            for s in self.sessions.values()
        ]

STATE = GatewayState()

# ─── Agent Simulation ──────────────────────────────────────────────────────────
EXPLOIT_TOOLS = {"sqlmap", "xss-verify", "ssrf-verify", "auth-bypass-check"}
RECON_TOOLS = ["subfinder", "httpx", "nuclei", "gitleaks", "yara-scan"]

async def agent_loop(sid: str, goal: str):
    """Simulate the agent lifecycle for a session."""
    sess = STATE.start_session(sid, goal)

    async def set_state(state: str, **extra):
        sess.state = state
        msg = {"type": "agent_status", "sessionId": sid, "status": state, **extra}
        await STATE.broadcast(msg)
        await STATE.broadcast({"type": "sessions_snapshot", "sessions": STATE.get_snapshot()})

    # Phase 1: Thinking
    await set_state("thinking", detail="Analyzing target scope and planning approach...")
    if SIMULATE_DELAYS:
        await asyncio.sleep(2.5)

    # Phase 2: Tool call (recon)
    tool = RECON_TOOLS[hash(sid) % len(RECON_TOOLS)]
    sess.tool_calls += 1
    sess.current_tool = tool

    if tool in EXPLOIT_TOOLS:
        sess.state = "awaiting_approval"
        sess.tool_args = {"target": "example.com", "mode": "passive"}
        await STATE.broadcast({
            "type": "tool_call_request",
            "sessionId": sid,
            "tool": tool,
            "args": sess.tool_args,
            "reason": f"Exploit-gated tool '{tool}' requires explicit approval",
        })
        # Wait for approval (with timeout)
        for _ in range(30):  # 30 seconds timeout
            await asyncio.sleep(1)
            if sess.approved:
                break
        if not sess.approved:
            await set_state("idle", detail="Tool approval timed out.")
            sess.finished_at = time.time()
            return

    await set_state("running_tool", detail=f"Executing {tool}...")
    if SIMULATE_DELAYS:
        await asyncio.sleep(2.0)

    # Tool result
    result = {"tool": tool, "ok": True, "findings": 2 if tool == "nuclei" else 0}
    await STATE.broadcast({
        "type": "tool_call_result",
        "sessionId": sid,
        "result": result,
    })

    # Phase 3: Writing output
    await set_state("writing", detail="Synthesizing results into report...")
    if SIMULATE_DELAYS:
        await asyncio.sleep(2.0)

    # Phase 4: Result burst
    await set_state("result", detail="Scan complete — 2 medium findings.")
    if SIMULATE_DELAYS:
        await asyncio.sleep(1.2)

    # Done
    sess.finished_at = time.time()
    await set_state("idle", detail="Session complete.")

# ─── FastAPI App ─────────────────────────────────────────────────────────────
app = FastAPI(title="Cybertron Gateway")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0", "sessions": len(STATE.sessions)}

@app.get("/auth")
async def auth_check(token: str = Query(...)):
    if token != AUTH_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid token")
    return {"ok": True}

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, token: str = Query(...)):
    if token != AUTH_TOKEN:
        await ws.close(code=4001, reason="Invalid auth token")
        return

    await ws.accept()
    await STATE.add_client(ws)

    # Send initial snapshot
    await ws.send_json({"type": "sessions_snapshot", "sessions": STATE.get_snapshot()})

    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            mtype = msg.get("type")

            if mtype == "session_start":
                sid = msg.get("sessionId", secrets.token_hex(8))
                goal = msg.get("goal", "Untitled session")
                task = asyncio.create_task(agent_loop(sid, goal))
                STATE._tasks[sid] = task
                await ws.send_json({"type": "session_started", "sessionId": sid})

            elif mtype == "tool_call_approval":
                sid = msg.get("sessionId")
                approved = msg.get("approved", False)
                if sid in STATE.sessions:
                    STATE.sessions[sid].approved = approved

            elif mtype == "sessions_request":
                await ws.send_json({"type": "sessions_snapshot", "sessions": STATE.get_snapshot()})

            elif mtype == "ping":
                await ws.send_json({"type": "pong"})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"WS error: {e}")
    finally:
        await STATE.remove_client(ws)

# ─── Main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"╔══════════════════════════════════════════════════════════════╗")
    print(f"║  CYBERTRON GATEWAY                                           ║")
    print(f"║  Red + Blue Team Agent Runtime                               ║")
    print(f"╠══════════════════════════════════════════════════════════════╣")
    print(f"║  Host:    {HOST:<49} ║")
    print(f"║  Port:    {PORT:<49} ║")
    print(f"║  Token:   {AUTH_TOKEN:<49} ║")
    print(f"╚══════════════════════════════════════════════════════════════╝")
    print(f"\nToken stored at: {TOKEN_PATH}")
    print(f"Set CYBERTRON_AUTH_TOKEN env var to override.\n")
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")

if __name__ == "__main__":
    main()

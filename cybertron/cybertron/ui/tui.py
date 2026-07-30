#!/usr/bin/env python3
"""Cybertron TUI — Rich terminal UI. Connects to Python gateway."""
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import websockets
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.align import Align
from rich.style import Style
from rich.spinner import Spinner
from rich.columns import Columns
from rich.prompt import Prompt

GATEWAY_HOST = os.environ.get("CYBERTRON_HOST", "127.0.0.1")
GATEWAY_PORT = int(os.environ.get("CYBERTRON_PORT", "8765"))
WS_URL = f"ws://{GATEWAY_HOST}:{GATEWAY_PORT}/ws"

THEME = {
    "bg": "#14141f", "fg": "#c0c0c0",
    "gold": "#FFD700", "amber": "#FFBF00", "bronze": "#CD7F32",
    "green": "#00ff88", "red": "#ff4444", "blue": "#4aa8ff",
    "dim": "#555555", "panel": "#1a1a2e", "border": "#333355",
    "success": "#00ff88", "warning": "#FFBF00", "error": "#ff4444",
}

console = Console()

@dataclass
class SessionInfo:
    id: str
    goal: str
    state: str
    startedAt: int
    finishedAt: Optional[int]
    toolCallCount: int

class CybertronTUI:
    def __init__(self):
        self.ws = None
        self.authed = False
        self.token = os.environ.get("CYBERTRON_AUTH_TOKEN", "")
        self.sessions: Dict[str, SessionInfo] = {}
        self.log_lines: List[str] = []
        self.pending_approvals: List[dict] = []
        self.connected = False
        self.current_state = "disconnected"
        self.current_detail = ""
        self.tool_catalog: List[dict] = []
        self.max_log_lines = 100

    def _make_layout(self) -> Layout:
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main"),
            Layout(name="status", size=3),
        )
        layout["main"].split_row(
            Layout(name="left", ratio=2),
            Layout(name="right", ratio=1),
        )
        layout["left"].split_column(
            Layout(name="sessions", ratio=1),
            Layout(name="log", ratio=1),
        )
        layout["right"].split_column(
            Layout(name="tools", ratio=1),
            Layout(name="approvals", ratio=1),
        )
        return layout

    def _header(self) -> Panel:
        title = Text("CYBERTRON", style=f"bold {THEME['gold']}")
        subtitle = Text(" v3.0.0 — Unified Security Agent", style=THEME["dim"])
        status = Text("● CONNECTED" if self.connected else "● DISCONNECTED", style=THEME["green"] if self.connected else THEME["red"])
        content = Columns([title + subtitle, status], align="center", expand=True)
        return Panel(content, style=Style(bgcolor=THEME["panel"], color=THEME["fg"]), border_style=THEME["gold"])

    def _sessions_panel(self) -> Panel:
        table = Table(show_header=True, header_style=f"bold {THEME['amber']}", border_style=THEME["border"], box=None)
        table.add_column("ID", style=THEME["fg"], width=12)
        table.add_column("Goal", style=THEME["fg"], min_width=20)
        table.add_column("State", style=THEME["fg"], width=16)
        table.add_column("Tools", style=THEME["fg"], width=6)
        table.add_column("Elapsed", style=THEME["fg"], width=10)
        for sid, s in list(self.sessions.items())[-8:]:
            state_color = {"idle": THEME["dim"], "thinking": THEME["blue"], "running_tool": THEME["amber"],
                           "awaiting_approval": THEME["warning"], "done": THEME["success"], "error": THEME["error"]}.get(s.state, THEME["fg"])
            elapsed = "—"
            if s.startedAt:
                elapsed = f"{int((time.time()*1000 - s.startedAt)/1000)}s"
            table.add_row(s.id[:10], s.goal[:28], Text(s.state, style=state_color), str(s.toolCallCount), elapsed)
        return Panel(table, title="[bold]Sessions", border_style=THEME["border"], style=Style(bgcolor=THEME["panel"]))

    def _log_panel(self) -> Panel:
        lines = self.log_lines[-12:]
        content = "\n".join(lines) if lines else Text("Waiting for activity...", style=THEME["dim"])
        return Panel(content, title="[bold]Live Log", border_style=THEME["border"], style=Style(bgcolor=THEME["panel"]))

    def _tools_panel(self) -> Panel:
        table = Table(show_header=False, box=None)
        table.add_column("Tool", style=THEME["fg"])
        table.add_column("Cat", style=THEME["dim"], width=8)
        for t in self.tool_catalog[:12]:
            icon = "✓" if t.get("implemented") else "✗"
            color = THEME["green"] if t.get("autoApprove") else THEME["warning"]
            table.add_row(f"[{color}]{icon}[/{color}] {t.get('label', t['id'])}", t.get("category", "?"))
        return Panel(table, title="[bold]Tools", border_style=THEME["border"], style=Style(bgcolor=THEME["panel"]))

    def _approvals_panel(self) -> Panel:
        if not self.pending_approvals:
            return Panel(Text("No pending approvals", style=THEME["dim"]), title="[bold]Approvals", border_style=THEME["border"], style=Style(bgcolor=THEME["panel"]))
        lines = []
        for a in self.pending_approvals:
            lines.append(f"[bold {THEME['warning']}]{a['toolId']}[/] ({a['sessionId'][:8]})")
        return Panel("\n".join(lines), title=f"[bold]Approvals ({len(self.pending_approvals)})", border_style=THEME["warning"], style=Style(bgcolor=THEME["panel"]))

    def _status_bar(self) -> Panel:
        state_color = {"disconnected": THEME["red"], "idle": THEME["dim"], "thinking": THEME["blue"],
                       "running_tool": THEME["amber"], "awaiting_approval": THEME["warning"],
                       "done": THEME["success"], "error": THEME["error"]}.get(self.current_state, THEME["fg"])
        content = Text()
        content.append(f"State: ", style=THEME["dim"])
        content.append(self.current_state.upper(), style=f"bold {state_color}")
        if self.current_detail:
            content.append(f"  |  {self.current_detail}", style=THEME["dim"])
        content.append(f"  |  Sessions: {len(self.sessions)}  |  Logs: {len(self.log_lines)}", style=THEME["dim"])
        return Panel(content, style=Style(bgcolor=THEME["panel"]), border_style=THEME["border"])

    def _render(self) -> Layout:
        layout = self._make_layout()
        layout["header"].update(self._header())
        layout["sessions"].update(self._sessions_panel())
        layout["log"].update(self._log_panel())
        layout["tools"].update(self._tools_panel())
        layout["approvals"].update(self._approvals_panel())
        layout["status"].update(self._status_bar())
        return layout

    def _log(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        self.log_lines.append(f"[{ts}] {msg}")
        self.log_lines = self.log_lines[-self.max_log_lines:]

    async def connect(self):
        while True:
            try:
                self.ws = await websockets.connect(WS_URL)
                self.connected = True
                self._log(f"Connected to {WS_URL}")
                if self.token:
                    await self.ws.send(json.dumps({"type": "auth", "token": self.token}))
                await self._listen()
            except Exception as e:
                self.connected = False
                self._log(f"Connection error: {e}")
                await asyncio.sleep(3)

    async def _listen(self):
        try:
            async for raw in self.ws:
                msg = json.loads(raw)
                await self._handle(msg)
        except websockets.exceptions.ConnectionClosed:
            self.connected = False
            self._log("Connection closed")

    async def _handle(self, msg: dict):
        mtype = msg.get("type")
        if mtype == "auth_result":
            self.authed = msg.get("ok", False)
            self._log("Auth " + ("OK" if self.authed else "FAILED"))
        elif mtype == "sessions_snapshot":
            for s in msg.get("sessions", []):
                self.sessions[s["id"]] = SessionInfo(
                    id=s["id"], goal=s.get("goal", ""), state=s.get("state", "idle"),
                    startedAt=s.get("startedAt", 0), finishedAt=s.get("finishedAt"),
                    toolCallCount=s.get("toolCallCount", 0),
                )
        elif mtype == "agent_status":
            self.current_state = msg.get("state", "idle")
            self.current_detail = msg.get("detail", "")
            self._log(f"Agent: {self.current_state} — {self.current_detail}")
        elif mtype == "stream":
            self._log(f"→ {msg.get('content', '')[:60]}")
        elif mtype == "tool_call_request":
            self.pending_approvals.append(msg)
            self._log(f"Approval needed: {msg.get('toolId')} ({msg.get('requestId')})")
        elif mtype == "tool_call_result":
            r = msg.get("result", {})
            self._log(f"Tool result: {r.get('toolId')} {'OK' if r.get('ok') else 'FAIL'}")
        elif mtype == "tools_catalog":
            self.tool_catalog = msg.get("tools", [])
        elif mtype == "error":
            self._log(f"Error: {msg.get('message', '')}")

    async def _input_loop(self):
        while True:
            await asyncio.sleep(0.1)
            if not self.connected or not self.authed:
                continue
            try:
                cmd = await asyncio.to_thread(Prompt.ask, "\n[cybertron]", console=console)
                cmd = cmd.strip()
                if not cmd:
                    continue
                if cmd.startswith("scan "):
                    target = cmd[5:].strip()
                    await self.ws.send(json.dumps({"type": "session_start", "goal": target}))
                    self._log(f"Started scan: {target}")
                elif cmd == "sessions":
                    await self.ws.send(json.dumps({"type": "list_sessions"}))
                elif cmd == "tools":
                    await self.ws.send(json.dumps({"type": "get_tools"}))
                elif cmd.startswith("approve "):
                    parts = cmd.split()
                    if len(parts) >= 3:
                        await self.ws.send(json.dumps({"type": "tool_call_approval", "sessionId": parts[1], "requestId": parts[2], "approved": True}))
                        self.pending_approvals = [a for a in self.pending_approvals if a.get("requestId") != parts[2]]
                elif cmd == "quit" or cmd == "exit":
                    break
                else:
                    self._log(f"Unknown command: {cmd}")
            except Exception as e:
                self._log(f"Input error: {e}")

    async def run(self):
        with Live(self._render(), screen=True, refresh_per_second=4, console=console) as live:
            asyncio.create_task(self.connect())
            asyncio.create_task(self._input_loop())
            while True:
                live.update(self._render())
                await asyncio.sleep(0.25)

if __name__ == "__main__":
    tui = CybertronTUI()
    try:
        asyncio.run(tui.run())
    except KeyboardInterrupt:
        console.print("\n[bold]Goodbye.[/]")

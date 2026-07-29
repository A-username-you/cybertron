#!/usr/bin/env python3
"""
Cybertron TUI (Python) — connects to the Node.js runtime gateway.
Uses Rich for rendering. Matches the Ink TUI protocol exactly.
"""
import asyncio
import json
import os
import secrets
import sys
import threading
import time
from pathlib import Path
from typing import Optional, List, Dict, Any

import websockets
from rich.align import Align
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.style import Style
from rich.table import Table
from rich.text import Text

# ─── Config ──────────────────────────────────────────────────────────────────
GATEWAY_HOST = os.environ.get("CYBERTRON_HOST", "127.0.0.1")
GATEWAY_PORT = int(os.environ.get("CYBERTRON_PORT", "8765"))
WS_URL = f"ws://{GATEWAY_HOST}:{GATEWAY_PORT}"
TOKEN_PATH = Path.home() / ".cybertron" / "auth-token"

RECONNECT_BASE_MS = 1000
RECONNECT_MAX_MS = 10000

# ─── Hermes Palette ──────────────────────────────────────────────────────────
GOLD = "#FFD700"
AMBER = "#FFBF00"
BRONZE = "#CD7F32"
CORNSILK = "#FFF8DC"
TEAL = "#4dd0e1"
ERROR = "#ef5350"
WARN = "#ffa726"
DIM = "#B8860B"
SURFACE_0 = "#14141f"
SURFACE_1 = "#1a1a2e"
SURFACE_2 = "#333355"
BORDER = "#CD7F32"
TEXT_PRIMARY = "#FFF8DC"
TEXT_MUTED = "#B8860B"
OK = "#4caf50"

SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

# ─── State ────────────────────────────────────────────────────────────────────
class TUIState:
    def __init__(self):
        self.connected = False
        self.authed = False
        self.status = "connecting"
        self.agent_state = "idle"
        self.logs: List[Dict[str, Any]] = []
        self.sessions: List[Dict[str, Any]] = []
        self.show_sessions = False
        self.pending_approval: Optional[Dict[str, Any]] = None
        self.turn_started_at: Optional[int] = None
        self.reconnect_in: Optional[int] = None
        self.ws = None
        self._running = True
        self._input_buffer = ""
        self.frame = 0
        self.current_session_id = self.new_session_id()
        self.reconnect_attempt = 0
        self.reconnect_timer = None

    def new_session_id(self):
        return f"tui-{int(time.time()*1000)}-{secrets.token_hex(3)}"

STATE = TUIState()
console = Console()

# ─── Helpers ─────────────────────────────────────────────────────────────────
def session_color(state: str) -> str:
    if state == "error": return ERROR
    if state == "done": return OK
    if state == "awaiting_approval": return WARN
    return AMBER

def elapsed(started_at: int, finished_at: Optional[int] = None) -> str:
    ms = (finished_at or int(time.time()*1000)) - started_at
    return f"{(ms/1000):.1f}s"

# ─── Layout ──────────────────────────────────────────────────────────────────
def build_layout() -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body"),
        Layout(name="footer", size=3),
    )
    return layout

def make_header() -> Panel:
    conn_color = OK if STATE.authed else WARN if STATE.connected else ERROR
    conn_text = "ONLINE" if STATE.authed else "AUTHING" if STATE.connected else "OFFLINE"
    status = Text(conn_text, style=Style(color=conn_color, bold=True))
    title = Text("CYBERTRON", style=Style(color=GOLD, bold=True))
    subtitle = Text("  Agent Console", style=Style(color=TEXT_MUTED))
    view = Text("[S]erver" if not STATE.show_sessions else "[S]ession", style=Style(color=AMBER))
    sep = Text("  │  ", style=Style(color=BRONZE))
    content = Text.assemble(title, subtitle, sep, status, sep, view)
    return Panel(content, style=Style(bgcolor=SURFACE_1), border_style=Style(color=BORDER))

def make_body(frame: int) -> Panel:
    if STATE.show_sessions:
        return make_sessions_panel()
    return make_log_panel(frame)

def make_log_panel(frame: int) -> Panel:
    content = Text()

    # Status line
    glyph = "?"
    glyph_color = WARN
    if STATE.pending_approval:
        glyph = "?"
        glyph_color = WARN
    elif STATE.agent_state in ("thinking", "running_tool"):
        glyph = SPINNER_FRAMES[(frame // 2) % len(SPINNER_FRAMES)]
        glyph_color = AMBER
    elif STATE.agent_state == "done":
        glyph = "✧"
        glyph_color = TEAL
    elif STATE.agent_state == "error":
        glyph = "✕"
        glyph_color = ERROR
    else:
        glyph = "●"
        glyph_color = BRONZE

    turn_elapsed = ""
    if STATE.turn_started_at and STATE.agent_state not in ("done", "error", "idle"):
        turn_elapsed = f"  turn {((time.time()*1000 - STATE.turn_started_at)/1000):.1f}s"

    recon = ""
    if STATE.reconnect_in is not None:
        recon = f"  reconnecting in {STATE.reconnect_in}s"

    status_line = Text.assemble(
        Text(glyph, style=Style(color=glyph_color, bold=True)),
        "  ",
        Text("cybertron", style=Style(color=GOLD, bold=True)),
        "  — ",
        Text(STATE.status, style=Style(color=TEXT_PRIMARY)),
        Text(turn_elapsed, style=Style(color=DIM)),
        Text(recon, style=Style(color=WARN)),
    )
    content.append(status_line)
    content.append("\n\n")

    # Approval prompt
    if STATE.pending_approval:
        content.append(Text.assemble(
            Text("approval required: ", style=Style(color=WARN, bold=True)),
            Text(STATE.pending_approval["toolId"], style=Style(color=AMBER, bold=True)),
            "\n",
            Text(json.dumps(STATE.pending_approval["args"], indent=2), style=Style(color=TEXT_MUTED)),
            "\n",
            Text("y to approve · n to deny", style=Style(color=DIM)),
        ))
        content.append("\n\n")

    # Logs
    if not STATE.logs:
        content.append(Text("no activity yet — type a goal and press enter", style=Style(color=TEXT_MUTED, dim=True)))
    else:
        for line in STATE.logs[-20:]:
            color = line.get("color", TEXT_MUTED)
            content.append(Text(line["text"], style=Style(color=color)))
            content.append("\n")

    return Panel(content, title="[bold]Transcript[/bold]", border_style=Style(color=TEAL), style=Style(bgcolor=SURFACE_0))

def make_sessions_panel() -> Panel:
    content = Text()
    content.append(Text("server view — every session on this gateway\n\n", style=Style(color=TEXT_PRIMARY, bold=True)))

    if not STATE.sessions:
        content.append(Text("no sessions yet", style=Style(color=TEXT_MUTED)))
    else:
        table = Table(show_header=False, box=None, pad_edge=False, border_style=Style(color=SURFACE_2))
        table.add_column(style=Style(color=session_color("")), width=18)
        table.add_column(style=Style(color=TEXT_PRIMARY), width=10)
        table.add_column(style=Style(color=TEXT_MUTED), width=8)
        table.add_column(style=Style(color=TEXT_MUTED))

        for s in STATE.sessions:
            state = s.get("state", "idle")
            started = s.get("startedAt", 0)
            finished = s.get("finishedAt")
            goal = s.get("goal", "")[:40]
            table.add_row(
                state.ljust(18),
                elapsed(started, finished),
                f"calls:{s.get('toolCallCount', 0)}",
                goal
            )
        content.append(table)

    return Panel(content, title="[bold]Sessions[/bold]", border_style=Style(color=AMBER), style=Style(bgcolor=SURFACE_0))

def make_footer() -> Panel:
    if STATE.pending_approval:
        prompt = Text("APPROVE? [Y/N]: ", style=Style(color=WARN, bold=True))
    else:
        prompt = Text("❯ ", style=Style(color=TEAL, bold=True))
    input_text = Text(STATE._input_buffer, style=Style(color=CORNSILK))
    cursor = Text("█", style=Style(color=AMBER, blink=True))
    content = Text.assemble(prompt, input_text, cursor)
    return Panel(content, style=Style(bgcolor=SURFACE_1), border_style=Style(color=BORDER))

# ─── WebSocket Client ─────────────────────────────────────────────────────────
async def ws_client():
    token = ""
    if TOKEN_PATH.exists():
        token = TOKEN_PATH.read_text().strip()
    if not token:
        console.print(f"[red]No auth token found at {TOKEN_PATH}. Start the gateway first.[/red]")
        return

    while STATE._running:
        try:
            async with websockets.connect(WS_URL) as ws:
                STATE.ws = ws
                STATE.connected = True
                STATE.reconnect_in = None
                STATE.reconnect_attempt = 0
                STATE.status = "authenticating"
                await ws.send(json.dumps({"type": "auth", "token": token}))

                async for raw in ws:
                    if not STATE._running:
                        break
                    try:
                        event = json.loads(raw)
                        handle_event(event)
                    except json.JSONDecodeError:
                        pass
        except Exception as e:
            STATE.connected = False
            STATE.authed = False
            STATE.status = "disconnected"
            if STATE._running:
                attempt = STATE.reconnect_attempt
                delay_ms = min(RECONNECT_BASE_MS * (2 ** attempt), RECONNECT_MAX_MS)
                STATE.reconnect_attempt = attempt + 1
                remaining = round(delay_ms / 1000)
                STATE.reconnect_in = remaining

                # Countdown
                for _ in range(remaining):
                    if not STATE._running:
                        break
                    await asyncio.sleep(1)
                    STATE.reconnect_in -= 1
                STATE.reconnect_in = None

def handle_event(event: dict):
    etype = event.get("type")

    if etype == "auth_result":
        STATE.authed = event.get("ok", False)
        if STATE.authed:
            STATE.status = "idle"
        else:
            STATE.status = "auth rejected — token file may be stale"
        return

    if etype == "agent_status":
        sid = event.get("sessionId")
        if sid == STATE.current_session_id:
            state = event.get("state", "idle")
            detail = event.get("detail", "")
            STATE.agent_state = state
            STATE.status = f"{state}: {detail}" if detail else state
            if state == "thinking":
                STATE.turn_started_at = int(time.time() * 1000)
            if state in ("done", "error"):
                STATE.turn_started_at = None
                STATE.pending_approval = None
            if state != "awaiting_approval":
                STATE.pending_approval = None
        return

    if etype == "tool_call_request":
        sid = event.get("sessionId")
        if sid == STATE.current_session_id:
            STATE.pending_approval = {
                "sessionId": event.get("sessionId"),
                "requestId": event.get("requestId"),
                "toolId": event.get("toolId"),
                "args": event.get("args", {}),
            }
        return

    if etype == "tool_call_result":
        sid = event.get("sessionId")
        if sid == STATE.current_session_id:
            tool_id = event.get("toolId", "?")
            ok = event.get("ok", False)
            output = event.get("output", "")
            error = event.get("error", "")
            duration = event.get("durationMs", 0)
            if ok:
                text = f"[{tool_id}] ok ({duration}ms)\n{output}"
                color = OK
            else:
                text = f"[{tool_id}] error ({duration}ms)\n{error}"
                color = ERROR
            STATE.logs.append({"text": text, "color": color})
        return

    if etype == "sessions_snapshot":
        STATE.sessions = event.get("sessions", [])
        return

    if etype == "config_state":
        nim_set = event.get("nimApiKeySet", False)
        nim_src = event.get("nimApiKeySource", "")
        if not nim_set:
            add_log("NIM API key not set — agent will not respond. Use Control Center to configure.", WARN)
        return

    if etype == "tools_catalog":
        tools = event.get("tools", [])
        implemented = sum(1 for t in tools if t.get("implemented"))
        add_log(f"{implemented} of {len(tools)} tools have real handlers", DIM)
        return

def add_log(text: str, color: str = TEXT_MUTED):
    STATE.logs.append({"text": text, "color": color})
    if len(STATE.logs) > 200:
        STATE.logs = STATE.logs[-100:]

# ─── Input Handler ────────────────────────────────────────────────────────────
def input_thread():
    import termios
    import tty
    import select
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        while STATE._running:
            if select.select([sys.stdin], [], [], 0.1)[0]:
                ch = sys.stdin.read(1)
                if ch == '\x03':  # Ctrl-C
                    STATE._running = False
                    break
                elif ch == '\x7f':  # Backspace
                    STATE._input_buffer = STATE._input_buffer[:-1]
                elif ch == '\r':  # Enter
                    handle_submit()
                elif ch.lower() == 's' and not STATE._input_buffer and not STATE.pending_approval:
                    STATE.show_sessions = not STATE.show_sessions
                    if STATE.show_sessions and STATE.ws and STATE.connected and STATE.authed:
                        asyncio.run_coroutine_threadsafe(
                            STATE.ws.send(json.dumps({"type": "list_sessions"})),
                            loop=asyncio.get_event_loop()
                        )
                elif ch.lower() == 'y' and STATE.pending_approval:
                    send_approval(True)
                elif ch.lower() == 'n' and STATE.pending_approval:
                    send_approval(False)
                elif ch.isprintable():
                    STATE._input_buffer += ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

def handle_submit():
    buf = STATE._input_buffer.strip()
    STATE._input_buffer = ""
    if not buf:
        return
    if STATE.pending_approval:
        if buf.lower() in ('y', 'yes'):
            send_approval(True)
        elif buf.lower() in ('n', 'no'):
            send_approval(False)
        return
    if STATE.ws and STATE.connected and STATE.authed:
        working = STATE.agent_state in ("thinking", "running_tool")
        if working:
            add_log("A session is already running — wait for it to finish or start a new one.", WARN)
            return
        STATE.current_session_id = STATE.new_session_id()
        STATE.logs = []  # fresh view for new session
        msg = json.dumps({
            "type": "session_start",
            "sessionId": STATE.current_session_id,
            "goal": buf,
            "origin": "cli"
        })
        asyncio.run_coroutine_threadsafe(STATE.ws.send(msg), loop=asyncio.get_event_loop())
        add_log(f"> {buf}", AMBER)
    else:
        add_log("Not connected to gateway", ERROR)

def send_approval(approved: bool):
    if STATE.ws and STATE.pending_approval:
        msg = json.dumps({
            "type": "tool_call_approval",
            "sessionId": STATE.pending_approval["sessionId"],
            "requestId": STATE.pending_approval["requestId"],
            "approved": approved
        })
        asyncio.run_coroutine_threadsafe(STATE.ws.send(msg), loop=asyncio.get_event_loop())
        add_log(f"{'approved' if approved else 'denied'}: {STATE.pending_approval['toolId']}", OK if approved else ERROR)
        STATE.pending_approval = None

# ─── Main ──────────────────────────────────────────────────────────────────────
def main():
    if not sys.stdin.isatty():
        console.print("[red]Cybertron TUI requires an interactive terminal.[/red]")
        console.print("[yellow]Use 'cybertron server' for headless mode.[/yellow]")
        sys.exit(1)

    ws_thread = threading.Thread(target=lambda: asyncio.run(ws_client()), daemon=True)
    ws_thread.start()
    input_thr = threading.Thread(target=input_thread, daemon=True)
    input_thr.start()

    layout = build_layout()
    frame = 0

    with Live(layout, console=console, screen=True, refresh_per_second=12) as live:
        while STATE._running:
            layout["header"].update(make_header())
            layout["body"].update(make_body(frame))
            layout["footer"].update(make_footer())
            frame += 1
            time.sleep(0.08)

    console.print("\n[gold]Cybertron TUI exited.[/gold]")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[gold]Goodbye.[/gold]")

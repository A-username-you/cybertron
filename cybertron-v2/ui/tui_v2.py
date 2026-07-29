#!/usr/bin/env python3
"""
Cybertron TUI v2 — Full-featured terminal UI.
Features: Chat transcript, Control Center, streaming, planning, memory,
keyboard shortcuts, themes, GitHub tool loader, dry-run toggle.
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
from rich.columns import Columns

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
TEAL_DIM = "#2a8a99"
ERROR = "#ef5350"
WARN = "#ffa726"
OK = "#4caf50"
DIM = "#B8860B"
SURFACE_0 = "#14141f"
SURFACE_1 = "#1a1a2e"
SURFACE_2 = "#333355"
SURFACE_3 = "#444466"
BORDER = "#CD7F32"
TEXT_PRIMARY = "#FFF8DC"
TEXT_MUTED = "#B8860B"

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
        self.show_control = False
        self.show_shortcuts = False
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
        self.plan: List[Dict[str, Any]] = []
        self.streaming_content = ""
        self.config = {}
        self.tool_catalog: List[Dict[str, Any]] = []
        self.dry_run = False
        self.current_persona = "default"
        self.notifications: List[str] = []

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
    subtitle = Text("  v2", style=Style(color=TEXT_MUTED))

    # Mode indicators
    modes = []
    if STATE.dry_run:
        modes.append(Text("DRY", style=Style(color=WARN, bold=True)))
    if STATE.show_control:
        modes.append(Text("CTRL", style=Style(color=TEAL, bold=True)))
    if STATE.show_sessions:
        modes.append(Text("SRV", style=Style(color=AMBER, bold=True)))

    mode_text = Text("  │  ").join(modes) if modes else Text("")

    sep = Text("  │  ", style=Style(color=BRONZE))
    content = Text.assemble(title, subtitle, sep, status)
    if modes:
        content = Text.assemble(content, sep, mode_text)
    return Panel(content, style=Style(bgcolor=SURFACE_1), border_style=Style(color=BORDER))

def make_body(frame: int) -> Panel:
    if STATE.show_shortcuts:
        return make_shortcuts_panel()
    if STATE.show_control:
        return make_control_panel()
    if STATE.show_sessions:
        return make_sessions_panel()
    return make_chat_panel(frame)

def make_chat_panel(frame: int) -> Panel:
    content = Text()

    # Status line with spinner
    glyph = "?"
    glyph_color = WARN
    if STATE.pending_approval:
        glyph = "?"
        glyph_color = WARN
    elif STATE.agent_state in ("thinking", "running_tool", "planning"):
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
    content.append("\n")
    content.append(Text("─" * 60, style=Style(color=BORDER)))
    content.append("\n\n")

    # Plan display
    if STATE.plan:
        content.append(Text("PLAN:\n", style=Style(color=BRONZE, bold=True)))
        for step in STATE.plan:
            status = step.get("status", "pending")
            icon = "○" if status == "pending" else "◐" if status == "running" else "●"
            color = DIM if status == "pending" else AMBER if status == "running" else OK
            content.append(Text.assemble(
                Text(f"  {icon} ", style=Style(color=color)),
                Text(f"Step {step.get('step', '?')}: {step.get('description', '')}", style=Style(color=TEXT_PRIMARY if status != "pending" else DIM)),
                "\n"
            ))
        content.append("\n")

    # Streaming content
    if STATE.streaming_content:
        content.append(Text(STATE.streaming_content, style=Style(color=TEAL)))
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

    # Chat messages
    if not STATE.logs:
        content.append(Text("no activity yet — type a goal and press enter", style=Style(color=TEXT_MUTED, dim=True)))
    else:
        for line in STATE.logs[-25:]:
            color = line.get("color", TEXT_MUTED)
            prefix = line.get("prefix", "")
            text = line.get("text", "")
            if prefix:
                content.append(Text.assemble(Text(prefix, style=Style(color=color, bold=True)), Text(text, style=Style(color=TEXT_PRIMARY))))
            else:
                content.append(Text(text, style=Style(color=color)))
            content.append("\n")

    # Notifications
    if STATE.notifications:
        content.append("\n")
        for note in STATE.notifications[-3:]:
            content.append(Text(f"  ! {note}", style=Style(color=WARN)))
            content.append("\n")

    return Panel(
        Align.left(content),
        title="[bold]Chat[/bold]",
        border_style=Style(color=TEAL_DIM),
        style=Style(bgcolor=SURFACE_0),
    )

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
            table.add_row(state.ljust(18), elapsed(started, finished), f"calls:{s.get('toolCallCount', 0)}", goal)
        content.append(table)

    return Panel(content, title="[bold]Sessions[/bold]", border_style=Style(color=AMBER), style=Style(bgcolor=SURFACE_0))

def make_control_panel() -> Panel:
    content = Text()
    content.append(Text("CONTROL CENTER\n\n", style=Style(color=GOLD, bold=True)))

    cfg = STATE.config

    # NIM API Key
    nim = cfg.get("nim_api_key", "")
    nim_status = Text("✓ configured", style=Style(color=OK)) if nim else Text("✗ not set", style=Style(color=ERROR))
    content.append(Text.assemble(Text("NIM API Key: ", style=Style(color=TEXT_PRIMARY, bold=True)), nim_status))
    content.append(Text("  [K] to set key\n\n", style=Style(color=DIM)))

    # Persona
    persona = STATE.current_persona
    content.append(Text.assemble(Text("Persona: ", style=Style(color=TEXT_PRIMARY, bold=True)), Text(persona, style=Style(color=AMBER))))
    content.append(Text("  [P] to cycle personas\n\n", style=Style(color=DIM)))

    # Dry run
    dry = STATE.dry_run
    dry_status = Text("ON", style=Style(color=WARN, bold=True)) if dry else Text("OFF", style=Style(color=DIM))
    content.append(Text.assemble(Text("Dry Run: ", style=Style(color=TEXT_PRIMARY, bold=True)), dry_status))
    content.append(Text("  [D] to toggle\n\n", style=Style(color=DIM)))

    # Theme
    theme = cfg.get("theme", "dark")
    content.append(Text.assemble(Text("Theme: ", style=Style(color=TEXT_PRIMARY, bold=True)), Text(theme, style=Style(color=AMBER))))
    content.append(Text("  [T] to toggle theme\n\n", style=Style(color=DIM)))

    # Rate limit
    rate = cfg.get("rate_limit_per_min", 30)
    content.append(Text.assemble(Text("Rate Limit: ", style=Style(color=TEXT_PRIMARY, bold=True)), Text(f"{rate}/min", style=Style(color=AMBER))))
    content.append(Text("  [R] to adjust\n\n", style=Style(color=DIM)))

    # GitHub Token
    gh = cfg.get("github_token", "")
    gh_status = Text("✓ configured", style=Style(color=OK)) if gh else Text("✗ not set", style=Style(color=ERROR))
    content.append(Text.assemble(Text("GitHub Token: ", style=Style(color=TEXT_PRIMARY, bold=True)), gh_status))
    content.append(Text("  [G] to set token\n\n", style=Style(color=DIM)))

    # Webhooks
    webhook = cfg.get("webhook_url", "")
    slack = cfg.get("slack_webhook", "")
    content.append(Text.assemble(Text("Webhook: ", style=Style(color=TEXT_PRIMARY, bold=True)), Text(webhook or "not set", style=Style(color=DIM))))
    content.append(Text.assemble(Text("Slack: ", style=Style(color=TEXT_PRIMARY, bold=True)), Text(slack or "not set", style=Style(color=DIM))))
    content.append(Text("  [W] to set webhooks\n\n", style=Style(color=DIM)))

    # Tool catalog
    content.append(Text.assemble(Text("Tools: ", style=Style(color=TEXT_PRIMARY, bold=True)), Text(f"{len(STATE.tool_catalog)} registered", style=Style(color=AMBER))))
    content.append(Text("  [A] to add GitHub tool\n", style=Style(color=DIM)))

    return Panel(content, title="[bold]Control Center[/bold]", border_style=Style(color=TEAL), style=Style(bgcolor=SURFACE_0))

def make_shortcuts_panel() -> Panel:
    content = Text()
    content.append(Text("KEYBOARD SHORTCUTS\n\n", style=Style(color=GOLD, bold=True)))

    shortcuts = [
        ("Enter", "Submit goal / confirm"),
        ("S", "Toggle Server View"),
        ("C", "Toggle Control Center"),
        ("?", "Toggle this help"),
        ("Y / N", "Approve / deny tool"),
        ("K", "Set NIM API key (in Control Center)"),
        ("P", "Cycle personas (in Control Center)"),
        ("D", "Toggle dry-run mode"),
        ("T", "Toggle theme"),
        ("R", "Adjust rate limit"),
        ("G", "Set GitHub token"),
        ("W", "Set webhooks"),
        ("A", "Add GitHub tool"),
        ("Backspace", "Delete character"),
        ("Ctrl+C", "Quit"),
    ]

    for key, desc in shortcuts:
        content.append(Text.assemble(
            Text(f"  {key:<12}", style=Style(color=AMBER, bold=True)),
            Text(desc, style=Style(color=TEXT_PRIMARY)),
            "\n"
        ))

    return Panel(content, title="[bold]Help[/bold]", border_style=Style(color=BRONZE), style=Style(bgcolor=SURFACE_0))

def make_footer() -> Panel:
    if STATE.pending_approval:
        prompt = Text("APPROVE? [Y/N]: ", style=Style(color=WARN, bold=True))
    elif STATE.show_control:
        prompt = Text("Control: ", style=Style(color=TEAL, bold=True))
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
            add_log("system", "Connected to gateway", OK)
        else:
            STATE.status = "auth rejected"
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
                STATE.streaming_content = ""
            if state != "awaiting_approval":
                STATE.pending_approval = None
            add_log("agent", f"[{state.upper()}] {detail}", session_color(state))
        return

    if etype == "stream":
        sid = event.get("sessionId")
        if sid == STATE.current_session_id:
            content = event.get("content", "")
            STATE.streaming_content += content + "\n"
            # Keep last 500 chars
            if len(STATE.streaming_content) > 500:
                STATE.streaming_content = STATE.streaming_content[-500:]
        return

    if etype == "plan":
        STATE.plan = event.get("plan", [])
        add_log("system", "Plan generated", BRONZE)
        return

    if etype == "plan_update":
        STATE.plan = event.get("plan", [])
        return

    if etype == "memory":
        ctx = event.get("context", "")
        if ctx:
            add_log("memory", "Loaded target history", TEAL)
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
            add_log("system", f"Approval needed: {event.get('toolId')}", WARN)
        return

    if etype == "tool_call_result":
        sid = event.get("sessionId")
        if sid == STATE.current_session_id:
            result = event.get("result", {})
            tool_id = result.get("toolId", "?")
            ok = result.get("ok", False)
            output = result.get("output", "")
            error = result.get("error", "")
            duration = result.get("durationMs", 0)
            if ok:
                add_log("result", f"[{tool_id}] {duration}ms\n{output[:200]}", OK)
            else:
                add_log("error", f"[{tool_id}] {duration}ms\n{error}", ERROR)
        return

    if etype == "sessions_snapshot":
        STATE.sessions = event.get("sessions", [])
        return

    if etype == "config_state":
        STATE.config = event
        return

    if etype == "tools_catalog":
        STATE.tool_catalog = event.get("tools", [])
        return

    if etype == "error":
        add_log("error", event.get("message", "Unknown error"), ERROR)
        return

def add_log(role: str, text: str, color: str = TEXT_MUTED):
    prefix_map = {
        "user": ("You ", TEAL),
        "agent": ("Cybertron ", AMBER),
        "system": ("", TEXT_MUTED),
        "result": ("RESULT ", OK),
        "error": ("ERROR ", ERROR),
        "memory": ("MEM ", TEAL),
    }
    prefix, prefix_color = prefix_map.get(role, ("", TEXT_MUTED))
    STATE.logs.append({"prefix": prefix, "text": text, "color": prefix_color})
    if len(STATE.logs) > 300:
        STATE.logs = STATE.logs[-150:]

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
                if ch == '\x03':
                    STATE._running = False
                    break
                elif ch == '\x7f':
                    STATE._input_buffer = STATE._input_buffer[:-1]
                elif ch == '\r':
                    handle_submit()
                elif ch == '?' and not STATE._input_buffer:
                    STATE.show_shortcuts = not STATE.show_shortcuts
                elif ch.lower() == 's' and not STATE._input_buffer and not STATE.pending_approval:
                    STATE.show_sessions = not STATE.show_sessions
                    STATE.show_control = False
                    STATE.show_shortcuts = False
                    if STATE.show_sessions and STATE.ws and STATE.connected and STATE.authed:
                        send_ws({"type": "list_sessions"})
                elif ch.lower() == 'c' and not STATE._input_buffer and not STATE.pending_approval:
                    STATE.show_control = not STATE.show_control
                    STATE.show_sessions = False
                    STATE.show_shortcuts = False
                    if STATE.show_control and STATE.ws:
                        send_ws({"type": "get_config"})
                elif ch.lower() == 'd' and STATE.show_control:
                    STATE.dry_run = not STATE.dry_run
                    add_log("system", f"Dry-run: {'ON' if STATE.dry_run else 'OFF'}", WARN if STATE.dry_run else OK)
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
    if STATE.show_control:
        # Handle control center commands
        if buf.lower().startswith("nim "):
            key = buf[4:].strip()
            send_ws({"type": "update_config", "nim_api_key": key})
            add_log("system", "NIM API key updated", OK)
        elif buf.lower().startswith("github "):
            key = buf[7:].strip()
            send_ws({"type": "update_config", "github_token": key})
            add_log("system", "GitHub token updated", OK)
        elif buf.lower().startswith("tool "):
            url = buf[5:].strip()
            send_ws({"type": "register_github_tool", "url": url})
            add_log("system", f"Registering tool from {url}...", AMBER)
        return
    if STATE.ws and STATE.connected and STATE.authed:
        working = STATE.agent_state in ("thinking", "running_tool", "planning")
        if working:
            add_log("system", "A session is already running — wait for it to finish.", WARN)
            return
        STATE.current_session_id = STATE.new_session_id()
        STATE.logs = []
        STATE.plan = []
        STATE.streaming_content = ""
        msg = json.dumps({
            "type": "session_start",
            "sessionId": STATE.current_session_id,
            "goal": buf,
            "origin": "cli"
        })
        send_ws_raw(msg)
        add_log("user", buf, TEAL)
    else:
        add_log("system", "Not connected to gateway", ERROR)

def send_approval(approved: bool):
    if STATE.ws and STATE.pending_approval:
        msg = json.dumps({
            "type": "tool_call_approval",
            "sessionId": STATE.pending_approval["sessionId"],
            "requestId": STATE.pending_approval["requestId"],
            "approved": approved
        })
        send_ws_raw(msg)
        add_log("system", f"{'approved' if approved else 'denied'}: {STATE.pending_approval['toolId']}", OK if approved else ERROR)
        STATE.pending_approval = None

def send_ws(msg: dict):
    if STATE.ws and STATE.connected:
        try:
            asyncio.run_coroutine_threadsafe(STATE.ws.send(json.dumps(msg)), loop=asyncio.get_event_loop())
        except Exception:
            pass

def send_ws_raw(msg: str):
    if STATE.ws and STATE.connected:
        try:
            asyncio.run_coroutine_threadsafe(STATE.ws.send(msg), loop=asyncio.get_event_loop())
        except Exception:
            pass

# ─── Main ──────────────────────────────────────────────────────────────────────
def main():
    if not sys.stdin.isatty():
        console.print("[red]Cybertron TUI requires an interactive terminal.[/red]")
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

    console.print("\n[gold]Cybertron TUI v2 exited.[/gold]")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[gold]Goodbye.[/gold]")

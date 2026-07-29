#!/usr/bin/env python3
"""
Cybertron TUI v2 — Full-featured terminal UI.
Features: planning, streaming, memory, control center, tool registry, audit log,
keyboard shortcuts, Hermes design system.
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
from rich.box import ROUNDED

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
TEXT_DIM = "#8B7355"

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
        self.show_tools = False
        self.show_help = False
        self.show_audit = False
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
        self.tool_catalog: List[Dict[str, Any]] = []
        self.config: Dict[str, Any] = {}
        self.audit_entries: List[Dict[str, Any]] = []
        self.memory_context = ""
        self.stream_buffer = ""

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

    views = []
    if STATE.show_sessions: views.append("[S]essions")
    elif STATE.show_control: views.append("[C]ontrol")
    elif STATE.show_tools: views.append("[T]ools")
    elif STATE.show_audit: views.append("[A]udit")
    elif STATE.show_help: views.append("[?]Help")
    else: views.append("[S]erver")

    view = Text("  │  ".join(views), style=Style(color=AMBER))
    sep = Text("  │  ", style=Style(color=BRONZE))
    content = Text.assemble(title, subtitle, sep, status, sep, view)
    return Panel(content, style=Style(bgcolor=SURFACE_1), border_style=Style(color=BORDER))

def make_body(frame: int) -> Panel:
    if STATE.show_help:
        return make_help_panel()
    if STATE.show_control:
        return make_control_panel()
    if STATE.show_tools:
        return make_tools_panel()
    if STATE.show_audit:
        return make_audit_panel()
    if STATE.show_sessions:
        return make_sessions_panel()
    return make_chat_panel(frame)

def make_help_panel() -> Panel:
    content = Text()
    content.append(Text("Keyboard Shortcuts\n", style=Style(color=GOLD, bold=True)))
    content.append(Text("─" * 50 + "\n\n", style=Style(color=BORDER)))

    shortcuts = [
        ("Enter", "Submit goal / confirm approval"),
        ("S", "Toggle Server/Sessions view"),
        ("C", "Toggle Control Center"),
        ("T", "Toggle Tool Registry"),
        ("A", "Toggle Audit Log"),
        ("? / H", "Toggle this help"),
        ("Y", "Approve pending tool"),
        ("N", "Deny pending tool"),
        ("Ctrl+C", "Quit"),
        ("", ""),
        ("/add-tool <url>", "Register GitHub tool (in composer)"),
        ("/persona <name>", "Switch persona"),
        ("/dry-run", "Toggle dry-run mode"),
        ("/theme", "Toggle dark/light theme"),
    ]
    for key, desc in shortcuts:
        if key:
            content.append(Text.assemble(
                Text(f"{key:<20}", style=Style(color=TEAL, bold=True)),
                Text(desc, style=Style(color=TEXT_PRIMARY)),
                "\n"
            ))
        else:
            content.append("\n")

    return Panel(content, title="[bold]Help[/bold]", border_style=Style(color=TEAL), style=Style(bgcolor=SURFACE_0))

def make_control_panel() -> Panel:
    content = Text()
    content.append(Text("Control Center\n", style=Style(color=GOLD, bold=True)))
    content.append(Text("─" * 50 + "\n\n", style=Style(color=BORDER)))

    cfg = STATE.config
    items = [
        ("NIM API Key", "***" if cfg.get("nim_api_key") else "NOT SET", OK if cfg.get("nim_api_key") else ERROR),
        ("NIM Model", cfg.get("nim_model", "default"), TEXT_PRIMARY),
        ("Theme", cfg.get("theme", "dark"), AMBER),
        ("Dry Run", str(cfg.get("dry_run", False)), WARN if cfg.get("dry_run") else TEXT_MUTED),
        ("Rate Limit", f"{cfg.get('rate_limit_per_min', 30)}/min", TEXT_PRIMARY),
        ("Max Iterations", str(cfg.get("max_iterations", 12)), TEXT_PRIMARY),
        ("Auto-approve Recon", str(cfg.get("auto_approve_recon", False)), TEXT_PRIMARY),
        ("Auto-approve Scan", str(cfg.get("auto_approve_scan", False)), TEXT_PRIMARY),
        ("Output Sanitize", str(cfg.get("output_sanitize", True)), OK),
        ("Sandbox Mode", str(cfg.get("sandbox_mode", False)), WARN if cfg.get("sandbox_mode") else TEXT_MUTED),
        ("Remember Sessions", str(cfg.get("remember_sessions", True)), OK),
        ("Webhook URL", cfg.get("webhook_url", "") or "none", TEXT_MUTED),
        ("Slack Webhook", cfg.get("slack_webhook", "") or "none", TEXT_MUTED),
        ("GitHub Token", "***" if cfg.get("github_token") else "NOT SET", OK if cfg.get("github_token") else ERROR),
    ]

    for label, value, color in items:
        content.append(Text.assemble(
            Text(f"{label:<22}", style=Style(color=TEXT_MUTED)),
            Text(value, style=Style(color=color)),
            "\n"
        ))

    content.append("\n")
    content.append(Text("Use /config <key> <value> in composer to change settings", style=Style(color=DIM, dim=True)))

    return Panel(content, title="[bold]Control Center[/bold]", border_style=Style(color=AMBER), style=Style(bgcolor=SURFACE_0))

def make_tools_panel() -> Panel:
    content = Text()
    content.append(Text("Tool Registry\n", style=Style(color=GOLD, bold=True)))
    content.append(Text("─" * 50 + "\n\n", style=Style(color=BORDER)))

    if not STATE.tool_catalog:
        content.append(Text("No tools loaded. Connect to gateway first.", style=Style(color=TEXT_MUTED)))
    else:
        table = Table(show_header=True, box=None, pad_edge=False, border_style=Style(color=SURFACE_2))
        table.add_column("ID", style=Style(color=TEXT_PRIMARY), width=16)
        table.add_column("Category", style=Style(color=AMBER), width=10)
        table.add_column("Auto", style=Style(color=TEXT_MUTED), width=6)
        table.add_column("Impl", style=Style(color=TEXT_MUTED), width=6)
        table.add_column("Source", style=Style(color=TEAL), width=10)

        for t in STATE.tool_catalog:
            auto = "✓" if t.get("autoApprove") else "✗"
            impl = "✓" if t.get("implemented") else "✗"
            src = t.get("source", "builtin")
            table.add_row(t["id"], t["category"], auto, impl, src)
        content.append(table)

    content.append("\n")
    content.append(Text("Use /add-tool <github-url> to install new tools", style=Style(color=DIM, dim=True)))

    return Panel(content, title="[bold]Tools[/bold]", border_style=Style(color=BRONZE), style=Style(bgcolor=SURFACE_0))

def make_audit_panel() -> Panel:
    content = Text()
    content.append(Text("Audit Log\n", style=Style(color=GOLD, bold=True)))
    content.append(Text("─" * 50 + "\n\n", style=Style(color=BORDER)))

    if not STATE.audit_entries:
        content.append(Text("No audit entries yet.", style=Style(color=TEXT_MUTED)))
    else:
        for entry in STATE.audit_entries[-20:]:
            ts = time.strftime("%H:%M:%S", time.localtime(entry.get("timestamp", 0) / 1000))
            etype = entry.get("type", "unknown")
            detail = json.dumps(entry.get("details", {}))[:60]
            content.append(Text.assemble(
                Text(f"[{ts}] ", style=Style(color=BRONZE)),
                Text(f"{etype:<20}", style=Style(color=AMBER)),
                Text(detail, style=Style(color=TEXT_MUTED)),
                "\n"
            ))

    return Panel(content, title="[bold]Audit[/bold]", border_style=Style(color=ERROR), style=Style(bgcolor=SURFACE_0))

def make_sessions_panel() -> Panel:
    content = Text()
    content.append(Text("Server View — every session on this gateway\n\n", style=Style(color=TEXT_PRIMARY, bold=True)))

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

def make_chat_panel(frame: int) -> Panel:
    content = Text()

    # Status line
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
        "  ", Text("cybertron", style=Style(color=GOLD, bold=True)),
        "  — ", Text(STATE.status, style=Style(color=TEXT_PRIMARY)),
        Text(turn_elapsed, style=Style(color=DIM)),
        Text(recon, style=Style(color=WARN)),
    )
    content.append(status_line)
    content.append("\n")

    # Plan display
    if STATE.plan:
        content.append(Text("Plan:\n", style=Style(color=BRONZE, bold=True)))
        for step in STATE.plan:
            status = step.get("status", "pending")
            icon = {"pending": "○", "running": "◐", "completed": "●", "failed": "✕"}.get(status, "○")
            color = {"pending": TEXT_MUTED, "running": AMBER, "completed": OK, "failed": ERROR}.get(status, TEXT_MUTED)
            content.append(Text.assemble(
                Text(f"  {icon} ", style=Style(color=color)),
                Text(f"Step {step['step']}: {step['description']}", style=Style(color=TEXT_PRIMARY if status != 'pending' else TEXT_MUTED)),
                "\n"
            ))
        content.append("\n")

    # Memory context
    if STATE.memory_context:
        content.append(Text("Memory:\n", style=Style(color=TEAL, bold=True)))
        for line in STATE.memory_context.split("\n")[:5]:
            content.append(Text(f"  {line}", style=Style(color=TEXT_MUTED, dim=True)))
            content.append("\n")
        content.append("\n")

    # Stream buffer
    if STATE.stream_buffer:
        content.append(Text(STATE.stream_buffer, style=Style(color=CORNSILK)))
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
        for line in STATE.logs[-18:]:
            color = line.get("color", TEXT_MUTED)
            content.append(Text(line["text"], style=Style(color=color)))
            content.append("\n")

    return Panel(content, title="[bold]Chat[/bold]", border_style=Style(color=TEAL), style=Style(bgcolor=SURFACE_0))

def make_footer() -> Panel:
    if STATE.pending_approval:
        prompt = Text("APPROVE? [Y/N]: ", style=Style(color=WARN, bold=True))
    elif STATE.show_help:
        prompt = Text("Press ? again to close ", style=Style(color=TEXT_MUTED))
    elif STATE.show_control:
        prompt = Text("Press C again to close ", style=Style(color=TEXT_MUTED))
    elif STATE.show_tools:
        prompt = Text("Press T again to close ", style=Style(color=TEXT_MUTED))
    elif STATE.show_audit:
        prompt = Text("Press A again to close ", style=Style(color=TEXT_MUTED))
    elif STATE.show_sessions:
        prompt = Text("Press S again to close ", style=Style(color=TEXT_MUTED))
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
            # Request config and tools
            asyncio.run_coroutine_threadsafe(
                STATE.ws.send(json.dumps({"type": "get_config"})),
                loop=asyncio.get_event_loop()
            )
            asyncio.run_coroutine_threadsafe(
                STATE.ws.send(json.dumps({"type": "get_tools"})),
                loop=asyncio.get_event_loop()
            )
        else:
            STATE.status = "auth rejected — token file may be stale"
        return

    if etype == "config_state":
        STATE.config = event
        return

    if etype == "tools_catalog":
        STATE.tool_catalog = event.get("tools", [])
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
                STATE.stream_buffer = ""
            if state != "awaiting_approval":
                STATE.pending_approval = None
        return

    if etype == "plan":
        STATE.plan = event.get("plan", [])
        return

    if etype == "plan_update":
        STATE.plan = event.get("plan", [])
        return

    if etype == "stream":
        content = event.get("content", "")
        STATE.stream_buffer += content + "\n"
        return

    if etype == "memory":
        STATE.memory_context = event.get("context", "")
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
            tool_id = event.get("result", {}).get("toolId", "?")
            ok = event.get("result", {}).get("ok", False)
            output = event.get("result", {}).get("output", "")
            error = event.get("result", {}).get("error", "")
            duration = event.get("result", {}).get("durationMs", 0)
            if ok:
                text = f"[{tool_id}] ok ({duration}ms)\n{output}"
                color = OK
            else:
                text = f"[{tool_id}] error ({duration}ms)\n{error}"
                color = ERROR
            STATE.logs.append({"text": text, "color": color})
            STATE.stream_buffer = ""
        return

    if etype == "sessions_snapshot":
        STATE.sessions = event.get("sessions", [])
        return

    if etype == "session_started":
        add_chat_msg("system", f"Session started: {event.get('sessionId', '?')}")
        return

def add_chat_msg(role: str, text: str, color: str = TEXT_MUTED):
    STATE.logs.append({"text": f"[{role}] {text}", "color": color})
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
                if ch == '\x03':
                    STATE._running = False
                    break
                elif ch == '\x7f':
                    STATE._input_buffer = STATE._input_buffer[:-1]
                elif ch == '\r':
                    handle_submit()
                elif ch.lower() == 's' and not STATE._input_buffer and not STATE.pending_approval:
                    STATE.show_sessions = not STATE.show_sessions
                    STATE.show_control = False
                    STATE.show_tools = False
                    STATE.show_audit = False
                    STATE.show_help = False
                    if STATE.show_sessions and STATE.ws and STATE.connected and STATE.authed:
                        asyncio.run_coroutine_threadsafe(
                            STATE.ws.send(json.dumps({"type": "list_sessions"})),
                            loop=asyncio.get_event_loop()
                        )
                elif ch.lower() == 'c' and not STATE._input_buffer and not STATE.pending_approval:
                    STATE.show_control = not STATE.show_control
                    STATE.show_sessions = False
                    STATE.show_tools = False
                    STATE.show_audit = False
                    STATE.show_help = False
                elif ch.lower() == 't' and not STATE._input_buffer and not STATE.pending_approval:
                    STATE.show_tools = not STATE.show_tools
                    STATE.show_sessions = False
                    STATE.show_control = False
                    STATE.show_audit = False
                    STATE.show_help = False
                    if STATE.show_tools and STATE.ws and STATE.connected and STATE.authed:
                        asyncio.run_coroutine_threadsafe(
                            STATE.ws.send(json.dumps({"type": "get_tools"})),
                            loop=asyncio.get_event_loop()
                        )
                elif ch.lower() == 'a' and not STATE._input_buffer and not STATE.pending_approval:
                    STATE.show_audit = not STATE.show_audit
                    STATE.show_sessions = False
                    STATE.show_control = False
                    STATE.show_tools = False
                    STATE.show_help = False
                elif ch == '?' or ch.lower() == 'h' and not STATE._input_buffer and not STATE.pending_approval:
                    STATE.show_help = not STATE.show_help
                    STATE.show_sessions = False
                    STATE.show_control = False
                    STATE.show_tools = False
                    STATE.show_audit = False
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

    # Slash commands
    if buf.startswith("/"):
        handle_slash_command(buf)
        return

    if STATE.pending_approval:
        if buf.lower() in ('y', 'yes'):
            send_approval(True)
        elif buf.lower() in ('n', 'no'):
            send_approval(False)
        return

    if STATE.ws and STATE.connected and STATE.authed:
        working = STATE.agent_state in ("thinking", "running_tool", "planning")
        if working:
            add_chat_msg("system", "A session is already running — wait for it to finish.", WARN)
            return
        STATE.current_session_id = STATE.new_session_id()
        STATE.logs = []
        STATE.plan = []
        STATE.stream_buffer = ""
        STATE.memory_context = ""
        msg = json.dumps({
            "type": "session_start",
            "sessionId": STATE.current_session_id,
            "goal": buf,
            "origin": "cli"
        })
        asyncio.run_coroutine_threadsafe(STATE.ws.send(msg), loop=asyncio.get_event_loop())
        add_chat_msg("user", buf, AMBER)
    else:
        add_chat_msg("system", "Not connected to gateway", ERROR)

def handle_slash_command(cmd: str):
    parts = cmd.split()
    if not parts:
        return

    if parts[0] == "/add-tool" and len(parts) > 1:
        url = parts[1]
        add_chat_msg("system", f"Registering tool from {url}...", AMBER)
        # Send to gateway via HTTP or WS
        if STATE.ws and STATE.connected and STATE.authed:
            # Use a simple message that gateway handles
            asyncio.run_coroutine_threadsafe(
                STATE.ws.send(json.dumps({"type": "register_github_tool", "url": url})),
                loop=asyncio.get_event_loop()
            )
    elif parts[0] == "/persona" and len(parts) > 1:
        add_chat_msg("system", f"Switching to persona: {parts[1]}", TEAL)
    elif parts[0] == "/dry-run":
        add_chat_msg("system", "Toggling dry-run mode (gateway-side)", WARN)
    elif parts[0] == "/theme":
        add_chat_msg("system", "Theme toggle not yet implemented in TUI", TEXT_MUTED)
    elif parts[0] == "/help":
        STATE.show_help = True
    else:
        add_chat_msg("system", f"Unknown command: {parts[0]}", ERROR)

def send_approval(approved: bool):
    if STATE.ws and STATE.pending_approval:
        msg = json.dumps({
            "type": "tool_call_approval",
            "sessionId": STATE.pending_approval["sessionId"],
            "requestId": STATE.pending_approval["requestId"],
            "toolId": STATE.pending_approval["toolId"],
            "approved": approved
        })
        asyncio.run_coroutine_threadsafe(STATE.ws.send(msg), loop=asyncio.get_event_loop())
        add_chat_msg("system", f"{'Approved' if approved else 'Denied'}: {STATE.pending_approval['toolId']}", OK if approved else ERROR)
        STATE.pending_approval = None

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

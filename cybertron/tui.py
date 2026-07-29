#!/usr/bin/env python3
"""
Cybertron TUI -- Terminal UI for the Cybertron Agent (Hermes-style)
Uses Rich for rendering, websockets for gateway comms.
"""
import asyncio
import json
import os
import sys
import threading
import time
from pathlib import Path

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
WS_URL = f"ws://{GATEWAY_HOST}:{GATEWAY_PORT}/ws"
TOKEN_PATH = Path.home() / ".cybertron" / "auth-token"

# ─── Hermes Agent Color Palette ──────────────────────────────────────────────
NAVY = "#0a0a1a"
NAVY_DEEP = "#1a1a2e"
NAVY_MID = "#14142b"
NAVY_LIGHT = "#1e1e3f"
GOLD = "#ffd700"
AMBER = "#ffbf00"
AMBER_DIM = "#b8860b"
TEAL = "#4dd0e1"
TEAL_DIM = "#2a8a99"
BRONZE = "#cd7f32"
CORNSILK = "#fff8dc"
MUTED = "#8a8a9a"
INK = "#e8e6e1"
DANGER = "#ff4444"
SUCCESS = "#44ff88"
WARN = "#ffa726"
BORDER = "#2a2a4a"
BORDER_BRONZE = "#cd7f32"

# ─── State ────────────────────────────────────────────────────────────────────
class TUIState:
    def __init__(self):
        self.connected = False
        self.current_state = "idle"
        self.state_detail = "Enter a goal to start."
        self.sessions = []
        self.server_view = False
        self.pending_approval = None
        self.chat_messages = []  # (role, text, timestamp)
        self.session_start = 0
        self.ws = None
        self._running = True
        self._input_buffer = ""
        self._scroll_offset = 0

STATE = TUIState()
console = Console()

# ─── ASCII Art State Icons ───────────────────────────────────────────────────
def get_state_icon(frame: int, state: str) -> Text:
    """Hermes-style ASCII state indicators."""
    if state in ("thinking", "running_tool", "awaiting_approval"):
        faces = ["(⚔)", "(⛨)", "(▲)"]
        return Text(faces[frame % len(faces)], style=Style(color=TEAL, bold=True))
    elif state == "writing":
        faces = ["(⌁)", "(<>)", "(⚡)"]
        return Text(faces[frame % len(faces)], style=Style(color=AMBER, bold=True))
    elif state == "result":
        return Text("(★)", style=Style(color=GOLD, bold=True))
    else:
        return Text("(○)", style=Style(color=MUTED))

# ─── Layout Builder ────────────────────────────────────────────────────────────
def build_layout() -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body"),
        Layout(name="footer", size=3),
    )
    layout["body"].split_row(
        Layout(name="chat", ratio=3),
        Layout(name="sidebar", size=34),
    )
    return layout

def make_header() -> Panel:
    conn_color = SUCCESS if STATE.connected else DANGER
    conn_text = "ONLINE" if STATE.connected else "OFFLINE"
    status = Text(conn_text, style=Style(color=conn_color, bold=True))
    title = Text("CYBERTRON", style=Style(color=GOLD, bold=True))
    subtitle = Text("  Agent Console", style=Style(color=MUTED))
    view = Text("[S]erver" if not STATE.server_view else "[S]ession", style=Style(color=AMBER))
    sep = Text("  │  ", style=Style(color=BRONZE))
    content = Text.assemble(title, subtitle, sep, status, sep, view)
    return Panel(content, style=Style(bgcolor=NAVY_MID), border_style=Style(color=BRONZE))

def make_chat(frame: int) -> Panel:
    """Hermes-style chat transcript panel."""
    content = Text()

    # State banner at top
    icon = get_state_icon(frame, STATE.current_state)
    state_banner = Text.assemble(
        icon, "  ",
        Text(STATE.current_state.upper(), style=Style(color=GOLD, bold=True)),
        "  --  ",
        Text(STATE.state_detail, style=Style(color=MUTED)),
    )
    content.append(state_banner)
    content.append("\n")
    content.append(Text("─" * 60, style=Style(color=BORDER_BRONZE)))
    content.append("\n\n")

    # Chat messages (Hermes-style transcript)
    visible_msgs = STATE.chat_messages[-20:]
    for role, text, ts in visible_msgs:
        if role == "user":
            label = Text("You ", style=Style(color=TEAL, bold=True))
            msg = Text(text, style=Style(color=CORNSILK))
            content.append(Text.assemble(label, msg))
        elif role == "agent":
            label = Text("Cybertron ", style=Style(color=AMBER, bold=True))
            msg = Text(text, style=Style(color=CORNSILK))
            content.append(Text.assemble(label, msg))
        elif role == "tool":
            label = Text("TOOL ", style=Style(color=BRONZE, bold=True))
            msg = Text(text, style=Style(color=MUTED))
            content.append(Text.assemble(label, msg))
        elif role == "result":
            label = Text("RESULT ", style=Style(color=SUCCESS, bold=True))
            msg = Text(text, style=Style(color=CORNSILK))
            content.append(Text.assemble(label, msg))
        elif role == "system":
            content.append(Text(f"  {text}", style=Style(color=MUTED, dim=True)))
        content.append("\n\n")

    if not visible_msgs:
        content.append(Text("  Enter a goal below to start a session...", style=Style(color=MUTED, dim=True)))

    return Panel(
        Align.left(content),
        title="[bold]Chat[/bold]",
        border_style=Style(color=TEAL_DIM),
        style=Style(bgcolor=NAVY),
    )

def make_sidebar() -> Panel:
    if not STATE.server_view:
        # Session info panel (Hermes-style status)
        table = Table(show_header=False, box=None, pad_edge=False, border_style=Style(color=BORDER))
        table.add_column(style=Style(color=MUTED), width=14)
        table.add_column(style=Style(color=CORNSILK))

        table.add_row("Status", STATE.current_state)
        table.add_row("Gateway", "Connected" if STATE.connected else "Disconnected")
        if STATE.session_start and STATE.current_state != "idle":
            elapsed = time.time() - STATE.session_start
            table.add_row("Elapsed", f"{elapsed:.1f}s")
        table.add_row("Sessions", str(len(STATE.sessions)))

        return Panel(table, title="[bold]Status[/bold]", border_style=Style(color=AMBER_DIM), style=Style(bgcolor=NAVY_MID))

    table = Table(show_header=True, header_style=Style(color=BRONZE, bold=True),
                  border_style=Style(color=BORDER), box=None, pad_edge=False)
    table.add_column("ID", style=Style(color=MUTED), width=8)
    table.add_column("State", style=Style(color=TEAL), width=10)
    table.add_column("T+", style=Style(color=AMBER), width=6)
    for s in STATE.sessions[-10:]:
        table.add_row(s.get("id", "?")[:6], s.get("state", "?"), str(s.get("elapsed", 0)))
    return Panel(table, title="[bold]Sessions[/bold]", border_style=Style(color=AMBER), style=Style(bgcolor=NAVY_MID))

def make_footer() -> Panel:
    if STATE.pending_approval:
        prompt = Text(f"APPROVE {STATE.pending_approval}? [Y/N]: ", style=Style(color=DANGER, bold=True))
    else:
        prompt = Text("Goal: ", style=Style(color=TEAL, bold=True))
    input_text = Text(STATE._input_buffer, style=Style(color=CORNSILK))
    cursor = Text("█", style=Style(color=AMBER, blink=True))
    content = Text.assemble(prompt, input_text, cursor)
    return Panel(content, style=Style(bgcolor=NAVY_MID), border_style=Style(color=BRONZE))

# ─── WebSocket Client ─────────────────────────────────────────────────────────
async def ws_client():
    token = ""
    if TOKEN_PATH.exists():
        token = TOKEN_PATH.read_text().strip()
    if not token:
        console.print("[red]No auth token found. Start the gateway first.[/red]")
        return
    while STATE._running:
        try:
            async with websockets.connect(f"{WS_URL}?token={token}") as ws:
                STATE.ws = ws
                STATE.connected = True
                add_chat_msg("system", "Connected to gateway")
                async for msg in ws:
                    if not STATE._running:
                        break
                    data = json.loads(msg)
                    handle_ws_msg(data)
        except Exception as e:
            STATE.connected = False
            add_chat_msg("system", f"Disconnected: {e}")
            await asyncio.sleep(3)

def handle_ws_msg(msg: dict):
    mtype = msg.get("type")
    if mtype == "agent_status":
        STATE.current_state = msg.get("status", "idle")
        STATE.state_detail = msg.get("detail", "")
        if STATE.current_state == "idle" and STATE.session_start:
            STATE.session_start = 0
    elif mtype == "sessions_snapshot":
        STATE.sessions = msg.get("sessions", [])
    elif mtype == "tool_call_request":
        STATE.pending_approval = msg.get("tool", "unknown")
        add_chat_msg("system", f"Approval needed: {msg.get('tool')}")
    elif mtype == "tool_call_result":
        add_chat_msg("result", f"{msg.get('result')}")
    elif mtype == "session_started":
        STATE.session_start = time.time()
        add_chat_msg("system", f"Session started: {msg.get('sessionId')}")

def add_chat_msg(role: str, text: str):
    ts = time.strftime("%H:%M:%S")
    STATE.chat_messages.append((role, text, ts))
    if len(STATE.chat_messages) > 200:
        STATE.chat_messages = STATE.chat_messages[-100:]

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
                elif ch.lower() == 's' and not STATE._input_buffer:
                    STATE.server_view = not STATE.server_view
                    if STATE.server_view and STATE.ws:
                        asyncio.run_coroutine_threadsafe(
                            STATE.ws.send(json.dumps({"type": "sessions_request"})),
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
    if STATE.ws and STATE.connected:
        add_chat_msg("user", buf)
        msg = json.dumps({"type": "session_start", "goal": buf})
        asyncio.run_coroutine_threadsafe(STATE.ws.send(msg), loop=asyncio.get_event_loop())
    else:
        add_chat_msg("system", "Not connected to gateway")

def send_approval(approved: bool):
    if STATE.ws and STATE.pending_approval:
        msg = json.dumps({"type": "tool_call_approval", "tool": STATE.pending_approval, "approved": approved})
        asyncio.run_coroutine_threadsafe(STATE.ws.send(msg), loop=asyncio.get_event_loop())
        add_chat_msg("system", f"{'Approved' if approved else 'Denied'}: {STATE.pending_approval}")
        STATE.pending_approval = None

# ─── Main ──────────────────────────────────────────────────────────────────────
def main():
    if not sys.stdin.isatty():
        console.print("[red]Cybertron TUI requires an interactive terminal.[/red]")
        console.print("[yellow]Use 'cybertron server' for headless mode or 'cybertron desktop' for GUI.[/yellow]")
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
            layout["chat"].update(make_chat(frame))
            layout["sidebar"].update(make_sidebar())
            layout["footer"].update(make_footer())
            frame += 1
            time.sleep(0.08)
    console.print("\n[gold]Cybertron TUI exited.[/gold]")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[gold]Goodbye.[/gold]")

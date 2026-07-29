#!/usr/bin/env python3
"""
Cybertron TUI (Python) — connects to the Node.js runtime gateway.
Uses Rich for rendering. Matches the Ink TUI protocol exactly.

NEW: GitHub Tool Loader
  /add-tool <github-url> [category]   Install a tool from GitHub releases
  /tools                              View installed tool registry
  /marketplace                        Browse curated security tools
  /remove-tool <id>                   Remove an installed tool
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
        self.show_tools = False
        self.show_marketplace = False
        self.show_control = False
        self.split_pane = False
        self.dry_run = False
        self.bb_mode = False  # Bug bounty mode
        self.current_target = ""
        self.pending_approval: Optional[Dict[str, Any]] = None
        self.pending_download: Optional[Dict[str, Any]] = None
        self.stream_buffer = ""
        self.plan_steps: List[str] = []
        self.current_plan_step = -1
        self.turn_started_at: Optional[int] = None
        self.reconnect_in: Optional[int] = None
        self.ws = None
        self._running = True
        self._input_buffer = ""
        self.frame = 0
        self.current_session_id = self.new_session_id()
        self.reconnect_attempt = 0
        self.reconnect_timer = None
        self.tool_loader = None
        self.audit_logger = None
        self.session_exporter = None
        self._init_services()

    def _init_services(self):
        try:
            from github_tool_loader import get_loader
            self.tool_loader = get_loader()
        except Exception:
            self.tool_loader = None
        try:
            from audit_logger import get_logger
            self.audit_logger = get_logger()
        except Exception:
            self.audit_logger = None
        try:
            from session_exporter import get_exporter
            self.session_exporter = get_exporter()
        except Exception:
            self.session_exporter = None

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

    views = []
    if STATE.show_sessions:
        views.append(Text("[S]essions", style=Style(color=AMBER)))
    elif STATE.show_tools:
        views.append(Text("[T]ools", style=Style(color=AMBER)))
    elif STATE.show_marketplace:
        views.append(Text("[M]arket", style=Style(color=AMBER)))
    elif STATE.show_control:
        views.append(Text("[C]ontrol", style=Style(color=AMBER)))
    else:
        views.append(Text("[S]erver", style=Style(color=TEXT_MUTED)))
        views.append(Text("[T]ools", style=Style(color=TEXT_MUTED)))
        views.append(Text("[M]arket", style=Style(color=TEXT_MUTED)))
        views.append(Text("[C]trl", style=Style(color=TEXT_MUTED)))
        if STATE.split_pane:
            views.append(Text("[P]ane", style=Style(color=TEAL)))

    sep = Text("  │  ", style=Style(color=BRONZE))
    view_text = Text.assemble(*[v if i == 0 else Text("  ", style=Style(color=BRONZE)) + v for i, v in enumerate(views)])
    content = Text.assemble(title, subtitle, sep, status, sep, view_text)
    return Panel(content, style=Style(bgcolor=SURFACE_1), border_style=Style(color=BORDER))

def make_body(frame: int) -> Panel:
    if STATE.show_sessions:
        return make_sessions_panel()
    if STATE.show_tools:
        return make_tools_panel()
    if STATE.show_marketplace:
        return make_marketplace_panel()
    if STATE.show_control:
        return make_control_panel()
    return make_log_panel(frame)

def make_log_panel(frame: int) -> Panel:
    content = Text()

    # Status line
    glyph = "?"
    glyph_color = WARN
    if STATE.pending_approval or STATE.pending_download:
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

    # Approval prompts
    if STATE.pending_download:
        content.append(Text.assemble(
            Text("download approval: ", style=Style(color=WARN, bold=True)),
            Text(STATE.pending_download["repo"], style=Style(color=AMBER, bold=True)),
            "\n",
            Text(f"Category: {STATE.pending_download.get('category', 'recon')}", style=Style(color=TEXT_MUTED)),
            "\n",
            Text("y to approve download · n to deny", style=Style(color=DIM)),
        ))
        content.append("\n\n")

    if STATE.pending_approval:
        content.append(Text.assemble(
            Text("tool approval required: ", style=Style(color=WARN, bold=True)),
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

def make_tools_panel() -> Panel:
    content = Text()
    content.append(Text("tool registry — locally installed github tools\n\n", style=Style(color=TEXT_PRIMARY, bold=True)))

    if STATE.tool_loader is None:
        content.append(Text("tool loader unavailable — install requests library", style=Style(color=ERROR)))
        return Panel(content, title="[bold]Tools[/bold]", border_style=Style(color=TEAL), style=Style(bgcolor=SURFACE_0))

    tools = STATE.tool_loader.get_catalog_list()
    if not tools:
        content.append(Text("no tools installed — use /add-tool <github-url> to install", style=Style(color=TEXT_MUTED)))
    else:
        table = Table(show_header=True, box=None, pad_edge=False, border_style=Style(color=SURFACE_2))
        table.add_column("ID", style=Style(color=AMBER), width=14)
        table.add_column("Version", style=Style(color=TEAL), width=16)
        table.add_column("Category", style=Style(color=TEXT_MUTED), width=10)
        table.add_column("Path", style=Style(color=DIM))

        for t in tools:
            table.add_row(
                t.get("id", "?"),
                t.get("version", "?")[:14],
                t.get("category", "?"),
                str(t.get("binary_path", "?"))[:50],
            )
        content.append(table)
        content.append(Text(f"\n{len(tools)} tool(s) installed", style=Style(color=TEXT_MUTED)))

    content.append(Text("\n\ncommands: /add-tool <url> [cat]  /remove-tool <id>", style=Style(color=DIM)))
    return Panel(content, title="[bold]Tools[/bold]", border_style=Style(color=TEAL), style=Style(bgcolor=SURFACE_0))

def make_marketplace_panel() -> Panel:
    content = Text()
    content.append(Text("marketplace — curated security tools\n\n", style=Style(color=TEXT_PRIMARY, bold=True)))

    if STATE.tool_loader is None:
        content.append(Text("tool loader unavailable", style=Style(color=ERROR)))
        return Panel(content, title="[bold]Marketplace[/bold]", border_style=Style(color=AMBER), style=Style(bgcolor=SURFACE_0))

    items = STATE.tool_loader.get_marketplace()
    if not items:
        content.append(Text("marketplace empty", style=Style(color=TEXT_MUTED)))
    else:
        table = Table(show_header=True, box=None, pad_edge=False, border_style=Style(color=SURFACE_2))
        table.add_column("Name", style=Style(color=AMBER), width=12)
        table.add_column("Category", style=Style(color=TEAL), width=10)
        table.add_column("Repo", style=Style(color=TEXT_MUTED), width=28)
        table.add_column("Description", style=Style(color=DIM))

        installed = set(STATE.tool_loader.catalog.keys())
        for item in items:
            name = item.get("name", "?")
            mark = "✓ " if name in installed else "  "
            table.add_row(
                mark + name,
                item.get("category", "?"),
                item.get("repo", "?"),
                item.get("description", "")[:40],
            )
        content.append(table)
        content.append(Text("\n\nuse /add-tool <repo-url> to install  (e.g. /add-tool projectdiscovery/httpx)", style=Style(color=DIM)))

    return Panel(content, title="[bold]Marketplace[/bold]", border_style=Style(color=AMBER), style=Style(bgcolor=SURFACE_0))

def make_control_panel() -> Panel:
    content = Text()
    content.append(Text("control center — settings & configuration\n\n", style=Style(color=TEXT_PRIMARY, bold=True)))

    # Theme
    content.append(Text("Appearance\n", style=Style(color=BRONZE, bold=True)))
    content.append(Text(f"  Theme: dark (Hermes)\n", style=Style(color=TEXT_MUTED)))
    content.append(Text(f"  Split-pane: {'ON' if STATE.split_pane else 'OFF'}\n", style=Style(color=TEXT_MUTED)))
    content.append(Text("\n", style=Style(color=TEXT_MUTED)))

    # Agent
    content.append(Text("Agent\n", style=Style(color=BRONZE, bold=True)))
    content.append(Text(f"  Dry-run mode: {'ON' if STATE.dry_run else 'OFF'}\n", style=Style(color=WARN if STATE.dry_run else TEXT_MUTED)))
    content.append(Text(f"  System prompt: default\n", style=Style(color=TEXT_MUTED)))
    content.append(Text("\n", style=Style(color=TEXT_MUTED)))

    # Security
    content.append(Text("Security\n", style=Style(color=BRONZE, bold=True)))
    content.append(Text(f"  Output sanitization: ON\n", style=Style(color=OK)))
    content.append(Text(f"  Rate limit: 30 calls/min\n", style=Style(color=TEXT_MUTED)))
    content.append(Text("\n", style=Style(color=TEXT_MUTED)))

    content.append(Text("commands: /dry-run  /split  /theme", style=Style(color=DIM)))
    return Panel(content, title="[bold]Control Center[/bold]", border_style=Style(color=AMBER), style=Style(bgcolor=SURFACE_0))

def make_footer() -> Panel:
    if STATE.pending_approval or STATE.pending_download:
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
            if STATE.audit_logger:
                STATE.audit_logger.tool_executed(sid, tool_id, ok, duration, output, error)
        return

    if etype == "sessions_snapshot":
        STATE.sessions = event.get("sessions", [])
        return

    if etype == "config_state":
        nim_set = event.get("nimApiKeySet", False)
        if not nim_set:
            add_log("NIM API key not set — agent will not respond. Use Control Center to configure.", WARN)
        return

    if etype == "tools_catalog":
        tools = event.get("tools", [])
        implemented = sum(1 for t in tools if t.get("implemented"))
        add_log(f"{implemented} of {len(tools)} tools have real handlers", DIM)
        return

    if etype == "stream_token":
        token = event.get("token", event.get("text", ""))
        STATE.stream_buffer += token
        # Update last log line if it's a stream
        if STATE.logs and STATE.logs[-1].get("is_stream"):
            STATE.logs[-1]["text"] = STATE.stream_buffer
        else:
            STATE.logs.append({"text": STATE.stream_buffer, "color": TEXT_PRIMARY, "is_stream": True})
        return

    if etype == "agent_plan":
        steps = event.get("steps", [])
        STATE.plan_steps = steps
        STATE.current_plan_step = -1
        plan_text = "PLAN:\n" + "\n".join(f"  {i+1}. {s}" for i, s in enumerate(steps))
        add_log(plan_text, AMBER)
        return

    if etype == "recon_complete":
        result = event.get("result", {})
        success = result.get("success", False)
        target = result.get("target", "?")
        findings = result.get("total_findings", 0)
        duration = result.get("duration_seconds", 0)
        if success:
            add_log(f"[RECON] {target} complete — {findings} findings in {duration}s", OK)
        else:
            add_log(f"[RECON] {target} failed: {result.get('error', 'unknown')}", ERROR)
        return

    if etype == "brute_complete":
        result = event.get("result", {})
        success = result.get("success", False)
        attack = result.get("attack_type", "?")
        count = result.get("results_count", 0)
        if success:
            add_log(f"[BRUTE] {attack} complete — {count} results", OK)
        else:
            add_log(f"[BRUTE] failed: {result.get('error', 'unknown')}", ERROR)
        return

    if etype == "report_generated":
        files = event.get("files", {})
        count = event.get("vulnerability_count", 0)
        add_log(f"[REPORT] Generated with {count} vulns — files: {', '.join(files.keys())}", OK)
        return

    if etype == "targets_list":
        targets = event.get("targets", [])
        add_log(f"Targets ({len(targets)}):", AMBER)
        for t in targets:
            name = t.get("name", "?")
            platform = t.get("platform", "?")
            enabled = "✓" if t.get("enabled") else "✗"
            add_log(f"  {enabled} {name} ({platform})", DIM)
        return

    if etype == "github_tool_status":
        success = event.get("success", False)
        msg = event.get("message", "")
        tool = event.get("tool")
        if success and tool:
            add_log(f"[github] {msg} — {tool.get('id')} {tool.get('version')}", OK)
        else:
            add_log(f"[github] {msg}", ERROR if not success else WARN)
        return

    if etype == "marketplace_catalog":
        items = event.get("marketplace", [])
        add_log(f"marketplace: {len(items)} tools available", DIM)
        return

def add_log(text: str, color: str = TEXT_MUTED):
    STATE.logs.append({"text": text, "color": color})
    if len(STATE.logs) > 200:
        STATE.logs = STATE.logs[-100:]

# ─── Slash Commands ──────────────────────────────────────────────────────────
def handle_slash_command(buf: str) -> bool:
    """Returns True if the buffer was a slash command and was handled."""
    parts = buf.split()
    if not parts:
        return False
    cmd = parts[0].lower()

    if cmd == "/add-tool":
        if len(parts) < 2:
            add_log("Usage: /add-tool <github-url-or-repo> [category]", WARN)
            return True
        url = parts[1]
        category = parts[2] if len(parts) > 2 else "recon"
        if STATE.tool_loader is None:
            add_log("Tool loader not available. Install requests: pip install requests", ERROR)
            return True
        # Approval gate
        repo = STATE.tool_loader.parse_repo(url)
        if not repo:
            add_log(f"Could not parse repo from: {url}", ERROR)
            return True
        STATE.pending_download = {
            "url": url,
            "repo": repo,
            "category": category,
        }
        add_log(f"Download approval requested for {repo} ({category})", WARN)
        return True

    if cmd == "/tools":
        STATE.show_tools = not STATE.show_tools
        STATE.show_sessions = False
        STATE.show_marketplace = False
        if STATE.show_tools:
            add_log("Showing tool registry. Press T again to close.", DIM)
        return True

    if cmd == "/marketplace":
        STATE.show_marketplace = not STATE.show_marketplace
        STATE.show_sessions = False
        STATE.show_tools = False
        if STATE.show_marketplace:
            add_log("Showing marketplace. Press M again to close.", DIM)
        return True

    if cmd == "/remove-tool":
        if len(parts) < 2:
            add_log("Usage: /remove-tool <tool-id>", WARN)
            return True
        tool_id = parts[1]
        if STATE.tool_loader is None:
            add_log("Tool loader not available.", ERROR)
            return True
        ok, msg = STATE.tool_loader.remove_tool(tool_id)
        add_log(msg, OK if ok else ERROR)
        return True

    if cmd == "/export":
        if len(parts) < 2:
            add_log("Usage: /export markdown | json | audit | list", WARN)
            return True
        fmt = parts[1].lower()
        if fmt == "audit":
            if STATE.audit_logger:
                recent = STATE.audit_logger.get_recent(20)
                add_log(f"Recent audit entries ({len(recent)}):", DIM)
                for entry in recent:
                    ts = entry.get("timestamp", "?")[11:19]
                    cat = entry.get("category", "?")
                    action = entry.get("action", "?")
                    actor = entry.get("actor", "?")
                    add_log(f"  [{ts}] {cat}/{action} by {actor}", DIM)
            else:
                add_log("Audit logger not available", ERROR)
            return True
        if fmt == "list":
            if STATE.session_exporter:
                exports = STATE.session_exporter.list_exports()
                add_log(f"Exports: {len(exports)} files", DIM)
                for e in exports[:10]:
                    add_log(f"  {e['filename']} ({e['size']} bytes)", DIM)
            else:
                add_log("Session exporter not available", ERROR)
            return True
        if fmt in ("markdown", "md"):
            if STATE.session_exporter:
                path = STATE.session_exporter.export_markdown(
                    STATE.current_session_id,
                    [{"role": "system", "text": l["text"]} for l in STATE.logs],
                )
                add_log(f"Exported to {path}", OK)
            else:
                add_log("Session exporter not available", ERROR)
            return True
        if fmt == "json":
            if STATE.session_exporter:
                path = STATE.session_exporter.export_json(
                    STATE.current_session_id,
                    [{"role": "system", "text": l["text"]} for l in STATE.logs],
                )
                add_log(f"Exported to {path}", OK)
            else:
                add_log("Session exporter not available", ERROR)
            return True
        add_log("Usage: /export markdown | json | audit | list", WARN)
        return True

    if cmd == "/dry-run":
        STATE.dry_run = not STATE.dry_run
        add_log(f"Dry-run mode: {'ON' if STATE.dry_run else 'OFF'}", WARN if STATE.dry_run else OK)
        return True

    if cmd == "/split":
        STATE.split_pane = not STATE.split_pane
        add_log(f"Split-pane: {'ON' if STATE.split_pane else 'OFF'}", OK)
        return True

    if cmd == "/config" or cmd == "/control":
        STATE.show_control = not STATE.show_control
        STATE.show_sessions = False
        STATE.show_tools = False
        STATE.show_marketplace = False
        if STATE.show_control:
            add_log("Showing Control Center. Press C again to close.", DIM)
        return True

    if cmd == "/bb" or cmd == "/bounty":
        STATE.bb_mode = not STATE.bb_mode
        add_log(f"Bug Bounty mode: {'ON' if STATE.bb_mode else 'OFF'}", OK if STATE.bb_mode else DIM)
        if STATE.bb_mode:
            add_log("Bug Bounty commands: /target <name>  /recon  /brute <type>  /report  /submit  /sync-h1 <handle>", AMBER)
        return True

    if cmd == "/target":
        if len(parts) < 2:
            add_log("Usage: /target <target-name>", WARN)
            return True
        STATE.current_target = parts[1]
        add_log(f"Target set: {parts[1]}", OK)
        return True

    if cmd == "/recon":
        if not STATE.current_target:
            add_log("No target set. Use /target <name> first.", ERROR)
            return True
        add_log(f"Starting reconnaissance on {STATE.current_target}...", AMBER)
        # Send to gateway/tools agent
        send_ws_sync({
            "type": "execute_recon",
            "target": STATE.current_target,
            "scope_name": STATE.current_target,
        })
        return True

    if cmd == "/brute":
        if len(parts) < 2:
            add_log("Usage: /brute <dirs|subdomains|params|vhosts|api|idor> [wordlist]", WARN)
            return True
        attack_type = parts[1]
        wordlist = parts[2] if len(parts) > 2 else "common"
        if not STATE.current_target:
            add_log("No target set. Use /target <name> first.", ERROR)
            return True
        add_log(f"Starting {attack_type} brute force on {STATE.current_target}...", AMBER)
        send_ws_sync({
            "type": "execute_brute",
            "target": STATE.current_target,
            "attack_type": attack_type,
            "wordlist": wordlist,
            "scope_name": STATE.current_target,
        })
        return True

    if cmd == "/report":
        if not STATE.current_target:
            add_log("No target set. Use /target <name> first.", ERROR)
            return True
        add_log(f"Generating report for {STATE.current_target}...", AMBER)
        send_ws_sync({
            "type": "generate_report",
            "program": STATE.current_target,
            "handle": STATE.current_target,
        })
        return True

    if cmd == "/submit":
        if not STATE.current_target:
            add_log("No target set. Use /target <name> first.", ERROR)
            return True
        add_log(f"Submitting findings to HackerOne for {STATE.current_target}...", AMBER)
        send_ws_sync({
            "type": "submit_hackerone",
            "target": STATE.current_target,
        })
        return True

    if cmd == "/sync-h1":
        if len(parts) < 2:
            add_log("Usage: /sync-h1 <program-handle>", WARN)
            return True
        handle = parts[1]
        add_log(f"Syncing HackerOne program: {handle}...", AMBER)
        send_ws_sync({
            "type": "sync_hackerone",
            "handle": handle,
        })
        return True

    if cmd == "/targets":
        send_ws_sync({"type": "list_targets"})
        return True

    if cmd in ("/help", "/?"):
        add_log("Commands: /add-tool <url> [cat]  /tools  /marketplace  /remove-tool <id>", DIM)
        add_log("          /export <fmt>  /dry-run  /split  /config  /bb  /target <name>", DIM)
        add_log("          /recon  /brute <type>  /report  /submit  /sync-h1 <handle>  /targets", DIM)
        return True

    return False

def execute_download(approved: bool):
    if not STATE.pending_download:
        return
    if not approved:
        add_log("Download denied.", ERROR)
        if STATE.audit_logger:
            STATE.audit_logger.system_event("Tool download denied by user", "warn")
        STATE.pending_download = None
        return

    dd = STATE.pending_download
    STATE.pending_download = None
    add_log(f"Downloading {dd['repo']}...", AMBER)
    if STATE.audit_logger:
        STATE.audit_logger.system_event(f"Tool download approved: {dd['repo']}", "info")

    def do_install():
        try:
            ok, msg, spec = STATE.tool_loader.install_tool(
                dd["url"], category=dd.get("category", "recon")
            )
            if ok and spec:
                add_log(f"✓ {msg}", OK)
                if STATE.audit_logger:
                    STATE.audit_logger.tool_installed(spec.id, spec.repo, spec.version, spec.binary_path)
                # Also notify gateway
                if STATE.ws and STATE.connected and STATE.authed:
                    send_ws_sync({
                        "type": "register_github_tool",
                        "url": dd["url"],
                        "category": dd.get("category", "recon"),
                        "tool": spec.__dict__ if hasattr(spec, "__dict__") else spec,
                    })
            else:
                add_log(f"✗ {msg}", ERROR)
                if STATE.audit_logger:
                    STATE.audit_logger.system_event(f"Tool install failed: {msg}", "error")
        except Exception as e:
            add_log(f"✗ Install error: {e}", ERROR)
            if STATE.audit_logger:
                STATE.audit_logger.system_event(f"Tool install exception: {e}", "error")

    threading.Thread(target=do_install, daemon=True).start()

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
                elif ch.lower() == 's' and not STATE._input_buffer and not STATE.pending_approval and not STATE.pending_download:
                    STATE.show_sessions = not STATE.show_sessions
                    STATE.show_tools = False
                    STATE.show_marketplace = False
                    if STATE.show_sessions and STATE.ws and STATE.connected and STATE.authed:
                        send_ws_sync({"type": "list_sessions"})
                elif ch.lower() == 't' and not STATE._input_buffer and not STATE.pending_approval and not STATE.pending_download:
                    STATE.show_tools = not STATE.show_tools
                    STATE.show_sessions = False
                    STATE.show_marketplace = False
                elif ch.lower() == 'm' and not STATE._input_buffer and not STATE.pending_approval and not STATE.pending_download:
                    STATE.show_marketplace = not STATE.show_marketplace
                    STATE.show_sessions = False
                    STATE.show_tools = False
                    STATE.show_control = False
                elif ch.lower() == 'c' and not STATE._input_buffer and not STATE.pending_approval and not STATE.pending_download:
                    STATE.show_control = not STATE.show_control
                    STATE.show_sessions = False
                    STATE.show_tools = False
                    STATE.show_marketplace = False
                elif ch.lower() == 'p' and not STATE._input_buffer and not STATE.pending_approval and not STATE.pending_download:
                    STATE.split_pane = not STATE.split_pane
                    add_log(f"Split-pane: {'ON' if STATE.split_pane else 'OFF'}", OK)
                elif ch.lower() == 'y' and (STATE.pending_approval or STATE.pending_download):
                    if STATE.pending_download:
                        execute_download(True)
                    elif STATE.pending_approval:
                        send_approval(True)
                elif ch.lower() == 'n' and (STATE.pending_approval or STATE.pending_download):
                    if STATE.pending_download:
                        execute_download(False)
                    elif STATE.pending_approval:
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
        if handle_slash_command(buf):
            return

    if STATE.pending_approval or STATE.pending_download:
        if buf.lower() in ('y', 'yes'):
            if STATE.pending_download:
                execute_download(True)
            else:
                send_approval(True)
        elif buf.lower() in ('n', 'no'):
            if STATE.pending_download:
                execute_download(False)
            else:
                send_approval(False)
        return

    if STATE.ws and STATE.connected and STATE.authed:
        working = STATE.agent_state in ("thinking", "running_tool")
        if working:
            add_log("A session is already running — wait for it to finish or start a new one.", WARN)
            return
        STATE.current_session_id = STATE.new_session_id()
        STATE.logs = []
        msg = json.dumps({
            "type": "session_start",
            "sessionId": STATE.current_session_id,
            "goal": buf,
            "origin": "cli"
        })
        send_ws_sync_raw(msg)
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
        send_ws_sync_raw(msg)
        add_log(f"{'approved' if approved else 'denied'}: {STATE.pending_approval['toolId']}", OK if approved else ERROR)
        STATE.pending_approval = None

def send_ws_sync(msg: dict):
    if STATE.ws and STATE.connected:
        try:
            asyncio.run_coroutine_threadsafe(
                STATE.ws.send(json.dumps(msg)),
                loop=asyncio.get_event_loop()
            )
        except Exception:
            pass

def send_ws_sync_raw(text: str):
    if STATE.ws and STATE.connected:
        try:
            asyncio.run_coroutine_threadsafe(
                STATE.ws.send(text),
                loop=asyncio.get_event_loop()
            )
        except Exception:
            pass

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

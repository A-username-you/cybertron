# Cybertron — Red + Blue Team Agent

A unified cybersecurity agent runtime with **three interfaces**: Terminal (TUI), Desktop (GUI), and Web — all connecting to one gateway.

![Cybertron](https://img.shields.io/badge/platform-Linux-blue) ![Python](https://img.shields.io/badge/python-3.10+-green)

## What's Inside

| Component | File | Description |
|-----------|------|-------------|
| **Gateway** | `gateway.py` | Async WebSocket + HTTP server. Runs the agent loop, manages sessions, handles auth. |
| **Web UI** | `web_ui.html` | Self-contained browser UI with live pixel-art animations (Canvas). |
| **TUI** | `tui.py` | Terminal UI using Rich. ASCII art state icons, keyboard-driven. |
| **GUI** | `gui.py` | Desktop UI using Tkinter. Canvas-rendered pixel art, mouse + keyboard. |
| **Launcher** | `cybertron.py` | Unified entry point: `gateway`, `tui`, `gui`, `web`. |

## Architecture

```
┌─────────────┐   ┌─────────────┐   ┌─────────────┐
│   Web UI    │   │    TUI      │   │    GUI      │
│  (Browser)  │   │ (Terminal)  │   │  (Desktop)  │
└──────┬──────┘   └──────┬──────┘   └──────┬──────┘
       │                 │                 │
       └─────────────────┼─────────────────┘
                         │  WebSocket + HTTP
                         ▼
              ┌─────────────────────┐
              │   Cybertron Gateway   │
              │   (FastAPI + WS)      │
              └─────────────────────┘
                         │
              ┌──────────┴──────────┐
              │   Agent Simulation    │
              │  thinking → tool →     │
              │  writing → result     │
              └─────────────────────┘
```

All three UIs are **thin clients** — the agent logic lives only in the gateway.

## Animated State Icons

Three pixel-art icons, drawn with the same mathematical functions across all interfaces:

| Icon | State | Description |
|------|-------|-------------|
| 🪐 **Ringed Planet** | `thinking`, `running_tool`, `awaiting_approval` | Slowly rotating rings, pulsing planet |
| 🌀 **Spiral** | `writing` | Continuously swirling arms |
| ⭐ **Star Burst** | `result` | One-shot explosive pop, then idle |

The Web UI and GUI render these as **28×28 pixel art scaled to 140×140** using the exact same color ramp (gold → amber → teal → navy).

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

Requires Python 3.10+ and these packages:
- `fastapi` + `uvicorn` — gateway HTTP/WebSocket server
- `websockets` — WebSocket client (all UIs)
- `rich` — terminal rendering (TUI)
- `tkinter` — built-in, for GUI

### 2. Start the Gateway

```bash
python cybertron.py gateway
# or
python gateway.py
```

The gateway will:
- Bind to `127.0.0.1:8765`
- Generate an auth token at `~/.cybertron/auth-token`
- Print the token to console

### 3. Launch a UI

**Web UI** (open in any browser):
```bash
python cybertron.py web
# Then open http://127.0.0.1:8080/web_ui.html
```

**Terminal UI**:
```bash
python cybertron.py tui
```

**Desktop GUI**:
```bash
python cybertron.py gui
# or
python cybertron.py desktop
```

All UIs auto-read the auth token from `~/.cybertron/auth-token` (except the Web UI in a standalone browser, which prompts for it).

## Authentication

- Token is generated on first gateway start and stored at `~/.cybertron/auth-token` (mode `0600`)
- Override with `CYBERTRON_AUTH_TOKEN` environment variable
- Wrong token → connection rejected immediately
- All commands gated until authenticated

## Agent Lifecycle

```
IDLE → THINKING → RUNNING_TOOL → WRITING → RESULT → IDLE
                ↑                    ↓
         (approval gate for         (star burst)
          exploit tools)
```

1. **Thinking** — Agent plans the approach (planet animation)
2. **Running Tool** — Executes recon tool: `subfinder`, `httpx`, `nuclei`, `gitleaks`, `yara-scan`
3. **Approval Gate** — Exploit tools (`sqlmap`, `xss-verify`, etc.) require explicit Y/N approval
4. **Writing** — Synthesizes results into report (spiral animation)
5. **Result** — Star burst animation, then back to idle

## TUI Controls

| Key | Action |
|-----|--------|
| `Enter` | Submit goal / confirm approval |
| `S` | Toggle Server View (all sessions) |
| `Y` / `N` | Approve / deny tool (when prompted) |
| `Backspace` | Delete character |
| `Ctrl+C` | Quit |

## GUI Features

- **Pixel-art Canvas** — Exact same 28×28 math as Web UI, rendered in Tkinter
- **Server Toggle** — Switch between current session and all gateway sessions
- **Approval Modal** — Popup dialog for exploit-gated tools
- **Event Log** — Scrollable colored log with timestamps
- **Responsive Layout** — Adapts to window resizing

## Web UI Features

- **Auth Gate** — Clean token entry with connection status
- **Responsive Design** — Works on phone, tablet, desktop
- **Real-time Animations** — 12fps Canvas rendering
- **Session Sidebar** — Live list of all active sessions
- **Approval Modal** — Full tool details before approval
- **Auto-reconnect** — 3-second retry on disconnect

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CYBERTRON_HOST` | `127.0.0.1` | Gateway bind address |
| `CYBERTRON_PORT` | `8765` | Gateway port |
| `CYBERTRON_AUTH_TOKEN` | *(auto)* | Override auth token |
| `CYBERTRON_WEB_PORT` | `8080` | Web UI server port |

## File Structure

```
cybertron/
├── gateway.py          # FastAPI + WebSocket gateway
├── web_ui.html         # Standalone browser UI
├── tui.py              # Rich-based terminal UI
├── gui.py              # Tkinter desktop UI
├── cybertron.py        # Unified launcher
├── requirements.txt    # Python dependencies
└── README.md           # This file
```

## Protocol

WebSocket messages (JSON):

**Client → Server:**
- `session_start` — `{type, goal}`
- `tool_call_approval` — `{type, sessionId, approved}`
- `sessions_request` — `{type}`

**Server → Client:**
- `agent_status` — `{type, sessionId, status, detail}`
- `sessions_snapshot` — `{type, sessions[]}`
- `tool_call_request` — `{type, sessionId, tool, args, reason}`
- `tool_call_result` — `{type, sessionId, result}`

## Security Notes

- Gateway binds to `127.0.0.1` only (not 0.0.0.0)
- Exploit-category tools are **stubbed and hard-gated** — no payload logic without human approval
- Auth token is 48 hex chars (24 random bytes)
- Token file has `0600` permissions

## Troubleshooting

| Issue | Fix |
|-------|-----|
| "No auth token found" | Start the gateway first to generate one |
| TUI crashes on startup | Ensure you're running in an interactive terminal (not piped) |
| Web UI won't connect | Verify gateway is running and token is correct |
| GUI shows blank window | Check that gateway is running and accessible |
| Port 8765 in use | Set `CYBERTRON_PORT` to a different port |

## License

MIT — Built for red/blue team operations with safety gating.

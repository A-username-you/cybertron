# Cybertron Python UI Layer

Alternative UI layer for the Cybertron red/blue team agent, built in Python.
Connects to the existing **Node.js runtime gateway** via WebSocket.

## What's Different

| | Original (Node) | This (Python) |
|---|---|---|
| **Gateway** | `runtime/src/server.ts` (kept) | Same gateway — no change |
| **Web UI** | Next.js + static export | Single HTML file, no build step |
| **TUI** | Ink (React for terminal) | Rich (Python terminal framework) |
| **GUI** | Electron + Next.js | Tkinter + Canvas pixel art |
| **Build** | `npm install`, `next build`, `electron-builder` | `pip install -r requirements.txt` |

## Quick Start

```bash
# 1. Install Python deps
pip install -r requirements.txt

# 2. Start the Node.js gateway (from your existing project)
cd /path/to/cybertron/runtime
npm run dev
# or: npx ts-node src/server.ts

# 3. Launch any Python UI
python cybertron_ui.py tui     # Terminal
python cybertron_ui.py gui     # Desktop
python cybertron_ui.py web     # Browser at http://127.0.0.1:8080/web_ui.html
```

## Protocol Compatibility

These UIs speak the **exact same WebSocket protocol** as your Node runtime:

| Message | Direction | Notes |
|---------|-----------|-------|
| `auth` | → | Sent after WS open |
| `auth_result` | ← | Unlocks the UI |
| `session_start` | → | `sessionId`, `goal`, `origin` |
| `agent_status` | ← | `state`, `detail`, `sessionId` |
| `tool_call_request` | ← | `requestId`, `toolId`, `args` |
| `tool_call_approval` | → | `requestId`, `approved` |
| `tool_call_result` | ← | `ok`, `output`, `error`, `durationMs` |
| `sessions_snapshot` | ← | All active sessions |
| `list_sessions` | → | Request snapshot |
| `get_tools` | → | Request tool catalog |
| `config_state` | ← | `nimApiKeySet` flag |

## Hermes Design System

All three UIs use the **Hermes Agent default skin**:

- **Background**: `#14141f` (deep navy)
- **Surface**: `#1a1a2e` (slightly lighter navy)
- **Text**: `#FFF8DC` (cornsilk)
- **Accent**: `#FFBF00` (amber) / `#FFD700` (gold)
- **Bronze**: `#CD7F32` (borders, labels)
- **Teal**: `#4dd0e1` (user labels, info)
- **Success**: `#4caf50` / **Error**: `#ef5350`

The Web UI includes the **warm glow vignette** and **grain texture overlay** from the original Hermes CSS.

## File Structure

```
cybertron-python-ui/
├── protocol.py          # Shared types & constants
├── tui.py               # Rich terminal UI
├── gui.py               # Tkinter desktop GUI
├── web_ui.html          # Standalone browser UI
├── cybertron_ui.py      # Unified launcher
├── requirements.txt     # Python dependencies
└── README.md            # This file
```

## Why Python UIs?

| Advantage | Detail |
|-----------|--------|
| **Zero build** | No `npm install`, no `next build`, no `electron-builder` |
| **Single file** | `web_ui.html` is self-contained — open in any browser |
| **No Node required** | For users who just want the UI, not the full dev stack |
| **Fast iteration** | Edit `.py` or `.html`, run immediately |
| **Lightweight** | `websockets` + `rich` = ~2MB vs Next.js + Electron = ~200MB+ |

## Notes

- The Python UIs are **thin clients** — all agent logic stays in the Node.js gateway
- Auth token is read from `~/.cybertron/auth-token` (same as Node runtime)
- The Web UI can be served from any static file server — no API routes needed
- All three UIs support the **Server toggle** (`S` key / button) to view all gateway sessions
- Exploit-gated tools trigger an approval modal in all three UIs

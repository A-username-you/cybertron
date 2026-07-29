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
| `register_github_tool` | → | Install tool from GitHub |
| `github_tool_status` | ← | Install result broadcast |
| `get_marketplace` | → | Request curated tool list |
| `marketplace_catalog` | ← | Curated security tools |
| `remove_tool` | → | Remove installed tool |
| `stream_token` | ← | **NEW** Real-time reasoning tokens |
| `agent_plan` | ← | **NEW** Multi-step execution plan |
| `dry_run` | → | **NEW** Plan without executing |
| `dry_run_result` | ← | **NEW** Dry-run plan output |
| `get_config` | → | **NEW** Request settings |
| `set_config` | → | **NEW** Update settings |
| `config_updated` | ← | **NEW** Settings confirmed |

## Feature Matrix

| Feature | TUI | GUI | Web UI |
|---------|-----|-----|--------|
| **GitHub Tool Loader** | | | |
| `/add-tool <url> [cat]` | ✅ | ✅ | ✅ |
| `/tools` registry view | ✅ | ✅ | ✅ |
| `/marketplace` browse | ✅ | ✅ | ✅ |
| `/remove-tool <id>` | ✅ | ✅ | ✅ |
| Download approval gate | ✅ | ✅ | ✅ |
| Auto platform detection | ✅ | ✅ | ✅ |
| Auto architecture detection | ✅ | ✅ | ✅ |
| `--version` validation | ✅ | ✅ | ✅ |
| `--help` schema inference | ✅ | ✅ | ✅ |
| Catalog persistence | ✅ | ✅ | ✅ |
| **Agent Intelligence** | | | |
| Streaming responses | ✅ | ✅ | ✅ |
| Multi-step planning | ✅ | ✅ | ✅ |
| Dry-run mode | ✅ | ✅ | ✅ |
| **UI/UX** | | | |
| Control Center panel | ✅ | ✅ | ✅ |
| Theme toggle (dark/light) | — | — | ✅ |
| Split-pane transcript | ✅ | ✅ | ✅ |
| Keyboard shortcuts | ✅ | ✅ | ✅ |
| PWA support | — | — | ✅ |
| **Security & Safety** | | | |
| Audit logging | ✅ | ✅ | — |
| Session export (MD/JSON) | ✅ | ✅ | — |
| Output sanitization | — | — | UI-ready |
| Rate limiting | — | — | UI-ready |

## GitHub Tool Loader

Paste any GitHub URL and Cybertron downloads, validates, and registers it as a usable tool.

```
/add-tool https://github.com/projectdiscovery/httpx recon
/add-tool projectdiscovery/subfinder
/marketplace
/tools
/remove-tool httpx
```

### How It Works

1. **Parse** — Extracts `owner/repo` from the URL
2. **Fetch** — Calls GitHub API for latest release
3. **Detect** — Auto-detects the correct binary for your platform (Linux/macOS/Windows, amd64/arm64)
4. **Download** — Fetches the release asset to `~/.cybertron/tools/<name>/`
5. **Extract** — Handles `.zip`, `.tar.gz`, `.tar.xz`, raw binaries
6. **Validate** — Runs `--version` to confirm it works
7. **Infer schema** — Parses `--help` output to build a JSON schema
8. **Register** — Adds to local catalog and broadcasts to all connected clients
9. **Persist** — Catalog saved to `~/.cybertron/tools/catalog.json`

### Marketplace

A curated list of popular security tools is built-in:

| Tool | Category | Description |
|------|----------|-------------|
| subfinder | recon | Fast passive subdomain discovery |
| httpx | recon | Fast multi-purpose HTTP toolkit |
| nuclei | scan | Vulnerability scanner |
| gitleaks | secrets | Detect hardcoded secrets |
| naabu | scan | Fast port scanner |
| katana | crawl | Next-gen crawling framework |
| amass | recon | Attack surface mapping |
| ffuf | fuzz | Fast web fuzzer |
| dalfox | scan | Modern XSS scanner |
| tlsx | recon | TLS connection analysis |

### Security

- **Approval gate** — Every download requires explicit Y/N approval before any network request
- **Sandboxed paths** — Tools are isolated in `~/.cybertron/tools/`
- **No PATH pollution** — Binaries are not added to system PATH
- **Version validation** — `--version` is run immediately; failures are logged but don't block registration
- **Source verification** — Only github.com URLs are accepted; repo format is strictly validated

## Agent Intelligence

### Streaming Responses

When the gateway sends `stream_token` messages, the UIs render them in real-time with a typewriter effect:
- **TUI**: Appends tokens to a live log line
- **GUI**: Updates a dedicated stream label in the chat
- **Web UI**: Appends tokens to a streaming message bubble with a blinking cursor

### Multi-step Planning

When the gateway sends `agent_plan` messages, the UIs display the execution plan:
```
PLAN:
  1. recon — subfinder -d example.com
  2. scan — httpx -l subdomains.txt
  3. report — nuclei -l live_hosts.txt
```

The Web UI renders this as an interactive checklist with active/done states.

### Dry-run Mode

Enable with `/dry-run` (or toggle in Control Center). The agent plans but does not execute — showing exactly what it *would* do.

## UI/UX Features

### Control Center

Access via `C` key or `/config` command:
- **Appearance**: Theme selector, split-pane toggle
- **Agent**: System prompt selection (Default, Red Team, Blue Team, Compliance, Custom), dry-run toggle
- **API**: NIM API key, model selection
- **Security**: Output sanitization, rate limiting

### Theme Toggle (Web UI)

Switch between **Hermes Dark** (default) and **Light Audit Mode** (for screenshots). Persisted in `localStorage`.

### Split-pane Transcript

Toggle with `P` key or `/split` command. Shows raw tool output in a side panel while chat stays clean on the left.

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Enter` | Send message / command |
| `S` | Toggle Server view |
| `T` | Toggle Tools registry |
| `M` | Toggle Marketplace |
| `C` | Open Control Center |
| `P` | Toggle split-pane |
| `?` | Show keyboard shortcuts |
| `Y` | Approve prompt |
| `N` | Deny prompt |
| `/` | Focus composer |
| `Esc` | Close overlays |

### PWA Support (Web UI)

The Web UI includes a web app manifest for installability:
- Works offline (shows connection status)
- Theme color matches current mode
- Responsive down to 320px

## Audit & Export

### Audit Logger

Every significant action is recorded to `~/.cybertron/audit.log`:
- Session starts (goal, origin, timestamp)
- Tool requests (toolId, args)
- Approvals/denials (actor, timestamp)
- Tool executions (success, duration, output)
- Downloads/installs (repo, version, path)
- Config changes (key, old→new value)

### Session Export

Export any session to Markdown or JSON:
```
/export markdown    → ~/.cybertron/exports/session_<id>_<timestamp>.md
/export json       → ~/.cybertron/exports/session_<id>_<timestamp>.json
/export audit      → View last 20 audit entries
/export list       → List all exported files
```

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
├── github_tool_loader.py      # Core GitHub tool download/validation engine
├── audit_logger.py             # Structured audit logging
├── session_exporter.py         # Markdown/JSON session export
├── marketplace.json            # Curated security tools catalog
├── protocol.py                 # Shared types & WebSocket message constants
├── tui.py                      # Rich terminal UI
├── gui.py                      # Tkinter desktop GUI
├── web_ui.html                 # Standalone browser UI (PWA-ready)
├── cybertron_ui.py             # Unified launcher
├── requirements.txt            # Python dependencies
└── README.md                   # This file
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
- Tool downloads from GitHub trigger a **second approval gate** before any network request is made
- Streaming responses require gateway support for `stream_token` messages
- Multi-step planning requires gateway support for `agent_plan` messages
- Dry-run mode requires gateway support for `dry_run` / `dry_run_result` messages

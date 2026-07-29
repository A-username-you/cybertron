# Cybertron Python UI — Quick Start

## 1. Install

```bash
pip install -r requirements.txt
```

Dependencies: `websockets`, `rich`, `requests`

## 2. Start Gateway

From your existing Cybertron project:

```bash
cd runtime
npm run dev
```

The gateway must be running on `ws://127.0.0.1:8765`.

## 3. Launch UI

```bash
# Terminal UI (Rich)
python cybertron_ui.py tui

# Desktop GUI (Tkinter)
python cybertron_ui.py gui

# Web UI (Browser)
python cybertron_ui.py web
# Then open http://127.0.0.1:8080/web_ui.html
```

## 4. First Commands

```
/help                    # Show all commands
/marketplace             # Browse curated security tools
/add-tool projectdiscovery/httpx recon    # Install httpx
/tools                   # View installed tools
/dry-run                 # Enable plan-only mode
/config                  # Open Control Center
/split                   # Toggle raw output pane
/export markdown         # Export session report
```

## 5. Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Enter` | Send |
| `S` | Server view |
| `T` | Tools registry |
| `M` | Marketplace |
| `C` | Control Center |
| `P` | Split-pane |
| `?` | Shortcuts help |
| `Y` / `N` | Approve / Deny |
| `/` | Focus input |
| `Esc` | Close overlay |

## 6. File Locations

| Path | Purpose |
|------|---------|
| `~/.cybertron/auth-token` | Gateway auth token |
| `~/.cybertron/tools/catalog.json` | Installed tools registry |
| `~/.cybertron/tools/<name>/` | Tool binaries |
| `~/.cybertron/audit.log` | Audit trail (JSON lines) |
| `~/.cybertron/exports/` | Session exports |
| `~/.cybertron/webhooks.json` | Webhook configs |

## 7. Architecture

```
User -> UI (TUI/GUI/Web) -> WebSocket -> Node.js Gateway -> NIM LLM
                |
        github_tool_loader.py  (downloads from GitHub)
        audit_logger.py        (records all actions)
        output_sanitizer.py    (redacts sensitive data)
        rate_limiter.py        (prevents runaway agents)
        webhook_notifier.py    (alerts to Slack/SIEM)
```

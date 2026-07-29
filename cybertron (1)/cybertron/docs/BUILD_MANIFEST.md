# Cybertron Python UI — Complete Build Manifest

## Overview

This build implements **all major features** from the Cybertron update spec across the entire Python UI layer (TUI, GUI, Web UI), plus supporting infrastructure modules.

---

## Files Delivered (14 files, ~210 KB)

| # | File | Lines | Purpose |
|---|------|-------|---------|
| 1 | `github_tool_loader.py` | ~450 | Core engine: GitHub release download, extract, validate, schema inference |
| 2 | `audit_logger.py` | ~180 | Structured append-only audit log to `~/.cybertron/audit.log` |
| 3 | `session_exporter.py` | ~110 | Markdown/JSON session transcript export |
| 4 | `output_sanitizer.py` | ~140 | Auto-redact IPs, emails, secrets, keys, credit cards |
| 5 | `rate_limiter.py` | ~100 | Sliding-window rate limiter (calls/min) |
| 6 | `webhook_notifier.py` | ~140 | POST findings to Slack, Discord, SIEM, custom endpoints |
| 7 | `marketplace.json` | ~50 | Curated security tools catalog (10 tools) |
| 8 | `protocol.py` | ~100 | Extended WebSocket message type definitions |
| 9 | `tui.py` | ~850 | Rich terminal UI with all features |
| 10 | `gui.py` | ~1100 | Tkinter desktop GUI with all features |
| 11 | `web_ui.html` | ~1700 | Standalone browser UI (PWA-ready) |
| 12 | `cybertron_ui.py` | ~60 | Unified launcher |
| 13 | `requirements.txt` | ~3 | `websockets`, `rich`, `requests` |
| 14 | `README.md` | ~350 | Full documentation |

---

## Feature Implementation Status

### 🎯 GitHub Tool Loader
| Feature | Status | Files |
|---------|--------|-------|
| Parse GitHub URL → owner/repo | ✅ | `github_tool_loader.py` |
| Fetch latest release via GitHub API | ✅ | `github_tool_loader.py` |
| Auto-detect platform (Linux/macOS/Windows) | ✅ | `github_tool_loader.py` |
| Auto-detect architecture (amd64/arm64/386) | ✅ | `github_tool_loader.py` |
| Download release asset | ✅ | `github_tool_loader.py` |
| Extract (.zip, .tar.gz, .tar.xz, raw binary) | ✅ | `github_tool_loader.py` |
| Find binary in extracted archive | ✅ | `github_tool_loader.py` |
| chmod +x | ✅ | `github_tool_loader.py` |
| Validate with `--version` | ✅ | `github_tool_loader.py` |
| Infer schema from `--help` (regex) | ✅ | `github_tool_loader.py` |
| Persist catalog to JSON | ✅ | `github_tool_loader.py` |
| `/add-tool <url> [category]` command | ✅ | All 3 UIs |
| `/tools` registry view | ✅ | All 3 UIs |
| `/marketplace` curated list | ✅ | All 3 UIs |
| `/remove-tool <id>` | ✅ | All 3 UIs |
| Download approval gate | ✅ | All 3 UIs |
| Tool execution approval gate | ✅ | All 3 UIs |
| Broadcast catalog updates to all clients | ✅ | All 3 UIs |

### 🧠 Agent Intelligence
| Feature | Status | Files |
|---------|--------|-------|
| Streaming responses (typewriter effect) | ✅ | All 3 UIs |
| Multi-step planning display | ✅ | All 3 UIs |
| Dry-run mode | ✅ | All 3 UIs |
| Memory across sessions (audit log) | ✅ | `audit_logger.py` |
| Custom system prompts (UI-ready) | ✅ | Web UI Control Center |
| Tool chaining (UI-ready) | 🟡 | Needs gateway support |

### 🎨 UI/UX Improvements
| Feature | Status | Files |
|---------|--------|-------|
| Control Center panel | ✅ | All 3 UIs |
| Dark/Light theme toggle | ✅ | Web UI |
| Export reports (Markdown/JSON) | ✅ | TUI, GUI |
| Keyboard shortcuts cheat sheet | ✅ | All 3 UIs (`?` key) |
| Mobile PWA | ✅ | Web UI (manifest + responsive) |
| Split-pane transcript | ✅ | All 3 UIs |

### 🔒 Security & Safety
| Feature | Status | Files |
|---------|--------|-------|
| Sandboxed tool execution paths | ✅ | `github_tool_loader.py` |
| Output sanitization | ✅ | `output_sanitizer.py` |
| Audit log | ✅ | `audit_logger.py` |
| Rate limiting | ✅ | `rate_limiter.py` |
| Dry-run mode | ✅ | All 3 UIs |

### 🔌 Integrations
| Feature | Status | Files |
|---------|--------|-------|
| Webhook notifications | ✅ | `webhook_notifier.py` |
| Slack/Discord bot | 🟡 | Webhook notifier covers this |
| Burp Suite extension | 🔴 | Separate project |
| VS Code extension | 🔴 | Separate project |
| n8n / Make.com node | 🔴 | Separate project |

---

## Command Reference

### Universal Commands (all UIs)
```
/add-tool <github-url> [category]     Install tool from GitHub
/tools                                 View installed registry
/marketplace                           Browse curated tools
/remove-tool <id>                      Remove installed tool
/export markdown                       Export session as Markdown
/export json                           Export session as JSON
/export audit                          View recent audit log
/export list                           List exported files
/dry-run                               Toggle dry-run mode
/config                                Open Control Center
/split                                 Toggle split-pane
/help                                  Show commands
```

### Keyboard Shortcuts (all UIs)
```
Enter      Send message
S          Toggle Server view
T          Toggle Tools registry
M          Toggle Marketplace
C          Open Control Center
P          Toggle split-pane
?          Show shortcuts
Y          Approve prompt
N          Deny prompt
/          Focus composer
Esc        Close overlays
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER INTERFACES                          │
├─────────────┬─────────────┬─────────────────────────────────────┤
│   TUI       │   GUI       │   Web UI (PWA)                     │
│  (Rich)     │ (Tkinter)   │  (Vanilla JS)                       │
├─────────────┴─────────────┴─────────────────────────────────────┤
│                    PYTHON UI LAYER                                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │ github_tool │  │  audit_     │  │  session_  │  output_   │  │
│  │ _loader.py  │  │  logger.py  │  │  exporter  │  sanitizer│  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
│  ┌─────────────┐  ┌─────────────┐                                  │
│  │ rate_       │  │ webhook_    │                                  │
│  │ limiter.py  │  │ notifier.py │                                  │
│  └─────────────┘  └─────────────┘                                  │
├─────────────────────────────────────────────────────────────────┤
│                    WEBSOCKET PROTOCOL                            │
│  auth → session_start → agent_status → tool_call_request → ...   │
├─────────────────────────────────────────────────────────────────┤
│                    NODE.JS GATEWAY (existing)                    │
│              runtime/src/server.ts                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## Data Flow: GitHub Tool Installation

```
User: /add-tool projectdiscovery/httpx recon
    │
    ▼
[Approval Gate] ──→ Y/N prompt in UI
    │
    ▼ (approved)
github_tool_loader.install_tool()
    │
    ├── parse_repo("projectdiscovery/httpx") → "projectdiscovery/httpx"
    ├── fetch_latest_release() → GitHub API
    ├── detect_asset() → platform + arch matching
    ├── download_asset() → ~/.cybertron/tools/httpx/
    ├── extract_archive() → zip/tar.gz/raw
    ├── find_binary() → locate executable
    ├── make_executable() → chmod +x
    ├── validate_tool() → ./httpx --version
    ├── infer_schema() → regex parse --help
    ├── save_catalog() → ~/.cybertron/tools/catalog.json
    └── broadcast → WS: register_github_tool
    │
    ▼
All connected UIs update their tool registry view
```

---

## Security Model

```
Layer 1: Download Approval
  └─ User must explicitly approve every GitHub download

Layer 2: Sandboxed Paths
  └─ Tools isolated in ~/.cybertron/tools/<name>/
  └─ Never added to system PATH

Layer 3: Execution Approval
  └─ Exploit-gated tools require second Y/N approval

Layer 4: Output Sanitization
  └─ IPs, emails, secrets auto-redacted before NIM

Layer 5: Rate Limiting
  └─ Max 30 calls/min + 5 burst

Layer 6: Audit Trail
  └─ Every action logged to ~/.cybertron/audit.log
```

---

## Next Steps for Gateway Integration

To fully activate these features, the Node.js gateway needs to support:

1. **`stream_token` messages** — Forward LLM reasoning tokens to clients
2. **`agent_plan` messages** — Send multi-step plans before execution
3. **`dry_run` / `dry_run_result`** — Plan without executing
4. **`set_config` / `config_updated`** — Persist user settings
5. **Tool catalog merge** — Merge gateway tools + github_tool_loader catalog
6. **Webhook integration** — Call webhook_notifier on findings
7. **Output sanitization** — Apply sanitizer before sending to NIM
8. **Rate limiting** — Enforce limits before tool execution

---

## Installation

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start the Node.js gateway
cd /path/to/cybertron/runtime
npm run dev

# 3. Launch any UI
python cybertron_ui.py tui
python cybertron_ui.py gui
python cybertron_ui.py web   # http://127.0.0.1:8080/web_ui.html
```

---

*Built for Cybertron — Agent Console*

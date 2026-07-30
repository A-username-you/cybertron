# Cybertron — Unified Security Automation Platform

> **Version 3.1.0** | The perfect Cybertron. All versions combined into one.

Cybertron is an AI-powered red/blue team security agent and automated bug bounty platform.

## What's New in v3.1

- **Agent Console Web UI** — Full-featured dashboard with pixel-art animations, auth gate, chat transcript, control center, keyboard shortcuts
- **10 AI Providers** — OpenRouter, OpenAI, Anthropic, Google Gemini, Mistral, Groq, Cohere, Azure, Ollama, NVIDIA NIM
- **Bug Bounty Mode** — `/bb`, `/target`, `/recon`, `/brute`, `/report`, `/submit`, `/sync-h1`
- **Tool Marketplace** — Browse and install 16 security tools from GitHub
- **Animated State Icons** — Ringed planet (thinking), spiral (writing), star burst (result)
- **Split-pane transcript** — Raw output side panel
- **Streaming tokens** — Real-time AI response streaming
- **Approval gates** — Tool execution and download modals with Y/N shortcuts

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .

# Start backend
python -m cybertron gateway

# Launch UIs (in new terminals with venv activated)
python -m cybertron tui      # Terminal UI
python -m cybertron gui      # Desktop GUI
python -m cybertron web      # Standalone web UI
```

Open `http://localhost:8765/` for the **Agent Console**.

## Docker

```bash
docker-compose up --build
```

## AI Providers

| Provider | Env Variable | Default Model |
|----------|-------------|---------------|
| OpenRouter | `CYBERTRON_LLM_API_KEY` | `nousresearch/hermes-3-llama-3.1-405b` |
| OpenAI | `OPENAI_API_KEY` | `gpt-4o` |
| Anthropic | `ANTHROPIC_API_KEY` | `claude-3-5-sonnet-20241022` |
| Google Gemini | `GOOGLE_API_KEY` | `gemini-1.5-pro` |
| Mistral | `MISTRAL_API_KEY` | `mistral-large-latest` |
| Groq | `GROQ_API_KEY` | `llama-3.1-70b-versatile` |
| Cohere | `COHERE_API_KEY` | `command-r-plus` |
| Azure | `AZURE_OPENAI_KEY` | `gpt-4` |
| Ollama | `OLLAMA_API_KEY` | `llama3.1` |
| NVIDIA NIM | `NIM_API_KEY` | `nvidia/nemotron-4-340b-instruct` |

Set provider: `export CYBERTRON_LLM_PROVIDER=openai`

## Slash Commands

| Command | Description |
|---------|-------------|
| `/add-tool <url> [cat]` | Install tool from GitHub |
| `/tools` | View tool registry |
| `/marketplace` | Browse tool marketplace |
| `/remove-tool <id>` | Remove installed tool |
| `/export <fmt>` | Export session (markdown/json/audit) |
| `/dry-run` | Toggle dry-run mode |
| `/config` | Open control center |
| `/split` | Toggle split-pane |
| `/bb` | Toggle bug bounty mode |
| `/target <name>` | Set current target |
| `/recon` | Start reconnaissance |
| `/brute <type>` | Brute force (dirs/subdomains/params/vhosts/api/idor) |
| `/report` | Generate report |
| `/submit` | Submit to HackerOne |
| `/sync-h1 <handle>` | Sync HackerOne program |
| `/targets` | List known targets |
| `/help` | Show commands |

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Enter` | Send message |
| `S` | Toggle Server view |
| `T` | Toggle Tools registry |
| `M` | Toggle Marketplace |
| `P` | Toggle split-pane |
| `C` | Control Center |
| `Y` | Approve prompt |
| `N` | Deny prompt |
| `?` | Show shortcuts |
| `/` | Focus composer |
| `Esc` | Close overlays |

## Environment Variables

| Variable | Description |
|----------|-------------|
| `CYBERTRON_PORT` | Gateway port (default: 8765) |
| `CYBERTRON_HOST` | Gateway host (default: 127.0.0.1) |
| `CYBERTRON_AUTH_TOKEN` | Override auto-generated auth token |
| `CYBERTRON_LLM_PROVIDER` | AI provider (see table above) |
| `CYBERTRON_LLM_API_KEY` | API key for LLM provider |
| `CYBERTRON_LLM_MODEL` | Model name |
| `NIM_API_KEY` | NVIDIA NIM API key |
| `GITHUB_TOKEN` | GitHub PAT for Tool Loader |

## License

MIT

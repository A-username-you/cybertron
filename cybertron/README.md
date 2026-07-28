# Cybertron Bug Bounty Hunter

## Quick Start

```bash
cd docker
chmod +x setup.sh
./setup.sh
```

## Directory Structure

```
cybertron/
├── docker/              # Dockerfiles, compose, setup script
├── src/
│   ├── core/            # Tool loader, protocol, scope manager
│   ├── agents/          # Bug bounty agent, recon, brute force, reports
│   ├── security/        # Sanitizer, rate limiter, audit logger
│   └── integrations/    # HackerOne API, webhooks
├── ui/                  # TUI, GUI, Web UI, launcher
├── configs/             # Target configs, webhooks
├── wordlists/           # Downloaded wordlists
├── reports/             # Generated reports
└── docs/                # Documentation
```

## Access After Setup

- Web UI: http://localhost:8080/web_ui.html
- Gateway: ws://localhost:8765

## First Commands

```
/target example-program
/sync-h1 program-handle
/recon
/brute dirs
/report
```

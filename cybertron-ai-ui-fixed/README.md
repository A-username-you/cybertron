# Cybertron AI v2.1.0

> AI-Powered Security Automation & Reverse Engineering Framework

## Quick Start

```bash
# 1. Extract
cd cybertron-ai-ui-fixed

# 2. Configure LLM
cp .env.example .env
# Edit .env with your OpenRouter key

# 3. Docker (recommended)
docker-compose up --build

# 4. Or local
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -e .
cd ..
uvicorn backend.main:app --reload --port 8000

# 5. Open http://localhost:8000
```

## What's Included

- **AI Chat** — Natural language security tasks via LLM
- **Pixel Art Icons** — Ringed planet, spiral, star burst (28px canvas)
- **Hermes Dark Theme** — Gold/amber/cyan console aesthetic with animated starfield
- **Live Dashboard** — WebSocket real-time findings, severity bars, activity feed
- **Multi-Provider LLM** — OpenRouter, OpenAI, Anthropic, Ollama
- **Self-Contained** — Original Cybertron v2 core embedded, no external repo needed

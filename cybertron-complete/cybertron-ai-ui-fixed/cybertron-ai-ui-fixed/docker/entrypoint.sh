#!/bin/bash
set -e
cd /app
pip install -e ./backend >/dev/null 2>&1
echo "🚀 Starting Cybertron AI on port 8000..."
exec uvicorn backend.main:app --host 0.0.0.0 --port 8000

"""Cybertron AI — Main FastAPI app."""
import json
from pathlib import Path
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import structlog
from cybertron_ai.core.state import AppState
from cybertron_ai.routers import scan, chat, plugins, engagements, findings, health
from cybertron_ai.services.websocket_manager import ConnectionManager

logger = structlog.get_logger()

# Resolve paths relative to this file (in /app/backend/)
BASE_DIR = Path(__file__).parent.parent.resolve()  # /app
FRONTEND_DIR = BASE_DIR / "frontend"
TEMPLATES_DIR = FRONTEND_DIR / "templates"
STATIC_DIR = FRONTEND_DIR / "static"

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    logger.info("cybertron_ai_startup", version="2.1.0")
    app.state.cybertron = AppState()
    await app.state.cybertron.initialize()
    yield
    await app.state.cybertron.shutdown()
    logger.info("cybertron_ai_shutdown")

app = FastAPI(
    title="Cybertron AI",
    version="2.1.0",
    description="AI-Powered Security Automation",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(scan.router, prefix="/api/scan", tags=["scan"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(plugins.router, prefix="/api/plugins", tags=["plugins"])
app.include_router(engagements.router, prefix="/api/engagements", tags=["engagements"])
app.include_router(findings.router, prefix="/api/findings", tags=["findings"])

manager = ConnectionManager()

@app.websocket("/ws/live")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "subscribe":
                await manager.subscribe(websocket, msg.get("channel", "global"))
            elif msg.get("type") == "ping":
                await websocket.send_json({"type": "pong", "ts": msg.get("ts")})
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.get("/", response_class=HTMLResponse)
async def root():
    index_path = TEMPLATES_DIR / "index.html"
    return HTMLResponse(content=index_path.read_text(encoding="utf-8"))

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

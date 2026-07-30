"""Cybertron Gateway — FastAPI API Server."""
import os
import asyncio
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from cybertron.core.config import CybertronConfig
from cybertron.core.engine import CybertronEngine
from cybertron.security.auth import AuthManager
from cybertron.security.rate_limiter import RateLimiter
from cybertron.security.audit import AuditLogger
from cybertron.agents.ai_orchestrator import AIOrchestrator


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.engine = CybertronEngine()
    app.state.auth = AuthManager()
    app.state.rate_limiter = RateLimiter(rps=10)
    app.state.audit = AuditLogger()
    app.state.ai = AIOrchestrator()
    yield
    print("[Gateway] Shutting down...")


app = FastAPI(
    title="Cybertron API",
    description="Unified Red/Blue Team Security Platform",
    version="3.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files for web UI
static_dir = os.path.join(os.path.dirname(__file__), "ui", "web_static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


async def verify_api_key(request: Request):
    key = request.headers.get("X-API-Key", "")
    if not request.app.state.auth.verify_api_key(key):
        raise HTTPException(status_code=401, detail="Invalid API key")
    return key


@app.get("/", response_class=HTMLResponse)
async def root():
    return """
    <!DOCTYPE html>
    <html>
    <head><title>Cybertron API</title></head>
    <body>
        <h1>Cybertron v3.0 API</h1>
        <p>Status: <span style="color:green">Online</span></p>
        <p>Docs: <a href="/docs">/docs</a></p>
        <p>Web UI: <a href="/ui">/ui</a></p>
    </body>
    </html>
    """


@app.get("/health")
async def health():
    return {"status": "ok", "version": "3.0.0"}


@app.get("/api/v1/config")
async def get_config(key: str = Depends(verify_api_key)):
    cfg = CybertronConfig.load()
    return cfg.model_dump(exclude={"jwt_secret", "passkey_secret", "api_key", "nim_api_key"})


@app.post("/api/v1/scan")
async def scan(target: str, key: str = Depends(verify_api_key)):
    from cybertron.red_team.scanner import VulnScanner
    scanner = VulnScanner(target=target)
    findings = scanner.run()
    return {"target": target, "findings_count": len(findings), "findings": findings}


@app.post("/api/v1/recon")
async def recon(target: str, key: str = Depends(verify_api_key)):
    from cybertron.red_team.recon import ReconEngine
    engine = ReconEngine(target=target)
    result = engine.run()
    return {"target": target, "subdomains": result.subdomains, "ports": result.open_ports}


@app.post("/api/v1/reverse")
async def reverse_engineer(target: str, key: str = Depends(verify_api_key)):
    from cybertron.reverse_engineering.analyzer import ReverseEngineer
    re = ReverseEngineer(target=target)
    result = re.run()
    return {"target": target, "file_type": result.file_type, "entropy": result.entropy}


@app.post("/api/v1/ai/chat")
async def ai_chat(prompt: str, key: str = Depends(verify_api_key)):
    response = await app.state.ai.chat(prompt)
    return {"response": response}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            msg = await app.state.ai.chat(data)
            await websocket.send_text(msg)
    except WebSocketDisconnect:
        pass


def start_gateway(host: str = "0.0.0.0", port: int = 8443):
    import uvicorn
    uvicorn.run(app, host=host, port=port)

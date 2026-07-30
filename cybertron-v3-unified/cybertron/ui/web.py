"""Cybertron Web UI — FastAPI-based with passkey auth."""
import os
from fastapi import FastAPI, Request, Form, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from cybertron.core.config import CybertronConfig
from cybertron.security.auth import AuthManager

# Create app for web UI
web_app = FastAPI(title="Cybertron Web UI")
web_app.add_middleware(SessionMiddleware, secret_key="cybertron-session-secret-change-me")

# Static files
static_dir = os.path.join(os.path.dirname(__file__), "web_static")
if os.path.exists(static_dir):
    web_app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Templates
template_dir = os.path.join(os.path.dirname(__file__), "web_static")
templates = Jinja2Templates(directory=template_dir)


def get_auth():
    return AuthManager()


@web_app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    cfg = CybertronConfig.load()
    if cfg.passkey_enabled and not request.session.get("authenticated"):
        return templates.TemplateResponse("login.html", {"request": request})
    return templates.TemplateResponse("index.html", {"request": request})


@web_app.post("/login")
async def login(request: Request, passkey: str = Form(...)):
    auth = get_auth()
    if auth.verify_passkey(passkey):
        request.session["authenticated"] = True
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid passkey"})


@web_app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)


@web_app.get("/api/status")
async def api_status(request: Request):
    return {"status": "ok", "version": "3.0.0", "authenticated": request.session.get("authenticated", False)}


@web_app.post("/api/recon")
async def api_recon(request: Request, target: str = Form(...)):
    from cybertron.red_team.recon import ReconEngine
    engine = ReconEngine(target=target)
    result = engine.run()
    return {"target": target, "subdomains": result.subdomains, "ports": result.open_ports}


@web_app.post("/api/scan")
async def api_scan(request: Request, target: str = Form(...)):
    from cybertron.red_team.scanner import VulnScanner
    scanner = VulnScanner(target=target)
    findings = scanner.run()
    return {"target": target, "findings_count": len(findings)}


@web_app.post("/api/brute")
async def api_brute(request: Request, target: str = Form(...), mode: str = Form("dirs")):
    from cybertron.red_team.brute_force import BruteForceEngine
    engine = BruteForceEngine(target=target, mode=mode)
    results = engine.run()
    return {"target": target, "mode": mode, "hits": results}


@web_app.post("/api/reverse")
async def api_reverse(request: Request, target: str = Form(...)):
    from cybertron.reverse_engineering.analyzer import ReverseEngineer
    re = ReverseEngineer(target=target)
    result = re.run()
    return {"target": target, "file_type": result.file_type, "entropy": result.entropy,
            "md5": result.md5, "sha256": result.sha256}


@web_app.post("/api/hunt")
async def api_hunt(request: Request, ioc: str = Form(...), source: str = Form("/var/log")):
    from cybertron.blue_team.threat_hunt import ThreatHunter
    hunter = ThreatHunter(ioc=ioc, source=source)
    results = hunter.run()
    return {"ioc": ioc, "matches": len(results)}


@web_app.post("/api/forensics")
async def api_forensics(request: Request, source: str = Form(...)):
    from cybertron.blue_team.forensics import ForensicsEngine
    engine = ForensicsEngine(source=source)
    artifacts = engine.run()
    return {"source": source, "artifacts": len(artifacts)}


@web_app.post("/api/ai/chat")
async def api_ai_chat(request: Request, prompt: str = Form(...)):
    from cybertron.agents.ai_orchestrator import AIOrchestrator
    ai = AIOrchestrator()
    response = await ai.chat(prompt)
    return {"response": response}


@web_app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    from cybertron.agents.ai_orchestrator import AIOrchestrator
    ai = AIOrchestrator()
    try:
        while True:
            data = await websocket.receive_text()
            async for chunk in ai.stream(data):
                await websocket.send_text(chunk)
            await websocket.send_text("[DONE]")
    except WebSocketDisconnect:
        pass


def start_web_server(host: str = "0.0.0.0", port: int = 8080, passkey_enabled: bool = True):
    import uvicorn
    cfg = CybertronConfig.load()
    cfg.passkey_enabled = passkey_enabled
    cfg.save()
    uvicorn.run(web_app, host=host, port=port)

"""Health API."""
from fastapi import APIRouter, Request
import time
router = APIRouter()
start_time = time.time()
@router.get("/health")
async def health(request: Request):
    state = request.app.state.cybertron
    return {"status":"healthy","version":"2.1.0","uptime_seconds":int(time.time()-start_time),"plugins_loaded":len(state.engine.registry.list_plugins()) if state.engine else 0,"ai_enabled":state.llm.api_key!="" if state.llm else False}
@router.get("/stats")
async def stats(request: Request):
    state = request.app.state.cybertron
    findings = state.engine.get_findings() if state.engine else []
    return {"total_scans":len(state.engine._task_history) if state.engine else 0,"total_findings":len(findings),"active_engagements":len(state.orchestrator.engagements) if state.orchestrator else 0,"plugins_available":len(state.engine.registry.list_plugins()) if state.engine else 0}

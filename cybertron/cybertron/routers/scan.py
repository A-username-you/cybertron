"""Scan router."""
from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()

class ScanRequest(BaseModel):
    target: str
    plugins: list = []
    options: dict = {}

@router.post("/")
async def scan(req: ScanRequest, request: Request):
    state = request.app.state.cybertron
    intent = await state.ai_orchestrator.parse_intent(f"scan {req.target}", {"session_id": "scan-api"})
    if req.plugins:
        intent.plugins = req.plugins
    results = await state.ai_orchestrator.execute_intent(intent)
    return {"intent": intent.__dict__, "results": results}

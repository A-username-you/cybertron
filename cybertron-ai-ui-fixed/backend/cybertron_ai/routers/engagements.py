"""Engagements API."""
from typing import Optional
from fastapi import APIRouter, Request
from pydantic import BaseModel
router = APIRouter()
class EngagementRequest(BaseModel):
    name: str; target: str; scope_file: str; type: str = "bug_bounty"
@router.post("/")
async def create_engagement(req: EngagementRequest, request: Request):
    state = request.app.state.cybertron
    eng = await state.orchestrator.start_engagement(req.name, req.target, req.scope_file)
    return {"id":eng.id,"name":eng.name,"target":eng.target,"status":eng.status,"start_time":eng.start_time.isoformat()}
@router.get("/")
async def list_engagements(request: Request):
    state = request.app.state.cybertron
    return {"engagements":[{"id":e.id,"name":e.name,"target":e.target,"status":e.status,"findings_count":len(e.findings)} for e in state.orchestrator.engagements.values()]}
@router.get("/{eng_id}")
async def get_engagement(eng_id: str, request: Request, min_severity: Optional[str]="low"):
    from cybertron.core import Severity
    state = request.app.state.cybertron
    sev_map = {"info":Severity.INFO,"low":Severity.LOW,"medium":Severity.MEDIUM,"high":Severity.HIGH,"critical":Severity.CRITICAL}
    findings = state.orchestrator.get_findings(eng_id, sev_map.get(min_severity,Severity.LOW))
    return {"engagement_id":eng_id,"findings":[f.model_dump() for f in findings],"count":len(findings)}

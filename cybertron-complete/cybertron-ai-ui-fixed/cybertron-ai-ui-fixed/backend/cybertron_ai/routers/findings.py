"""Findings API."""
from typing import Optional
from fastapi import APIRouter, Request
router = APIRouter()
@router.get("/")
async def get_findings(request: Request, severity: Optional[str]=None, category: Optional[str]=None, limit: int=100):
    state = request.app.state.cybertron
    findings = state.engine.get_findings()
    if severity: findings = [f for f in findings if f.severity.value==severity]
    if category: findings = [f for f in findings if f.category==category]
    findings = findings[:limit]
    dist = {"critical":0,"high":0,"medium":0,"low":0,"info":0}
    for f in findings: dist[f.severity.value] = dist.get(f.severity.value,0)+1
    return {"findings":[f.model_dump() for f in findings],"total":len(findings),"distribution":dist,"categories":list(set(f.category for f in findings))}
@router.get("/export/{format}")
async def export_findings(format: str, request: Request):
    findings = request.app.state.cybertron.engine.get_findings()
    if format=="json": return {"findings":[f.model_dump() for f in findings]}
    elif format=="summary": return {"total":len(findings),"by_severity":{sev:len([f for f in findings if f.severity.value==sev]) for sev in ["critical","high","medium","low","info"]}}
    return {"error":"Unsupported format"}

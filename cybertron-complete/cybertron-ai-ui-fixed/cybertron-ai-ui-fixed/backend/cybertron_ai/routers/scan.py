"""Scan API."""
from typing import Dict, Any, List
from fastapi import APIRouter, Request
from pydantic import BaseModel
router = APIRouter()
class ScanRequest(BaseModel):
    target: str; plugin: str = "subdomain_enum"; options: Dict[str,Any] = {}; scope_file: str = None
class PipelineRequest(BaseModel):
    target: str; steps: List[Dict[str,Any]]; scope_file: str = None
@router.post("/single")
async def scan_single(req: ScanRequest, request: Request):
    state = request.app.state.cybertron
    if req.scope_file: state.engine.scope.load_scope(req.scope_file)
    result = await state.engine.execute_task(req.plugin, req.target, req.options)
    return {"task_id":result.task_id,"status":result.status.name,"findings":[f.model_dump() for f in result.findings],"artifacts":result.artifacts,"execution_time_ms":result.execution_time_ms,"error":result.error}
@router.post("/pipeline")
async def scan_pipeline(req: PipelineRequest, request: Request):
    state = request.app.state.cybertron
    if req.scope_file: state.engine.scope.load_scope(req.scope_file)
    results = await state.engine.execute_pipeline(req.steps, req.target)
    return {"results":[{"task_id":r.task_id,"status":r.status.name,"findings":[f.model_dump() for f in r.findings],"execution_time_ms":r.execution_time_ms} for r in results],"total_findings":sum(len(r.findings) for r in results),"total_time_ms":sum(r.execution_time_ms for r in results)}

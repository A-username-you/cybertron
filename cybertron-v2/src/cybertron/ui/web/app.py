"""Cybertron Web Dashboard"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List
from cybertron.core import ExecutionEngine, Severity
from cybertron.agents import CybertronOrchestrator

app = FastAPI(title="Cybertron", version="2.0.0")
engine = ExecutionEngine()
orchestrator = CybertronOrchestrator(engine)


class ScanRequest(BaseModel):
    target: str
    plugin: str = "subdomain_enum"
    options: Dict[str, Any] = {}


@app.get("/")
async def root():
    return {"message": "Cybertron v2.0 API", "status": "operational"}


@app.get("/plugins")
async def list_plugins():
    return {"plugins": engine.registry.list_plugins()}


@app.post("/scan")
async def run_scan(request: ScanRequest):
    result = await engine.execute_task(request.plugin, request.target, request.options)
    return {
        "task_id": result.task_id,
        "status": result.status.name,
        "findings": [f.model_dump() for f in result.findings],
        "execution_time_ms": result.execution_time_ms
    }


@app.get("/health")
async def health():
    return {"status": "healthy", "plugins_loaded": len(engine.registry.list_plugins())}

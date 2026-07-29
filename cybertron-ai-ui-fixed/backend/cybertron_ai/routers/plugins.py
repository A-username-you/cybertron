"""Plugins API."""
from fastapi import APIRouter, Request
router = APIRouter()
@router.get("/")
async def list_plugins(request: Request):
    return {"plugins": request.app.state.cybertron.engine.registry.list_plugins()}
@router.get("/{plugin_name}/health")
async def plugin_health(plugin_name: str, request: Request):
    try:
        instance = await request.app.state.cybertron.engine.registry.get_instance(plugin_name, {})
        return {"plugin":plugin_name,"health":instance.health_check()}
    except Exception as e:
        return {"plugin":plugin_name,"health":{"status":"error","error":str(e)}}

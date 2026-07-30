"""Engagements router."""
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

class Engagement(BaseModel):
    name: str
    target: str

@router.post("/")
async def create_engagement(req: Engagement):
    return {"id": f"eng-{req.name[:8]}", "name": req.name, "target": req.target, "status": "active"}

@router.get("/")
async def list_engagements():
    return {"engagements": []}

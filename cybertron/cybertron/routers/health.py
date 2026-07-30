"""Health router."""
from fastapi import APIRouter

router = APIRouter()

@router.get("/")
async def health():
    return {"status": "ok", "version": "3.0.0", "service": "cybertron"}

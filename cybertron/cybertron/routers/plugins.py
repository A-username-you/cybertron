"""Plugins router."""
from fastapi import APIRouter

router = APIRouter()

@router.get("/")
async def list_plugins():
    return {"plugins": ["subdomain_enum", "port_scan", "aws_misconfig", "docker_audit", "openapi_fuzz", "apk_static", "pcap_parser"]}

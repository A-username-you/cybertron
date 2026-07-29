"""Utility Functions"""
import asyncio
import hashlib
import random
import string
from typing import Any, Dict, List, Optional
from pathlib import Path


def generate_id(length: int = 12) -> str:
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))


def truncate_string(s: str, max_length: int = 200) -> str:
    if len(s) <= max_length:
        return s
    return s[:max_length] + "..."


def merge_dicts(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_dicts(result[key], value)
        else:
            result[key] = value
    return result


async def run_command(cmd: List[str], timeout: int = 60, cwd: Optional[Path] = None) -> Dict[str, Any]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return {
            "returncode": proc.returncode,
            "stdout": stdout.decode("utf-8", errors="ignore"),
            "stderr": stderr.decode("utf-8", errors="ignore")
        }
    except asyncio.TimeoutError:
        proc.kill()
        return {"returncode": -1, "stdout": "", "stderr": "Timeout"}


def compute_file_hash(path: Path, algorithm: str = "sha256") -> str:
    h = hashlib.new(algorithm)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

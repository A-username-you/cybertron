#!/usr/bin/env python3
"""Cybertron GitHub Tool Loader — download, validate, register security tools from GitHub."""
import json
import os
import platform
import re
import shutil
import subprocess
import tarfile
import time
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests

TOOLS_DIR = Path.home() / ".cybertron" / "tools"
TOOLS_DIR.mkdir(parents=True, exist_ok=True)
GITHUB_API = "https://api.github.com"

SYSTEM = platform.system().lower()
MACHINE = platform.machine().lower()
ARCH_MAP = {
    "x86_64": "amd64", "amd64": "amd64",
    "aarch64": "arm64", "arm64": "arm64",
    "i386": "386", "i686": "386",
}
CURRENT_ARCH = ARCH_MAP.get(MACHINE, MACHINE)

def parse_github_url(url: str) -> Tuple[str, str]:
    patterns = [
        r"github\.com/([^/]+)/([^/]+)/?",
        r"github\.com/([^/]+)/([^/]+)\.git",
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            return m.group(1), m.group(2).replace(".git", "")
    raise ValueError(f"Cannot parse GitHub URL: {url}")

def fetch_latest_release(owner: str, repo: str, token: Optional[str] = None) -> dict:
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    url = f"{GITHUB_API}/repos/{owner}/{repo}/releases/latest"
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()

def find_matching_asset(release: dict) -> Optional[dict]:
    assets = release.get("assets", [])
    if not assets:
        return None
    best = None
    best_score = -1
    for asset in assets:
        name = asset.get("name", "").lower()
        score = 0
        if SYSTEM in name or (SYSTEM == "darwin" and "mac" in name) or (SYSTEM == "darwin" and "osx" in name):
            score += 10
        if "linux" in name and SYSTEM == "linux":
            score += 10
        if "windows" in name and SYSTEM == "windows":
            score += 10
        if CURRENT_ARCH in name:
            score += 5
        if MACHINE in name:
            score += 3
        if any(name.endswith(ext) for ext in [".zip", ".tar.gz", ".tgz", ".gz"]):
            score += 2
        if "source" in name:
            score -= 10
        if score > best_score:
            best_score = score
            best = asset
    return best

def download_asset(url: str, dest: Path, headers: Optional[dict] = None) -> Path:
    resp = requests.get(url, headers=headers, stream=True, timeout=120)
    resp.raise_for_status()
    total = int(resp.headers.get("content-length", 0))
    downloaded = 0
    with open(dest, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    print(f"\r downloading... {downloaded/total*100:.1f}%", end="", flush=True)
    print()
    return dest

def extract_archive(archive_path: Path, dest_dir: Path) -> List[Path]:
    extracted = []
    if archive_path.suffix == ".zip" or str(archive_path).endswith(".zip"):
        with zipfile.ZipFile(archive_path, "r") as z:
            z.extractall(dest_dir)
            extracted = [dest_dir / name for name in z.namelist()]
    elif archive_path.suffix in (".gz", ".tgz") or str(archive_path).endswith(".tar.gz"):
        with tarfile.open(archive_path, "r:gz") as t:
            t.extractall(dest_dir)
            extracted = [dest_dir / name for name in t.getnames()]
    else:
        bin_path = dest_dir / archive_path.name
        shutil.move(str(archive_path), str(bin_path))
        extracted = [bin_path]
    return extracted

def find_binary(extracted_files: List[Path], tool_name: str) -> Optional[Path]:
    candidates = []
    for f in extracted_files:
        if f.is_dir():
            continue
        name = f.name.lower()
        if tool_name.lower() in name or name == tool_name.lower():
            candidates.append(f)
        elif os.access(f, os.X_OK) and not name.endswith((".txt", ".md", ".json", ".yaml", ".yml", ".sh", ".bat")):
            candidates.append(f)
    if not candidates:
        return None
    candidates.sort(key=lambda p: abs(len(p.name) - len(tool_name)))
    return candidates[0]

def validate_binary(binary_path: Path) -> Tuple[bool, str]:
    try:
        result = subprocess.run([str(binary_path), "--version"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            return True, result.stdout.strip() or result.stderr.strip()
        if result.stderr:
            return True, result.stderr.strip()
        return False, f"exit code {result.returncode}"
    except Exception as e:
        return False, str(e)

def infer_schema(binary_path: Path) -> dict:
    try:
        result = subprocess.run([str(binary_path), "--help"], capture_output=True, text=True, timeout=10)
        help_text = result.stdout + result.stderr
    except Exception:
        help_text = ""
    schema = {"flags": [], "args": [], "description": "", "examples": []}
    flag_pattern = r"\s+(-[a-zA-Z],?\s*)?(--[a-zA-Z0-9_-]+)\s+(.+)?"
    for match in re.finditer(flag_pattern, help_text):
        short = match.group(1).strip(", ") if match.group(1) else None
        long = match.group(2)
        desc = match.group(3) or ""
        schema["flags"].append({"short": short, "long": long, "description": desc.strip()})
    lines = help_text.split("\n")
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("$") or binary_path.name in stripped[:50]:
            schema["examples"].append(stripped)
    for line in lines:
        if line.strip() and not line.strip().startswith(("-", "Usage", "Options", "Flags")):
            schema["description"] = line.strip()[:200]
            break
    return schema

def register_tool(
    repo_url: str, tool_name: Optional[str] = None,
    category: str = "recon", auto_approve: bool = False,
    github_token: Optional[str] = None,
) -> dict:
    owner, repo = parse_github_url(repo_url)
    name = tool_name or repo
    tool_dir = TOOLS_DIR / name
    tool_dir.mkdir(parents=True, exist_ok=True)
    result = {"ok": False, "name": name, "repo": f"{owner}/{repo}", "version": None, "binary_path": None, "schema": None, "error": None}
    try:
        release = fetch_latest_release(owner, repo, github_token)
        result["version"] = release.get("tag_name", "unknown")
        asset = find_matching_asset(release)
        if not asset:
            result["error"] = "No release assets found. Tool may require manual build."
            return result
        asset_name = asset["name"]
        asset_url = asset["browser_download_url"]
        archive_path = tool_dir / asset_name
        headers = {}
        if github_token:
            headers["Authorization"] = f"Bearer {github_token}"
        download_asset(asset_url, archive_path, headers)
        extracted = extract_archive(archive_path, tool_dir)
        binary = find_binary(extracted, name)
        if not binary:
            result["error"] = f"Could not find binary in extracted files: {[f.name for f in extracted]}"
            return result
        os.chmod(binary, 0o755)
        ok, version = validate_binary(binary)
        if not ok:
            result["error"] = f"Validation failed: {version}"
            return result
        result["version"] = version or result["version"]
        result["binary_path"] = str(binary)
        schema = infer_schema(binary)
        result["schema"] = schema
        meta = {
            "name": name, "repo": f"{owner}/{repo}", "version": result["version"],
            "binary_path": str(binary), "category": category, "auto_approve": auto_approve,
            "installed_at": int(time.time()), "schema": schema,
        }
        with open(tool_dir / "cybertron.json", "w") as f:
            json.dump(meta, f, indent=2)
        result["ok"] = True
    except Exception as e:
        result["error"] = str(e)
    return result

def list_installed_tools() -> List[dict]:
    tools = []
    if not TOOLS_DIR.exists():
        return tools
    for tool_dir in TOOLS_DIR.iterdir():
        meta_path = tool_dir / "cybertron.json"
        if meta_path.exists():
            with open(meta_path) as f:
                tools.append(json.load(f))
    return tools

def remove_tool(name: str) -> bool:
    tool_dir = TOOLS_DIR / name
    if tool_dir.exists():
        shutil.rmtree(tool_dir)
        return True
    return False

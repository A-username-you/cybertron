#!/usr/bin/env python3
"""
Cybertron GitHub Tool Loader
Dynamically downloads, validates, and registers security tools from GitHub.
"""
import json
import os
import platform
import re
import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests

# ─── Config ──────────────────────────────────────────────────────────────────
TOOLS_DIR = Path.home() / ".cybertron" / "tools"
TOOLS_DIR.mkdir(parents=True, exist_ok=True)
GITHUB_API = "https://api.github.com"

# Platform detection
SYSTEM = platform.system().lower()  # linux, darwin, windows
MACHINE = platform.machine().lower()
ARCH_MAP = {
    "x86_64": "amd64", "amd64": "amd64",
    "aarch64": "arm64", "arm64": "arm64",
    "i386": "386", "i686": "386",
}
CURRENT_ARCH = ARCH_MAP.get(MACHINE, MACHINE)

# ─── URL Parser ──────────────────────────────────────────────────────────────
def parse_github_url(url: str) -> Tuple[str, str]:
    """Extract owner/repo from various GitHub URL formats."""
    patterns = [
        r"github\.com/([^/]+)/([^/]+)/?",
        r"github\.com/([^/]+)/([^/]+)\.git",
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            return m.group(1), m.group(2).replace(".git", "")
    raise ValueError(f"Cannot parse GitHub URL: {url}")

# ─── Release Fetcher ─────────────────────────────────────────────────────────
def fetch_latest_release(owner: str, repo: str, token: Optional[str] = None) -> dict:
    """Fetch latest release from GitHub API."""
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    url = f"{GITHUB_API}/repos/{owner}/{repo}/releases/latest"
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()

def find_matching_asset(release: dict) -> Optional[dict]:
    """Find the best asset for current platform from release assets."""
    assets = release.get("assets", [])
    if not assets:
        # Some releases have no assets (source-only), check tag_name for go install
        return None

    # Score each asset by platform match
    best = None
    best_score = -1

    for asset in assets:
        name = asset.get("name", "").lower()
        score = 0

        # Check OS
        if SYSTEM in name or (SYSTEM == "darwin" and "mac" in name) or (SYSTEM == "darwin" and "osx" in name):
            score += 10
        if "linux" in name and SYSTEM == "linux":
            score += 10
        if "windows" in name and SYSTEM == "windows":
            score += 10

        # Check arch
        if CURRENT_ARCH in name:
            score += 5
        if MACHINE in name:
            score += 3

        # Prefer binaries over source
        if any(name.endswith(ext) for ext in [".zip", ".tar.gz", ".tgz", ".gz"]):
            score += 2

        # Penalize source code
        if "source" in name:
            score -= 10

        if score > best_score:
            best_score = score
            best = asset

    return best

# ─── Download & Extract ──────────────────────────────────────────────────────
def download_asset(url: str, dest: Path, headers: Optional[dict] = None) -> Path:
    """Download with progress."""
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
                    pct = downloaded / total * 100
                    print(f"\r  downloading... {pct:.1f}%", end="", flush=True)
    print()  # newline
    return dest

def extract_archive(archive_path: Path, dest_dir: Path) -> List[Path]:
    """Extract zip or tar.gz to dest_dir. Returns list of extracted file paths."""
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
        # Single binary, just move it
        bin_path = dest_dir / archive_path.name
        shutil.move(str(archive_path), str(bin_path))
        extracted = [bin_path]

    return extracted

def find_binary(extracted_files: List[Path], tool_name: str) -> Optional[Path]:
    """Find the actual binary among extracted files."""
    candidates = []
    for f in extracted_files:
        if f.is_dir():
            continue
        name = f.name.lower()
        # Prefer exact match
        if tool_name.lower() in name or name == tool_name.lower():
            candidates.append(f)
        # Also check if executable
        elif os.access(f, os.X_OK) and not name.endswith((".txt", ".md", ".json", ".yaml", ".yml", ".sh", ".bat")):
            candidates.append(f)

    if not candidates:
        return None

    # Prefer the one closest to the tool name
    candidates.sort(key=lambda p: abs(len(p.name) - len(tool_name)))
    return candidates[0]

# ─── Validation ──────────────────────────────────────────────────────────────
def validate_binary(binary_path: Path) -> Tuple[bool, str]:
    """Run --version and check exit code. Returns (ok, version_string)."""
    try:
        result = subprocess.run(
            [str(binary_path), "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return True, result.stdout.strip() or result.stderr.strip()
        # Some tools print version to stderr
        if result.stderr:
            return True, result.stderr.strip()
        return False, f"exit code {result.returncode}"
    except Exception as e:
        return False, str(e)

# ─── Schema Inference ───────────────────────────────────────────────────────
def infer_schema(binary_path: Path) -> dict:
    """Parse --help output to infer tool schema."""
    try:
        result = subprocess.run(
            [str(binary_path), "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        help_text = result.stdout + result.stderr
    except Exception:
        help_text = ""

    schema = {
        "flags": [],
        "args": [],
        "description": "",
        "examples": [],
    }

    # Extract flags (-f, --flag)
    flag_pattern = r"\s+(-[a-zA-Z],?\s*)?(--[a-zA-Z0-9_-]+)\s+(.+)?"
    for match in re.finditer(flag_pattern, help_text):
        short = match.group(1).strip(", ") if match.group(1) else None
        long = match.group(2)
        desc = match.group(3) or ""
        schema["flags"].append({"short": short, "long": long, "description": desc.strip()})

    # Extract examples (lines with $ or tool name)
    lines = help_text.split("\n")
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("$") or binary_path.name in stripped[:50]:
            schema["examples"].append(stripped)

    # First non-empty line as description
    for line in lines:
        if line.strip() and not line.strip().startswith(("-", "Usage", "Options", "Flags")):
            schema["description"] = line.strip()[:200]
            break

    return schema

# ─── Registration ────────────────────────────────────────────────────────────
def register_tool(
    repo_url: str,
    tool_name: Optional[str] = None,
    category: str = "recon",
    auto_approve: bool = False,
    github_token: Optional[str] = None,
) -> dict:
    """
    Full pipeline: download → extract → validate → register.
    Returns registration result dict.
    """
    owner, repo = parse_github_url(repo_url)
    name = tool_name or repo
    tool_dir = TOOLS_DIR / name
    tool_dir.mkdir(parents=True, exist_ok=True)

    result = {
        "ok": False,
        "name": name,
        "repo": f"{owner}/{repo}",
        "version": None,
        "binary_path": None,
        "schema": None,
        "error": None,
    }

    try:
        # 1. Fetch release
        print(f"[GitHub Loader] Fetching latest release for {owner}/{repo}...")
        release = fetch_latest_release(owner, repo, github_token)
        result["version"] = release.get("tag_name", "unknown")

        # 2. Find asset
        asset = find_matching_asset(release)
        if not asset:
            # Try go install fallback
            result["error"] = "No release assets found. Tool may require 'go install' or manual build."
            return result

        asset_name = asset["name"]
        asset_url = asset["browser_download_url"]
        print(f"[GitHub Loader] Selected asset: {asset_name}")

        # 3. Download
        archive_path = tool_dir / asset_name
        headers = {}
        if github_token:
            headers["Authorization"] = f"Bearer {github_token}"

        print(f"[GitHub Loader] Downloading {asset_name}...")
        download_asset(asset_url, archive_path, headers)

        # 4. Extract
        print(f"[GitHub Loader] Extracting...")
        extracted = extract_archive(archive_path, tool_dir)

        # 5. Find binary
        binary = find_binary(extracted, name)
        if not binary:
            result["error"] = f"Could not find binary in extracted files: {[f.name for f in extracted]}"
            return result

        # 6. Make executable
        os.chmod(binary, 0o755)

        # 7. Validate
        print(f"[GitHub Loader] Validating {binary.name}...")
        ok, version = validate_binary(binary)
        if not ok:
            result["error"] = f"Validation failed: {version}"
            return result

        result["version"] = version or result["version"]
        result["binary_path"] = str(binary)

        # 8. Infer schema
        print(f"[GitHub Loader] Inferring schema from --help...")
        schema = infer_schema(binary)
        result["schema"] = schema

        # 9. Save metadata
        meta = {
            "name": name,
            "repo": f"{owner}/{repo}",
            "version": result["version"],
            "binary_path": str(binary),
            "category": category,
            "auto_approve": auto_approve,
            "installed_at": int(time.time()),
            "schema": schema,
        }
        meta_path = tool_dir / "cybertron.json"
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2)

        result["ok"] = True
        print(f"[GitHub Loader] ✓ {name} installed successfully!")

    except Exception as e:
        result["error"] = str(e)
        print(f"[GitHub Loader] ✗ Failed: {e}")

    return result

def list_installed_tools() -> List[dict]:
    """List all tools installed by the GitHub loader."""
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
    """Remove an installed tool."""
    tool_dir = TOOLS_DIR / name
    if tool_dir.exists():
        shutil.rmtree(tool_dir)
        return True
    return False

# ─── CLI ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import time
    import argparse

    parser = argparse.ArgumentParser(description="Cybertron GitHub Tool Loader")
    parser.add_argument("url", nargs="?", help="GitHub repo URL")
    parser.add_argument("--name", help="Tool name override")
    parser.add_argument("--category", default="recon", help="Tool category")
    parser.add_argument("--auto-approve", action="store_true", help="Auto-approve this tool")
    parser.add_argument("--token", help="GitHub personal access token")
    parser.add_argument("--list", action="store_true", help="List installed tools")
    parser.add_argument("--remove", help="Remove installed tool by name")

    args = parser.parse_args()

    if args.list:
        tools = list_installed_tools()
        if not tools:
            print("No tools installed.")
        else:
            print(f"{'Name':<20} {'Version':<20} {'Category':<12} {'Path'}")
            print("-" * 80)
            for t in tools:
                print(f"{t['name']:<20} {t['version'][:18]:<20} {t['category']:<12} {t['binary_path']}")
    elif args.remove:
        if remove_tool(args.remove):
            print(f"Removed {args.remove}")
        else:
            print(f"Tool {args.remove} not found")
    elif args.url:
        result = register_tool(
            args.url,
            tool_name=args.name,
            category=args.category,
            auto_approve=args.auto_approve,
            github_token=args.token,
        )
        print(json.dumps(result, indent=2))
    else:
        parser.print_help()

#!/usr/bin/env python3
"""
Cybertron GitHub Tool Loader
==============================
Downloads, validates, and registers security tools from GitHub releases.
Phase 1 implementation: auto-detect platform asset, extract, chmod, validate.
Phase 2 ready: schema inference from --help output.

Tools are stored in ~/.cybertron/tools/<name>/
Catalog is persisted to ~/.cybertron/tools/catalog.json
"""
import os
import json
import re
import shutil
import stat
import subprocess
import zipfile
import tarfile
import platform
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

try:
    import requests
except ImportError:
    requests = None

# ─── Paths ───────────────────────────────────────────────────────────────────
TOOLS_DIR = Path.home() / ".cybertron" / "tools"
CATALOG_PATH = TOOLS_DIR / "catalog.json"
MARKETPLACE_PATH = Path(__file__).parent / "marketplace.json"


# ─── Data Models ─────────────────────────────────────────────────────────────
@dataclass
class GitHubToolSpec:
    id: str
    repo: str
    label: str
    category: str
    binary_name: str
    binary_path: str
    version: str
    auto_approve: bool = False
    handler: str = "github"
    installed_at: str = ""
    last_updated: str = ""
    schema: Dict[str, Any] = field(default_factory=dict)


# ─── Loader Core ─────────────────────────────────────────────────────────────
class GitHubToolLoader:
    def __init__(self):
        TOOLS_DIR.mkdir(parents=True, exist_ok=True)
        self.catalog: Dict[str, GitHubToolSpec] = {}
        self._load_catalog()
        self._pending_approval: Optional[Dict[str, Any]] = None

    # ── Catalog ──────────────────────────────────────────────────────────────
    def _load_catalog(self):
        if CATALOG_PATH.exists():
            try:
                data = json.loads(CATALOG_PATH.read_text())
                for k, v in data.items():
                    self.catalog[k] = GitHubToolSpec(**v)
            except Exception:
                self.catalog = {}

    def save_catalog(self):
        data = {k: asdict(v) for k, v in self.catalog.items()}
        CATALOG_PATH.write_text(json.dumps(data, indent=2))

    def get_catalog_list(self) -> List[Dict[str, Any]]:
        return [asdict(v) for v in self.catalog.values()]

    def get_tool(self, tool_id: str) -> Optional[GitHubToolSpec]:
        return self.catalog.get(tool_id)

    # ── GitHub API ───────────────────────────────────────────────────────────
    @staticmethod
    def parse_repo(url: str) -> Optional[str]:
        """Extract owner/repo from various GitHub URL formats."""
        patterns = [
            r"github\.com/([^/]+/[^/]+?)(?:\.git|/|$)",
            r"^([^/]+/[^/]+)$",
        ]
        for pat in patterns:
            m = re.search(pat, url)
            if m:
                return m.group(1).strip().strip("/")
        return None

    def fetch_latest_release(self, repo: str) -> Optional[Dict[str, Any]]:
        if requests is None:
            raise RuntimeError("requests library not installed")
        url = f"https://api.github.com/repos/{repo}/releases/latest"
        resp = requests.get(url, timeout=30, headers={"Accept": "application/vnd.github+json"})
        resp.raise_for_status()
        return resp.json()

    def fetch_releases(self, repo: str) -> List[Dict[str, Any]]:
        if requests is None:
            raise RuntimeError("requests library not installed")
        url = f"https://api.github.com/repos/{repo}/releases"
        resp = requests.get(url, timeout=30, headers={"Accept": "application/vnd.github+json"})
        resp.raise_for_status()
        return resp.json()

    # ── Asset Detection ──────────────────────────────────────────────────────
    def detect_asset(self, release: Dict[str, Any], binary_name: str) -> Optional[Dict[str, Any]]:
        """Auto-detect the best release asset for the current platform."""
        assets = release.get("assets", [])
        if not assets:
            # Some releases have no assets (source-only) — try tag tarball
            return None

        system = platform.system().lower()
        machine = platform.machine().lower()

        plat_map = {"darwin": "macos", "linux": "linux", "windows": "windows"}
        sys_name = plat_map.get(system, system)

        arch_map = {
            "amd64": "amd64", "x86_64": "amd64", "x64": "amd64",
            "arm64": "arm64", "aarch64": "arm64",
            "386": "386", "i386": "386", "i686": "386",
        }
        arch = arch_map.get(machine, machine)

        candidates = []
        for asset in assets:
            name = asset.get("name", "").lower()
            score = 0

            # Penalize source archives
            if any(x in name for x in ["source", "src", ".sig", ".pem", ".sbom"]):
                score -= 50
                continue

            # Prefer actual archives / binaries
            if name.endswith((".zip", ".tar.gz", ".tgz", ".tar.xz", ".tar.bz2")):
                score += 15
            if not name.endswith((".txt", ".md", ".json", ".yaml", ".yml", ".sha256", ".checksum")):
                score += 5

            # Platform match
            if sys_name in name:
                score += 10
            elif system in name:
                score += 8

            # Architecture match
            if arch in name:
                score += 10
            elif machine in name:
                score += 5

            candidates.append((score, asset))

        candidates.sort(key=lambda x: x[0], reverse=True)
        if candidates and candidates[0][0] > 0:
            return candidates[0][1]
        return None

    # ── Download / Extract ───────────────────────────────────────────────────
    def download_asset(self, url: str, dest: Path) -> Path:
        if requests is None:
            raise RuntimeError("requests library not installed")
        resp = requests.get(url, stream=True, timeout=120)
        resp.raise_for_status()
        filename = url.split("/")[-1].split("?")[0]
        dest_path = dest / filename
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return dest_path

    def extract_archive(self, archive_path: Path, dest_dir: Path) -> List[Path]:
        extracted: List[Path] = []
        name = archive_path.name.lower()

        if name.endswith(".zip") or zipfile.is_zipfile(archive_path):
            with zipfile.ZipFile(archive_path, "r") as zf:
                zf.extractall(dest_dir)
                for member in zf.namelist():
                    extracted.append(dest_dir / member)
        elif name.endswith((".tar.gz", ".tgz")):
            with tarfile.open(archive_path, "r:gz") as tf:
                tf.extractall(dest_dir)
                for member in tf.getnames():
                    extracted.append(dest_dir / member)
        elif name.endswith(".tar.xz"):
            with tarfile.open(archive_path, "r:xz") as tf:
                tf.extractall(dest_dir)
                for member in tf.getnames():
                    extracted.append(dest_dir / member)
        elif name.endswith(".tar.bz2"):
            with tarfile.open(archive_path, "r:bz2") as tf:
                tf.extractall(dest_dir)
                for member in tf.getnames():
                    extracted.append(dest_dir / member)
        else:
            # Treat as raw binary
            extracted.append(archive_path)

        return extracted

    def find_binary(self, dest_dir: Path, binary_name: str) -> Optional[Path]:
        """Locate the executable inside extracted files."""
        # Direct name matches first
        for path in dest_dir.rglob("*"):
            if not path.is_file():
                continue
            if path.name == binary_name:
                return path
            if os.name == "nt" and path.name == binary_name + ".exe":
                return path
            if path.stem == binary_name and path.stat().st_mode & stat.S_IXUSR:
                return path

        # Fallback: any executable-looking file with similar name
        for path in dest_dir.rglob("*"):
            if not path.is_file():
                continue
            if path.name.startswith(".") or path.name.endswith((".txt", ".md", ".json")):
                continue
            if binary_name.replace("-", "").replace("_", "") in path.name.replace("-", "").replace("_", ""):
                return path

        return None

    def make_executable(self, path: Path):
        if os.name == "nt":
            return
        try:
            st = os.stat(path)
            os.chmod(path, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        except Exception:
            pass

    # ── Validation ────────────────────────────────────────────────────────────
    def validate_tool(self, binary_path: Path) -> tuple[bool, str, str]:
        """Run --version and return (success, version_string, error)."""
        flags = ["--version", "-version", "version"]
        for flag in flags:
            try:
                result = subprocess.run(
                    [str(binary_path), flag],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    env={**os.environ, "NO_COLOR": "1", "TERM": "dumb"},
                )
                if result.returncode == 0:
                    ver = (result.stdout.strip() or result.stderr.strip())[:200]
                    return True, ver, ""
            except Exception:
                continue
        return False, "", "Could not determine version (--version failed)"

    # ── Schema Inference (Phase 1: regex on --help) ───────────────────────────
    def infer_schema(self, binary_path: Path) -> Dict[str, Any]:
        try:
            result = subprocess.run(
                [str(binary_path), "--help"],
                capture_output=True,
                text=True,
                timeout=15,
                env={**os.environ, "NO_COLOR": "1", "TERM": "dumb"},
            )
            help_text = result.stdout or result.stderr or ""
        except Exception as e:
            help_text = f"Could not retrieve help: {e}"

        schema: Dict[str, Any] = {
            "type": "object",
            "description": f"Auto-detected schema for {binary_path.name}",
            "properties": {},
            "required": [],
        }

        # Regex patterns for common CLI help formats
        patterns = [
            (r"^\s*(-\w),\s*(--[\w-]+)\s+(\S+)", "flag_with_arg"),
            (r"^\s*(-\w),\s*(--[\w-]+)", "boolean_flag"),
            (r"^\s*(--[\w-]+)\s+(\S+)", "long_flag_with_arg"),
            (r"^\s*(--[\w-]+)", "long_boolean_flag"),
            (r"^\s*(-\w)\s+(\S+)", "short_flag_with_arg"),
        ]

        seen = set()
        for line in help_text.splitlines():
            for pattern, ftype in patterns:
                m = re.match(pattern, line.strip())
                if m:
                    if ftype in ("flag_with_arg", "long_flag_with_arg", "short_flag_with_arg"):
                        name = m.group(2 if ftype != "short_flag_with_arg" else 1).lstrip("-").replace("-", "_")
                    else:
                        name = m.group(1).lstrip("-").replace("-", "_")

                    if name in seen or not name:
                        continue
                    seen.add(name)

                    prop: Dict[str, Any] = {"description": line.strip()[:120]}
                    if ftype in ("flag_with_arg", "long_flag_with_arg", "short_flag_with_arg"):
                        prop["type"] = "string"
                    else:
                        prop["type"] = "boolean"
                    schema["properties"][name] = prop
                    break

        return schema

    # ── Main Install Flow ────────────────────────────────────────────────────
    def install_tool(
        self,
        github_url: str,
        category: str = "recon",
        auto_approve: bool = False,
        specific_version: Optional[str] = None,
    ) -> tuple[bool, str, Optional[GitHubToolSpec]]:
        """
        Full install pipeline:
        1. Parse repo
        2. Fetch release
        3. Detect asset
        4. Download & extract
        5. Find binary + chmod
        6. Validate (--version)
        7. Infer schema (--help)
        8. Save catalog
        """
        repo = self.parse_repo(github_url)
        if not repo:
            return False, "Could not parse owner/repo from URL. Use github.com/owner/repo format.", None

        binary_name = repo.split("/")[-1]

        # Fetch release
        try:
            if specific_version and specific_version != "latest":
                releases = self.fetch_releases(repo)
                release = None
                for r in releases:
                    if r.get("tag_name") == specific_version:
                        release = r
                        break
                if not release:
                    return False, f"Version {specific_version} not found in {repo}", None
            else:
                release = self.fetch_latest_release(repo)
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                return False, f"Repository {repo} not found or has no releases.", None
            return False, f"GitHub API error: {e}", None
        except Exception as e:
            return False, f"Failed to fetch release info: {e}", None

        tag = release.get("tag_name", "unknown")

        # Detect asset
        asset = self.detect_asset(release, binary_name)
        if not asset:
            # Fallback: try source tarball (Go tools can be go-installed later)
            return False, (
                f"No pre-built binary found for {platform.system()} {platform.machine()}. "
                f"Asset list: {[a['name'] for a in release.get('assets', [])]}"
            ), None

        asset_url = asset["browser_download_url"]
        asset_name = asset["name"]

        # Prepare directory
        tool_dir = TOOLS_DIR / binary_name
        if tool_dir.exists():
            shutil.rmtree(tool_dir)
        tool_dir.mkdir(parents=True)

        # Download
        try:
            archive_path = self.download_asset(asset_url, tool_dir)
        except Exception as e:
            return False, f"Download failed: {e}", None

        # Extract
        try:
            extracted = self.extract_archive(archive_path, tool_dir)
        except Exception as e:
            return False, f"Extraction failed: {e}", None

        # Find binary
        binary_path = self.find_binary(tool_dir, binary_name)
        if not binary_path:
            # Last resort: if archive was a raw binary, use it directly
            if archive_path.is_file() and archive_path.stat().st_size > 1000:
                binary_path = archive_path
            else:
                return False, f"Could not locate binary '{binary_name}' in extracted archive.", None

        self.make_executable(binary_path)

        # Validate
        ok, version, error = self.validate_tool(binary_path)
        if not ok:
            version = tag  # fallback to tag name

        # Schema
        schema = self.infer_schema(binary_path)

        # Persist
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        spec = GitHubToolSpec(
            id=binary_name,
            repo=repo,
            label=binary_name,
            category=category,
            binary_name=binary_name,
            binary_path=str(binary_path),
            version=version or tag,
            auto_approve=auto_approve,
            installed_at=now,
            last_updated=now,
            schema=schema,
        )

        self.catalog[binary_name] = spec
        self.save_catalog()

        return True, f"Installed {binary_name} {spec.version} → {binary_path}", spec

    def remove_tool(self, tool_id: str) -> tuple[bool, str]:
        if tool_id not in self.catalog:
            return False, f"Tool '{tool_id}' is not in the local catalog."
        spec = self.catalog[tool_id]
        tool_dir = TOOLS_DIR / tool_id
        if tool_dir.exists():
            shutil.rmtree(tool_dir)
        del self.catalog[tool_id]
        self.save_catalog()
        return True, f"Removed {tool_id} ({spec.repo})"

    # ── Marketplace ──────────────────────────────────────────────────────────
    def get_marketplace(self) -> List[Dict[str, str]]:
        if MARKETPLACE_PATH.exists():
            try:
                data = json.loads(MARKETPLACE_PATH.read_text())
                return data.get("marketplace", [])
            except Exception:
                pass
        return self._default_marketplace()

    @staticmethod
    def _default_marketplace() -> List[Dict[str, str]]:
        return [
            {"name": "subfinder", "repo": "projectdiscovery/subfinder", "category": "recon",
             "description": "Fast passive subdomain discovery"},
            {"name": "httpx", "repo": "projectdiscovery/httpx", "category": "recon",
             "description": "Fast multi-purpose HTTP toolkit"},
            {"name": "nuclei", "repo": "projectdiscovery/nuclei", "category": "scan",
             "description": "Vulnerability scanner based on templates"},
            {"name": "gitleaks", "repo": "gitleaks/gitleaks", "category": "secrets",
             "description": "Detect hardcoded secrets in git repos"},
            {"name": "naabu", "repo": "projectdiscovery/naabu", "category": "scan",
             "description": "Fast port scanner"},
            {"name": "katana", "repo": "projectdiscovery/katana", "category": "crawl",
             "description": "Next-generation crawling framework"},
            {"name": "amass", "repo": "owasp-amass/amass", "category": "recon",
             "description": "In-depth attack surface mapping"},
            {"name": "ffuf", "repo": "ffuf/ffuf", "category": "fuzz",
             "description": "Fast web fuzzer"},
            {"name": "dalfox", "repo": "hahwul/dalfox", "category": "scan",
             "description": "Modern XSS scanner"},
            {"name": "nmap", "repo": "nmap/nmap", "category": "scan",
             "description": "Network discovery and security auditing"},
        ]


# ─── Singleton ───────────────────────────────────────────────────────────────
_loader_instance: Optional[GitHubToolLoader] = None

def get_loader() -> GitHubToolLoader:
    global _loader_instance
    if _loader_instance is None:
        _loader_instance = GitHubToolLoader()
    return _loader_instance

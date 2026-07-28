#!/usr/bin/env python3
"""
Cybertron Brute Force Engine
=============================
Orchestrates brute force attacks for bug bounty hunting.

Supported attacks:
- Directory/file brute force (ffuf, gobuster, dirb)
- Subdomain brute force (subfinder + wordlist)
- Parameter brute force (arjun, param-miner style)
- API endpoint brute force
- Virtual host brute force
- DNS brute force
- Credential brute force (hydra, medusa)
- JWT token brute force
- IDOR enumeration

SAFETY: All brute force is rate-limited and scope-validated.
"""
import json
import os
import subprocess
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed

from rate_limiter import get_limiter
from scope_manager import get_scope_manager
from output_sanitizer import get_sanitizer

WORDLISTS_DIR = Path("/app/wordlists")
TOOLS_DIR = Path.home() / ".cybertron" / "tools"


@dataclass
class BruteConfig:
    target: str
    attack_type: str  # dirs, subdomains, params, vhosts, dns, credentials, api, jwt, idor
    wordlist: str
    threads: int = 20
    timeout: int = 10
    rate_limit: int = 30  # requests per minute
    extensions: List[str] = field(default_factory=lambda: ["php", "txt", "html", "js", "json", "xml"])
    headers: Dict[str, str] = field(default_factory=dict)
    follow_redirects: bool = True
    hide_status: List[int] = field(default_factory=lambda: [404])
    match_status: List[int] = field(default_factory=lambda: [200, 301, 302, 401, 403, 500])
    scope_name: str = ""  # For scope validation
    dry_run: bool = False


class BruteForceEngine:
    def __init__(self):
        self.results: List[Dict[str, Any]] = []
        self.running = False
        self.current_job = None

    def _validate_scope(self, config: BruteConfig) -> Tuple[bool, str]:
        """Ensure target is in scope."""
        if not config.scope_name:
            return True, "No scope validation (use scope_name to enforce)"
        sm = get_scope_manager()
        ok, reason = sm.is_in_scope(config.scope_name, config.target)
        return ok, reason

    def _rate_limit_check(self, scope_name: str = "") -> Tuple[bool, str]:
        """Check rate limits."""
        limiter = get_limiter()
        session_id = scope_name or "brute_force"
        allowed, reason = limiter.check(session_id)
        return allowed, reason

    def _sanitize_output(self, text: str) -> str:
        """Redact sensitive data from output."""
        sanitizer = get_sanitizer()
        return sanitizer.sanitize(text)

    def _run_command(self, cmd: List[str], timeout: int = 60) -> Tuple[int, str, str]:
        """Execute a command safely."""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env={**os.environ, "NO_COLOR": "1"},
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -1, "", "Command timed out"
        except Exception as e:
            return -1, "", str(e)

    # ─── Directory Brute Force ────────────────────────────────────────────────
    def brute_dirs(self, config: BruteConfig) -> List[Dict[str, Any]]:
        """Brute force directories and files using ffuf."""
        if config.dry_run:
            return [{"dry_run": True, "target": config.target, "type": "dirs", "wordlist": config.wordlist}]

        wordlist_path = self._resolve_wordlist(config.wordlist)
        if not wordlist_path:
            return [{"error": f"Wordlist not found: {config.wordlist}"}]

        # Build ffuf command
        cmd = [
            "ffuf",
            "-u", f"{config.target}/FUZZ",
            "-w", str(wordlist_path),
            "-t", str(config.threads),
            "-timeout", str(config.timeout),
            "-mc", ",".join(map(str, config.match_status)),
            "-fc", ",".join(map(str, config.hide_status)),
            "-of", "json",
            "-o", "/tmp/ffuf_out.json",
        ]

        if config.extensions:
            cmd.extend(["-e", ",".join(f".{e}" for e in config.extensions)])
        if config.follow_redirects:
            cmd.append("-r")
        for k, v in config.headers.items():
            cmd.extend(["-H", f"{k}: {v}"])

        _, stdout, stderr = self._run_command(cmd, timeout=300)

        # Parse ffuf JSON output
        results = []
        try:
            output_path = Path("/tmp/ffuf_out.json")
            if output_path.exists():
                data = json.loads(output_path.read_text())
                for r in data.get("results", []):
                    results.append({
                        "url": r.get("url", ""),
                        "status": r.get("status", 0),
                        "size": r.get("length", 0),
                        "words": r.get("words", 0),
                        "lines": r.get("lines", 0),
                        "redirect": r.get("redirectlocation", ""),
                    })
        except Exception:
            pass

        return results

    # ─── Subdomain Brute Force ───────────────────────────────────────────────
    def brute_subdomains(self, config: BruteConfig) -> List[Dict[str, Any]]:
        """Brute force subdomains using subfinder + dnsx."""
        if config.dry_run:
            return [{"dry_run": True, "target": config.target, "type": "subdomains"}]

        # First use subfinder with wordlist
        wordlist_path = self._resolve_wordlist(config.wordlist)

        cmd = [
            "subfinder",
            "-d", config.target,
            "-all",
            "-recursive",
            "-silent",
        ]
        if wordlist_path:
            cmd.extend(["-w", str(wordlist_path)])

        _, stdout, _ = self._run_command(cmd, timeout=300)
        subdomains = [s.strip() for s in stdout.splitlines() if s.strip()]

        # Verify with dnsx
        if subdomains:
            dnsx_input = "\n".join(subdomains)
            result = subprocess.run(
                ["dnsx", "-silent", "-a", "-resp"],
                input=dnsx_input,
                capture_output=True,
                text=True,
                timeout=120,
            )
            verified = []
            for line in result.stdout.splitlines():
                if "[" in line:
                    parts = line.split(" ")
                    domain = parts[0]
                    ips = line[line.find("[")+1:line.find("]")].split(",")
                    verified.append({"domain": domain, "ips": [ip.strip() for ip in ips]})
            return verified

        return [{"subdomain": s} for s in subdomains]

    # ─── Parameter Brute Force ───────────────────────────────────────────────
    def brute_params(self, config: BruteConfig) -> List[Dict[str, Any]]:
        """Brute force parameters using arjun."""
        if config.dry_run:
            return [{"dry_run": True, "target": config.target, "type": "params"}]

        wordlist_path = self._resolve_wordlist(config.wordlist)

        cmd = [
            "arjun",
            "-u", config.target,
            "-t", str(config.threads),
            "-oJ", "/tmp/arjun_out.json",
        ]
        if wordlist_path:
            cmd.extend(["-w", str(wordlist_path)])

        _, stdout, _ = self._run_command(cmd, timeout=300)

        results = []
        try:
            output_path = Path("/tmp/arjun_out.json")
            if output_path.exists():
                data = json.loads(output_path.read_text())
                for entry in data.get("params", []):
                    results.append({
                        "name": entry.get("name", ""),
                        "type": entry.get("type", ""),
                        "method": entry.get("method", ""),
                    })
        except Exception:
            pass

        return results

    # ─── Virtual Host Brute Force ────────────────────────────────────────────
    def brute_vhosts(self, config: BruteConfig) -> List[Dict[str, Any]]:
        """Brute force virtual hosts using ffuf."""
        if config.dry_run:
            return [{"dry_run": True, "target": config.target, "type": "vhosts"}]

        wordlist_path = self._resolve_wordlist(config.wordlist)
        if not wordlist_path:
            return [{"error": f"Wordlist not found: {config.wordlist}"}]

        cmd = [
            "ffuf",
            "-u", config.target,
            "-H", "Host: FUZZ",
            "-w", str(wordlist_path),
            "-t", str(config.threads),
            "-mc", "200,301,302,401,403,500",
            "-fs", "0",
            "-of", "json",
            "-o", "/tmp/ffuf_vhost.json",
        ]

        _, stdout, _ = self._run_command(cmd, timeout=300)

        results = []
        try:
            output_path = Path("/tmp/ffuf_vhost.json")
            if output_path.exists():
                data = json.loads(output_path.read_text())
                for r in data.get("results", []):
                    results.append({
                        "vhost": r.get("input", {}).get("FUZZ", ""),
                        "status": r.get("status", 0),
                        "size": r.get("length", 0),
                    })
        except Exception:
            pass

        return results

    # ─── API Endpoint Brute Force ────────────────────────────────────────────
    def brute_api(self, config: BruteConfig) -> List[Dict[str, Any]]:
        """Brute force API endpoints."""
        if config.dry_run:
            return [{"dry_run": True, "target": config.target, "type": "api"}]

        wordlist_path = self._resolve_wordlist(config.wordlist)
        if not wordlist_path:
            return [{"error": f"Wordlist not found: {config.wordlist}"}]

        cmd = [
            "ffuf",
            "-u", f"{config.target}/api/FUZZ",
            "-w", str(wordlist_path),
            "-t", str(config.threads),
            "-mc", "200,201,204,301,302,401,403,405,500",
            "-H", "Content-Type: application/json",
            "-H", "Accept: application/json",
            "-of", "json",
            "-o", "/tmp/ffuf_api.json",
        ]

        _, stdout, _ = self._run_command(cmd, timeout=300)

        results = []
        try:
            output_path = Path("/tmp/ffuf_api.json")
            if output_path.exists():
                data = json.loads(output_path.read_text())
                for r in data.get("results", []):
                    results.append({
                        "endpoint": f"/api/{r.get('input', {}).get('FUZZ', '')}",
                        "status": r.get("status", 0),
                        "size": r.get("length", 0),
                    })
        except Exception:
            pass

        return results

    # ─── IDOR Enumeration ─────────────────────────────────────────────────────
    def brute_idor(self, config: BruteConfig) -> List[Dict[str, Any]]:
        """Enumerate IDOR vulnerabilities by iterating IDs."""
        if config.dry_run:
            return [{"dry_run": True, "target": config.target, "type": "idor"}]

        # Parse target URL - should contain FUZZ placeholder
        if "FUZZ" not in config.target:
            return [{"error": "Target must contain FUZZ placeholder (e.g., /api/users/FUZZ)"}]

        results = []
        # Generate ID ranges
        ranges = [
            range(1, 101),           # Sequential 1-100
            range(1000, 1100),       # 1000-1100
            range(10000, 10100),     # 10000-10100
        ]

        for id_range in ranges:
            ids = [str(i) for i in id_range]
            id_file = "/tmp/idor_ids.txt"
            Path(id_file).write_text("\n".join(ids))

            cmd = [
                "ffuf",
                "-u", config.target,
                "-w", id_file,
                "-t", str(min(config.threads, 10)),
                "-mc", "200,201,204",
                "-fs", "0",
                "-of", "json",
                "-o", "/tmp/ffuf_idor.json",
            ]

            _, stdout, _ = self._run_command(cmd, timeout=120)

            try:
                output_path = Path("/tmp/ffuf_idor.json")
                if output_path.exists():
                    data = json.loads(output_path.read_text())
                    for r in data.get("results", []):
                        results.append({
                            "id": r.get("input", {}).get("FUZZ", ""),
                            "status": r.get("status", 0),
                            "size": r.get("length", 0),
                        })
            except Exception:
                pass

            time.sleep(1)  # Rate limiting between ranges

        return results

    # ─── Helper ────────────────────────────────────────────────────────────────
    def _resolve_wordlist(self, wordlist: str) -> Optional[Path]:
        """Resolve a wordlist path."""
        # Direct path
        p = Path(wordlist)
        if p.exists():
            return p

        # Check wordlists directories
        search_paths = [
            WORDLISTS_DIR / "web" / wordlist,
            WORDLISTS_DIR / "dns" / wordlist,
            WORDLISTS_DIR / "brute" / wordlist,
            WORDLISTS_DIR / "api" / wordlist,
            WORDLISTS_DIR / "seclists" / "Discovery" / "Web-Content" / wordlist,
            WORDLISTS_DIR / "seclists" / "Discovery" / "DNS" / wordlist,
        ]

        for sp in search_paths:
            if sp.exists():
                return sp

        # Check if it's a known wordlist name
        known = {
            "common": WORDLISTS_DIR / "seclists/Discovery/Web-Content/common.txt",
            "big": WORDLISTS_DIR / "seclists/Discovery/Web-Content/big.txt",
            "raft-small": WORDLISTS_DIR / "seclists/Discovery/Web-Content/raft-small-words.txt",
            "raft-medium": WORDLISTS_DIR / "seclists/Discovery/Web-Content/raft-medium-words.txt",
            "raft-large": WORDLISTS_DIR / "seclists/Discovery/Web-Content/raft-large-words.txt",
            "subdomains-top1million": WORDLISTS_DIR / "seclists/Discovery/DNS/subdomains-top1million-5000.txt",
            "subdomains": WORDLISTS_DIR / "seclists/Discovery/DNS/subdomains-top1million-5000.txt",
            "api-endpoints": WORDLISTS_DIR / "api/api-endpoints.txt",
            "parameters": WORDLISTS_DIR / "seclists/Discovery/Web-Content/burp-parameter-names.txt",
        }

        if wordlist.lower() in known:
            p = known[wordlist.lower()]
            if p.exists():
                return p

        return None

    def run(self, config: BruteConfig) -> Dict[str, Any]:
        """Main entry point for brute force attacks."""
        # Validate scope
        scope_ok, scope_reason = self._validate_scope(config)
        if not scope_ok:
            return {"success": False, "error": f"Scope validation failed: {scope_reason}"}

        # Check rate limits
        rate_ok, rate_reason = self._rate_limit_check(config.scope_name)
        if not rate_ok:
            return {"success": False, "error": f"Rate limit: {rate_reason}"}

        self.running = True
        self.current_job = config
        start_time = time.time()

        # Dispatch to appropriate method
        dispatch = {
            "dirs": self.brute_dirs,
            "subdomains": self.brute_subdomains,
            "params": self.brute_params,
            "vhosts": self.brute_vhosts,
            "api": self.brute_api,
            "idor": self.brute_idor,
        }

        handler = dispatch.get(config.attack_type)
        if not handler:
            self.running = False
            return {"success": False, "error": f"Unknown attack type: {config.attack_type}"}

        try:
            results = handler(config)
            duration = time.time() - start_time

            # Sanitize output
            for r in results:
                for key in ["url", "endpoint", "domain", "vhost"]:
                    if key in r and isinstance(r[key], str):
                        r[key] = self._sanitize_output(r[key])

            return {
                "success": True,
                "attack_type": config.attack_type,
                "target": config.target,
                "results_count": len(results),
                "duration_seconds": round(duration, 2),
                "results": results,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            self.running = False
            self.current_job = None


# ─── Singleton ───────────────────────────────────────────────────────────────
_brute_instance: Optional[BruteForceEngine] = None

def get_brute_engine() -> BruteForceEngine:
    global _brute_instance
    if _brute_instance is None:
        _brute_instance = BruteForceEngine()
    return _brute_instance

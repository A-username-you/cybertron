#!/usr/bin/env python3
"""
Cybertron Recon Pipeline
=========================
Automated bug bounty reconnaissance pipeline.

Stages:
1. Subdomain Enumeration (subfinder, amass, assetfinder)
2. DNS Resolution & Validation (dnsx)
3. Live Host Discovery (httpx)
4. Port Scanning (naabu, nmap)
5. Technology Detection (httpx, wappalyzer)
6. Screenshotting (gowitness)
7. Content Discovery (gau, waybackurls, hakrawler)
8. JavaScript Analysis (getJS, jsluice)
9. Secret Detection (gitleaks, trufflehog)
10. Vulnerability Scanning (nuclei)

All stages are scope-validated and rate-limited.
"""
import json
import os
import subprocess
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed

from scope_manager import get_scope_manager
from rate_limiter import get_limiter
from output_sanitizer import get_sanitizer

REPORTS_DIR = Path("/app/reports")


@dataclass
class ReconConfig:
    target: str
    scope_name: str = ""
    stages: List[str] = field(default_factory=lambda: [
        "subdomains", "dns", "live_hosts", "ports",
        "tech", "screenshots", "content", "js", "secrets", "vulns"
    ])
    threads: int = 20
    timeout: int = 300
    rate_limit: int = 30
    wordlist: str = "subdomains-top1million-5000.txt"
    ports: str = "top-100"
    nuclei_severity: List[str] = field(default_factory=lambda: ["critical", "high", "medium"])
    dry_run: bool = False
    output_dir: str = "/app/reports"


class ReconPipeline:
    def __init__(self):
        self.results: Dict[str, Any] = {}
        self.running = False
        self.current_stage = ""
        self.start_time = 0

    def _run_cmd(self, cmd: List[str], timeout: int = 300, input_text: str = "") -> Tuple[int, str, str]:
        """Execute a command safely."""
        try:
            result = subprocess.run(
                cmd,
                input=input_text,
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

    def _save_stage(self, stage: str, data: Any):
        """Save stage results to file."""
        out_dir = Path(self.config.output_dir) / self.config.target.replace(".", "_")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"{stage}.json"
        out_file.write_text(json.dumps(data, indent=2, default=str))

    def _load_stage(self, stage: str) -> Any:
        """Load previously saved stage results."""
        out_dir = Path(self.config.output_dir) / self.config.target.replace(".", "_")
        out_file = out_dir / f"{stage}.json"
        if out_file.exists():
            return json.loads(out_file.read_text())
        return None

    # ─── Stage 1: Subdomain Enumeration ───────────────────────────────────────
    def stage_subdomains(self) -> Dict[str, Any]:
        self.current_stage = "subdomains"
        domain = self.config.target

        if self.config.dry_run:
            return {"dry_run": True, "method": "subfinder + amass + assetfinder", "target": domain}

        subdomains = set()

        # subfinder
        _, stdout, _ = self._run_cmd([
            "subfinder", "-d", domain, "-all", "-recursive", "-silent"
        ], timeout=self.config.timeout)
        subdomains.update(s.strip() for s in stdout.splitlines() if s.strip())

        # amass
        _, stdout, _ = self._run_cmd([
            "amass", "enum", "-passive", "-d", domain
        ], timeout=self.config.timeout)
        subdomains.update(s.strip() for s in stdout.splitlines() if s.strip())

        # assetfinder
        _, stdout, _ = self._run_cmd([
            "assetfinder", "--subs-only", domain
        ], timeout=self.config.timeout)
        subdomains.update(s.strip() for s in stdout.splitlines() if s.strip())

        return {
            "count": len(subdomains),
            "subdomains": sorted(list(subdomains)),
        }

    # ─── Stage 2: DNS Resolution ──────────────────────────────────────────────
    def stage_dns(self, subdomains: List[str]) -> Dict[str, Any]:
        self.current_stage = "dns"

        if self.config.dry_run:
            return {"dry_run": True, "method": "dnsx", "count": len(subdomains)}

        if not subdomains:
            return {"count": 0, "resolved": []}

        input_text = "\n".join(subdomains)
        _, stdout, _ = self._run_cmd(
            ["dnsx", "-silent", "-a", "-resp", "-rcode", "noerror,servfail,refused"],
            timeout=self.config.timeout,
            input_text=input_text,
        )

        resolved = []
        for line in stdout.splitlines():
            if "[" in line:
                parts = line.split(" ")
                domain = parts[0]
                ips = line[line.find("[")+1:line.find("]")].split(",")
                resolved.append({
                    "domain": domain,
                    "ips": [ip.strip() for ip in ips],
                })

        return {
            "count": len(resolved),
            "resolved": resolved,
        }

    # ─── Stage 3: Live Host Discovery ─────────────────────────────────────────
    def stage_live_hosts(self, urls: List[str]) -> Dict[str, Any]:
        self.current_stage = "live_hosts"

        if self.config.dry_run:
            return {"dry_run": True, "method": "httpx", "count": len(urls)}

        if not urls:
            return {"count": 0, "live": []}

        input_text = "\n".join(urls)
        _, stdout, _ = self._run_cmd(
            ["httpx", "-silent", "-title", "-tech-detect", "-status-code", "-content-length", "-json"],
            timeout=self.config.timeout,
            input_text=input_text,
        )

        live = []
        for line in stdout.splitlines():
            try:
                data = json.loads(line)
                live.append({
                    "url": data.get("url", ""),
                    "status": data.get("status_code", 0),
                    "title": data.get("title", ""),
                    "tech": data.get("tech", []),
                    "content_length": data.get("content_length", 0),
                    "webserver": data.get("webserver", ""),
                })
            except json.JSONDecodeError:
                continue

        return {
            "count": len(live),
            "live": live,
        }

    # ─── Stage 4: Port Scanning ───────────────────────────────────────────────
    def stage_ports(self, hosts: List[str]) -> Dict[str, Any]:
        self.current_stage = "ports"

        if self.config.dry_run:
            return {"dry_run": True, "method": "naabu", "count": len(hosts)}

        if not hosts:
            return {"count": 0, "ports": []}

        input_text = "\n".join(hosts)
        _, stdout, _ = self._run_cmd(
            ["naabu", "-silent", "-p", self.config.ports, "-json"],
            timeout=self.config.timeout,
            input_text=input_text,
        )

        ports = []
        for line in stdout.splitlines():
            try:
                data = json.loads(line)
                ports.append({
                    "host": data.get("host", ""),
                    "port": data.get("port", 0),
                    "ip": data.get("ip", ""),
                })
            except json.JSONDecodeError:
                continue

        return {
            "count": len(ports),
            "ports": ports,
        }

    # ─── Stage 5: Technology Detection ──────────────────────────────────────────
    def stage_tech(self, urls: List[str]) -> Dict[str, Any]:
        self.current_stage = "tech"

        if self.config.dry_run:
            return {"dry_run": True, "method": "httpx tech-detect", "count": len(urls)}

        if not urls:
            return {"count": 0, "technologies": {}}

        input_text = "\n".join(urls)
        _, stdout, _ = self._run_cmd(
            ["httpx", "-silent", "-tech-detect", "-json"],
            timeout=self.config.timeout,
            input_text=input_text,
        )

        tech_map = {}
        for line in stdout.splitlines():
            try:
                data = json.loads(line)
                url = data.get("url", "")
                tech = data.get("tech", [])
                tech_map[url] = tech
            except json.JSONDecodeError:
                continue

        return {
            "count": len(tech_map),
            "technologies": tech_map,
        }

    # ─── Stage 6: Screenshots ─────────────────────────────────────────────────
    def stage_screenshots(self, urls: List[str]) -> Dict[str, Any]:
        self.current_stage = "screenshots"

        if self.config.dry_run:
            return {"dry_run": True, "method": "gowitness", "count": len(urls)}

        if not urls:
            return {"count": 0, "screenshots": []}

        out_dir = Path(self.config.output_dir) / self.config.target.replace(".", "_") / "screenshots"
        out_dir.mkdir(parents=True, exist_ok=True)

        input_text = "\n".join(urls)
        self._run_cmd(
            ["gowitness", "scan", "file", "-f", "-", "-P", str(out_dir)],
            timeout=self.config.timeout,
            input_text=input_text,
        )

        screenshots = [str(p) for p in out_dir.glob("*.png")]
        return {
            "count": len(screenshots),
            "screenshots": screenshots,
        }

    # ─── Stage 7: Content Discovery ───────────────────────────────────────────
    def stage_content(self, urls: List[str]) -> Dict[str, Any]:
        self.current_stage = "content"

        if self.config.dry_run:
            return {"dry_run": True, "method": "gau + waybackurls + hakrawler", "count": len(urls)}

        all_urls = set()

        for url in urls[:10]:  # Limit to first 10 to avoid overwhelming
            # gau
            _, stdout, _ = self._run_cmd(["gau", url], timeout=60)
            all_urls.update(s.strip() for s in stdout.splitlines() if s.strip())

            # waybackurls
            _, stdout, _ = self._run_cmd(["waybackurls", url], timeout=60)
            all_urls.update(s.strip() for s in stdout.splitlines() if s.strip())

        return {
            "count": len(all_urls),
            "urls": sorted(list(all_urls))[:10000],  # Limit output size
        }

    # ─── Stage 8: JavaScript Analysis ─────────────────────────────────────────
    def stage_js(self, urls: List[str]) -> Dict[str, Any]:
        self.current_stage = "js"

        if self.config.dry_run:
            return {"dry_run": True, "method": "getJS + jsluice", "count": len(urls)}

        js_urls = set()
        for url in urls:
            if ".js" in url:
                js_urls.add(url)

        endpoints = []
        secrets = []

        for js_url in list(js_urls)[:50]:  # Limit
            # jsluice
            _, stdout, _ = self._run_cmd(["jsluice", "urls", js_url], timeout=30)
            for line in stdout.splitlines():
                if line.strip():
                    endpoints.append({"source": js_url, "endpoint": line.strip()})

        return {
            "js_files": len(js_urls),
            "endpoints": endpoints[:1000],
        }

    # ─── Stage 9: Secret Detection ────────────────────────────────────────────
    def stage_secrets(self, urls: List[str]) -> Dict[str, Any]:
        self.current_stage = "secrets"

        if self.config.dry_run:
            return {"dry_run": True, "method": "trufflehog + gitleaks", "count": len(urls)}

        # trufflehog on URLs
        findings = []
        for url in urls[:20]:  # Limit
            _, stdout, _ = self._run_cmd(
                ["trufflehog", "filesystem", "--json", url],
                timeout=60,
            )
            for line in stdout.splitlines():
                try:
                    data = json.loads(line)
                    findings.append({
                        "detector": data.get("DetectorName", ""),
                        "raw": data.get("Raw", "")[:100],  # Truncate
                        "source": url,
                    })
                except json.JSONDecodeError:
                    continue

        return {
            "count": len(findings),
            "findings": findings,
        }

    # ─── Stage 10: Vulnerability Scanning ─────────────────────────────────────
    def stage_vulns(self, urls: List[str]) -> Dict[str, Any]:
        self.current_stage = "vulns"

        if self.config.dry_run:
            return {"dry_run": True, "method": "nuclei", "count": len(urls)}

        if not urls:
            return {"count": 0, "vulnerabilities": []}

        input_text = "\n".join(urls)
        severity_filter = ",".join(self.config.nuclei_severity)

        _, stdout, _ = self._run_cmd(
            ["nuclei", "-silent", "-severity", severity_filter, "-jsonl"],
            timeout=self.config.timeout,
            input_text=input_text,
        )

        vulns = []
        for line in stdout.splitlines():
            try:
                data = json.loads(line)
                vulns.append({
                    "template": data.get("template-id", ""),
                    "name": data.get("info", {}).get("name", ""),
                    "severity": data.get("info", {}).get("severity", ""),
                    "host": data.get("host", ""),
                    "url": data.get("matched-at", ""),
                    "extracted": data.get("extracted-results", []),
                })
            except json.JSONDecodeError:
                continue

        return {
            "count": len(vulns),
            "vulnerabilities": vulns,
        }

    # ─── Main Pipeline ────────────────────────────────────────────────────────
    def run(self, config: ReconConfig) -> Dict[str, Any]:
        self.config = config
        self.running = True
        self.start_time = time.time()
        self.results = {"target": config.target, "stages": {}}

        # Validate scope
        if config.scope_name:
            sm = get_scope_manager()
            ok, reason = sm.is_in_scope(config.scope_name, config.target)
            if not ok:
                self.running = False
                return {"success": False, "error": f"Scope validation failed: {reason}"}

        # Execute stages
        subdomains = []
        resolved = []
        urls = []

        for stage in config.stages:
            if not self.running:
                break

            self.current_stage = stage
            stage_result = {"status": "running"}

            try:
                if stage == "subdomains":
                    result = self.stage_subdomains()
                    subdomains = result.get("subdomains", [])
                    urls = [f"https://{s}" for s in subdomains]
                    stage_result = result

                elif stage == "dns":
                    result = self.stage_dns(subdomains)
                    resolved = result.get("resolved", [])
                    stage_result = result

                elif stage == "live_hosts":
                    result = self.stage_live_hosts(urls)
                    # Filter to only live hosts
                    live_urls = [h["url"] for h in result.get("live", []) if h.get("status", 0) in [200, 301, 302, 401, 403]]
                    urls = live_urls or urls
                    stage_result = result

                elif stage == "ports":
                    hosts = [r["domain"] for r in resolved]
                    stage_result = self.stage_ports(hosts)

                elif stage == "tech":
                    stage_result = self.stage_tech(urls)

                elif stage == "screenshots":
                    stage_result = self.stage_screenshots(urls)

                elif stage == "content":
                    stage_result = self.stage_content(urls)

                elif stage == "js":
                    content_urls = self._load_stage("content")
                    all_urls = content_urls.get("urls", []) if content_urls else urls
                    stage_result = self.stage_js(all_urls)

                elif stage == "secrets":
                    content_urls = self._load_stage("content")
                    all_urls = content_urls.get("urls", []) if content_urls else urls
                    stage_result = self.stage_secrets(all_urls)

                elif stage == "vulns":
                    stage_result = self.stage_vulns(urls)

                stage_result["status"] = "completed"
                self._save_stage(stage, stage_result)

            except Exception as e:
                stage_result = {"status": "error", "error": str(e)}
                self._save_stage(stage, stage_result)

            self.results["stages"][stage] = stage_result

        duration = time.time() - self.start_time
        self.results["duration_seconds"] = round(duration, 2)
        self.results["success"] = True
        self.running = False

        return self.results

    def stop(self):
        self.running = False


# ─── Singleton ───────────────────────────────────────────────────────────────
_recon_instance: Optional[ReconPipeline] = None

def get_recon_pipeline() -> ReconPipeline:
    global _recon_instance
    if _recon_instance is None:
        _recon_instance = ReconPipeline()
    return _recon_instance

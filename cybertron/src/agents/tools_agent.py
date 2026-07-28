#!/usr/bin/env python3
"""
Cybertron Tools Agent
=====================
Runs inside the tools Docker container.
Connects to the gateway via WebSocket and executes security tools on demand.

Handles:
- Reconnaissance pipeline execution
- Brute force attacks
- Vulnerability scanning
- Report generation
- Scope validation
- Rate limiting
"""
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, Any, Optional

import websockets

# Import our modules
sys.path.insert(0, "/app")
from recon_pipeline import ReconPipeline, ReconConfig
from brute_force_engine import BruteForceEngine, BruteConfig
from report_generator import ReportGenerator, Report, Vulnerability
from scope_manager import ScopeManager, get_scope_manager
from rate_limiter import get_limiter
from output_sanitizer import get_sanitizer
from audit_logger import get_logger

GATEWAY_HOST = os.environ.get("CYBERTRON_HOST", "gateway")
GATEWAY_PORT = int(os.environ.get("CYBERTRON_PORT", "8765"))
WS_URL = f"ws://{GATEWAY_HOST}:{GATEWAY_PORT}"
TOKEN_PATH = Path.home() / ".cybertron" / "auth-token"


class ToolsAgent:
    def __init__(self):
        self.ws = None
        self.authed = False
        self.running = True
        self.recon = ReconPipeline()
        self.brute = BruteForceEngine()
        self.reports = ReportGenerator()
        self.scope = get_scope_manager()
        self.limiter = get_limiter()
        self.sanitizer = get_sanitizer()
        self.audit = get_logger()

    async def connect(self):
        token = ""
        if TOKEN_PATH.exists():
            token = TOKEN_PATH.read_text().strip()

        while self.running:
            try:
                async with websockets.connect(WS_URL) as ws:
                    self.ws = ws
                    await ws.send(json.dumps({"type": "auth", "token": token, "origin": "tools_agent"}))

                    async for raw in ws:
                        if not self.running:
                            break
                        try:
                            msg = json.loads(raw)
                            await self.handle_message(msg)
                        except json.JSONDecodeError:
                            pass
            except Exception as e:
                print(f"[ToolsAgent] Connection error: {e}")
                await asyncio.sleep(5)

    async def handle_message(self, msg: Dict[str, Any]):
        mtype = msg.get("type")

        if mtype == "auth_result":
            self.authed = msg.get("ok", False)
            if self.authed:
                print("[ToolsAgent] Authenticated with gateway")
            return

        if mtype == "execute_recon":
            await self.handle_recon(msg)
            return

        if mtype == "execute_brute":
            await self.handle_brute(msg)
            return

        if mtype == "generate_report":
            await self.handle_report(msg)
            return

        if mtype == "get_recon_status":
            await self.send_status()
            return

        if mtype == "stop_recon":
            self.recon.stop()
            await self.send({"type": "recon_stopped"})
            return

    async def handle_recon(self, msg: Dict[str, Any]):
        """Execute reconnaissance pipeline."""
        config = ReconConfig(
            target=msg.get("target", ""),
            scope_name=msg.get("scope_name", ""),
            stages=msg.get("stages", ["subdomains", "dns", "live_hosts", "ports", "tech", "vulns"]),
            threads=msg.get("threads", 20),
            timeout=msg.get("timeout", 300),
            dry_run=msg.get("dry_run", False),
            output_dir=msg.get("output_dir", "/app/reports"),
        )

        # Send plan
        await self.send({
            "type": "agent_plan",
            "steps": config.stages,
            "target": config.target,
        })

        # Execute
        result = self.recon.run(config)

        # Sanitize output
        result = self.sanitizer.sanitize_dict(result)

        await self.send({
            "type": "recon_complete",
            "result": result,
        })

        # Audit log
        self.audit.system_event(
            f"Recon completed for {config.target}: {result.get('duration_seconds', 0)}s",
            "info"
        )

    async def handle_brute(self, msg: Dict[str, Any]):
        """Execute brute force attack."""
        config = BruteConfig(
            target=msg.get("target", ""),
            attack_type=msg.get("attack_type", "dirs"),
            wordlist=msg.get("wordlist", "common"),
            threads=msg.get("threads", 20),
            scope_name=msg.get("scope_name", ""),
            dry_run=msg.get("dry_run", False),
        )

        result = self.brute.run(config)
        result = self.sanitizer.sanitize_dict(result)

        await self.send({
            "type": "brute_complete",
            "result": result,
        })

    async def handle_report(self, msg: Dict[str, Any]):
        """Generate vulnerability report."""
        program = msg.get("program", "")
        handle = msg.get("handle", "")
        vulns_data = msg.get("vulnerabilities", [])

        vulns = []
        for vd in vulns_data:
            vulns.append(Vulnerability(**vd))

        report = Report(
            program_name=program,
            program_handle=handle,
            platform=msg.get("platform", "hackerone"),
            title=msg.get("title", f"Bug Bounty Report for {program}"),
            summary=msg.get("summary", ""),
            vulnerabilities=vulns,
        )

        formats = msg.get("formats", ["markdown", "json"])
        saved = self.reports.save_report(report, formats)

        await self.send({
            "type": "report_generated",
            "files": {k: str(v) for k, v in saved.items()},
            "vulnerability_count": len(vulns),
        })

    async def send_status(self):
        await self.send({
            "type": "recon_status",
            "running": self.recon.running,
            "current_stage": self.recon.current_stage,
            "target": self.recon.config.target if self.recon.config else "",
            "elapsed": time.time() - self.recon.start_time if self.recon.running else 0,
        })

    async def send(self, msg: Dict[str, Any]):
        if self.ws and self.ws.open:
            await self.ws.send(json.dumps(msg))


async def main():
    agent = ToolsAgent()
    await agent.connect()

if __name__ == "__main__":
    asyncio.run(main())

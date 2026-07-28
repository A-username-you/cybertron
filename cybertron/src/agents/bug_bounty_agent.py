#!/usr/bin/env python3
"""
Cybertron Bug Bounty Agent
==========================
Main orchestrator for automated bug bounty hunting.

Workflow:
1. Load target configuration
2. Sync scope from HackerOne (if applicable)
3. Execute reconnaissance pipeline
4. Execute brute force discovery
5. Run vulnerability scans
6. Analyze findings
7. Generate reports
8. Submit to HackerOne (optional)

This agent runs inside the gateway container and coordinates
between the tools container and the UI.
"""
import asyncio
import json
import os
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

from scope_manager import get_scope_manager
from hackerone_integration import get_hackerone_api
from recon_pipeline import get_recon_pipeline
from brute_force_engine import get_brute_engine
from report_generator import get_report_generator
from rate_limiter import get_limiter
from output_sanitizer import get_sanitizer
from audit_logger import get_logger
from webhook_notifier import get_notifier


class BugBountyAgent:
    """Main bug bounty hunting orchestrator."""

    def __init__(self):
        self.scope = get_scope_manager()
        self.h1 = get_hackerone_api()
        self.recon = get_recon_pipeline()
        self.brute = get_brute_engine()
        self.reports = get_report_generator()
        self.limiter = get_limiter()
        self.sanitizer = get_sanitizer()
        self.audit = get_logger()
        self.notifier = get_notifier()
        self.current_target = None
        self.findings = []

    def sync_hackerone_program(self, handle: str) -> Dict[str, Any]:
        """Sync a HackerOne program's scope to local configuration."""
        try:
            result = self.h1.sync_scope_to_local(handle)
            self.audit.system_event(f"Synced HackerOne program: {handle}", "info")
            return result
        except Exception as e:
            self.audit.system_event(f"HackerOne sync failed: {e}", "error")
            return {"success": False, "error": str(e)}

    def run_recon(self, target_name: str, stages: List[str] = None) -> Dict[str, Any]:
        """Run full reconnaissance on a target."""
        target = self.scope.get_target(target_name)
        if not target:
            return {"success": False, "error": f"Target '{target_name}' not found"}

        domains = self.scope.get_scope_domains(target_name)
        if not domains:
            return {"success": False, "error": "No domains in scope"}

        self.current_target = target
        self.findings = []

        all_results = {}
        for domain in domains:
            from recon_pipeline import ReconConfig
            config = ReconConfig(
                target=domain,
                scope_name=target_name,
                stages=stages or ["subdomains", "dns", "live_hosts", "ports", "tech", "vulns"],
                dry_run=False,
            )
            result = self.recon.run(config)
            all_results[domain] = result

            # Extract vulnerabilities from recon
            vulns = result.get("stages", {}).get("vulns", {}).get("vulnerabilities", [])
            self.findings.extend(vulns)

        # Notify webhooks
        if self.findings:
            self.notifier.notify_finding(
                session_id=f"recon-{target_name}",
                severity="high",
                title=f"Recon findings for {target_name}",
                description=f"Found {len(self.findings)} potential vulnerabilities",
                target=target_name,
            )

        return {
            "success": True,
            "target": target_name,
            "domains_scanned": len(domains),
            "total_findings": len(self.findings),
            "results": all_results,
        }

    def run_brute_force(self, target_name: str, attack_type: str,
                        wordlist: str = "common") -> Dict[str, Any]:
        """Run brute force discovery on a target."""
        target = self.scope.get_target(target_name)
        if not target:
            return {"success": False, "error": f"Target '{target_name}' not found"}

        domains = self.scope.get_scope_domains(target_name)
        all_results = []

        for domain in domains:
            from brute_force_engine import BruteConfig
            config = BruteConfig(
                target=domain,
                attack_type=attack_type,
                wordlist=wordlist,
                scope_name=target_name,
            )
            result = self.brute.run(config)
            all_results.append(result)

        return {
            "success": True,
            "target": target_name,
            "attack_type": attack_type,
            "results": all_results,
        }

    def generate_report(self, target_name: str, formats: List[str] = None) -> Dict[str, Any]:
        """Generate a vulnerability report for findings."""
        target = self.scope.get_target(target_name)
        if not target:
            return {"success": False, "error": f"Target '{target_name}' not found"}

        # Convert findings to vulnerabilities
        vulns = []
        for finding in self.findings:
            vuln = self.reports.create_vulnerability(
                title=finding.get("name", "Unknown"),
                severity=finding.get("severity", "info"),
                cvss_score=8.0 if finding.get("severity") == "high" else 5.5,
                cvss_vector="",
                category=finding.get("template", "unknown"),
                description=f"Detected by {finding.get('template', 'unknown')}",
                impact=f"This vulnerability was found on {finding.get('host', 'unknown')}",
                steps=[f"Navigate to {finding.get('url', 'the affected endpoint')}"],
                affected_urls=[finding.get("url", "")],
            )
            vulns.append(vuln)

        report = Report(
            program_name=target.name,
            program_handle=target.handle,
            platform=target.platform,
            title=f"Bug Bounty Report: {target.name}",
            summary=f"Automated assessment of {target.name} identified {len(vulns)} security issues.",
            vulnerabilities=vulns,
        )

        saved = self.reports.save_report(report, formats or ["markdown", "json", "hackerone"])

        return {
            "success": True,
            "files": {k: str(v) for k, v in saved.items()},
            "vulnerability_count": len(vulns),
        }

    def submit_to_hackerone(self, target_name: str) -> Dict[str, Any]:
        """Submit findings to HackerOne."""
        target = self.scope.get_target(target_name)
        if not target or target.platform != "hackerone":
            return {"success": False, "error": "Not a HackerOne target"}

        submitted = []
        for finding in self.findings:
            try:
                result = self.h1.submit_report(
                    handle=target.handle,
                    title=finding.get("name", "Vulnerability Found"),
                    vulnerability_types=[finding.get("template", "other")],
                    summary=finding.get("name", ""),
                    severity=finding.get("severity", "medium"),
                    impact="Automated detection by Cybertron Agent",
                    steps=[f"Visit {finding.get('url', '')}"],
                )
                submitted.append(result)
            except Exception as e:
                submitted.append({"error": str(e)})

        return {
            "success": True,
            "submitted": len(submitted),
            "results": submitted,
        }

    def get_stats(self) -> Dict[str, Any]:
        """Get bug bounty statistics."""
        targets = self.scope.list_targets()
        h1_stats = {}
        try:
            h1_stats = self.h1.get_stats()
        except:
            pass

        return {
            "targets": len(targets),
            "findings": len(self.findings),
            "hackerone": h1_stats,
        }


# ─── Singleton ───────────────────────────────────────────────────────────────
_bb_agent_instance: Optional[BugBountyAgent] = None

def get_bug_bounty_agent() -> BugBountyAgent:
    global _bb_agent_instance
    if _bb_agent_instance is None:
        _bb_agent_instance = BugBountyAgent()
    return _bb_agent_instance


if __name__ == "__main__":
    agent = get_bug_bounty_agent()
    # Example usage
    print("Bug Bounty Agent initialized")
    print(f"Targets: {len(agent.scope.list_targets())}")

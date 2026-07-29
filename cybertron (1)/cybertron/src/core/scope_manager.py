#!/usr/bin/env python3
"""
Cybertron Scope Manager
=======================
Manages bug bounty program targets, in-scope/out-of-scope rules,
rate limiting per target, and program metadata.

Supports: HackerOne, Bugcrowd, Intigriti, custom programs.
"""
import json
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

CONFIG_DIR = Path.home() / ".cybertron" / "configs"
TARGETS_FILE = CONFIG_DIR / "targets.json"


@dataclass
class Target:
    name: str
    platform: str  # hackerone, bugcrowd, intigriti, custom
    handle: str
    scope: List[str]  # wildcard patterns like "*.example.com"
    out_of_scope: List[str]
    severity_filter: List[str]  # critical, high, medium, low, info
    enabled: bool = True
    max_concurrent_scans: int = 3
    scan_timeout_minutes: int = 60
    rate_limit_per_minute: int = 30
    custom_headers: Dict[str, str] = None
    auth_tokens: Dict[str, str] = None
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""


class ScopeManager:
    def __init__(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self.targets: Dict[str, Target] = {}
        self._load_targets()

    def _load_targets(self):
        if TARGETS_FILE.exists():
            try:
                data = json.loads(TARGETS_FILE.read_text())
                for t in data.get("targets", []):
                    self.targets[t["name"]] = Target(**t)
            except Exception:
                pass

    def save_targets(self):
        data = {
            "targets": [asdict(t) for t in self.targets.values()],
            "global_settings": {
                "max_concurrent_scans": 3,
                "scan_timeout_minutes": 60,
                "auto_report": False,
                "report_template": "hackerone",
            }
        }
        TARGETS_FILE.write_text(json.dumps(data, indent=2))

    def add_target(self, name: str, platform: str, handle: str,
                   scope: List[str], out_of_scope: List[str] = None,
                   severity_filter: List[str] = None, **kwargs) -> Target:
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        target = Target(
            name=name,
            platform=platform,
            handle=handle,
            scope=scope,
            out_of_scope=out_of_scope or [],
            severity_filter=severity_filter or ["critical", "high", "medium"],
            created_at=now,
            updated_at=now,
            **kwargs
        )
        self.targets[name] = target
        self.save_targets()
        return target

    def remove_target(self, name: str) -> bool:
        if name in self.targets:
            del self.targets[name]
            self.save_targets()
            return True
        return False

    def get_target(self, name: str) -> Optional[Target]:
        return self.targets.get(name)

    def list_targets(self) -> List[Dict[str, Any]]:
        return [asdict(t) for t in self.targets.values()]

    def is_in_scope(self, target_name: str, url_or_domain: str) -> tuple[bool, str]:
        """Check if a URL/domain is in scope for a target. Returns (in_scope, reason)."""
        target = self.targets.get(target_name)
        if not target:
            return False, "Target not found"
        if not target.enabled:
            return False, "Target is disabled"

        # Check out-of-scope first
        for pattern in target.out_of_scope:
            if self._match_wildcard(pattern, url_or_domain):
                return False, f"Matches out-of-scope pattern: {pattern}"

        # Check in-scope
        for pattern in target.scope:
            if self._match_wildcard(pattern, url_or_domain):
                return True, f"Matches in-scope pattern: {pattern}"

        return False, "Does not match any in-scope pattern"

    def _match_wildcard(self, pattern: str, value: str) -> bool:
        """Match a wildcard pattern against a value."""
        # Convert wildcard to regex
        regex = pattern.replace(".", r"\.")
        regex = regex.replace("*", ".*")
        regex = f"^{regex}$"
        return bool(re.match(regex, value, re.IGNORECASE))

    def get_scope_domains(self, target_name: str) -> List[str]:
        """Extract base domains from scope patterns."""
        target = self.targets.get(target_name)
        if not target:
            return []
        domains = []
        for pattern in target.scope:
            # Remove wildcards to get base domain
            domain = pattern.replace("*.", "").replace("*", "")
            if domain:
                domains.append(domain)
        return domains

    def validate_scope(self, target_name: str) -> Dict[str, Any]:
        """Validate a target's scope configuration."""
        target = self.targets.get(target_name)
        if not target:
            return {"valid": False, "errors": ["Target not found"]}

        errors = []
        warnings = []

        if not target.scope:
            errors.append("No scope defined")
        if not target.severity_filter:
            warnings.append("No severity filter set — will report all severities")
        if target.rate_limit_per_minute > 100:
            warnings.append(f"Rate limit ({target.rate_limit_per_minute}/min) is high — may trigger WAF")
        if target.max_concurrent_scans > 5:
            warnings.append(f"Concurrent scans ({target.max_concurrent_scans}) may overwhelm target")

        # Check for scope overlap
        for oos in target.out_of_scope:
            for ins in target.scope:
                if self._match_wildcard(ins, oos) or self._match_wildcard(oos, ins):
                    warnings.append(f"Scope overlap: {ins} vs {oos}")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }


# ─── Singleton ───────────────────────────────────────────────────────────────
_scope_manager_instance: Optional[ScopeManager] = None

def get_scope_manager() -> ScopeManager:
    global _scope_manager_instance
    if _scope_manager_instance is None:
        _scope_manager_instance = ScopeManager()
    return _scope_manager_instance

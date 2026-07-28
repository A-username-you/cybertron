#!/usr/bin/env python3
"""
Cybertron HackerOne Integration
================================
Full API wrapper for HackerOne bug bounty platform.

Features:
- Program discovery and metadata
- Scope synchronization
- Report submission (draft + published)
- Report status tracking
- Bounty/payment tracking
- Notification handling

API Docs: https://api.hackerone.com/
"""
import json
import os
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

try:
    import requests
except ImportError:
    requests = None

H1_API_BASE = "https://api.hackerone.com/v1"


@dataclass
class H1Program:
    handle: str
    name: str
    url: str
    offers_bounties: bool
    state: str
    submission_state: str
    currency: str
    scopes: List[Dict[str, Any]]


@dataclass
class H1Report:
    id: str
    title: str
    state: str
    severity: str
    bounty: float
    currency: str
    submitted_at: str
    program_handle: str


class HackerOneAPI:
    def __init__(self, api_key: Optional[str] = None, username: Optional[str] = None):
        self.api_key = api_key or os.environ.get("HACKERONE_API_KEY", "")
        self.username = username or os.environ.get("HACKERONE_USERNAME", "")
        self.session = requests.Session() if requests else None
        if self.session:
            self.session.auth = (self.username, self.api_key)
            self.session.headers.update({
                "Accept": "application/json",
                "Content-Type": "application/json",
            })

    def _request(self, method: str, endpoint: str, **kwargs) -> Optional[Dict[str, Any]]:
        if not self.session:
            raise RuntimeError("requests library not available")
        url = f"{H1_API_BASE}{endpoint}"
        try:
            resp = self.session.request(method, url, timeout=30, **kwargs)
            resp.raise_for_status()
            return resp.json()
        except requests.HTTPError as e:
            if e.response is not None:
                try:
                    err = e.response.json()
                    raise RuntimeError(f"HackerOne API error: {err}")
                except:
                    raise RuntimeError(f"HackerOne API error: {e.response.status_code}")
            raise
        except Exception as e:
            raise RuntimeError(f"Request failed: {e}")

    # ─── Programs ────────────────────────────────────────────────────────────
    def get_programs(self) -> List[Dict[str, Any]]:
        """List all programs the user has access to."""
        data = self._request("GET", "/me/programs")
        return data.get("data", []) if data else []

    def get_program(self, handle: str) -> Optional[H1Program]:
        """Get detailed info about a specific program."""
        data = self._request("GET", f"/programs/{handle}")
        if not data:
            return None
        attrs = data.get("attributes", {})
        rels = data.get("relationships", {})
        scopes_data = rels.get("structured_scopes", {}).get("data", [])
        return H1Program(
            handle=attrs.get("handle", handle),
            name=attrs.get("name", ""),
            url=attrs.get("url", ""),
            offers_bounties=attrs.get("offers_bounties", False),
            state=attrs.get("state", ""),
            submission_state=attrs.get("submission_state", ""),
            currency=attrs.get("currency", "USD"),
            scopes=scopes_data,
        )

    def get_program_scopes(self, handle: str) -> List[Dict[str, Any]]:
        """Get structured scopes for a program."""
        data = self._request("GET", f"/programs/{handle}/structured_scopes")
        return data.get("data", []) if data else []

    # ─── Reports ─────────────────────────────────────────────────────────────
    def submit_report(self, handle: str, title: str, vulnerability_types: List[str],
                      summary: str, severity: str, impact: str,
                      steps: List[str], attachments: List[str] = None) -> Dict[str, Any]:
        """Submit a vulnerability report to a program."""
        payload = {
            "data": {
                "type": "report",
                "attributes": {
                    "title": title,
                    "vulnerability_types": vulnerability_types,
                    "severity_rating": severity,
                    "bug_reproducibility": "always",
                },
                "relationships": {
                    "program": {
                        "data": {
                            "type": "program",
                            "id": handle,
                        }
                    }
                }
            }
        }

        # Submit initial report
        data = self._request("POST", "/reports", json=payload)
        report_id = data.get("data", {}).get("id") if data else None

        if report_id:
            # Add summary and steps as comments
            full_summary = f"## Summary\n\n{summary}\n\n## Impact\n\n{impact}\n\n## Steps to Reproduce\n\n" + "\n".join(f"{i+1}. {s}" for i, s in enumerate(steps))
            self._request("POST", f"/reports/{report_id}/activities", json={
                "data": {
                    "type": "activity-comment",
                    "attributes": {
                        "message": full_summary,
                        "internal": False,
                    }
                }
            })

        return data or {}

    def get_reports(self, state: Optional[str] = None) -> List[Dict[str, Any]]:
        """List reports. Optionally filter by state (new, triaged, resolved, etc.)."""
        params = {}
        if state:
            params["filter[state]"] = state
        data = self._request("GET", "/reports", params=params)
        return data.get("data", []) if data else []

    def get_report(self, report_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed info about a specific report."""
        data = self._request("GET", f"/reports/{report_id}")
        return data.get("data") if data else None

    # ─── Scope Sync ──────────────────────────────────────────────────────────
    def sync_scope_to_local(self, handle: str) -> Dict[str, Any]:
        """Sync HackerOne program scope to local scope manager."""
        from scope_manager import get_scope_manager

        program = self.get_program(handle)
        if not program:
            return {"success": False, "error": "Program not found"}

        scopes = self.get_program_scopes(handle)
        in_scope = []
        out_of_scope = []

        for scope in scopes:
            attrs = scope.get("attributes", {})
            asset = attrs.get("asset_identifier", "")
            if attrs.get("eligible_for_submission", False):
                in_scope.append(asset)
            else:
                out_of_scope.append(asset)

        sm = get_scope_manager()
        sm.add_target(
            name=program.name,
            platform="hackerone",
            handle=handle,
            scope=in_scope,
            out_of_scope=out_of_scope,
            offers_bounties=program.offers_bounties,
        )

        return {
            "success": True,
            "program": program.name,
            "in_scope_count": len(in_scope),
            "out_of_scope_count": len(out_of_scope),
        }

    # ─── Statistics ────────────────────────────────────────────────────────
    def get_stats(self) -> Dict[str, Any]:
        """Get bug bounty statistics."""
        reports = self.get_reports()
        stats = {
            "total_reports": len(reports),
            "by_state": {},
            "total_bounty": 0.0,
            "currency": "USD",
        }
        for r in reports:
            attrs = r.get("attributes", {})
            state = attrs.get("state", "unknown")
            stats["by_state"][state] = stats["by_state"].get(state, 0) + 1
            bounty = attrs.get("bounty_amount", 0)
            if bounty:
                stats["total_bounty"] += float(bounty)
        return stats


# ─── Singleton ───────────────────────────────────────────────────────────────
_h1_instance: Optional[HackerOneAPI] = None

def get_hackerone_api() -> HackerOneAPI:
    global _h1_instance
    if _h1_instance is None:
        _h1_instance = HackerOneAPI()
    return _h1_instance

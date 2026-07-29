#!/usr/bin/env python3
"""
Cybertron Webhook Notifier
==========================
POST findings to SIEM, Slack, Discord, or any custom endpoint.

Configuration via ~/.cybertron/webhooks.json:
{
  "webhooks": [
    {
      "name": "slack-alerts",
      "url": "https://hooks.slack.com/services/...",
      "events": ["tool_executed", "session_completed", "finding"],
      "headers": {"Content-Type": "application/json"},
      "enabled": true
    }
  ]
}
"""
import json
import os
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict

try:
    import requests
except ImportError:
    requests = None

WEBHOOK_CONFIG_PATH = Path.home() / ".cybertron" / "webhooks.json"


@dataclass
class WebhookConfig:
    name: str
    url: str
    events: List[str]
    headers: Dict[str, str]
    enabled: bool = True
    timeout: int = 10


class WebhookNotifier:
    def __init__(self):
        self.webhooks: List[WebhookConfig] = []
        self._load_config()

    def _load_config(self):
        if WEBHOOK_CONFIG_PATH.exists():
            try:
                data = json.loads(WEBHOOK_CONFIG_PATH.read_text())
                for wh in data.get("webhooks", []):
                    self.webhooks.append(WebhookConfig(**wh))
            except Exception:
                pass

    def save_config(self):
        data = {"webhooks": [asdict(wh) for wh in self.webhooks]}
        WEBHOOK_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        WEBHOOK_CONFIG_PATH.write_text(json.dumps(data, indent=2))

    def add_webhook(self, name: str, url: str, events: List[str],
                    headers: Optional[Dict[str, str]] = None):
        wh = WebhookConfig(
            name=name, url=url, events=events,
            headers=headers or {"Content-Type": "application/json"},
        )
        self.webhooks.append(wh)
        self.save_config()

    def remove_webhook(self, name: str) -> bool:
        original = len(self.webhooks)
        self.webhooks = [wh for wh in self.webhooks if wh.name != name]
        if len(self.webhooks) < original:
            self.save_config()
            return True
        return False

    def notify(self, event_type: str, payload: Dict[str, Any]):
        if requests is None:
            return
        for wh in self.webhooks:
            if not wh.enabled:
                continue
            if event_type not in wh.events and "*" not in wh.events:
                continue
            try:
                body = {
                    "event": event_type,
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "payload": payload,
                }
                requests.post(wh.url, json=body, headers=wh.headers, timeout=wh.timeout)
            except Exception:
                pass  # Silently fail — webhooks are best-effort

    def notify_tool_executed(self, session_id: str, tool_id: str, ok: bool,
                             output: str = "", error: str = ""):
        self.notify("tool_executed", {
            "session_id": session_id,
            "tool_id": tool_id,
            "success": ok,
            "output_preview": output[:500],
            "error_preview": error[:500],
        })

    def notify_session_completed(self, session_id: str, goal: str,
                                 tool_calls: int, findings: List[str]):
        self.notify("session_completed", {
            "session_id": session_id,
            "goal": goal,
            "tool_calls": tool_calls,
            "findings": findings,
        })

    def notify_finding(self, session_id: str, severity: str, title: str,
                       description: str, target: str = ""):
        self.notify("finding", {
            "session_id": session_id,
            "severity": severity,
            "title": title,
            "description": description,
            "target": target,
        })

    def list_webhooks(self) -> List[Dict[str, Any]]:
        return [asdict(wh) for wh in self.webhooks]


# ─── Singleton ───────────────────────────────────────────────────────────────
_notifier_instance: Optional[WebhookNotifier] = None

def get_notifier() -> WebhookNotifier:
    global _notifier_instance
    if _notifier_instance is None:
        _notifier_instance = WebhookNotifier()
    return _notifier_instance

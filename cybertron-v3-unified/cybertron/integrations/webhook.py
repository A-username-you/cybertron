"""Webhook Notifier."""
import httpx
from typing import Optional
from cybertron.core.config import CybertronConfig


class WebhookNotifier:
    """Send notifications to Slack, Discord, or custom webhooks."""

    def __init__(self, config: Optional[CybertronConfig] = None):
        self.config = config or CybertronConfig.load()

    def notify(self, message: str, channel: str = "slack") -> dict:
        url = getattr(self.config, f"{channel}_webhook", "")
        if not url:
            return {"error": f"No webhook configured for {channel}"}
        payload = {"text": message}
        if channel == "discord":
            payload = {"content": message}
        try:
            r = httpx.post(url, json=payload, timeout=10)
            return {"status": r.status_code, "response": r.text}
        except Exception as e:
            return {"error": str(e)}

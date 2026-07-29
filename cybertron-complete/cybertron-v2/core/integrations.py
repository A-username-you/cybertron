#!/usr/bin/env python3
"""
Cybertron Integrations — Webhooks, Slack, generic HTTP callbacks.
"""
import json
import requests
from typing import Optional

def send_webhook(url: str, payload: dict, timeout: int = 10) -> bool:
    """Send a generic webhook POST."""
    if not url:
        return False
    try:
        resp = requests.post(url, json=payload, timeout=timeout)
        return resp.status_code < 400
    except Exception:
        return False

def send_slack(webhook_url: str, text: str, session_id: Optional[str] = None) -> bool:
    """Send a Slack message via incoming webhook."""
    if not webhook_url:
        return False
    payload = {
        "text": text,
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "Cybertron Alert", "emoji": True}
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Session:*\n`{session_id or 'N/A'}`"},
                    {"type": "mrkdwn", "text": f"*Status:*\n{text[:100]}"},
                ]
            }
        ]
    }
    return send_webhook(webhook_url, payload)

def notify_session_complete(
    webhook_url: str,
    slack_url: str,
    session_id: str,
    goal: str,
    state: str,
    findings: list,
    elapsed_ms: int,
):
    """Notify all configured channels that a session completed."""
    summary = f"Session {session_id[:8]} completed: {state}\nGoal: {goal}\nFindings: {len(findings)}\nElapsed: {elapsed_ms}ms"

    if webhook_url:
        send_webhook(webhook_url, {
            "event": "session_complete",
            "session_id": session_id,
            "goal": goal,
            "state": state,
            "findings_count": len(findings),
            "elapsed_ms": elapsed_ms,
        })

    if slack_url:
        send_slack(slack_url, summary, session_id)

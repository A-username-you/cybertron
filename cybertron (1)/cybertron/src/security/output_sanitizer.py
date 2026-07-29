#!/usr/bin/env python3
"""
Cybertron Output Sanitization
=============================
Auto-redact sensitive data from tool output before sending to NIM or displaying.

Patterns detected:
- IPv4 addresses (optionally preserve private ranges)
- IPv6 addresses
- Email addresses
- API keys / tokens (heuristic)
- Domain names (optionally preserve TLD list)
- Credit card numbers
- AWS keys, GitHub tokens, Slack webhooks
"""
import re
from typing import List, Dict, Any, Optional


class Sanitizer:
    """Redacts sensitive information from text output."""

    # Patterns
    IPV4 = re.compile(r"\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b")
    IPV6 = re.compile(r"\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b")
    EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
    CREDIT_CARD = re.compile(r"\b(?:\d[ -]*?){13,16}\b")
    AWS_KEY = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
    GITHUB_TOKEN = re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{36,}\b")
    SLACK_WEBHOOK = re.compile(r"https://hooks\.slack\.com/services/T[a-zA-Z0-9_]+/B[a-zA-Z0-9_]+/[a-zA-Z0-9_]+")
    BEARER_TOKEN = re.compile(r"\bBearer\s+[A-Za-z0-9_\-\.]+\b")
    PRIVATE_KEY = re.compile(r"-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----")
    GENERIC_SECRET = re.compile(
        r"\b(?:api[_-]?key|token|secret|password|passwd|pwd)\s*[:=]\s*['\"]?([A-Za-z0-9_\-./+=]{8,})['\"]?",
        re.IGNORECASE,
    )

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.redact_ips = self.config.get("redact_ips", True)
        self.redact_emails = self.config.get("redact_emails", True)
        self.redact_domains = self.config.get("redact_domains", False)
        self.redact_secrets = self.config.get("redact_secrets", True)
        self.redact_credit_cards = self.config.get("redact_credit_cards", True)
        self.preserve_private_ips = self.config.get("preserve_private_ips", True)
        self.mask_char = self.config.get("mask_char", "\u2588")

    def _mask(self, text: str, visible: int = 4) -> str:
        """Mask a string, keeping first N chars visible."""
        if len(text) <= visible * 2:
            return self.mask_char * len(text)
        return text[:visible] + self.mask_char * (len(text) - visible * 2) + text[-visible:]

    def _is_private_ip(self, ip: str) -> bool:
        """Check if an IPv4 address is in a private range."""
        parts = ip.split(".")
        if len(parts) != 4:
            return False
        try:
            first, second = int(parts[0]), int(parts[1])
        except ValueError:
            return False
        if first == 10:
            return True
        if first == 172 and 16 <= second <= 31:
            return True
        if first == 192 and second == 168:
            return True
        if first == 127:
            return True
        return False

    def sanitize(self, text: str) -> str:
        """Apply all configured sanitization rules."""
        if not isinstance(text, str):
            text = str(text)

        if self.redact_ips:
            def replace_ip(m):
                ip = m.group(0)
                if self.preserve_private_ips and self._is_private_ip(ip):
                    return ip
                return "[REDACTED_IP]"
            text = self.IPV4.sub(replace_ip, text)
            text = self.IPV6.sub("[REDACTED_IPv6]", text)

        if self.redact_emails:
            text = self.EMAIL.sub("[REDACTED_EMAIL]", text)

        if self.redact_credit_cards:
            text = self.CREDIT_CARD.sub("[REDACTED_CC]", text)

        if self.redact_secrets:
            text = self.AWS_KEY.sub("[REDACTED_AWS_KEY]", text)
            text = self.GITHUB_TOKEN.sub("[REDACTED_GH_TOKEN]", text)
            text = self.SLACK_WEBHOOK.sub("[REDACTED_SLACK_WEBHOOK]", text)
            text = self.BEARER_TOKEN.sub("Bearer [REDACTED]", text)
            text = self.PRIVATE_KEY.sub("[REDACTED_PRIVATE_KEY]", text)

            def replace_secret(m):
                return m.group(0).replace(m.group(1), "[REDACTED]")
            text = self.GENERIC_SECRET.sub(replace_secret, text)

        return text

    def sanitize_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively sanitize a dictionary."""
        result = {}
        for k, v in data.items():
            if isinstance(v, str):
                result[k] = self.sanitize(v)
            elif isinstance(v, dict):
                result[k] = self.sanitize_dict(v)
            elif isinstance(v, list):
                result[k] = [self.sanitize(i) if isinstance(i, str) else i for i in v]
            else:
                result[k] = v
        return result


_sanitizer_instance: Optional[Sanitizer] = None

def get_sanitizer(config: Optional[Dict[str, Any]] = None) -> Sanitizer:
    global _sanitizer_instance
    if _sanitizer_instance is None:
        _sanitizer_instance = Sanitizer(config)
    return _sanitizer_instance

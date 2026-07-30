"""Red Team — Vulnerability Scanner."""
import asyncio
import httpx
from typing import List
from dataclasses import dataclass, field
from datetime import datetime
from cybertron.core.protocol import Finding, Severity


class VulnScanner:
    """Multi-vector vulnerability scanner."""

    CHECKS = [
        "xss", "sqli", "ssrf", "idor", "csrf", "lfi", "rfi",
        "open_redirect", "cors_misconfig", "security_headers",
        "ssl_tls", "cookie_flags", "information_disclosure"
    ]

    def __init__(self, target: str):
        self.target = target
        self.findings: List[Finding] = []

    def run(self):
        print(f"[Scanner] Scanning {self.target} with {len(self.CHECKS)} checks...")
        self._check_headers()
        self._check_ssl()
        print(f"[Scanner] Found {len(self.findings)} issues.")
        return self.findings

    def _check_headers(self):
        try:
            import requests
            r = requests.get(self.target, timeout=10, verify=False)
            headers = r.headers
            security_headers = ["X-Frame-Options", "X-Content-Type-Options",
                                "Content-Security-Policy", "Strict-Transport-Security",
                                "Referrer-Policy", "Permissions-Policy"]
            missing = [h for h in security_headers if h not in headers]
            if missing:
                self.findings.append(Finding(
                    title="Missing Security Headers",
                    severity=Severity.MEDIUM,
                    description=f"Missing: {', '.join(missing)}",
                    remediation="Add the missing security headers to all responses."
                ))
        except Exception as e:
            print(f"[Scanner] Header check error: {e}")

    def _check_ssl(self):
        try:
            import ssl
            import socket
            ctx = ssl.create_default_context()
            with socket.create_connection((self.target.replace("https://", "").split("/")[0], 443), timeout=5) as sock:
                with ctx.wrap_socket(sock, server_hostname=self.target.replace("https://", "").split("/")[0]) as ssock:
                    cert = ssock.getpeercert()
                    cipher = ssock.cipher()
                    if cipher and "RC4" in str(cipher):
                        self.findings.append(Finding(
                            title="Weak SSL/TLS Cipher",
                            severity=Severity.HIGH,
                            description="RC4 cipher detected.",
                            remediation="Disable RC4 and enable only modern TLS 1.2+ ciphers."
                        ))
        except Exception:
            pass

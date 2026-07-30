"""Output Sanitizer."""
import re


class OutputSanitizer:
    """Sanitize tool output to prevent injection."""

    PATTERNS = {
        "api_key": re.compile(r'[a-zA-Z0-9_-]{32,64}'),
        "password": re.compile(r'password[=:]\s*\S+', re.I),
        "token": re.compile(r'token[=:]\s*\S+', re.I),
        "secret": re.compile(r'secret[=:]\s*\S+', re.I),
        "email": re.compile(r'[\w.-]+@[\w.-]+\.\w+'),
        "ip": re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b'),
    }

    @classmethod
    def sanitize(cls, text: str, mask: bool = True) -> str:
        if not mask:
            return text
        for name, pattern in cls.PATTERNS.items():
            text = pattern.sub(f"[REDACTED_{name.upper()}]", text)
        return text

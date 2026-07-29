"""Output Sanitizer"""
import re
from typing import Dict, Any, List


class OutputSanitizer:
    SENSITIVE_PATTERNS = [
        (re.compile(r"password[\s]*=[\s]*([^\s]+)", re.I), "[REDACTED_PASSWORD]"),
        (re.compile(r"api[_-]?key[\s]*=[\s]*([^\s]+)", re.I), "[REDACTED_API_KEY]"),
        (re.compile(r"secret[\s]*=[\s]*([^\s]+)", re.I), "[REDACTED_SECRET]"),
        (re.compile(r"token[\s]*=[\s]*([^\s]+)", re.I), "[REDACTED_TOKEN]"),
        (re.compile(r"AKIA[0-9A-Z]{16}"), "[REDACTED_AWS_KEY]"),
    ]

    def sanitize_string(self, text: str) -> str:
        for pattern, replacement in self.SENSITIVE_PATTERNS:
            text = pattern.sub(replacement, text)
        return text

    def sanitize_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        result = {}
        for key, value in data.items():
            if isinstance(value, str):
                result[key] = self.sanitize_string(value)
            elif isinstance(value, dict):
                result[key] = self.sanitize_dict(value)
            elif isinstance(value, list):
                result[key] = self.sanitize_list(value)
            else:
                result[key] = value
        return result

    def sanitize_list(self, data: List[Any]) -> List[Any]:
        result = []
        for item in data:
            if isinstance(item, str):
                result.append(self.sanitize_string(item))
            elif isinstance(item, dict):
                result.append(self.sanitize_dict(item))
            elif isinstance(item, list):
                result.append(self.sanitize_list(item))
            else:
                result.append(item)
        return result

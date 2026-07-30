"""HackerOne Integration."""
import httpx
from typing import Optional, List
from cybertron.core.config import CybertronConfig


class HackerOneIntegration:
    """Submit reports to HackerOne."""

    BASE_URL = "https://api.hackerone.com/v1"

    def __init__(self, config: Optional[CybertronConfig] = None):
        self.config = config or CybertronConfig.load()
        self.token = self.config.hackerone_token

    def submit_report(self, program: str, title: str, summary: str,
                      severity: str = "medium", impact: str = "") -> dict:
        if not self.token:
            return {"error": "HackerOne token not configured"}
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        payload = {
            "data": {
                "type": "report",
                "attributes": {
                    "title": title,
                    "vulnerability_information": summary,
                    "severity_rating": severity,
                    "impact": impact
                }
            }
        }
        try:
            r = httpx.post(f"{self.BASE_URL}/reports", headers=headers, json=payload, timeout=30)
            return r.json()
        except Exception as e:
            return {"error": str(e)}

    def get_programs(self) -> List[dict]:
        if not self.token:
            return []
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            r = httpx.get(f"{self.BASE_URL}/me/programs", headers=headers, timeout=30)
            return r.json().get("data", [])
        except Exception:
            return []

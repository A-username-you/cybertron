"""HackerOne Integration"""
from typing import Dict, List
import structlog
import httpx
from cybertron.core import PluginInterface, TaskResult, TaskStatus, Finding, Severity

logger = structlog.get_logger()


class HackerOneIntegration(PluginInterface):
    name = "hackerone"
    version = "2.0.0"
    description = "HackerOne API integration"
    BASE_URL = "https://api.hackerone.com/v1"

    async def execute(self, target: str, options: Dict) -> TaskResult:
        action = options.get("action", "list_programs")
        api_username = options.get("api_username", "")
        api_token = options.get("api_token", "")

        if not api_username or not api_token:
            return TaskResult(
                task_id=__import__("uuid").uuid4().hex,
                status=TaskStatus.FAILED,
                error="HackerOne API credentials required"
            )

        auth = httpx.BasicAuth(api_username, api_token)
        findings = []

        async with httpx.AsyncClient(auth=auth, timeout=30) as client:
            if action == "list_programs":
                resp = await client.get(f"{self.BASE_URL}/hackers/programs")
                if resp.status_code == 200:
                    data = resp.json()
                    for prog in data.get("data", []):
                        findings.append(Finding(
                            title=f"Program: {prog.get('attributes', {}).get('name')}",
                            description=prog.get("attributes", {}).get("submission_state", ""),
                            severity=Severity.INFO,
                            category="platform",
                            target=prog.get("attributes", {}).get("handle", "")
                        ))

        return TaskResult(
            task_id=__import__("uuid").uuid4().hex,
            status=TaskStatus.SUCCESS,
            findings=findings
        )

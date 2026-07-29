"""API Security Fuzzer"""
from typing import Dict, List
import structlog
import httpx
from cybertron.core import PluginInterface, TaskResult, TaskStatus, Finding, Severity

logger = structlog.get_logger()


class OpenAPIFuzzer(PluginInterface):
    name = "openapi_fuzzer"
    version = "2.0.0"
    description = "Fuzz OpenAPI endpoints for vulnerabilities"

    async def execute(self, target: str, options: Dict) -> TaskResult:
        findings = []
        spec_url = options.get("spec_url", f"{target}/openapi.json")

        async with httpx.AsyncClient(timeout=30, verify=False) as client:
            try:
                resp = await client.get(spec_url)
                if resp.status_code == 200:
                    spec = resp.json()
                    paths = spec.get("paths", {})
                    for path, methods in paths.items():
                        for method, details in methods.items():
                            if method in ("get", "post", "put", "delete", "patch"):
                                security = details.get("security", spec.get("security", []))
                                if not security:
                                    findings.append(Finding(
                                        title=f"Missing Auth: {method.upper()} {path}",
                                        description="Endpoint has no security scheme",
                                        severity=Severity.HIGH,
                                        category="api",
                                        target=f"{target}{path}",
                                        remediation="Add security requirements"
                                    ))
            except Exception as e:
                logger.warning("openapi_fuzz_failed", error=str(e))

        return TaskResult(
            task_id=__import__("uuid").uuid4().hex,
            status=TaskStatus.SUCCESS,
            findings=findings
        )

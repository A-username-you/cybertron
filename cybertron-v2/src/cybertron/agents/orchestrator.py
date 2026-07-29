"""Cybertron Agent Orchestrator"""
import asyncio
from typing import Dict, List
from dataclasses import dataclass
from datetime import datetime
import structlog

from cybertron.core import ExecutionEngine, Finding, TaskResult, Severity


logger = structlog.get_logger()


@dataclass
class Engagement:
    id: str
    name: str
    target: str
    scope_file: str
    start_time: datetime
    status: str = "active"
    findings: List[Finding] = None

    def __post_init__(self):
        if self.findings is None:
            self.findings = []


class CybertronOrchestrator:
    def __init__(self, engine: ExecutionEngine):
        self.engine = engine
        self.engagements: Dict[str, Engagement] = {}
        self.logger = structlog.get_logger(orchestrator="main")

    async def start_engagement(self, name: str, target: str, scope_file: str) -> Engagement:
        import uuid
        eng = Engagement(
            id=uuid.uuid4().hex[:12],
            name=name,
            target=target,
            scope_file=scope_file,
            start_time=datetime.utcnow()
        )
        self.engagements[eng.id] = eng
        self.engine.scope.load_scope(scope_file)
        self.logger.info("engagement_started", id=eng.id, target=target)
        return eng

    async def run_bug_bounty_pipeline(self, engagement_id: str, target: str) -> List[TaskResult]:
        pipeline = [
            {"plugin": "subdomain_enum", "options": {"wordlist": "wordlists/subdomains.txt"}},
            {"plugin": "port_scan", "options": {"top_ports": 1000}, "condition": "has_findings"},
        ]
        results = await self.engine.execute_pipeline(pipeline, target)
        eng = self.engagements[engagement_id]
        for r in results:
            eng.findings.extend(r.findings)
        return results

    def get_findings(self, engagement_id: str, min_severity: Severity = Severity.LOW) -> List[Finding]:
        eng = self.engagements.get(engagement_id)
        if not eng:
            return []
        severity_order = [Severity.INFO, Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]
        min_idx = severity_order.index(min_severity)
        return [f for f in eng.findings if severity_order.index(f.severity) >= min_idx]

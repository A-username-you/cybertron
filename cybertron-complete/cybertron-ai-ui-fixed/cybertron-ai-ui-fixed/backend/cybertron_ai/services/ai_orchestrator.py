"""AI Orchestrator."""
import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import structlog
from cybertron.core import ExecutionEngine, TaskResult
from cybertron_ai.services.llm_client import LLMClient
from cybertron_ai.services.memory_store import MemoryStore
logger = structlog.get_logger()
@dataclass
class AgentIntent:
    intent: str; target: str; plugins: List[str]; options: Dict[str,Any]; reasoning: str
class AIOrchestrator:
    SYSTEM_PROMPT = """You are Cybertron AI, a security automation orchestrator.
Available plugins:
- subdomain_enum: DNS brute force subdomain discovery
- port_scan: Async TCP port scanner
- aws_misconfig: AWS security posture scanner
- docker_audit: Container security auditor
- openapi_fuzz: OpenAPI endpoint fuzzer
- apk_static: Android APK static analyzer
- pcap_parser: Network capture credential extractor

Rules:
1. Validate targets are in scope
2. Chain reconnaissance before exploitation
3. Provide clear reasoning

Respond ONLY with valid JSON:
{"intent":"scan|audit|analyze|engage","target":"domain","plugins":["plugin_name"],"options":{},"reasoning":"..."}"""
    def __init__(self, engine: ExecutionEngine, llm: LLMClient, memory: MemoryStore):
        self.engine = engine; self.llm = llm; self.memory = memory
        self.logger = structlog.get_logger(ai_orchestrator=True)
    async def parse_intent(self, user_message: str, context: Dict[str,Any]) -> AgentIntent:
        history = await self.memory.get_recent(context.get("session_id","default"), limit=5)
        messages = [{"role":"system","content":self.SYSTEM_PROMPT}] + [{"role":m["role"],"content":m["content"]} for m in history] + [{"role":"user","content":user_message}]
        response = await self.llm.chat_completion(messages, temperature=0.2)
        try: parsed = json.loads(response); return AgentIntent(**parsed)
        except json.JSONDecodeError:
            self.logger.error("intent_parse_failed", raw=response)
            return self._fallback_intent(user_message)
    def _fallback_intent(self, message: str) -> AgentIntent:
        msg = message.lower(); plugins = []
        if "subdomain" in msg or "domain" in msg: plugins.append("subdomain_enum")
        if "port" in msg: plugins.append("port_scan")
        if "aws" in msg or "cloud" in msg: plugins.append("aws_misconfig")
        if "api" in msg or "openapi" in msg: plugins.append("openapi_fuzz")
        if not plugins: plugins = ["subdomain_enum","port_scan"]
        return AgentIntent(intent="scan", target=self._extract_target(msg) or "example.com", plugins=plugins, options={}, reasoning="Fallback keyword extraction")
    def _extract_target(self, message: str) -> Optional[str]:
        import re
        domains = re.findall(r'(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}', message)
        ips = re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', message)
        return domains[0] if domains else (ips[0] if ips else None)
    async def execute_intent(self, intent: AgentIntent, engagement_id: Optional[str]=None) -> List[TaskResult]:
        self.logger.info("executing_intent", intent=intent.intent, target=intent.target, plugins=intent.plugins)
        pipeline = [{"plugin":p, "options":intent.options.get(p,{}), "condition":"has_findings" if i>0 else None} for i,p in enumerate(intent.plugins)]
        return await self.engine.execute_pipeline(pipeline, intent.target)
    async def analyze_findings(self, findings: List[Any]) -> Dict[str,Any]:
        if not findings: return {"summary":"No findings.","risk_score":0,"recommendations":[]}
        findings_text = "\n".join([f"- [{f.severity.value}] {f.title}: {f.description}" for f in findings[:20]])
        prompt = f"""Analyze these findings:
1. Executive summary (2-3 sentences)
2. Risk score (0-100)
3. Top 3 remediation steps

Findings:
{findings_text}

Respond as JSON: {{"summary":"...","risk_score":N,"recommendations":["..."]}}"""
        response = await self.llm.chat_completion([{"role":"system","content":"Senior security analyst."},{"role":"user","content":prompt}], temperature=0.3)
        try: return json.loads(response)
        except: return {"summary":response[:500],"risk_score":50,"recommendations":["Review manually"]}

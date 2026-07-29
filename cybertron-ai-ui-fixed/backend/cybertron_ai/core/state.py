"""Application state."""
from typing import Optional
from cybertron.core import ExecutionEngine
from cybertron.agents import CybertronOrchestrator
from cybertron_ai.services.llm_client import LLMClient
from cybertron_ai.services.ai_orchestrator import AIOrchestrator
from cybertron_ai.services.memory_store import MemoryStore

class AppState:
    def __init__(self):
        self.engine: Optional[ExecutionEngine] = None
        self.orchestrator: Optional[CybertronOrchestrator] = None
        self.llm: Optional[LLMClient] = None
        self.ai_orchestrator: Optional[AIOrchestrator] = None
        self.memory: Optional[MemoryStore] = None
        self._initialized = False
    async def initialize(self) -> None:
        if self._initialized: return
        self.engine = ExecutionEngine(max_workers=20)
        self.engine.registry.discover("cybertron.plugins")
        self.orchestrator = CybertronOrchestrator(self.engine)
        self.llm = LLMClient()
        self.memory = MemoryStore()
        self.ai_orchestrator = AIOrchestrator(engine=self.engine, llm=self.llm, memory=self.memory)
        self._initialized = True
    async def shutdown(self) -> None:
        if self.engine: await self.engine.shutdown()

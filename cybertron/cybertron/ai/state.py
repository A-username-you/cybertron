"""Application state unifying agent runtime + AI backend."""
from typing import Optional
from cybertron.ai.llm_client import LLMClient
from cybertron.ai.orchestrator import AIOrchestrator
from cybertron.ai.memory_store import MemoryStore
from cybertron.ai.websocket_manager import ConnectionManager


class AppState:
    def __init__(self):
        self.llm: Optional[LLMClient] = None
        self.ai_orchestrator: Optional[AIOrchestrator] = None
        self.memory: Optional[MemoryStore] = None
        self.ws_manager: Optional[ConnectionManager] = None
        self._initialized = False

    async def initialize(self) -> None:
        if self._initialized:
            return
        self.llm = LLMClient()
        self.memory = MemoryStore()
        self.ai_orchestrator = AIOrchestrator(llm=self.llm, memory=self.memory)
        self.ws_manager = ConnectionManager()
        self._initialized = True

    async def shutdown(self) -> None:
        pass

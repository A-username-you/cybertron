"""Cybertron execution engine."""
import asyncio
import time
from typing import Callable, List, Optional
from dataclasses import dataclass, field
from cybertron.core.protocol import AgentState, AgentMessage, ScanResult, Finding
from cybertron.core.config import CybertronConfig


class CybertronEngine:
    """Central execution engine for all operations."""

    def __init__(self, config: Optional[CybertronConfig] = None):
        self.config = config or CybertronConfig.load()
        self.state = AgentState.IDLE
        self._listeners: List[Callable] = []
        self._history: List[AgentMessage] = []
        self._results: List[ScanResult] = []

    def on_state_change(self, callback: Callable):
        self._listeners.append(callback)

    def _emit(self, state: AgentState, content: str = "", metadata: dict = None):
        self.state = state
        msg = AgentMessage(state=state, content=content, metadata=metadata or {})
        self._history.append(msg)
        for cb in self._listeners:
            try:
                cb(msg)
            except Exception:
                pass

    async def run_module(self, name: str, coro, *args, **kwargs):
        self._emit(AgentState.THINKING, f"Initializing {name}...")
        start = time.time()
        try:
            result = await coro(*args, **kwargs)
            self._emit(AgentState.RESULT, f"{name} completed.", {"result": result})
            return result
        except Exception as e:
            self._emit(AgentState.ERROR, str(e))
            raise
        finally:
            elapsed = int((time.time() - start) * 1000)
            self._emit(AgentState.IDLE, f"{name} finished in {elapsed}ms")

    def get_history(self) -> List[AgentMessage]:
        return self._history.copy()

    def get_results(self) -> List[ScanResult]:
        return self._results.copy()

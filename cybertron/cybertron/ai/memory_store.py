"""Memory store."""
from typing import Dict, List, Any

class MemoryStore:
    def __init__(self):
        self._data: Dict[str, List[Dict[str, Any]]] = {}

    async def add(self, session_id: str, role: str, content: str, meta: Dict[str, Any] = None):
        if session_id not in self._data:
            self._data[session_id] = []
        self._data[session_id].append({"role": role, "content": content, "meta": meta or {}})

    async def get_recent(self, session_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        return self._data.get(session_id, [])[-limit:]

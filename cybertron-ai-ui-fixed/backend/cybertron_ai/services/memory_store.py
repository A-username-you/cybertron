"""Memory store."""
import time
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
@dataclass
class MemoryEntry:
    role: str; content: str; timestamp: float; metadata: Dict[str,Any]
class MemoryStore:
    def __init__(self, db_path: Optional[str]=None):
        self._store: Dict[str,List[MemoryEntry]] = {}; self.db_path = db_path
    async def add(self, session_id: str, role: str, content: str, metadata: Dict[str,Any]=None):
        entry = MemoryEntry(role=role, content=content, timestamp=time.time(), metadata=metadata or {})
        if session_id not in self._store: self._store[session_id] = []
        self._store[session_id].append(entry)
        self._store[session_id] = self._store[session_id][-100:]
    async def get_recent(self, session_id: str, limit: int=10) -> List[Dict[str,Any]]:
        entries = self._store.get(session_id, [])
        return [{"role":e.role,"content":e.content,"timestamp":e.timestamp,**e.metadata} for e in entries[-limit:]]

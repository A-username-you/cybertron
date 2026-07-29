"""
Cybertron Python UI — Protocol definitions matching the Node.js runtime exactly.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum

class AgentState(str, Enum):
    IDLE = "idle"
    THINKING = "thinking"
    RUNNING_TOOL = "running_tool"
    AWAITING_APPROVAL = "awaiting_approval"
    DONE = "done"
    ERROR = "error"

GATEWAY_HOST = "127.0.0.1"
GATEWAY_PORT = 8765

@dataclass
class SessionSummary:
    id: str
    goal: str
    state: str
    startedAt: int
    finishedAt: Optional[int] = None
    toolCallCount: int = 0
    lastToolId: Optional[str] = None
    origin: Optional[str] = None

@dataclass
class ToolCatalogEntry:
    id: str
    label: str
    category: str
    autoApprove: bool
    implemented: bool

@dataclass
class PendingApproval:
    sessionId: str
    requestId: str
    toolId: str
    args: Dict[str, Any]

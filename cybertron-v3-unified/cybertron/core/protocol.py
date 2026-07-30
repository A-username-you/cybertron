"""Inter-module communication protocol."""
from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime


class AgentState(str, Enum):
    IDLE = "idle"
    THINKING = "thinking"
    WRITING = "writing"
    RESULT = "result"
    ERROR = "error"
    WAITING_APPROVAL = "waiting_approval"


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class Finding:
    title: str
    severity: Severity
    description: str
    evidence: str = ""
    remediation: str = ""
    cwe: str = ""
    cvss: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ScanResult:
    target: str
    module: str
    findings: List[Finding] = field(default_factory=list)
    raw_output: str = ""
    duration_ms: int = 0
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class AgentMessage:
    state: AgentState
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)

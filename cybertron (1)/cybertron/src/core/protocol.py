"""
Cybertron Python UI — Protocol definitions matching the Node.js runtime exactly.
Extended with GitHub Tool Loader message types.
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


class MessageType(str, Enum):
    # Auth & Session
    AUTH = "auth"
    AUTH_RESULT = "auth_result"
    SESSION_START = "session_start"
    SESSION_STARTED = "session_started"
    # Agent lifecycle
    AGENT_STATUS = "agent_status"
    # Tool execution
    TOOL_CALL_REQUEST = "tool_call_request"
    TOOL_CALL_APPROVAL = "tool_call_approval"
    TOOL_CALL_RESULT = "tool_call_result"
    # Server state
    SESSIONS_SNAPSHOT = "sessions_snapshot"
    LIST_SESSIONS = "list_sessions"
    # Tool catalog
    GET_TOOLS = "get_tools"
    TOOLS_CATALOG = "tools_catalog"
    # Config
    CONFIG_STATE = "config_state"
    # ── GitHub Tool Loader ──────────────────────────────────────────────────
    REGISTER_GITHUB_TOOL = "register_github_tool"
    GITHUB_TOOL_STATUS = "github_tool_status"
    REMOVE_TOOL = "remove_tool"
    GET_MARKETPLACE = "get_marketplace"
    MARKETPLACE_CATALOG = "marketplace_catalog"
    # ── Streaming / Intelligence ───────────────────────────────────────────
    STREAM_TOKEN = "stream_token"
    AGENT_PLAN = "agent_plan"
    # ── Control Center ────────────────────────────────────────────────────
    GET_CONFIG = "get_config"
    SET_CONFIG = "set_config"
    CONFIG_UPDATED = "config_updated"
    # ── Dry Run ────────────────────────────────────────────────────────────
    DRY_RUN = "dry_run"
    DRY_RUN_RESULT = "dry_run_result"


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


@dataclass
class GitHubToolSpec:
    id: str
    repo: str
    label: str
    category: str
    binary_name: str
    binary_path: str
    version: str
    auto_approve: bool = False
    handler: str = "github"
    installed_at: str = ""
    last_updated: str = ""
    schema: Dict[str, Any] = field(default_factory=dict)

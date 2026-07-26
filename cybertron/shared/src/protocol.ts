/**
 * Shared wire protocol between the runtime gateway (runtime/src/server.ts),
 * the Electron preload bridge (electron/preload.ts), and the UI (app/, cli).
 *
 * This is the one file every side imports from, so the contract can't drift.
 */

export type ToolCategory = "recon" | "crawl" | "scan" | "secrets" | "defense" | "exploit";
// "defense" = blue-team tooling (detection/response). "exploit" = red-team
// verification steps, hard-gated behind human approval regardless of team.

export interface ToolDefinition {
  id: string;
  category: ToolCategory;
  label: string;
  /** true = runs immediately when the agent calls it; false = needs explicit human approval first */
  autoApprove: boolean;
  implemented: boolean;
}

export interface ToolCallRequest {
  type: "tool_call_request";
  sessionId: string;
  requestId: string;
  toolId: string;
  args: Record<string, string>;
}

export interface ToolCallApproval {
  type: "tool_call_approval";
  sessionId: string;
  requestId: string;
  approved: boolean;
}

export interface ToolCallResult {
  type: "tool_call_result";
  sessionId: string;
  requestId: string;
  toolId: string;
  ok: boolean;
  output: string;
  error?: string;
  durationMs: number;
}

export type AgentState = "idle" | "thinking" | "awaiting_approval" | "running_tool" | "done" | "error";

export type SessionOrigin = "web" | "cli";

export interface AgentStatusEvent {
  type: "agent_status";
  sessionId: string;
  state: AgentState;
  detail?: string;
  /** cumulative tokens used by this session so far, if the model returned usage data */
  tokensUsed?: number;
  /** the model's context window, passed through so the client never has to hardcode it */
  contextWindow?: number;
}

export interface AgentSessionStart {
  type: "session_start";
  /** client-generated id, so a session can be tracked before the server acks it */
  sessionId: string;
  goal: string;
  origin: SessionOrigin;
}

export interface AuthCommand {
  type: "auth";
  token: string;
}

export interface AuthResultEvent {
  type: "auth_result";
  ok: boolean;
}

export interface ListSessionsCommand {
  type: "list_sessions";
}

export interface GetConfigCommand {
  type: "get_config";
}

export interface SetConfigCommand {
  type: "set_config";
  nimApiKey: string;
}

export interface ConfigStateEvent {
  type: "config_state";
  /** never the actual key value — only whether one is set, and where it
   * came from, so the settings panel can show real status without ever
   * receiving the secret back down over the wire once it's saved. */
  nimApiKeySet: boolean;
  nimApiKeySource: "env" | "file" | "none";
}

export interface GetToolsCommand {
  type: "get_tools";
}

export interface ToolsCatalogEvent {
  type: "tools_catalog";
  tools: ToolDefinition[];
}

export interface SessionSummary {
  id: string;
  goal: string;
  state: AgentState;
  startedAt: number;
  finishedAt?: number;
  toolCallCount: number;
  lastToolId?: string;
  origin: SessionOrigin;
}

export interface SessionsSnapshotEvent {
  type: "sessions_snapshot";
  sessions: SessionSummary[];
}

export type RuntimeEvent =
  | ToolCallRequest
  | ToolCallResult
  | AgentStatusEvent
  | SessionsSnapshotEvent
  | AuthResultEvent
  | ConfigStateEvent
  | ToolsCatalogEvent;

export type RuntimeCommand =
  | AgentSessionStart
  | ToolCallApproval
  | ListSessionsCommand
  | AuthCommand
  | GetConfigCommand
  | SetConfigCommand
  | GetToolsCommand;

export const GATEWAY_PORT = 8765;
// Explicit IP, not "localhost" — the hostname form is what a system-wide
// proxy (common on Kali if Burp Suite or similar is configured) or a
// misbehaving resolver can intercept/redirect, even for loopback traffic.
// Plain Node (the TUI, the `ws` client) doesn't consult a browser's proxy
// settings, but Electron's Chromium-based renderer does — which is why the
// TUI could connect fine while the desktop UI hung on "Connecting...".
export const GATEWAY_HOST = "127.0.0.1";

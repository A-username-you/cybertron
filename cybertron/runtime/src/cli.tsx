import React, { useEffect, useRef, useState } from "react";
import { render, Box, Text, useInput, useApp } from "ink";
import WebSocket from "ws";
import { GATEWAY_PORT, GATEWAY_HOST, type RuntimeEvent, type SessionSummary, type AgentState } from "@cybertron/shared";
import { getOrCreateToken } from "./auth.js";

/**
 * `cybertron` — the bare command. Same protocol client as the desktop UI:
 * connects to the runtime gateway over WebSocket rather than importing
 * agent code directly, so the TUI and the GUI are two views of one truth.
 *
 * Auto-authenticates with the local token file on connect (trusted local
 * owner, same reasoning as the Electron shell).
 *
 * Keys: enter to send · y/n to approve or deny a pending tool call ·
 * s for server view · esc to quit.
 */

const GOLD = "#FFD700";
const AMBER = "#FFBF00";
const BRONZE = "#CD7F32";
const CORNSILK = "#FFF8DC";
const TEAL = "#4dd0e1";
const ERROR = "#ef5350";
const WARN = "#ffa726";
const DIM = "#B8860B";

const SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];
const RECONNECT_BASE_MS = 1000;
const RECONNECT_MAX_MS = 10000;

type LogLine = { text: string; color?: string };
type PendingApproval = { sessionId: string; requestId: string; toolId: string; args: Record<string, string> };

function elapsed(startedAt: number, finishedAt?: number): string {
  const ms = (finishedAt ?? Date.now()) - startedAt;
  return `${(ms / 1000).toFixed(1)}s`;
}

function sessionColor(state: string): string {
  if (state === "error") return ERROR;
  if (state === "done") return TEAL;
  if (state === "awaiting_approval") return WARN;
  return AMBER;
}

function newSessionId() {
  return `tui-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export function App() {
  const { exit } = useApp();
  const [status, setStatus] = useState("connecting");
  const [agentState, setAgentState] = useState<AgentState>("idle");
  const [authed, setAuthed] = useState(false);
  const [log, setLog] = useState<LogLine[]>([]);
  const [goal, setGoal] = useState("");
  const [showSessions, setShowSessions] = useState(false);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [approval, setApproval] = useState<PendingApproval | null>(null);
  const [turnStartedAt, setTurnStartedAt] = useState<number | null>(null);
  const [reconnectIn, setReconnectIn] = useState<number | null>(null);
  const [frame, setFrame] = useState(0);

  const wsRef = useRef<WebSocket | null>(null);
  const currentSessionIdRef = useRef<string>(newSessionId());
  const quittingRef = useRef(false);
  const reconnectAttemptRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    function connect() {
      const socket = new WebSocket(`ws://${GATEWAY_HOST}:${GATEWAY_PORT}`);
      wsRef.current = socket;

      socket.on("open", () => {
        reconnectAttemptRef.current = 0;
        setReconnectIn(null);
        setStatus("authenticating");
        socket.send(JSON.stringify({ type: "auth", token: getOrCreateToken() }));
      });

      socket.on("close", () => {
        setAuthed(false);
        if (quittingRef.current) return;
        const attempt = reconnectAttemptRef.current;
        const delayMs = Math.min(RECONNECT_BASE_MS * 2 ** attempt, RECONNECT_MAX_MS);
        reconnectAttemptRef.current = attempt + 1;
        setStatus("disconnected");
        let remaining = Math.round(delayMs / 1000);
        setReconnectIn(remaining);
        const countdown = setInterval(() => {
          remaining -= 1;
          setReconnectIn(remaining > 0 ? remaining : 0);
          if (remaining <= 0) clearInterval(countdown);
        }, 1000);
        reconnectTimerRef.current = setTimeout(() => {
          clearInterval(countdown);
          if (!quittingRef.current) connect();
        }, delayMs);
      });

      socket.on("error", () => setStatus("connection error"));

      socket.on("message", (raw) => {
        const event = JSON.parse(raw.toString()) as RuntimeEvent;
        if (event.type === "auth_result") {
          setAuthed(event.ok);
          setStatus(event.ok ? "idle" : "auth rejected — token file may be stale, restart the gateway");
          return;
        }
        if (event.type === "agent_status") {
          if (event.sessionId === currentSessionIdRef.current) {
            setStatus(event.state + (event.detail ? `: ${event.detail}` : ""));
            setAgentState(event.state);
            if (event.state === "thinking") setTurnStartedAt(Date.now());
            if (event.state === "done" || event.state === "error") setTurnStartedAt(null);
            if (event.state !== "awaiting_approval") setApproval(null);
          }
          return;
        }
        if (event.type === "tool_call_request") {
          if (event.sessionId === currentSessionIdRef.current) {
            setApproval({ sessionId: event.sessionId, requestId: event.requestId, toolId: event.toolId, args: event.args });
          }
          return;
        }
        if (event.type === "tool_call_result") {
          if (event.sessionId !== currentSessionIdRef.current) return;
          setLog((prev) => [
            ...prev,
            {
              text: `[${event.toolId}] ${event.ok ? "ok" : "error"} (${event.durationMs}ms)\n${
                event.ok ? event.output : event.error
              }`,
              color: event.ok ? "#4caf50" : ERROR,
            },
          ]);
          return;
        }
        if (event.type === "sessions_snapshot") {
          setSessions(event.sessions);
        }
      });
    }

    connect();

    const tick = setInterval(() => setFrame((n) => n + 1), 100);
    return () => {
      quittingRef.current = true;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      wsRef.current?.close();
      clearInterval(tick);
    };
  }, []);

  function sendApproval(approved: boolean) {
    if (!approval || !wsRef.current) return;
    wsRef.current.send(
      JSON.stringify({ type: "tool_call_approval", sessionId: approval.sessionId, requestId: approval.requestId, approved })
    );
    setLog((prev) => [...prev, { text: `${approved ? "approved" : "denied"}: ${approval.toolId}`, color: approved ? "#4caf50" : ERROR }]);
    setApproval(null);
  }

  useInput((input, key) => {
    if (key.escape) {
      quittingRef.current = true;
      exit();
      return;
    }
    if (!authed) return;

    if (approval) {
      if (input === "y" || input === "Y") return sendApproval(true);
      if (input === "n" || input === "N") return sendApproval(false);
      return; // ignore everything else while an approval is pending — no accidental sends
    }

    if (input === "s") {
      setShowSessions((v) => !v);
      wsRef.current?.send(JSON.stringify({ type: "list_sessions" }));
      return;
    }
    if (key.return && goal.trim() && wsRef.current) {
      if (working) return; // current session is still running — don't orphan it
      const sessionId = newSessionId();
      currentSessionIdRef.current = sessionId;
      setLog([]); // fresh view for the new session, matches "one goal, one session" like the web UI
      wsRef.current.send(JSON.stringify({ type: "session_start", sessionId, goal, origin: "cli" }));
      setLog((prev) => [...prev, { text: `> ${goal}`, color: AMBER }]);
      setGoal("");
      return;
    }
    if (key.backspace || key.delete) {
      setGoal((g) => g.slice(0, -1));
      return;
    }
    if (input) setGoal((g) => g + input);
  });

  const working = agentState === "thinking" || agentState === "running_tool";
  const glyph = approval ? "?"
    : working ? SPINNER_FRAMES[Math.floor(frame / 2) % SPINNER_FRAMES.length]
    : agentState === "done" ? "✧"
    : agentState === "error" ? "✕"
    : "●";
  const glyphColor = approval ? WARN : working ? AMBER : agentState === "done" ? TEAL : agentState === "error" ? ERROR : BRONZE;
  const turnElapsed = turnStartedAt ? `${((Date.now() - turnStartedAt) / 1000).toFixed(1)}s` : null;

  return (
    <Box flexDirection="column" padding={1}>
      <Text>
        <Text color={glyphColor} bold>{glyph}</Text>{" "}
        <Text color={GOLD} bold>cybertron</Text>{" "}
        <Text color={TEAL}>— {status}</Text>
        {turnElapsed && <Text color={DIM}>  turn {turnElapsed}</Text>}
        {reconnectIn !== null && <Text color={WARN}>  reconnecting in {reconnectIn}s</Text>}
      </Text>

      {approval && (
        <Box flexDirection="column" marginY={1} borderStyle="round" borderColor={WARN} paddingX={1}>
          <Text color={WARN} bold>
            approval required: {approval.toolId}
          </Text>
          <Text color={CORNSILK} dimColor>
            {JSON.stringify(approval.args)}
          </Text>
          <Text color={DIM}>y to approve · n to deny</Text>
        </Box>
      )}

      {showSessions ? (
        <Box flexDirection="column" marginY={1}>
          <Text color={DIM}>server view — every session on this gateway</Text>
          {sessions.length === 0 && <Text color={DIM}>no sessions yet</Text>}
          {sessions.map((s) => (
            <Text key={s.id}>
              <Text color={sessionColor(s.state)}>{s.state.padEnd(18)}</Text>
              <Text color={CORNSILK}>
                {elapsed(s.startedAt, s.finishedAt).padEnd(8)} calls:{s.toolCallCount} {s.goal.slice(0, 40)}
              </Text>
            </Text>
          ))}
        </Box>
      ) : (
        <Box flexDirection="column" marginY={1}>
          {log.length === 0 && <Text color={DIM}>no activity yet — type a goal and press enter</Text>}
          {log.slice(-20).map((line, i) => (
            <Text key={i} color={line.color ?? CORNSILK}>
              {line.text}
            </Text>
          ))}
        </Box>
      )}

      {!approval && (
        <Box>
          <Text color={AMBER}>❯ </Text>
          <Text color={CORNSILK}>{goal}</Text>
        </Box>
      )}
      <Text color={DIM}>
        {approval ? "y approve · n deny · esc quit" : "enter to send · s server view · esc quit"}
      </Text>
    </Box>
  );
}

export function runTui() {
  render(<App />);
}

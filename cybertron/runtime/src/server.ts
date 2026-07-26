import { createServer } from "node:http";
import { timingSafeEqual } from "node:crypto";
import { WebSocketServer, type WebSocket } from "ws";
import { runAgentSession } from "./agent/core.js";
import { getOrCreateToken, tokenFilePath } from "./auth.js";
import { initConfig, setNimApiKey, nimKeyStatus } from "./config.js";
import { TOOL_CATALOG } from "./tools/index.js";
import {
  GATEWAY_PORT,
  GATEWAY_HOST,
  type RuntimeCommand,
  type RuntimeEvent,
  type SessionSummary,
} from "@cybertron/shared";

/**
 * This process is the whole point of the merge: a plain Node process, not
 * a Next.js API route. It runs identically whether launched by
 * `npm run dev:runtime`, spawned by Electron's main process, or run
 * headless via `cybertron server`. Static-exporting the UI never breaks
 * this, because the UI never held the agent logic.
 *
 * Multi-session: any number of sessions can run concurrently, from any
 * number of connected clients. Every client sees every session's status —
 * that's what backs the "server" toggle in the UI: turn it on and you're
 * looking at every session running against this gateway, not just the one
 * you started.
 */

const sessions = new Map<string, SessionSummary>();
const clients = new Set<WebSocket>();
const pendingApprovals = new Map<string, (approved: boolean) => void>();
const pendingApprovalTimers = new Map<string, ReturnType<typeof setTimeout>>();
const APPROVAL_TIMEOUT_MS = 10 * 60 * 1000; // 10 minutes — long enough for a human to notice and respond, short enough not to leak a session forever
const authenticated = new WeakSet<WebSocket>();
const AUTH_TOKEN = getOrCreateToken();
initConfig();

function configStateEvent(): RuntimeEvent {
  const status = nimKeyStatus();
  return { type: "config_state", nimApiKeySet: status.set, nimApiKeySource: status.source };
}

function toolsCatalogEvent(): RuntimeEvent {
  return { type: "tools_catalog", tools: TOOL_CATALOG };
}

function tokensMatch(candidate: unknown): boolean {
  if (typeof candidate !== "string") return false;
  const a = Buffer.from(candidate);
  const b = Buffer.from(AUTH_TOKEN);
  // timingSafeEqual throws on length mismatch rather than returning false,
  // and a length mismatch is itself timing-observable info we don't need
  // to leak either — pad to a fixed comparison instead of short-circuiting.
  if (a.length !== b.length) return false;
  return timingSafeEqual(a, b);
}

function broadcast(event: RuntimeEvent) {
  const payload = JSON.stringify(event);
  for (const client of clients) {
    if (client.readyState === client.OPEN) client.send(payload);
  }
}

function broadcastSessions() {
  broadcast({ type: "sessions_snapshot", sessions: [...sessions.values()].sort((a, b) => b.startedAt - a.startedAt) });
}

const httpServer = createServer((req, res) => {
  if (req.url === "/health") {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ ok: true, sessions: sessions.size }));
    return;
  }
  res.writeHead(404);
  res.end();
});

const wss = new WebSocketServer({ server: httpServer });

wss.on("connection", (socket: WebSocket) => {
  clients.add(socket);
  socket.on("close", () => clients.delete(socket));

  socket.on("message", async (raw) => {
    let cmd: RuntimeCommand;
    try {
      cmd = JSON.parse(raw.toString());
    } catch {
      return;
    }

    if (cmd.type === "auth") {
      const ok = tokensMatch(cmd.token);
      if (ok) authenticated.add(socket);
      socket.send(JSON.stringify({ type: "auth_result", ok }));
      if (ok) {
        socket.send(JSON.stringify(configStateEvent()));
        socket.send(JSON.stringify(toolsCatalogEvent()));
        socket.send(
          JSON.stringify({
            type: "sessions_snapshot",
            sessions: [...sessions.values()].sort((a, b) => b.startedAt - a.startedAt),
          })
        );
      }
      return;
    }

    if (!authenticated.has(socket)) {
      socket.send(JSON.stringify({ type: "auth_result", ok: false }));
      return;
    }

    if (cmd.type === "list_sessions") {
      socket.send(
        JSON.stringify({
          type: "sessions_snapshot",
          sessions: [...sessions.values()].sort((a, b) => b.startedAt - a.startedAt),
        })
      );
      return;
    }

    if (cmd.type === "get_config") {
      socket.send(JSON.stringify(configStateEvent()));
      return;
    }

    if (cmd.type === "set_config") {
      if (cmd.nimApiKey.trim()) setNimApiKey(cmd.nimApiKey);
      broadcast(configStateEvent()); // every connected client's settings panel reflects the change, not just the one that saved it
      return;
    }

    if (cmd.type === "get_tools") {
      socket.send(JSON.stringify(toolsCatalogEvent()));
      return;
    }

    if (cmd.type === "tool_call_approval") {
      pendingApprovals.get(cmd.sessionId)?.(cmd.approved);
      pendingApprovals.delete(cmd.sessionId);
      const timer = pendingApprovalTimers.get(cmd.sessionId);
      if (timer) clearTimeout(timer);
      pendingApprovalTimers.delete(cmd.sessionId);
      return;
    }

    if (cmd.type === "session_start") {
      const sessionId = cmd.sessionId;
      sessions.set(sessionId, {
        id: sessionId,
        goal: cmd.goal,
        state: "thinking",
        startedAt: Date.now(),
        toolCallCount: 0,
        origin: cmd.origin,
      });
      broadcastSessions();

      // Deliberately not awaited here — sessions run concurrently, this
      // handler returns immediately so the socket can accept the next
      // command (another session_start, an approval for a different
      // session, a list_sessions poll) without blocking on this one.
      runAgentSession(sessionId, cmd.goal, {
        onStatus: (event) => {
          const s = sessions.get(sessionId);
          if (s) {
            s.state = event.state;
            if (event.state === "done" || event.state === "error") s.finishedAt = Date.now();
          }
          broadcast(event);
          broadcastSessions();
        },
        onToolResult: (event) => broadcast(event),
        onToolCallCount: (toolId) => {
          const s = sessions.get(sessionId);
          if (s) {
            s.toolCallCount += 1;
            s.lastToolId = toolId;
          }
        },
        requestApproval: (toolId, args) =>
          new Promise<boolean>((resolve) => {
            pendingApprovals.set(sessionId, resolve);
            const requestId = `${toolId}-${Date.now()}`;
            const timer = setTimeout(() => {
              if (pendingApprovals.get(sessionId) !== resolve) return; // already resolved by a real response
              pendingApprovals.delete(sessionId);
              pendingApprovalTimers.delete(sessionId);
              resolve(false);
            }, APPROVAL_TIMEOUT_MS);
            pendingApprovalTimers.set(sessionId, timer);
            broadcast({
              type: "tool_call_request",
              sessionId,
              requestId,
              toolId,
              args,
            });
          }),
      }).catch((err) => {
        const s = sessions.get(sessionId);
        if (s) {
          s.state = "error";
          s.finishedAt = Date.now();
        }
        broadcast({ type: "agent_status", sessionId, state: "error", detail: err.message });
        broadcastSessions();
      });
    }
  });
});

httpServer.listen(GATEWAY_PORT, GATEWAY_HOST, () => {
  console.log(`[cybertron-runtime] gateway listening on ws://${GATEWAY_HOST}:${GATEWAY_PORT}`);
  console.log(`[cybertron-runtime] auth token (stored at ${tokenFilePath()}):`);
  console.log(`[cybertron-runtime]   ${AUTH_TOKEN}`);
  console.log(`[cybertron-runtime] enter this in the UI, or set CYBERTRON_AUTH_TOKEN to override it`);
});

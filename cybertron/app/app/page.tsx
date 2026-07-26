"use client";

import { useEffect, useRef, useState } from "react";
import { StateIcon, type IconMainState } from "./components/StateIcon";

/**
 * Sidebar + composer-footer + Control Center layout, modeled on Hermes
 * Agent's own web UI (three-panel: sidebar/chat/workspace — we drop the
 * workspace panel since Cybertron has no file-workspace backend to power
 * one yet; that'd be a real feature to add, not a restyle).
 *
 * Still never calls a Next.js API route — every dynamic action goes over
 * a message channel to the runtime gateway. See electron/preload.ts /
 * electron/main.ts for the Electron IPC transport, or the direct
 * WebSocket path below for a plain browser tab.
 *
 * Session model: each session is one autonomous agent run for one goal
 * (see runtime/src/agent/core.ts) — not a multi-turn conversation. The
 * composer always starts a *new* session; the sidebar lets you navigate
 * between all of them, running or finished, including ones started from
 * the TUI (tagged with a "cli" badge, matching Hermes's own CLI-bridge
 * convention).
 *
 * Transcript limitation, disclosed rather than hidden: the gateway keeps
 * only a live summary per session (state, tool count, last tool), not a
 * full replayable log. This client builds each session's transcript from
 * events it personally observed since connecting — so a session started
 * before this tab opened (by another tab, or the TUI) will show up in the
 * sidebar with correct status, but with an empty or partial transcript
 * until you watch it produce new events. Full server-side transcript
 * persistence would be a real backend feature, not a UI change.
 */

type Line = { text: string; kind: "human" | "system" | "danger" };
type Session = {
  id: string;
  goal: string;
  state: string;
  startedAt: number;
  finishedAt?: number;
  toolCallCount: number;
  lastToolId?: string;
  origin?: "web" | "cli";
};
type Approval = { requestId: string; toolId: string; args: Record<string, string> };
type ToolDef = { id: string; category: string; label: string; autoApprove: boolean; implemented: boolean };

// Mirrors runtime/src/agent/nim-client.ts's NIM_CONTEXT_WINDOW — used only
// as a fallback until the first real agent_status tells us the actual
// figure the server is using, so the ring is never wrong even if that
// constant changes on the server side.
const FALLBACK_CONTEXT_WINDOW = 262_144;

declare global {
  interface Window {
    cybertron?: {
      gatewayPort: number;
      platform: string;
      send: (json: string) => void;
      onMessage: (cb: (data: string) => void) => () => void;
      onStatus: (cb: (status: string) => void) => () => void;
      getStatus: () => Promise<string>;
      getToken: () => Promise<string | null>;
    };
  }
}

function newSessionId() {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `sess-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function ContextRing({ used, max }: { used: number; max: number }) {
  const pct = Math.max(0, Math.min(used / max, 1));
  const r = 9;
  const circumference = 2 * Math.PI * r;
  const dash = circumference * pct;
  return (
    <svg
      width="22"
      height="22"
      viewBox="0 0 22 22"
      role="img"
      aria-label={`context: ${used.toLocaleString()} of ${max.toLocaleString()} tokens`}
    >
      <title>{`${used.toLocaleString()} / ${max.toLocaleString()} tokens`}</title>
      <circle cx="11" cy="11" r={r} fill="none" stroke="var(--surface-2)" strokeWidth="2.5" />
      <circle
        cx="11"
        cy="11"
        r={r}
        fill="none"
        stroke={pct > 0.85 ? "var(--danger)" : "var(--gold)"}
        strokeWidth="2.5"
        strokeDasharray={`${dash} ${circumference - dash}`}
        strokeLinecap="round"
        transform="rotate(-90 11 11)"
      />
    </svg>
  );
}

export default function Home() {
  const [status, setStatus] = useState("connecting");
  const [wsOpen, setWsOpen] = useState(false);
  const [authed, setAuthed] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const [authPending, setAuthPending] = useState(false);
  const [tokenInput, setTokenInput] = useState("");
  const [goal, setGoal] = useState("");

  const [sessions, setSessions] = useState<Session[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [transcripts, setTranscripts] = useState<Record<string, Line[]>>({});
  const [pendingApprovals, setPendingApprovals] = useState<Record<string, Approval>>({});
  const [contextUsage, setContextUsage] = useState<Record<string, { used: number; max: number }>>({});
  const [recentlyDone, setRecentlyDone] = useState<{ sessionId: string; until: number } | null>(null);
  const [burstKey, setBurstKey] = useState(0);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const [controlCenterOpen, setControlCenterOpen] = useState(false);
  const [nimKeySet, setNimKeySet] = useState(false);
  const [nimKeySource, setNimKeySource] = useState<"env" | "file" | "none">("none");
  const [nimKeyInput, setNimKeyInput] = useState("");
  const [settingsSaved, setSettingsSaved] = useState(false);
  const [tools, setTools] = useState<ToolDef[]>([]);

  const [connectError, setConnectError] = useState<string | null>(null);
  const [isElectron, setIsElectron] = useState(false);
  const [, forceTick] = useState(0);

  const sendRef = useRef<(obj: unknown) => void>(() => {});
  const authedRef = useRef(false);
  const selectedSessionIdRef = useRef<string | null>(null);
  const doneSettleTickRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const authTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const connectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const autoTokenRef = useRef<string | null>(null);

  useEffect(() => {
    selectedSessionIdRef.current = selectedSessionId;
  }, [selectedSessionId]);

  useEffect(() => {
    let cleanupFns: Array<() => void> = [];

    function handleStatus(rawStatus: string) {
      const open = rawStatus === "open";
      setWsOpen(open);
      if (open) {
        if (connectTimeoutRef.current) clearTimeout(connectTimeoutRef.current);
        setConnectError(null);
        setStatus("authenticating");
        if (autoTokenRef.current) sendAuth(autoTokenRef.current);
      } else if (rawStatus === "error") {
        setStatus("error — is the runtime process running?");
      } else if (rawStatus === "closed") {
        setStatus("disconnected");
      }
    }

    function appendLine(sessionId: string, line: Line) {
      setTranscripts((prev) => ({ ...prev, [sessionId]: [...(prev[sessionId] ?? []), line] }));
    }

    function handleMessage(raw: string) {
      const msg = JSON.parse(raw);

      if (msg.type === "auth_result") {
        if (authTimeoutRef.current) clearTimeout(authTimeoutRef.current);
        setAuthPending(false);
        authedRef.current = msg.ok;
        setAuthed(msg.ok);
        setStatus(msg.ok ? "idle" : "awaiting authentication");
        setAuthError(msg.ok ? null : "Incorrect token.");
        return;
      }
      if (!authedRef.current) return; // ignore everything else until the gate opens

      if (msg.type === "agent_status") {
        if (typeof msg.tokensUsed === "number") {
          setContextUsage((prev) => ({
            ...prev,
            [msg.sessionId]: { used: msg.tokensUsed, max: msg.contextWindow ?? prev[msg.sessionId]?.max ?? FALLBACK_CONTEXT_WINDOW },
          }));
        }
        if (msg.state === "done") setRecentlyDone({ sessionId: msg.sessionId, until: Date.now() + 2000 });
        if (msg.state === "error" && msg.detail) {
          appendLine(msg.sessionId, { text: `error: ${msg.detail}`, kind: "danger" });
        }
        // sessions[] itself is kept in sync by the sessions_snapshot broadcast
        // that always immediately follows an agent_status server-side.
      } else if (msg.type === "tool_call_result") {
        if (msg.ok && msg.sessionId === selectedSessionIdRef.current) setBurstKey((k) => k + 1);
        appendLine(msg.sessionId, {
          text: `[${msg.toolId}] ${msg.ok ? "ok" : "error"} (${msg.durationMs}ms)\n${msg.ok ? msg.output : msg.error}`,
          kind: msg.ok ? "system" : "danger",
        });
      } else if (msg.type === "tool_call_request") {
        setPendingApprovals((prev) => ({
          ...prev,
          [msg.sessionId]: { requestId: msg.requestId, toolId: msg.toolId, args: msg.args },
        }));
      } else if (msg.type === "sessions_snapshot") {
        setSessions(msg.sessions);
      } else if (msg.type === "config_state") {
        setNimKeySet(msg.nimApiKeySet);
        setNimKeySource(msg.nimApiKeySource);
      } else if (msg.type === "tools_catalog") {
        setTools(msg.tools);
      }
    }

    async function setup() {
      const bridge = typeof window !== "undefined" ? window.cybertron : undefined;

      if (bridge?.send) {
        // Electron: IPC transport, no renderer-side networking at all.
        setIsElectron(true);
        sendRef.current = (obj) => bridge.send(JSON.stringify(obj));
        const unsubMsg = bridge.onMessage(handleMessage);
        const unsubStatus = bridge.onStatus(handleStatus);
        cleanupFns.push(unsubMsg, unsubStatus);

        autoTokenRef.current = await bridge.getToken();
        const initialStatus = await bridge.getStatus();
        handleStatus(initialStatus);
      } else {
        // Plain browser tab: direct WebSocket. This path was never the one
        // that was broken — keeping it simple and unchanged in spirit.
        const port = 8765;
        const ws = new WebSocket(`ws://127.0.0.1:${port}`);
        sendRef.current = (obj) => ws.send(JSON.stringify(obj));

        connectTimeoutRef.current = setTimeout(() => {
          if (ws.readyState !== WebSocket.OPEN) {
            setConnectError(`Couldn't reach ws://127.0.0.1:${port} after 6s. Is the gateway running?`);
          }
        }, 6000);

        ws.onopen = () => handleStatus("open");
        ws.onclose = () => handleStatus("closed");
        ws.onerror = () => handleStatus("error");
        ws.onmessage = (event) => handleMessage(event.data);

        cleanupFns.push(() => ws.close());
      }
    }

    setup();

    const tick = setInterval(() => forceTick((n) => n + 1), 1000);
    return () => {
      clearInterval(tick);
      if (doneSettleTickRef.current) clearTimeout(doneSettleTickRef.current);
      if (authTimeoutRef.current) clearTimeout(authTimeoutRef.current);
      if (connectTimeoutRef.current) clearTimeout(connectTimeoutRef.current);
      cleanupFns.forEach((fn) => fn());
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function sendAuth(token: string) {
    setAuthPending(true);
    setAuthError(null);
    sendRef.current({ type: "auth", token });
    if (authTimeoutRef.current) clearTimeout(authTimeoutRef.current);
    authTimeoutRef.current = setTimeout(() => {
      setAuthPending(false);
      setAuthError("No response from the gateway — is it running?");
    }, 5000);
  }

  function submitToken() {
    if (!tokenInput.trim()) return;
    sendAuth(tokenInput.trim());
  }

  function sendGoal() {
    if (!goal.trim() || !wsOpen) return;
    const sessionId = newSessionId();
    setSelectedSessionId(sessionId);
    setSidebarOpen(false);
    sendRef.current({ type: "session_start", sessionId, goal, origin: "web" });
    setTranscripts((prev) => ({ ...prev, [sessionId]: [{ text: `> ${goal}`, kind: "human" }] }));
    setGoal("");
  }

  function respondApproval(approved: boolean) {
    const sid = selectedSessionId;
    if (!sid) return;
    const a = pendingApprovals[sid];
    if (!a) return;
    sendRef.current({ type: "tool_call_approval", sessionId: sid, requestId: a.requestId, approved });
    setPendingApprovals((prev) => {
      const next = { ...prev };
      delete next[sid];
      return next;
    });
  }

  function toggleControlCenter() {
    const next = !controlCenterOpen;
    setControlCenterOpen(next);
    setSettingsSaved(false);
    if (next) {
      sendRef.current({ type: "get_config" });
      sendRef.current({ type: "get_tools" });
    }
  }

  function saveNimKey() {
    if (!nimKeyInput.trim()) return;
    sendRef.current({ type: "set_config", nimApiKey: nimKeyInput.trim() });
    setNimKeyInput("");
    setSettingsSaved(true);
    setTimeout(() => setSettingsSaved(false), 2500);
  }

  function selectSession(id: string) {
    setSelectedSessionId(id);
    setSidebarOpen(false);
  }

  function startNewSession() {
    setSelectedSessionId(null);
    setSidebarOpen(false);
  }

  if (!authed) {
    const hadAutoToken = !!autoTokenRef.current;

    let subtitle = "Enter the gateway token to connect.";
    if (connectError) subtitle = "Connection problem — see below.";
    else if (!wsOpen) subtitle = "Connecting to the gateway…";
    else if (authPending) subtitle = hadAutoToken ? "Authenticating automatically…" : "Checking token…";

    return (
      <main className="gate-shell">
        <div className="panel">
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
            <StateIcon state={wsOpen && authPending ? "thinking" : "idle"} burstKey={0} size={20} displayPx={28} />
            <h1 style={{ fontSize: "var(--font-title)", letterSpacing: 1.5, textTransform: "uppercase", margin: 0, color: "var(--text-primary)" }}>
              Cybertron
            </h1>
          </div>
          <p style={{ color: "var(--text-primary)", fontSize: "var(--font-small)", marginTop: 8, marginBottom: 16 }}>{subtitle}</p>

          {connectError && (
            <p className="label-danger" style={{ fontSize: "var(--font-small)", marginBottom: 16, lineHeight: 1.5, overflowWrap: "anywhere" }}>
              {connectError}
            </p>
          )}

          <input
            type="password"
            value={tokenInput}
            onChange={(e) => setTokenInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && wsOpen && !authPending && submitToken()}
            placeholder="gateway token"
            autoFocus={!hadAutoToken}
            disabled={!wsOpen || authPending}
            className="composer-input"
            style={{ width: "100%", marginBottom: 10, opacity: !wsOpen || authPending ? 0.6 : 1 }}
          />
          <button
            className="primary"
            onClick={submitToken}
            disabled={!wsOpen || authPending || !tokenInput.trim()}
            style={{ opacity: !wsOpen || authPending || !tokenInput.trim() ? 0.5 : 1, width: "100%" }}
          >
            {!wsOpen ? "Connecting…" : authPending ? "Checking…" : "Connect"}
          </button>
          {authError && (
            <p className="label-danger" style={{ fontSize: "var(--font-small)", marginTop: 12 }}>
              {authError}
            </p>
          )}
          <p style={{ color: "var(--text-muted)", fontSize: 11.5, marginTop: 20, marginBottom: 0, lineHeight: 1.6 }}>
            Printed to the console when the gateway starts, and stored at{" "}
            <code>~/.cybertron/auth-token</code>.
            {isElectron && !hadAutoToken && (
              <>
                {" "}
                (Desktop app detected but no token was supplied automatically — enter it manually
                below for now.)
              </>
            )}
          </p>
        </div>
      </main>
    );
  }

  const sortedSessions = [...sessions].sort((a, b) => b.startedAt - a.startedAt);
  const selectedSession = sessions.find((s) => s.id === selectedSessionId) ?? null;
  const selectedTranscript = selectedSessionId ? transcripts[selectedSessionId] ?? [] : [];
  const selectedApproval = selectedSessionId ? pendingApprovals[selectedSessionId] : undefined;
  const selectedUsage = selectedSessionId ? contextUsage[selectedSessionId] : undefined;
  const activeCount = sessions.filter((s) => s.state !== "done" && s.state !== "error").length;
  const implementedCount = tools.filter((t) => t.implemented).length;
  const connectionNotice = !wsOpen ? status : null;

  let headerAgentState: IconMainState = "idle";
  if (selectedSession) {
    if (selectedSession.state === "done") {
      headerAgentState = recentlyDone?.sessionId === selectedSession.id && recentlyDone.until > Date.now() ? "done" : "idle";
    } else {
      headerAgentState = selectedSession.state as IconMainState;
    }
  }

  const elapsed = selectedSession
    ? (((selectedSession.finishedAt ?? Date.now()) - selectedSession.startedAt) / 1000).toFixed(1) + "s"
    : null;

  return (
    <div className="shell">
      {sidebarOpen && <div className="sidebar-backdrop" onClick={() => setSidebarOpen(false)} />}

      <aside className={`sidebar ${sidebarOpen ? "sidebar-open" : ""}`}>
        <div className="sidebar-header">
          <StateIcon state="idle" burstKey={0} size={18} displayPx={22} />
          <span className="brand">Cybertron</span>
        </div>
        {connectionNotice && <p className="connection-notice">{connectionNotice}</p>}

        <button className="new-session-button" onClick={startNewSession}>
          + New session
        </button>

        <div className="session-list">
          {sortedSessions.length === 0 && <p className="sidebar-empty">No sessions yet — describe a goal below.</p>}
          {sortedSessions.map((s) => (
            <button
              key={s.id}
              className={`session-item ${s.id === selectedSessionId ? "session-item-selected" : ""}`}
              onClick={() => selectSession(s.id)}
            >
              <span className={`session-dot session-dot-${s.state}`} />
              <span className="session-item-goal">{s.goal || "(no goal text)"}</span>
              {s.origin === "cli" && <span className="badge-cli">cli</span>}
              {pendingApprovals[s.id] && <span className="badge-approval" aria-label="approval needed" />}
            </button>
          ))}
        </div>

        <button className="control-center-button" onClick={toggleControlCenter} aria-expanded={controlCenterOpen}>
          Control Center{!nimKeySet && <span className="label-danger"> ●</span>}
        </button>
      </aside>

      <main className="main-area">
        <div className="main-topbar">
          <button className="sidebar-toggle" onClick={() => setSidebarOpen(true)}>
            Sessions{activeCount > 0 ? ` (${activeCount})` : ""}
          </button>
          <div className="main-topbar-title">
            <StateIcon state={headerAgentState} burstKey={burstKey} size={20} displayPx={24} />
            <span className="main-topbar-goal">{selectedSession ? selectedSession.goal : "New session"}</span>
          </div>
          <div className="main-topbar-meta">
            {selectedUsage && <ContextRing used={selectedUsage.used} max={selectedUsage.max} />}
            {elapsed && <span className="meta-turn">{elapsed}</span>}
          </div>
        </div>

        <div className="panel transcript-panel">
          {!selectedSession && (
            <p className="empty-hint">Describe a goal in the composer below to dispatch a new session.</p>
          )}
          {selectedSession && selectedTranscript.length === 0 && (
            <p className="empty-hint">
              No log observed yet for this session{selectedSession.origin === "cli" ? " (started from the TUI)" : ""} — it may have
              run before this tab was open. Current state: {selectedSession.state}, {selectedSession.toolCallCount} tool call
              {selectedSession.toolCallCount === 1 ? "" : "s"}.
            </p>
          )}
          {selectedTranscript.map((l, i) => (
            <div key={i} className={`log-line label-${l.kind}`}>
              {l.text}
            </div>
          ))}
        </div>

        {selectedApproval && (
          <div className="panel approval-panel">
            <p className="label-human" style={{ overflowWrap: "anywhere" }}>
              Approval required: {selectedApproval.toolId} — {JSON.stringify(selectedApproval.args)}
            </p>
            <div className="approval-actions">
              <button className="primary" onClick={() => respondApproval(true)}>
                Approve
              </button>
              <button className="primary" onClick={() => respondApproval(false)}>
                Deny
              </button>
            </div>
          </div>
        )}

        <div className="composer">
          <input
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && sendGoal()}
            placeholder={wsOpen ? "e.g. enumerate subdomains for example.com and probe for live hosts" : "disconnected…"}
            disabled={!wsOpen}
            className="composer-input"
            style={{ opacity: wsOpen ? 1 : 0.6 }}
          />
          <button className="primary" onClick={sendGoal} disabled={!wsOpen || !goal.trim()} style={{ opacity: !wsOpen || !goal.trim() ? 0.5 : 1 }}>
            Send
          </button>
        </div>
      </main>

      {controlCenterOpen && (
        <div className="modal-backdrop" onClick={() => setControlCenterOpen(false)}>
          <div className="panel modal-panel control-center" onClick={(e) => e.stopPropagation()}>
            <h2 className="modal-title">Control Center</h2>

            <section className="cc-section">
              <h3 className="cc-section-title">NIM API key</h3>
              <div className="settings-row">
                <span>Status</span>
                <span className={nimKeySet ? "label-system" : "label-danger"}>
                  {nimKeySet ? (nimKeySource === "env" ? "set (environment variable)" : "set (saved here)") : "not set"}
                </span>
              </div>
              <p className="cc-hint">
                Required for the agent to respond to anything. Get one at{" "}
                <span style={{ overflowWrap: "anywhere" }}>build.nvidia.com</span>. Saved locally at{" "}
                <code>~/.cybertron/config.json</code> — never sent anywhere except NVIDIA&apos;s API.
                {nimKeySource === "env" && <> An environment variable is currently set and takes priority over anything saved here.</>}
              </p>
              <input
                type="password"
                value={nimKeyInput}
                onChange={(e) => setNimKeyInput(e.target.value)}
                placeholder={nimKeySet ? "paste a new key to replace it" : "paste your NIM API key"}
                className="composer-input"
                style={{ width: "100%" }}
              />
              <div style={{ display: "flex", gap: 10, marginTop: 10, flexWrap: "wrap" }}>
                <button className="primary" onClick={saveNimKey} disabled={!nimKeyInput.trim()} style={{ opacity: !nimKeyInput.trim() ? 0.5 : 1 }}>
                  Save
                </button>
              </div>
              {settingsSaved && (
                <p className="label-system cc-hint" style={{ marginTop: 8, marginBottom: 0 }}>
                  Saved — takes effect on the next message, no restart needed.
                </p>
              )}
            </section>

            <section className="cc-section">
              <h3 className="cc-section-title">Tools</h3>
              <p className="cc-hint" style={{ marginTop: 0 }}>
                {tools.length === 0 ? "Loading…" : `${implementedCount} of ${tools.length} cataloged tools have real handlers wired up.`}
              </p>
              {tools.length > 0 && (
                <div className="tool-grid">
                  {tools.map((t) => (
                    <div key={t.id} className="tool-row">
                      <span className={t.implemented ? "label-system" : "label-danger"}>{t.implemented ? "●" : "○"}</span>
                      <span className="tool-id">{t.id}</span>
                      <span className="cc-hint">{t.category}</span>
                      {!t.autoApprove && <span className="label-human cc-hint">approval</span>}
                    </div>
                  ))}
                </div>
              )}
            </section>

            <section className="cc-section">
              <h3 className="cc-section-title">Sessions</h3>
              <p className="cc-hint" style={{ marginTop: 0, marginBottom: 0 }}>
                {sessions.length} total this gateway session, {activeCount} active right now.
              </p>
            </section>

            <button className="primary" onClick={() => setControlCenterOpen(false)} style={{ width: "100%", marginTop: 4 }}>
              Close
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

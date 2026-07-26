import { chat, NIM_CONTEXT_WINDOW, type ChatMessage } from "./nim-client.js";
import { TOOL_CATALOG, TOOL_HANDLERS, getTool } from "../tools/index.js";
import type { AgentState, AgentStatusEvent, ToolCallResult } from "@cybertron/shared";

const MAX_ITERATIONS = 12;

const AVAILABLE_TOOLS = TOOL_CATALOG.filter((t) => TOOL_HANDLERS[t.id]);

const SYSTEM_PROMPT = `You are Cybertron, an authorized cybersecurity agent operating across both
red-team (offense) and blue-team (defense/detection) work. You may only act against targets or
systems the operator has explicitly given you and confirmed are in scope.
Available tools:
${AVAILABLE_TOOLS.map((t) => `- ${t.id} (${t.category}): ${t.label}${t.autoApprove ? "" : " [requires human approval]"}`).join("\n")}

To call a tool, respond with ONLY a JSON object: {"tool": "<id>", "args": {...}}
When you have enough information to conclude, respond with ONLY: {"done": true, "summary": "..."}
Never fabricate tool output. Never claim a vulnerability is confirmed, or a system is clean,
without a tool result showing it.`;

export interface AgentCallbacks {
  onStatus: (event: AgentStatusEvent) => void;
  onToolResult: (event: ToolCallResult) => void;
  onToolCallCount?: (toolId: string) => void;
  /** Must resolve to true/false; used for any tool where autoApprove is false */
  requestApproval: (toolId: string, args: Record<string, string>) => Promise<boolean>;
}

export async function runAgentSession(sessionId: string, goal: string, cb: AgentCallbacks): Promise<string> {
  const messages: ChatMessage[] = [
    { role: "system", content: SYSTEM_PROMPT },
    { role: "user", content: goal },
  ];

  // total_tokens from the most recent call approximates current context
  // occupancy (prompt grows every iteration since the whole transcript is
  // resent) — that's the right number for a "how full is the context
  // window" indicator, not a lifetime sum across calls.
  let tokensUsed: number | undefined;
  const status = (state: AgentState, detail?: string) =>
    cb.onStatus({ type: "agent_status", sessionId, state, detail, tokensUsed, contextWindow: NIM_CONTEXT_WINDOW });

  for (let i = 0; i < MAX_ITERATIONS; i++) {
    status("thinking");

    const { content: raw, totalTokens } = await chat(messages);
    if (typeof totalTokens === "number") tokensUsed = totalTokens;
    let parsed: any;
    try {
      parsed = JSON.parse(raw.trim());
    } catch {
      // Model didn't return valid JSON — treat as a final summary rather than crashing the loop.
      status("done");
      return raw;
    }

    if (parsed.done) {
      status("done");
      return parsed.summary ?? "(agent finished without a summary)";
    }

    const tool = getTool(parsed.tool);
    if (!tool) {
      messages.push({ role: "assistant", content: raw });
      messages.push({ role: "user", content: `Error: unknown tool "${parsed.tool}"` });
      continue;
    }

    if (!tool.autoApprove) {
      status("awaiting_approval", tool.id);
      const approved = await cb.requestApproval(tool.id, parsed.args ?? {});
      if (!approved) {
        messages.push({ role: "assistant", content: raw });
        messages.push({ role: "user", content: `Human denied approval for "${tool.id}". Choose a different approach.` });
        continue;
      }
    }

    status("running_tool", tool.id);
    cb.onToolCallCount?.(tool.id);
    const handler = TOOL_HANDLERS[tool.id];
    const started = Date.now();
    const requestId = `${tool.id}-${started}`;

    try {
      if (!handler) {
        throw new Error(`"${tool.id}" is in the catalog but has no handler implemented yet.`);
      }
      const output = await handler(parsed.args ?? {});
      const result: ToolCallResult = {
        type: "tool_call_result",
        sessionId,
        requestId,
        toolId: tool.id,
        ok: true,
        output,
        durationMs: Date.now() - started,
      };
      cb.onToolResult(result);
      messages.push({ role: "assistant", content: raw });
      messages.push({ role: "user", content: `[${tool.id}] output:\n${output}` });
    } catch (err: any) {
      const result: ToolCallResult = {
        type: "tool_call_result",
        sessionId,
        requestId,
        toolId: tool.id,
        ok: false,
        output: "",
        error: err.message,
        durationMs: Date.now() - started,
      };
      cb.onToolResult(result);
      messages.push({ role: "assistant", content: raw });
      messages.push({ role: "user", content: `[${tool.id}] error: ${err.message}` });
    }
  }

  status("done", "max iterations reached");
  return "(reached max iterations without a final summary)";
}

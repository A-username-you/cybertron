/**
 * Thin client for NVIDIA NIM's OpenAI-compatible chat completions endpoint,
 * targeting Nemotron 3 Ultra 550B as the reasoning layer.
 *
 * Real network call — needs NIM_API_KEY set in the environment. No mock
 * response path; if the key is missing this throws rather than pretending
 * to work.
 */

const NIM_BASE_URL = process.env.NIM_BASE_URL ?? "https://integrate.api.nvidia.com/v1";
const NIM_MODEL = process.env.NIM_MODEL ?? "nvidia/nemotron-3-ultra-550b";

// NVIDIA's own NIM day-0 guide for this model: 262,144 tokens (256K) is the
// default --max-model-len served by the hosted NIM endpoint we actually call
// (integrate.api.nvidia.com), reported by its /v1/models endpoint. The model
// weights support up to 1M with extra vLLM flags, but that's not what's
// actually running behind the default hosted endpoint, so 256K is the
// honest number for a usage ring rather than the larger headline figure.
export const NIM_CONTEXT_WINDOW = 262_144;

export interface ChatMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

export interface ChatResult {
  content: string;
  /** absent if the endpoint doesn't return usage for some reason — never fabricated */
  totalTokens?: number;
}

export async function chat(messages: ChatMessage[]): Promise<ChatResult> {
  const apiKey = process.env.NIM_API_KEY;
  if (!apiKey) {
    throw new Error(
      "NIM_API_KEY is not set. Get one at https://build.nvidia.com and set it in your environment."
    );
  }

  const res = await fetch(`${NIM_BASE_URL}/chat/completions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify({
      model: NIM_MODEL,
      messages,
      temperature: 0.2,
      max_tokens: 1024,
    }),
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`NIM request failed: ${res.status} ${res.statusText} ${text}`);
  }

  const data = await res.json();
  const content = data?.choices?.[0]?.message?.content;
  if (typeof content !== "string") {
    throw new Error("NIM response missing choices[0].message.content");
  }
  const totalTokens = typeof data?.usage?.total_tokens === "number" ? data.usage.total_tokens : undefined;
  return { content, totalTokens };
}

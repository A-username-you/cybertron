"""LLM client with multi-provider support."""
import os, json
from typing import List, Dict, Any, AsyncGenerator, Optional
import httpx, structlog

logger = structlog.get_logger()

PROVIDER_CONFIGS = {
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "key_env": "CYBERTRON_LLM_API_KEY",
        "default_model": "nousresearch/hermes-3-llama-3.1-405b",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "key_env": "OPENAI_API_KEY",
        "default_model": "gpt-4o",
    },
    "anthropic": {
        "base_url": "https://api.anthropic.com/v1",
        "key_env": "ANTHROPIC_API_KEY",
        "default_model": "claude-3-5-sonnet-20241022",
        "headers": {"anthropic-version": "2023-06-01"},
    },
    "google": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "key_env": "GOOGLE_API_KEY",
        "default_model": "gemini-1.5-pro",
    },
    "mistral": {
        "base_url": "https://api.mistral.ai/v1",
        "key_env": "MISTRAL_API_KEY",
        "default_model": "mistral-large-latest",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "key_env": "GROQ_API_KEY",
        "default_model": "llama-3.1-70b-versatile",
    },
    "cohere": {
        "base_url": "https://api.cohere.ai/v1",
        "key_env": "COHERE_API_KEY",
        "default_model": "command-r-plus",
    },
    "azure": {
        "base_url": "",
        "key_env": "AZURE_OPENAI_KEY",
        "default_model": "gpt-4",
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "key_env": "OLLAMA_API_KEY",
        "default_model": "llama3.1",
    },
    "nim": {
        "base_url": "https://integrate.api.nvidia.com/v1",
        "key_env": "NIM_API_KEY",
        "default_model": "nvidia/nemotron-4-340b-instruct",
    },
}

class LLMClient:
    def __init__(self):
        self.provider = os.getenv("CYBERTRON_LLM_PROVIDER", "openrouter")
        cfg = PROVIDER_CONFIGS.get(self.provider, PROVIDER_CONFIGS["openrouter"])
        self.api_key = os.getenv(cfg["key_env"], os.getenv("CYBERTRON_LLM_API_KEY", ""))
        self.model = os.getenv("CYBERTRON_LLM_MODEL", cfg.get("default_model", ""))
        self.base_url = os.getenv("CYBERTRON_LLM_BASE_URL", cfg.get("base_url", ""))
        self.extra_headers = cfg.get("headers", {})
        self.client = httpx.AsyncClient(timeout=120.0)
        self.logger = structlog.get_logger(llm_client=True)

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            if self.provider == "anthropic":
                h["x-api-key"] = self.api_key
            else:
                h["Authorization"] = f"Bearer {self.api_key}"
        h.update(self.extra_headers)
        if self.provider == "openrouter":
            h["HTTP-Referer"] = "https://cybertron.local"
            h["X-Title"] = "Cybertron AI"
        return h

    def _payload(self, messages: List[Dict[str, str]], temperature: float, max_tokens: int, stream: bool) -> dict:
        if self.provider == "anthropic":
            system_msg = ""
            user_msgs = []
            for m in messages:
                if m["role"] == "system":
                    system_msg = m["content"]
                else:
                    user_msgs.append({"role": m["role"], "content": m["content"]})
            payload = {
                "model": self.model,
                "messages": user_msgs,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": stream,
            }
            if system_msg:
                payload["system"] = system_msg
            return payload
        if self.provider == "google":
            contents = []
            for m in messages:
                role = "user" if m["role"] == "user" else "model"
                contents.append({"role": role, "parts": [{"text": m["content"]}]})
            return {
                "contents": contents,
                "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
            }
        if self.provider == "cohere":
            preamble = ""
            chat_history = []
            message = ""
            for m in messages:
                if m["role"] == "system":
                    preamble = m["content"]
                elif m["role"] == "user":
                    if not message:
                        message = m["content"]
                    else:
                        chat_history.append({"role": "USER", "message": m["content"]})
                else:
                    chat_history.append({"role": "CHATBOT", "message": m["content"]})
            payload = {"message": message, "model": self.model, "temperature": temperature, "stream": stream}
            if preamble:
                payload["preamble"] = preamble
            if chat_history:
                payload["chat_history"] = chat_history
            return payload
        return {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }

    def _extract_content(self, data: dict) -> str:
        if self.provider == "anthropic":
            return data.get("content", [{}])[0].get("text", "")
        if self.provider == "google":
            return data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        if self.provider == "cohere":
            return data.get("text", "")
        return data.get("choices", [{}])[0].get("message", {}).get("content", "")

    def _endpoint(self) -> str:
        if self.provider == "anthropic":
            return f"{self.base_url}/messages"
        if self.provider == "google":
            return f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}"
        if self.provider == "cohere":
            return f"{self.base_url}/chat"
        return f"{self.base_url}/chat/completions"

    async def chat_completion(self, messages: List[Dict[str, str]], temperature: float = 0.7, max_tokens: int = 4096, stream: bool = False) -> str:
        if not self.api_key and self.provider not in ("ollama",):
            return json.dumps({"intent": "scan", "target": "example.com", "plugins": ["subdomain_enum", "port_scan"], "options": {}, "reasoning": "LLM offline fallback."})
        payload = self._payload(messages, temperature, max_tokens, stream)
        headers = self._headers()
        try:
            endpoint = self._endpoint()
            resp = await self.client.post(endpoint, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return self._extract_content(data)
        except Exception as e:
            self.logger.error("llm_request_failed", provider=self.provider, error=str(e))
            return json.dumps({"intent": "scan", "target": "example.com", "plugins": ["subdomain_enum"], "options": {}, "reasoning": f"LLM error: {str(e)}"})

    async def stream_completion(self, messages: List[Dict[str, str]], temperature: float = 0.7) -> AsyncGenerator[str, None]:
        if not self.api_key and self.provider not in ("ollama",):
            yield "LLM not configured."
            return
        payload = self._payload(messages, temperature, 4096, True)
        headers = self._headers()
        try:
            endpoint = self._endpoint()
            async with self.client.stream("POST", endpoint, json=payload, headers=headers) as resp:
                async for line in resp.aiter_lines():
                    if self.provider == "anthropic":
                        if line.startswith("data: "):
                            chunk = line[6:]
                            if chunk == "[DONE]":
                                break
                            try:
                                d = json.loads(chunk)
                                if d.get("type") == "content_block_delta":
                                    yield d.get("delta", {}).get("text", "")
                            except:
                                pass
                    else:
                        if line.startswith("data: "):
                            chunk = line[6:]
                            if chunk == "[DONE]":
                                break
                            try:
                                delta = json.loads(chunk)["choices"][0]["delta"].get("content", "")
                                if delta:
                                    yield delta
                            except:
                                pass
        except Exception as e:
            self.logger.error("llm_stream_failed", provider=self.provider, error=str(e))
            yield f"Stream error: {str(e)}"

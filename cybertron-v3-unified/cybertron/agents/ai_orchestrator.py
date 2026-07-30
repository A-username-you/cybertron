"""AI Orchestrator — Nemotron / LLM integration."""
import os
import httpx
import json
from typing import Optional, AsyncGenerator
from cybertron.core.config import CybertronConfig


class AIOrchestrator:
    """Orchestrate AI agents with Nemotron via NIM API."""

    NIM_BASE = "https://integrate.api.nvidia.com/v1"
    DEFAULT_MODEL = "nvidia/nemotron-4-340b-instruct"

    def __init__(self, config: Optional[CybertronConfig] = None):
        self.config = config or CybertronConfig.load()
        self.api_key = self.config.nim_api_key or os.getenv("NIM_API_KEY", "")
        self.history: list = []

    async def chat(self, prompt: str, system: str = "") -> str:
        if not self.api_key:
            return "[AI] NIM API key not configured. Set NIM_API_KEY or use 'cybertron config --set nim_api_key=xxx'"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": self.DEFAULT_MODEL,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 2048,
            "stream": False
        }
        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(f"{self.NIM_BASE}/chat/completions", headers=headers, json=payload, timeout=60)
                data = r.json()
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            return f"[AI] Error: {e}"

    async def stream(self, prompt: str) -> AsyncGenerator[str, None]:
        if not self.api_key:
            yield "[AI] NIM API key not configured."
            return
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": self.DEFAULT_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 2048,
            "stream": True
        }
        try:
            async with httpx.AsyncClient() as client:
                async with client.stream("POST", f"{self.NIM_BASE}/chat/completions", headers=headers, json=payload, timeout=60) as response:
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            chunk = line[6:]
                            if chunk == "[DONE]":
                                break
                            try:
                                obj = json.loads(chunk)
                                delta = obj["choices"][0]["delta"].get("content", "")
                                if delta:
                                    yield delta
                            except Exception:
                                pass
        except Exception as e:
            yield f"[AI] Error: {e}"

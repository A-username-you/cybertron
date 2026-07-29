"""LLM client."""
import os, json
from typing import List, Dict, Any, AsyncGenerator, Optional
import httpx, structlog
logger = structlog.get_logger()
class LLMClient:
    def __init__(self):
        self.provider = os.getenv("CYBERTRON_LLM_PROVIDER","openrouter")
        self.api_key = os.getenv("CYBERTRON_LLM_API_KEY","")
        self.model = os.getenv("CYBERTRON_LLM_MODEL","nousresearch/hermes-3-llama-3.1-405b")
        self.base_url = os.getenv("CYBERTRON_LLM_BASE_URL","https://openrouter.ai/api/v1")
        self.client = httpx.AsyncClient(timeout=60.0)
        self.logger = structlog.get_logger(llm_client=True)
    async def chat_completion(self, messages: List[Dict[str,str]], temperature: float=0.7, max_tokens: int=4096, stream: bool=False) -> str:
        if not self.api_key:
            return json.dumps({"intent":"scan","target":"example.com","plugins":["subdomain_enum","port_scan"],"options":{},"reasoning":"LLM offline fallback."})
        payload = {"model":self.model,"messages":messages,"temperature":temperature,"max_tokens":max_tokens,"stream":stream}
        headers = {"Authorization":f"Bearer {self.api_key}","Content-Type":"application/json","HTTP-Referer":"https://cybertron.local","X-Title":"Cybertron AI"}
        try:
            resp = await self.client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            self.logger.error("llm_request_failed", error=str(e))
            return json.dumps({"intent":"scan","target":"example.com","plugins":["subdomain_enum"],"options":{},"reasoning":f"LLM error: {str(e)}"})
    async def stream_completion(self, messages: List[Dict[str,str]], temperature: float=0.7) -> AsyncGenerator[str,None]:
        if not self.api_key:
            yield "LLM not configured."; return
        payload = {"model":self.model,"messages":messages,"temperature":temperature,"stream":True}
        headers = {"Authorization":f"Bearer {self.api_key}","Content-Type":"application/json"}
        async with self.client.stream("POST", f"{self.base_url}/chat/completions", json=payload, headers=headers) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    chunk = line[6:]
                    if chunk == "[DONE]": break
                    try:
                        delta = json.loads(chunk)["choices"][0]["delta"].get("content","")
                        if delta: yield delta
                    except: pass

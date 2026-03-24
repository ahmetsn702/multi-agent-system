"""
core/llm_client.py
OpenRouter LLM wrapper with async httpx, streaming, and retry logic.
"""
import asyncio
import os
import json
import time
from collections import deque
from typing import AsyncGenerator, Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
MAX_RETRIES = 3


class TokenUsage:
    """Track token usage per agent per session."""

    def __init__(self):
        self._usage: dict[str, dict[str, float]] = {}

    def record(self, agent_id: str, prompt_tokens: int, completion_tokens: int, cost: float = 0.0):
        if agent_id not in self._usage:
            self._usage[agent_id] = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "total_cost": 0.0,
            }
        self._usage[agent_id]["prompt_tokens"] += prompt_tokens
        self._usage[agent_id]["completion_tokens"] += completion_tokens
        self._usage[agent_id]["total_tokens"] += prompt_tokens + completion_tokens
        self._usage[agent_id]["total_cost"] += cost

    def get(self, agent_id: str) -> dict[str, float]:
        return self._usage.get(agent_id, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "total_cost": 0.0})

    def get_all(self) -> dict[str, dict[str, float]]:
        return dict(self._usage)

    def estimated_cost_usd(self) -> float:
        total_cost = 0.0
        for data in self._usage.values():
            total_cost += data.get("total_cost", 0.0)
        return round(total_cost, 6)


# Global token tracker
token_tracker = TokenUsage()


class RateLimiter:
    def __init__(self, max_requests: int = 50, window_seconds: int = 10):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = deque()

    async def acquire(self):
        now = time.time()
        while self.requests and now - self.requests[0] > self.window_seconds:
            self.requests.popleft()

        if len(self.requests) >= self.max_requests:
            wait_time = self.window_seconds - (now - self.requests[0]) + 1
            print(f"[RATE LIMIT] {wait_time:.1f}s bekleniyor...")
            await asyncio.sleep(wait_time)

        self.requests.append(time.time())


_rate_limiter = RateLimiter(max_requests=50, window_seconds=10)


class LLMClient:
    """Async OpenRouter LLM client with streaming and retry support."""

    def __init__(self, agent_id: str = "system"):
        from config.settings import MODEL_ROUTING, TOKEN_BUDGET, PRICING, PROVIDER_CONFIG
        import os

        self.agent_id = agent_id

        # V4: Dual-provider — MODEL_ROUTING artık dict: {"model": ..., "provider": ...}
        routing = MODEL_ROUTING.get(agent_id)
        if isinstance(routing, dict):
            self.model_id = routing["model"]
            provider_name = routing["provider"]
        elif isinstance(routing, str):
            self.model_id = routing
            provider_name = "openrouter"
        else:
            self.model_id = "openai/gpt-4o-mini"
            provider_name = "openrouter"

        self.model_key = self.model_id
        self.provider = provider_name

        # Provider'a göre base_url ve API key belirle
        provider_cfg = PROVIDER_CONFIG.get(provider_name, PROVIDER_CONFIG["openrouter"])
        self.base_url = provider_cfg["base_url"]
        api_key = os.getenv(provider_cfg["env_key"], "")

        if not api_key:
            # Fallback: OpenRouter key'i dene
            api_key = os.getenv("OPENROUTER_API_KEY", "")

        # No-key environments (e.g. local unit tests) should still initialize cleanly.
        self._mock_mode = not bool(api_key)

        self.pricing = PRICING.get(self.model_id, {"input": 0.15, "output": 0.60})
        budget = TOKEN_BUDGET.get(self.model_id, {"max_input": 128000, "max_output": 4000})
        self.token_budget = budget

        # Per-agent output limit
        per_agent = budget.get("per_agent", {})
        self._max_output = per_agent.get(agent_id, budget.get("max_output", 4000))

        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        # OpenRouter'a özel header'lar
        if provider_name == "openrouter":
            self.headers["HTTP-Referer"] = "https://github.com/multi-agent-system"
            self.headers["X-Title"] = "Multi-Agent System"

    def _prepare_payload(
        self,
        messages: list[dict],
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stream: bool = False,
    ) -> dict:
        formatted_messages = []
        if system_prompt:
            formatted_messages.append({"role": "system", "content": system_prompt})

        for msg in messages:
            formatted_messages.append({"role": msg["role"], "content": msg["content"]})

        payload = {
            "model": self.model_id,
            "messages": formatted_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": stream,
        }

        if system_prompt and "json" in system_prompt.lower():
            payload["response_format"] = {"type": "json_object"}

        return payload

    async def complete(
        self,
        messages: list[dict],
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stream: bool = False,
    ) -> str:
        if self._mock_mode:
            # Return a deterministic response for offline/test mode.
            return "Mock response (no API key configured)."

        await _rate_limiter.acquire()

        # V2: respect per-agent output limit
        limit_output = getattr(self, "_max_output", self.token_budget.get("max_output", 4000))
        if max_tokens > limit_output:
            max_tokens = limit_output

        payload = self._prepare_payload(messages, system_prompt, temperature, max_tokens, stream=stream)

        for attempt in range(MAX_RETRIES):
            try:
                if stream:
                    return await self._stream_complete(payload)
                else:
                    return await self._regular_complete(payload)
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    wait_str = e.response.headers.get("Retry-After")
                    wait = int(wait_str) if wait_str else 2 ** attempt * 5
                    print(f"[429] Rate limit! {wait}s bekleniyor...")
                    await asyncio.sleep(wait)
                elif attempt < MAX_RETRIES - 1:
                    wait = 2 ** attempt
                    await asyncio.sleep(wait)
                else:
                    print(f"HTTP ERROR: {e.response.text}")
                    raise
            except Exception as e:
                err_str = str(e)
                if ("Connect" in err_str or "Timeout" in err_str) and attempt < MAX_RETRIES - 1:
                    wait = 2 ** attempt
                    await asyncio.sleep(wait)
                else:
                    raise

        raise RuntimeError("LLM request failed after max retries")

    async def _regular_complete(self, payload: dict) -> str:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                self.base_url,
                headers=self.headers,
                json=payload,
            )
            response.raise_for_status()
            response_body = response.json()

        print(f"[DEBUG] response_body type: {type(response_body)}, keys: {list(response_body.keys()) if isinstance(response_body, dict) else 'N/A'}")
        print(f"[DEBUG] choices: {response_body.get('choices', 'N/A')}")

        usage = response_body.get("usage", {})
        in_tok = usage.get("prompt_tokens", 0)
        out_tok = usage.get("completion_tokens", 0)

        in_cost = self.pricing.get("input", 0.15)
        out_cost = self.pricing.get("output", 0.60)
        cost = (in_tok / 1_000_000) * in_cost + (out_tok / 1_000_000) * out_cost

        token_tracker.record(self.agent_id, in_tok, out_tok, cost)
        print(f"[COST] {self.agent_id} | {self.model_id} | in:{in_tok} out:{out_tok} | ${cost:.6f}")

        result_text = response_body["choices"][0]["message"]["content"]
        print(f"[DEBUG] _extract_text result: {repr(result_text[:200]) if result_text else None}")
        
        return result_text

    async def _stream_complete(self, payload: dict) -> str:
        full_text = ""
        completion_tokens = 0

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                self.base_url,
                headers=self.headers,
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            if "choices" in chunk and len(chunk["choices"]) > 0:
                                delta = chunk["choices"][0].get("delta", {}).get("content", "")
                                if delta:
                                    full_text += delta
                                    completion_tokens += 1
                        except json.JSONDecodeError:
                            continue

        prompt_tokens = len(str(payload.get("messages", ""))) // 4
        in_cost = self.pricing.get("input", 0.15)
        out_cost = self.pricing.get("output", 0.60)
        cost = (prompt_tokens / 1_000_000) * in_cost + (completion_tokens / 1_000_000) * out_cost

        token_tracker.record(self.agent_id, prompt_tokens, completion_tokens, cost)
        print(f"[COST] {self.agent_id} | {self.model_id} | in:{prompt_tokens} out:{completion_tokens} | ${cost:.6f}")

        return full_text

    async def stream_to_console(
        self,
        messages: list[dict],
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        limit_output = self.token_budget.get("max_output", 4096)
        if max_tokens > limit_output:
            max_tokens = limit_output

        payload = self._prepare_payload(messages, system_prompt, temperature, max_tokens, stream=True)

        prompt_tokens = len(str(payload.get("messages", ""))) // 4
        completion_tokens = 0

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                OPENROUTER_BASE_URL,
                headers=self.headers,
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            if "choices" in chunk and len(chunk["choices"]) > 0:
                                delta = chunk["choices"][0].get("delta", {}).get("content", "")
                                if delta:
                                    yield delta
                                    completion_tokens += 1
                                    await asyncio.sleep(0)
                        except json.JSONDecodeError:
                            continue

        in_cost = self.pricing.get("input", 0.15)
        out_cost = self.pricing.get("output", 0.60)
        cost = (prompt_tokens / 1_000_000) * in_cost + (completion_tokens / 1_000_000) * out_cost

        token_tracker.record(self.agent_id, prompt_tokens, completion_tokens, cost)
        print(f"[COST] {self.agent_id} | {self.model_id} | in:{prompt_tokens} out:{completion_tokens} | ${cost:.6f}")

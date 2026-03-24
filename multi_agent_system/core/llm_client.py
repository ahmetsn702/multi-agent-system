"""
core/llm_client.py
Blackbox/OpenAI-compatible LLM wrapper with async httpx, streaming, and retry logic.
"""
import asyncio
import os
import json
import time
from collections import deque
from typing import AsyncGenerator, Optional

import httpx
from dotenv import load_dotenv

try:
    from google import genai
    from google.genai import errors as genai_errors
    VERTEX_RETRY_EXCEPTIONS = (genai_errors.APIError,)
except Exception:  # pragma: no cover - Vertex AI opsiyonel import
    genai = None
    genai_errors = None
    VERTEX_RETRY_EXCEPTIONS = ()

try:
    from google.api_core.exceptions import (
        DeadlineExceeded,
        GoogleAPICallError,
        ResourceExhausted,
        ServiceUnavailable,
    )
    VERTEX_RETRY_EXCEPTIONS = VERTEX_RETRY_EXCEPTIONS + (
        ResourceExhausted,
        ServiceUnavailable,
        DeadlineExceeded,
        GoogleAPICallError,
    )
except Exception:  # pragma: no cover - Vertex AI opsiyonel import
    pass

if not VERTEX_RETRY_EXCEPTIONS:  # pragma: no cover - Vertex AI opsiyonel import
    VERTEX_RETRY_EXCEPTIONS = (Exception,)

load_dotenv()

# OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
# OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
BLACKBOX_API_KEY = os.getenv("BLACKBOX_API_KEY", "")
BLACKBOX_BASE_URL = "https://api.blackbox.ai/chat/completions"
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

    def reset(self) -> None:
        """Tum oturum token ve maliyet sayaçlarini sifirla."""
        self._usage = {}


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


def _resolve_model_routing(agent_id: str) -> tuple[str, str]:
    from config.settings import MODEL_ROUTING

    routing = MODEL_ROUTING.get(agent_id)
    if isinstance(routing, dict):
        return routing.get("model", "openai/gpt-4o-mini"), routing.get("provider", "blackbox")
    if isinstance(routing, str):
        return routing, "blackbox"
    return "openai/gpt-4o-mini", "blackbox"


def _resolve_model_settings(model_id: str, agent_id: str) -> tuple[dict, dict, int, float]:
    from config.settings import MODEL_TIMEOUTS, PRICING, TOKEN_BUDGET

    pricing = PRICING.get(model_id, {"input": 0.15, "output": 0.60})
    budget = TOKEN_BUDGET.get(model_id, {"max_input": 128000, "max_output": 4000})
    per_agent = budget.get("per_agent", {})
    max_output = per_agent.get(agent_id, budget.get("max_output", 4000))
    timeout = MODEL_TIMEOUTS.get(model_id, 120.0)
    return pricing, budget, max_output, timeout


def _estimate_tokens(payload: object) -> int:
    text = str(payload)
    if not text:
        return 0
    return max(len(text) // 4, 1)


class VertexAIClient:
    """Async wrapper around Vertex AI Gemini models via google-genai SDK."""

    _client_cls = None
    _generation_config_cls = None
    _model_aliases = {
        "gemini-2.0-flash": "gemini-2.0-flash-001",
        "gemini-3.1-pro-preview": "gemini-3.1-pro-preview",
    }

    def __init__(self, agent_id: str = "system"):
        self.agent_id = agent_id
        self.model_id, self.provider = _resolve_model_routing(agent_id)
        self.model_key = self.model_id
        self.base_url = "vertexai"
        self.headers: dict[str, str] = {}
        self.pricing, self.token_budget, self._max_output, self.timeout = _resolve_model_settings(self.model_id, agent_id)

        self.project = os.getenv("VERTEX_PROJECT", "maos-ai-project").strip() or "maos-ai-project"
        self.location = os.getenv("VERTEX_LOCATION", "us-central1").strip() or "us-central1"
        self._ensure_vertex_initialized()
        self._model_name = self._normalize_vertex_model_name(self.model_id)
        self._client = self._client_cls(
            vertexai=True,
            project=self.project,
            location=self.location,
            http_options={"timeout": int(self.timeout * 1000)},
        )

        if self.timeout != 120.0:
            print(f"[LLM] {self.model_id} için özel timeout: {self.timeout}s")

    @classmethod
    def _ensure_vertex_initialized(cls) -> None:
        if cls._client_cls is not None:
            return

        if genai is None:
            raise ImportError("google-genai paketi yüklü değil. `pip install google-genai` çalıştırın.")

        cls._client_cls = genai.Client
        cls._generation_config_cls = genai.types.GenerateContentConfig

    @classmethod
    def _normalize_vertex_model_name(cls, model_id: str) -> str:
        for prefix in ("publishers/google/models/", "models/"):
            if model_id.startswith(prefix):
                model_id = model_id[len(prefix):]
                break
        return cls._model_aliases.get(model_id, model_id)

    def _prepare_prompt(self, messages: list[dict], system_prompt: Optional[str] = None) -> str:
        sections: list[str] = []
        if system_prompt:
            sections.append(f"[SYSTEM]\n{system_prompt}")

        for msg in messages:
            role = str(msg.get("role", "user")).upper()
            content = str(msg.get("content", ""))
            sections.append(f"[{role}]\n{content}")

        sections.append("[ASSISTANT]")
        return "\n\n".join(sections)

    def _prepare_generation_config(self, temperature: float, max_tokens: int, extra_config: Optional[dict] = None):
        config_kwargs = {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        }
        
        # Merge extra_config if provided (for tools like Google Search)
        if extra_config:
            config_kwargs.update(extra_config)
        
        return self._generation_config_cls(**config_kwargs)


    def _extract_text(self, response) -> str:
        result_text = ""
        candidates = getattr(response, "candidates", []) or []
        if candidates:
            content = getattr(candidates[0], "content", None)
            for part in getattr(content, "parts", []) or []:
                if hasattr(part, "text") and part.text:
                    result_text += part.text

        if result_text:
            return result_text

        try:
            text = getattr(response, "text", "")
            if text:
                return text
        except Exception:
            pass

        parts: list[str] = []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            for part in getattr(content, "parts", []) or []:
                part_text = getattr(part, "text", "")
                if part_text:
                    parts.append(part_text)
        return "".join(parts)

    def _extract_usage(self, response, prompt_tokens: int, completion_tokens: int) -> tuple[int, int]:
        usage = getattr(response, "usage_metadata", None)
        if usage is None:
            return prompt_tokens, completion_tokens

        prompt_count = getattr(usage, "prompt_token_count", None)
        candidate_count = getattr(usage, "candidates_token_count", None)
        if prompt_count is not None:
            prompt_tokens = int(prompt_count)
        if candidate_count is not None:
            completion_tokens = int(candidate_count)
        return prompt_tokens, completion_tokens

    def _record_usage(self, prompt_tokens: int, completion_tokens: int) -> None:
        in_cost = self.pricing.get("input", 0.15)
        out_cost = self.pricing.get("output", 0.60)
        cost = (prompt_tokens / 1_000_000) * in_cost + (completion_tokens / 1_000_000) * out_cost
        token_tracker.record(self.agent_id, prompt_tokens, completion_tokens, cost)
        print(f"[COST] {self.agent_id} | {self.model_id} | in:{prompt_tokens} out:{completion_tokens} | ${cost:.6f}")

    @staticmethod
    def _retry_wait(exc: Exception, attempt: int) -> int:
        if getattr(exc, "code", None) == 429:
            return 30
        return 2 ** attempt

    async def complete(
        self,
        messages: list[dict],
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stream: bool = False,
        extra_config: Optional[dict] = None,
    ) -> str:
        await _rate_limiter.acquire()

        if max_tokens > self._max_output:
            max_tokens = self._max_output

        prompt = self._prepare_prompt(messages, system_prompt)
        generation_config = self._prepare_generation_config(temperature, max_tokens, extra_config)

        for attempt in range(MAX_RETRIES):
            try:
                if stream:
                    return await self._stream_complete(prompt, generation_config)
                return await self._regular_complete(prompt, generation_config)
            except VERTEX_RETRY_EXCEPTIONS as exc:
                if attempt < MAX_RETRIES - 1:
                    wait = self._retry_wait(exc, attempt)
                    print(f"[VERTEX RETRY] {type(exc).__name__}: {exc} | {wait}s bekleniyor...")
                    await asyncio.sleep(wait)
                else:
                    raise
            except Exception:
                if attempt < MAX_RETRIES - 1:
                    wait = 2 ** attempt
                    await asyncio.sleep(wait)
                else:
                    raise

        raise RuntimeError("Vertex AI request failed after max retries")

    async def _regular_complete(self, prompt: str, generation_config) -> str:
        response = await self._client.aio.models.generate_content(
            model=self._model_name,
            contents=prompt,
            config=generation_config,
        )

        text = self._extract_text(response)
        prompt_tokens = _estimate_tokens(prompt)
        completion_tokens = _estimate_tokens(text)
        prompt_tokens, completion_tokens = self._extract_usage(response, prompt_tokens, completion_tokens)
        self._record_usage(prompt_tokens, completion_tokens)
        return text

    async def _stream_complete(self, prompt: str, generation_config) -> str:
        full_text: list[str] = []
        last_chunk = None
        async for chunk in self._client.aio.models.generate_content_stream(
            model=self._model_name,
            contents=prompt,
            config=generation_config,
        ):
            last_chunk = chunk
            piece = self._extract_text(chunk)
            if piece:
                full_text.append(piece)

        text = "".join(full_text)
        prompt_tokens = _estimate_tokens(prompt)
        completion_tokens = _estimate_tokens(text)
        if last_chunk is not None:
            prompt_tokens, completion_tokens = self._extract_usage(last_chunk, prompt_tokens, completion_tokens)
        self._record_usage(prompt_tokens, completion_tokens)
        return text

    async def stream_to_console(
        self,
        messages: list[dict],
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        text = await self.complete(
            messages,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        if text:
            yield text


class LLMClient:
    """Async Blackbox-compatible LLM client with streaming and retry support."""

    def __new__(cls, agent_id: str = "system"):
        if cls is LLMClient:
            _, provider_name = _resolve_model_routing(agent_id)
            if provider_name == "vertex":
                return VertexAIClient(agent_id)
        return super().__new__(cls)

    def __init__(self, agent_id: str = "system"):
        from config.settings import PROVIDER_CONFIG

        self.agent_id = agent_id
        self.model_id, provider_name = _resolve_model_routing(agent_id)
        self.model_key = self.model_id
        self.provider = provider_name

        # Provider'a göre base_url ve API key belirle
        provider_cfg = PROVIDER_CONFIG.get(provider_name)
        if not provider_cfg:
            # Fallback to blackbox if provider not found
            provider_cfg = PROVIDER_CONFIG.get("blackbox", {
                "base_url": "https://api.blackbox.ai/chat/completions",
                "env_key": "BLACKBOX_API_KEY",
            })
        self.base_url = provider_cfg.get("base_url", "")
        api_key = os.getenv(provider_cfg.get("env_key", ""), "")

        if not api_key:
            # Fallback: OpenRouter key'i dene
            api_key = os.getenv("BLACKBOX_API_KEY", "")
            if not api_key:
                raise ValueError(f"API key bulunamadı: {provider_cfg['env_key']}")

        self.pricing, self.token_budget, self._max_output, self.timeout = _resolve_model_settings(self.model_id, agent_id)

        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        # OpenRouter'a özel header'lar
        if provider_name == "openrouter":
            self.headers["HTTP-Referer"] = "https://github.com/multi-agent-system"
            self.headers["X-Title"] = "Multi-Agent System"

        if self.timeout != 120.0:
            print(f"[LLM] {self.model_id} için özel timeout: {self.timeout}s")

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

        return payload

    async def complete(
        self,
        messages: list[dict],
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stream: bool = False,
        extra_config: Optional[dict] = None,
    ) -> str:
        await _rate_limiter.acquire()

        # V2: respect per-agent output limit
        limit_output = getattr(self, "_max_output", self.token_budget.get("max_output", 4000))
        if max_tokens > limit_output:
            max_tokens = limit_output

        # Note: extra_config is ignored for non-Vertex providers
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
                    wait = int(wait_str) if wait_str else 2 ** attempt * 30
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
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                self.base_url,
                headers=self.headers,
                json=payload,
            )
            response.raise_for_status()
            response_body = response.json()

        usage = response_body.get("usage", {})
        in_tok = usage.get("prompt_tokens", 0)
        out_tok = usage.get("completion_tokens", 0)

        in_cost = self.pricing.get("input", 0.15)
        out_cost = self.pricing.get("output", 0.60)
        cost = (in_tok / 1_000_000) * in_cost + (out_tok / 1_000_000) * out_cost

        token_tracker.record(self.agent_id, in_tok, out_tok, cost)
        print(f"[COST] {self.agent_id} | {self.model_id} | in:{in_tok} out:{out_tok} | ${cost:.6f}")

        return response_body["choices"][0]["message"]["content"]

    async def _stream_complete(self, payload: dict) -> str:
        full_text = ""
        completion_tokens = 0

        async with httpx.AsyncClient(timeout=self.timeout) as client:
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

        async with httpx.AsyncClient(timeout=self.timeout) as client:
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



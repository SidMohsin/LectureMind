"""LLM provider abstraction.

The application owns retrieval, prompts, validation and persistence; a provider
only turns (system, user) messages into a JSON object. The first implementation
speaks the OpenAI-compatible Chat Completions API, which OpenAI, Groq, Gemini's
OpenAI endpoint and local servers such as Ollama all expose.
"""

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import urlparse

import httpx

from app.core.config import Settings

logger = logging.getLogger(__name__)


class LLMError(Exception):
    def __init__(self, code: str, message: str, *, retryable: bool, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details or {}


@dataclass
class LLMUsage:
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    milliseconds: int = 0
    rate_limited_seconds: float = 0.0
    per_call: list[dict] = field(default_factory=list)


class LLMProvider(Protocol):
    name: str
    model: str

    async def generate_json(self, system: str, user: str, *, max_tokens: int = 4096) -> dict: ...


def _retry_after(response: httpx.Response) -> float:
    """Seconds the provider asks us to wait (Retry-After header), bounded to 1-90s."""
    try:
        seconds = float(response.headers.get("retry-after", "10"))
    except ValueError:
        seconds = 10.0
    return min(max(seconds, 1.0), 90.0)


def _strip_fences(text: str) -> str:
    text = text.strip()
    match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    return match.group(1) if match else text


class OpenAICompatibleProvider:
    def __init__(self, http: httpx.AsyncClient, settings: Settings):
        self._http = http
        self._url = settings.llm_base_url.rstrip("/") + "/chat/completions"
        self._key = settings.llm_api_key
        self._timeout = settings.llm_timeout_seconds
        self.temperature = settings.llm_temperature
        self.model = settings.llm_model
        self.name = urlparse(settings.llm_base_url).hostname or "openai-compatible"
        self.usage = LLMUsage()
        self._rate_limit_retries = settings.llm_rate_limit_retries
        self.reasoning_effort = settings.llm_reasoning_effort

    async def _post(self, body: dict, headers: dict) -> httpx.Response:
        """POST once, waiting out rate limits (HTTP 429) as the provider instructs."""
        for attempt in range(self._rate_limit_retries + 1):
            try:
                response = await self._http.post(self._url, json=body, headers=headers, timeout=self._timeout)
            except httpx.TimeoutException as exc:
                raise LLMError("llm_timeout", "The language model took too long to respond.", retryable=True) from exc
            except httpx.HTTPError as exc:
                raise LLMError("llm_unreachable", "The language model service couldn't be reached.", retryable=True) from exc
            if response.status_code != 429 or attempt == self._rate_limit_retries:
                return response
            wait = _retry_after(response)
            self.usage.rate_limited_seconds += wait
            logger.info("LLM rate limited; waiting %.1fs before retrying", wait)
            await asyncio.sleep(wait)
        return response

    async def generate_json(self, system: str, user: str, *, max_tokens: int = 4096) -> dict:
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": self.temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        if self.reasoning_effort:
            # Reasoning models spend output tokens thinking; a lower effort leaves room for the answer.
            body["reasoning_effort"] = self.reasoning_effort
        headers = {"Authorization": f"Bearer {self._key}"} if self._key else {}
        started = time.monotonic()
        response = await self._post(body, headers)
        elapsed = int((time.monotonic() - started) * 1000)

        if response.status_code == 413:
            raise LLMError(
                "llm_request_too_large",
                "A request was larger than the language model provider allows. Lower LLM_WINDOW_TOKENS "
                "and/or LLM_MAX_OUTPUT_TOKENS in the server configuration.",
                retryable=False,
                details={"status": 413, "body": response.text[:300]},
            )
        if response.status_code == 400 and "json_validate_failed" in response.text:
            # The provider's JSON mode rejected what the model produced (often an empty or
            # truncated answer). That's a bad generation, not a bad configuration.
            raise LLMError(
                "llm_invalid_output", "The language model returned invalid JSON.", retryable=True,
                details={"status": 400, "body": response.text[:300]},
            )
        if response.status_code == 429 or response.status_code >= 500:
            raise LLMError(
                "llm_unavailable",
                "The language model service is busy or unavailable.",
                retryable=True,
                details={"status": response.status_code, "body": response.text[:300]},
            )
        if response.status_code >= 400:
            raise LLMError(
                "llm_rejected",
                "The language model service rejected the request. Check the LLM configuration.",
                retryable=False,
                details={"status": response.status_code, "body": response.text[:300]},
            )

        data = response.json()
        usage = data.get("usage") or {}
        self.usage.calls += 1
        self.usage.prompt_tokens += usage.get("prompt_tokens") or 0
        self.usage.completion_tokens += usage.get("completion_tokens") or 0
        self.usage.milliseconds += elapsed
        finish = ((data.get("choices") or [{}])[0] or {}).get("finish_reason")
        self.usage.per_call.append(
            {"ms": elapsed, "finish_reason": finish, **{k: usage.get(k) for k in ("prompt_tokens", "completion_tokens")}}
        )

        try:
            content = data["choices"][0]["message"]["content"] or ""
            parsed = json.loads(_strip_fences(content))
        except (KeyError, IndexError, json.JSONDecodeError) as exc:
            raise LLMError(
                "llm_invalid_output", "The language model returned invalid JSON.", retryable=True,
                details={"content": str(data)[:300]},
            ) from exc
        if not isinstance(parsed, dict):
            raise LLMError("llm_invalid_output", "The language model returned invalid JSON.", retryable=True)
        return parsed

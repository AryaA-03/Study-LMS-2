"""Unified async LLM Gateway with pooled HTTP client, per-provider RPM pacer, 429 retry/backoff, and Ollama support."""

import asyncio
import logging
import os
import random
import time
from typing import Any, Dict, Optional, Tuple

import httpx

from backend.config import get_settings
from backend.infra.net_guard import validate_ollama_url, validate_public_url

logger = logging.getLogger("learn_lms.llm_gateway")

RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


class _ProviderPacer:
    """Lightweight per-provider RPM pacer so background queues don't burst into 429s."""

    def __init__(self) -> None:
        self._last_call: Dict[str, float] = {}
        self._locks: Dict[str, asyncio.Lock] = {}

    def _min_interval(self, provider: str) -> float:
        defaults = {"gemini": 15.0, "groq": 25.0, "openrouter": 20.0, "ollama": 120.0}
        env_key = f"{provider.upper()}_RPM"
        try:
            rpm = float(os.getenv(env_key, str(defaults.get(provider, 30.0))))
        except ValueError:
            rpm = defaults.get(provider, 30.0)
        if rpm <= 0:
            return 0.0
        return 60.0 / rpm

    async def wait(self, provider: str) -> None:
        if os.getenv("PYTEST_CURRENT_TEST"):
            return
        min_gap = self._min_interval(provider)
        if min_gap <= 0:
            return
        lock = self._locks.setdefault(provider, asyncio.Lock())
        async with lock:
            now = time.monotonic()
            last = self._last_call.get(provider, 0.0)
            wait_sec = min_gap - (now - last)
            if wait_sec > 0:
                await asyncio.sleep(min(wait_sec, 6.0))
            self._last_call[provider] = time.monotonic()


class LLMGateway:
    """Single entry point for all LLM completions across Gemini, Groq, OpenRouter, and Ollama."""

    def __init__(self, timeout: float = 45.0, max_retries: int = 3):
        self.timeout = timeout
        self.max_retries = max_retries
        self._client: Optional[httpx.AsyncClient] = None
        self._pacer = _ProviderPacer()

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    async def _post_with_retry(
        self,
        client: httpx.AsyncClient,
        provider: str,
        url: str,
        payload: Dict[str, Any],
        headers: Dict[str, str],
    ) -> httpx.Response:
        last_exc: Optional[Exception] = None
        for attempt in range(self.max_retries):
            await self._pacer.wait(provider)
            try:
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code not in RETRYABLE_STATUSES:
                    return resp
                retry_after = resp.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    delay = min(float(retry_after), 15.0)
                else:
                    delay = min(2**attempt + random.uniform(0.1, 0.5), 10.0)
                if attempt < self.max_retries - 1:
                    logger.warning(f"LLM [{provider}] HTTP {resp.status_code} on attempt {attempt+1}, retrying in {delay:.1f}s")
                    await asyncio.sleep(delay)
                else:
                    return resp
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_exc = exc
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(min(2**attempt, 8.0))
                else:
                    raise
        if last_exc:
            raise last_exc
        raise RuntimeError("LLM request exhausted retries")

    async def generate_text(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        json_mode: bool = False,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        user_secrets: Optional[Dict[str, str]] = None,
    ) -> Tuple[Optional[str], Optional[str]]:
        """Try configured providers in priority order: Gemini -> Groq -> OpenRouter -> Ollama.

        Accepts optional per-request `user_secrets` (decrypted BYOK keys for hosted mode).
        Returns: (text_output, provider_model_used) or (None, None) if no provider succeeded.
        """
        s = get_settings()
        sec = user_secrets or {}
        gemini_key = sec.get("gemini") or s.GEMINI_API_KEY
        groq_key = sec.get("groq") or s.GROQ_API_KEY
        openrouter_key = sec.get("openrouter") or s.OPENROUTER_API_KEY
        ollama_raw = sec.get("ollama_base_url") or s.OLLAMA_BASE_URL

        client = self._get_client()

        # 1. Gemini (x-goog-api-key header — never in URL query string)
        if gemini_key:
            model = s.GEMINI_MODEL
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            body: Dict[str, Any] = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": temperature,
                    "maxOutputTokens": max_tokens,
                },
            }
            if system_instruction:
                body["systemInstruction"] = {"parts": [{"text": system_instruction}]}
            if json_mode:
                body["generationConfig"]["responseMimeType"] = "application/json"
            try:
                resp = await self._post_with_retry(
                    client, "gemini", url, body, {"x-goog-api-key": gemini_key}
                )
                if resp.status_code == 200:
                    data = resp.json()
                    candidates = data.get("candidates") or []
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts") or []
                        if parts and parts[0].get("text"):
                            return parts[0]["text"], f"gemini:{model}"
            except Exception as exc:
                logger.warning(f"Gemini call failed ({type(exc).__name__})")

        # 2. Groq (OpenAI-compatible)
        if groq_key:
            model = s.GROQ_MODEL
            messages = []
            if system_instruction:
                messages.append({"role": "system", "content": system_instruction})
            messages.append({"role": "user", "content": prompt})
            body = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if json_mode:
                body["response_format"] = {"type": "json_object"}
            try:
                resp = await self._post_with_retry(
                    client,
                    "groq",
                    "https://api.groq.com/openai/v1/chat/completions",
                    body,
                    {"Authorization": f"Bearer {groq_key}"},
                )
                if resp.status_code == 200:
                    choices = resp.json().get("choices") or []
                    if choices and choices[0].get("message", {}).get("content"):
                        return choices[0]["message"]["content"], f"groq:{model}"
            except Exception as exc:
                logger.warning(f"Groq call failed ({type(exc).__name__})")

        # 3. OpenRouter (OpenAI-compatible)
        if openrouter_key:
            model = s.OPENROUTER_MODEL
            try:
                base_url = validate_public_url(s.OPENROUTER_BASE_URL.rstrip("/"))
            except Exception:
                base_url = "https://openrouter.ai/api/v1"
            messages = []
            if system_instruction:
                messages.append({"role": "system", "content": system_instruction})
            messages.append({"role": "user", "content": prompt})
            body = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            try:
                resp = await self._post_with_retry(
                    client,
                    "openrouter",
                    f"{base_url}/chat/completions",
                    body,
                    {"Authorization": f"Bearer {openrouter_key}"},
                )
                if resp.status_code == 200:
                    choices = resp.json().get("choices") or []
                    if choices and choices[0].get("message", {}).get("content"):
                        return choices[0]["message"]["content"], f"openrouter:{model}"
            except Exception as exc:
                logger.warning(f"OpenRouter call failed ({type(exc).__name__})")

        # 4. Local Ollama fallback (loopback-only in local mode)
        if ollama_raw and os.getenv("AUTH_MODE", "local").strip().lower() == "local":
            try:
                ollama_base = validate_ollama_url(ollama_raw, auth_mode="local")
                model = s.OLLAMA_MODEL
                messages = []
                if system_instruction:
                    messages.append({"role": "system", "content": system_instruction})
                messages.append({"role": "user", "content": prompt})
                body = {"model": model, "messages": messages, "stream": False}
                if json_mode:
                    body["format"] = "json"
                resp = await client.post(f"{ollama_base}/api/chat", json=body, timeout=15.0)
                if resp.status_code == 200:
                    msg = resp.json().get("message", {}).get("content")
                    if msg:
                        return msg, f"ollama:{model}"
            except Exception:
                pass

        return None, None


_default_gateway = LLMGateway()


def get_llm_gateway() -> LLMGateway:
    return _default_gateway

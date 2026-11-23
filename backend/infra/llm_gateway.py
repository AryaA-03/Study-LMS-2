"""Unified async LLM Gateway with header auth, user-configured models, 429 retry/backoff, and Ollama support."""

import asyncio
import logging
import random
from typing import Any, Dict, Optional, Tuple

import httpx

from backend.config import get_settings
from backend.infra.net_guard import validate_ollama_url

logger = logging.getLogger("learn_lms.llm_gateway")

RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


class LLMGateway:
    """Single entry point for all LLM completions across Gemini, Groq, OpenRouter, and Ollama."""

    def __init__(self, timeout: float = 45.0, max_retries: int = 3):
        self.timeout = timeout
        self.max_retries = max_retries

    async def _post_with_retry(
        self,
        client: httpx.AsyncClient,
        url: str,
        payload: Dict[str, Any],
        headers: Dict[str, str],
    ) -> httpx.Response:
        last_exc: Optional[Exception] = None
        for attempt in range(self.max_retries):
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
                    logger.warning(f"LLM HTTP {resp.status_code} on attempt {attempt+1}, retrying in {delay:.1f}s")
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
    ) -> Tuple[Optional[str], Optional[str]]:
        """Try configured providers in priority order: Gemini -> Groq -> OpenRouter -> Ollama.

        Returns: (text_output, provider_model_used) or (None, None) if no provider succeeded.
        """
        s = get_settings()
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            # 1. Gemini (x-goog-api-key header — never in URL query string)
            if s.GEMINI_API_KEY:
                model = s.GEMINI_MODEL
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
                body: Dict[str, Any] = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": temperature},
                }
                if system_instruction:
                    body["systemInstruction"] = {"parts": [{"text": system_instruction}]}
                if json_mode:
                    body["generationConfig"]["responseMimeType"] = "application/json"
                try:
                    resp = await self._post_with_retry(
                        client, url, body, {"x-goog-api-key": s.GEMINI_API_KEY}
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
            if s.GROQ_API_KEY:
                model = s.GROQ_MODEL
                messages = []
                if system_instruction:
                    messages.append({"role": "system", "content": system_instruction})
                messages.append({"role": "user", "content": prompt})
                body = {"model": model, "messages": messages, "temperature": temperature}
                if json_mode:
                    body["response_format"] = {"type": "json_object"}
                try:
                    resp = await self._post_with_retry(
                        client,
                        "https://api.groq.com/openai/v1/chat/completions",
                        body,
                        {"Authorization": f"Bearer {s.GROQ_API_KEY}"},
                    )
                    if resp.status_code == 200:
                        choices = resp.json().get("choices") or []
                        if choices and choices[0].get("message", {}).get("content"):
                            return choices[0]["message"]["content"], f"groq:{model}"
                except Exception as exc:
                    logger.warning(f"Groq call failed ({type(exc).__name__})")

            # 3. OpenRouter (OpenAI-compatible)
            if s.OPENROUTER_API_KEY:
                model = s.OPENROUTER_MODEL
                base_url = s.OPENROUTER_BASE_URL.rstrip("/")
                messages = []
                if system_instruction:
                    messages.append({"role": "system", "content": system_instruction})
                messages.append({"role": "user", "content": prompt})
                body = {"model": model, "messages": messages, "temperature": temperature}
                try:
                    resp = await self._post_with_retry(
                        client,
                        f"{base_url}/chat/completions",
                        body,
                        {"Authorization": f"Bearer {s.OPENROUTER_API_KEY}"},
                    )
                    if resp.status_code == 200:
                        choices = resp.json().get("choices") or []
                        if choices and choices[0].get("message", {}).get("content"):
                            return choices[0]["message"]["content"], f"openrouter:{model}"
                except Exception as exc:
                    logger.warning(f"OpenRouter call failed ({type(exc).__name__})")

            # 4. Local Ollama fallback (loopback-only)
            try:
                ollama_base = validate_ollama_url(s.OLLAMA_BASE_URL)
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

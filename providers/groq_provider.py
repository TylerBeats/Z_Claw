"""
Groq provider — Tier 2.5 external API.
Runs Llama 3.3 70B via Groq's LPU inference (very fast, generous free tier).
Used for escalation reasoning and digest synthesis when Ollama is offline.
Requires GROQ_API_KEY in environment.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from typing import Any

from providers.base import BaseProvider, ProviderError

log = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "llama-3.3-70b-versatile"


class GroqProvider(BaseProvider):
    """
    Groq LPU inference via OpenAI-compatible REST API.
    Free tier: 14,400 requests/day, 6,000 tokens/min.
    No extra packages required — uses urllib.
    """

    def __init__(self, model: str | None = None):
        self._model = model or os.getenv("GROQ_MODEL", DEFAULT_MODEL)

    @property
    def provider_id(self) -> str:
        return f"groq:{self._model}"

    def is_available(self) -> bool:
        return bool(os.getenv("GROQ_API_KEY", "").strip())

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 2048,
        json_mode: bool = False,
    ) -> str:
        api_key = os.getenv("GROQ_API_KEY", "").strip()
        if not api_key:
            raise ProviderError("GROQ_API_KEY not set — Groq unavailable", retryable=False)

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        try:
            body = json.dumps(payload).encode()
            req = urllib.request.Request(
                GROQ_API_URL,
                data=body,
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                    "User-Agent": "J_Claw/1.0",
                },
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
            return data["choices"][0]["message"]["content"].strip()

        except urllib.error.HTTPError as e:
            body_text = e.read().decode(errors="replace")
            log.error("GroqProvider HTTP %s: %s", e.code, body_text[:300])
            retryable = e.code in (429, 503)
            raise ProviderError(f"Groq HTTP {e.code}: {body_text[:200]}", retryable=retryable) from e
        except Exception as e:
            log.error("GroqProvider chat failed: %s", e)
            raise ProviderError(str(e), retryable=False) from e

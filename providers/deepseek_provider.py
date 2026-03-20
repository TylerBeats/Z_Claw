"""
DeepSeek provider — Tier 2.7 external API (backup to Groq).
Runs DeepSeek V3 — rivals GPT-4o at ~$0.27/1M input tokens.
Used as fallback when Groq is rate-limited.
Requires DEEPSEEK_API_KEY in environment.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from typing import Any

from providers.base import BaseProvider, ProviderError

log = logging.getLogger(__name__)

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = "deepseek-chat"


class DeepSeekProvider(BaseProvider):
    """
    DeepSeek V3 via OpenAI-compatible REST API.
    Paid only — but effectively free at J_Claw's usage volume (<$0.01/day).
    No extra packages required — uses urllib.
    """

    def __init__(self, model: str | None = None):
        self._model = model or os.getenv("DEEPSEEK_MODEL", DEFAULT_MODEL)

    @property
    def provider_id(self) -> str:
        return f"deepseek:{self._model}"

    def is_available(self) -> bool:
        return bool(os.getenv("DEEPSEEK_API_KEY", "").strip())

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 2048,
        json_mode: bool = False,
    ) -> str:
        api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        if not api_key:
            raise ProviderError("DEEPSEEK_API_KEY not set — DeepSeek unavailable", retryable=False)

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
                DEEPSEEK_API_URL,
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
            log.error("DeepSeekProvider HTTP %s: %s", e.code, body_text[:300])
            retryable = e.code in (429, 503)
            raise ProviderError(f"DeepSeek HTTP {e.code}: {body_text[:200]}", retryable=retryable) from e
        except Exception as e:
            log.error("DeepSeekProvider chat failed: %s", e)
            raise ProviderError(str(e), retryable=False) from e

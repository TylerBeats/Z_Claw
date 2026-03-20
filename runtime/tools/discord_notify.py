"""
Discord webhook notification utility.
Posts escalation alerts to a Discord channel via webhook.
Webhook URL is read from the .env file (DISCORD_WEBHOOK_URL).
"""

import json
import logging
import os
import urllib.request
from pathlib import Path

log = logging.getLogger(__name__)

_ENV_FILE = Path(__file__).parents[2] / ".env"


def _get_webhook_url() -> str | None:
    # 1. Check environment variable first
    url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if url:
        return url

    # 2. Fall back to reading .env file directly
    try:
        for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("DISCORD_WEBHOOK_URL="):
                url = line.split("=", 1)[1].strip().strip('"').strip("'")
                if url:
                    return url
    except Exception:
        pass

    return None


def notify(message: str) -> bool:
    """
    Post a message to the configured Discord webhook channel.
    Returns True on success, False on any failure (never raises).
    """
    url = _get_webhook_url()
    if not url:
        log.warning("discord_notify: DISCORD_WEBHOOK_URL not set — skipping notification")
        return False

    try:
        body = json.dumps({"content": message[:2000]}).encode()
        req = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "User-Agent": "J_Claw/1.0",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
        return True
    except Exception as e:
        log.error("discord_notify: webhook POST failed: %s", e)
        return False


def _enrich_via_groq(division: str, skill: str, reason: str,
                     action_items: list | None = None) -> str | None:
    """
    Use Groq (Llama 3.3 70B) to rewrite the escalation into a clear,
    actionable Discord alert. Returns enriched text or None on failure.
    """
    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not groq_key:
        return None

    items_text = ""
    if action_items:
        items_text = "\nAction items:\n" + "\n".join(
            f"- {(i.get('description', i) if isinstance(i, dict) else str(i))[:200]}"
            for i in action_items[:5]
        )

    messages = [
        {
            "role": "system",
            "content": (
                "You are J_Claw, an AI orchestrator writing a Discord escalation alert for Matthew. "
                "Rewrite the escalation into 2-3 concise sentences. "
                "Be direct: state what happened, why it matters, and what Matthew should do. "
                "No filler. No generic advice. Output only the alert text — no labels or headers."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Division: {division.upper()} | Skill: {skill}\n"
                f"Reason: {reason}{items_text}"
            ),
        },
    ]

    try:
        payload = json.dumps({
            "model": "llama-3.3-70b-versatile",
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 200,
        }).encode()
        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {groq_key}",
                "User-Agent": "J_Claw/1.0",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        log.warning("Groq escalation enrichment failed (using plain format): %s", e)
        return None


def notify_escalation(division: str, skill: str, reason: str,
                      action_items: list | None = None) -> bool:
    """
    Convenience wrapper for orchestrator escalation alerts.
    Attempts Groq enrichment first; falls back to plain format.
    """
    enriched = _enrich_via_groq(division, skill, reason, action_items)

    if enriched:
        message = (
            f"**J_Claw Escalation** — {division.upper()} / {skill}\n"
            f"{enriched}"
        )
    else:
        lines = [
            f"**J_Claw Escalation** — {division.upper()} / {skill}",
            f"> {reason}",
        ]
        if action_items:
            lines.append("")
            for item in action_items[:5]:
                label = item.get("description", item) if isinstance(item, dict) else str(item)
                lines.append(f"• {label[:200]}")
            if len(action_items) > 5:
                lines.append(f"_…and {len(action_items) - 5} more_")
        message = "\n".join(lines)

    return notify(message)

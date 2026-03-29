"""
Notifier — sends messages to Matthew via Discord (primary) or Telegram (fallback).

Primary channel: Discord webhook (DISCORD_WEBHOOK_URL in .env).
Fallback channel: Telegram bot (TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID in .env).

SOUL.md declares Discord as the primary notification channel. Telegram is kept
as a fallback so alerts are never silently dropped if Discord is not configured.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from pathlib import Path

from schemas.tasks import ApprovalRequest

log = logging.getLogger(__name__)

URGENCY_EMOJI = {
    "low":      "📋",
    "normal":   "📬",
    "high":     "⚠️",
    "critical": "🚨",
}

_ENV_FILE = Path(__file__).parents[1] / ".env"


def _load_env_var(key: str) -> str:
    """Read a key from process env, then fall back to .env file."""
    value = os.environ.get(key, "").strip()
    if value:
        return value
    try:
        for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith(f"{key}="):
                value = line.split("=", 1)[1].strip().strip('"').strip("'")
                if value:
                    return value
    except Exception:
        pass
    return ""


class Notifier:

    def __init__(self):
        # Discord (primary — per SOUL.md)
        self._webhook_url = _load_env_var("DISCORD_WEBHOOK_URL")
        # Telegram (fallback)
        self._tg_token   = _load_env_var("TELEGRAM_BOT_TOKEN")
        self._tg_chat_id = _load_env_var("TELEGRAM_CHAT_ID")

    # ── Discord ───────────────────────────────────────────────────────────────

    def _discord_configured(self) -> bool:
        return bool(self._webhook_url)

    def _post_discord(self, text: str) -> bool:
        """POST text to the Discord webhook. Returns True on success."""
        if not self._discord_configured():
            return False
        try:
            body = json.dumps({"content": text[:2000]}).encode("utf-8")
            req = urllib.request.Request(
                self._webhook_url,
                data=body,
                method="POST",
                headers={"Content-Type": "application/json", "User-Agent": "J_Claw/1.0"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp.read()
            return True
        except Exception as e:
            log.error("notify: Discord webhook POST failed: %s", e)
            return False

    # ── Telegram ──────────────────────────────────────────────────────────────

    def _telegram_configured(self) -> bool:
        return bool(self._tg_token and self._tg_chat_id)

    def _post_telegram(self, text: str) -> bool:
        """POST text to Telegram. Returns True on success."""
        if not self._telegram_configured():
            return False
        try:
            url = f"https://api.telegram.org/bot{self._tg_token}/sendMessage"
            payload = json.dumps({
                "chat_id": self._tg_chat_id,
                "text": text,
                "parse_mode": "Markdown",
            }).encode("utf-8")
            req = urllib.request.Request(
                url, data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status == 200
        except Exception as e:
            log.error("notify: Telegram send failed: %s", e)
            return False

    # ── Routing: Discord first, Telegram fallback ────────────────────────────

    def _send_raw(self, text: str) -> bool:
        """Try Discord first (primary per SOUL.md). Fall back to Telegram if unavailable."""
        if self._discord_configured():
            if self._post_discord(text):
                log.info("notify: sent via Discord webhook")
                return True
            log.warning("notify: Discord webhook failed — attempting Telegram fallback")

        if self._telegram_configured():
            if self._post_telegram(text):
                log.info("notify: sent via Telegram (fallback)")
                return True
            log.error("notify: Telegram fallback also failed")
        else:
            if not self._discord_configured():
                log.warning(
                    "notify: no notification channel configured "
                    "(set DISCORD_WEBHOOK_URL in .env for primary, "
                    "TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID for fallback)"
                )
        return False

    # ── Public API ────────────────────────────────────────────────────────────

    def send(self, message: str, urgency: str = "normal") -> bool:
        emoji = URGENCY_EMOJI.get(urgency, "📬")
        return self._send_raw(f"{emoji} {message}")

    def send_approval_request(self, approval: ApprovalRequest) -> bool:
        emoji = URGENCY_EMOJI.get(approval.urgency, "📬")
        text = (
            f"{emoji} **APPROVAL REQUIRED**\n\n"
            f"**Task ID:** `{approval.task_id}`\n"
            f"**Approval ID:** `{approval.id}`\n"
            f"**Urgency:** {approval.urgency.upper()}\n\n"
            f"**Summary:** {approval.summary}\n\n"
            f"**Recommended:** {approval.recommended_action}\n\n"
            f"Approve/reject via Mission Control dashboard or:\n"
            f"`POST /api/approvals/{approval.id}/approve`\n"
            f"`POST /api/approvals/{approval.id}/reject`"
        )
        return self._send_raw(text)

    def send_packet_summary(self, packet: dict) -> bool:
        division = packet.get("division", "?")
        skill    = packet.get("skill", "?")
        status   = packet.get("status", "?")
        summary  = packet.get("summary", "")
        escalate = packet.get("escalate", False)
        provider = packet.get("provider_used", "")

        emoji    = "✅" if status == "success" else ("⚠️" if status == "partial" else "❌")
        esc_note = "\n🚨 **ESCALATION REQUIRED**" if escalate else ""

        text = (
            f"{emoji} **{division.upper()} / {skill}**\n"
            f"Status: `{status}` | Provider: `{provider or 'unknown'}`\n\n"
            f"{summary[:400]}"
            f"{esc_note}"
        )
        return self._send_raw(text)

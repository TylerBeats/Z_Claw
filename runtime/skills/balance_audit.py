"""
Balance Auditor — reviews and audits game balance data.

Uses local LLM (Tier 1 7B) to analyze game balance across XP curves,
damage values, economy, difficulty, drop rates, and ability costs.

Optionally reads a JSON data file for context.
Output saved to divisions/gamedev/audits/.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from runtime.config import MODEL_7B, OLLAMA_HOST, BASE_DIR
from runtime.ollama_client import chat_json, is_available

log = logging.getLogger(__name__)

OUTPUT_DIR = BASE_DIR / "divisions" / "gamedev" / "audits"

AUDIT_TYPES = {
    "xp_curve":      "XP curve and progression speed audit",
    "damage_values": "damage values and combat balance audit",
    "economy":       "in-game economy and currency balance audit",
    "difficulty":    "difficulty curve and challenge balance audit",
    "drop_rates":    "item drop rates and loot table balance audit",
    "ability_costs": "ability costs, cooldowns, and resource balance audit",
}

_SYSTEM_PROMPT = """\
You are a Game Balance Auditor for ARDENT's Engine Hearth — J_Claw's game development division.
Audit game balance with precision. Identify broken economies before they ship.
Return ONLY valid JSON with this exact structure:
{
  "audit_type": "the type of audit performed",
  "target": "the specific system or values audited",
  "findings": ["specific balance issues or observations found"],
  "recommendations": ["actionable balance adjustments to make"],
  "risk_level": "low | medium | high | critical",
  "action_items": ["immediate steps to address the most critical findings"]
}
Be specific about numbers and thresholds. No fluff.\
"""


def run(
    audit_type: str = "xp_curve",
    target: str = "",
    data_file: str = "",
) -> dict:
    """Balance Auditor skill entry point."""
    if audit_type not in AUDIT_TYPES:
        valid = ", ".join(sorted(AUDIT_TYPES))
        return {
            "status": "failed",
            "summary": f"Unknown audit_type '{audit_type}'. Valid: {valid}",
            "metrics": {}, "action_items": [], "escalate": False,
        }

    if not target:
        target = f"default {AUDIT_TYPES[audit_type]}"

    # Optionally read data file for context
    data_context = ""
    if data_file:
        try:
            data_path = Path(data_file)
            if data_path.exists():
                raw = data_path.read_text(encoding="utf-8")
                # Truncate to avoid blowing token budget
                data_context = raw[:3000]
                log.info("balance_audit: loaded data file %s (%d chars)", data_file, len(raw))
            else:
                log.warning("balance_audit: data_file not found: %s", data_file)
        except Exception as exc:
            log.warning("balance_audit: could not read data_file %s — %s", data_file, exc)

    if not is_available(MODEL_7B, host=OLLAMA_HOST):
        return {
            "status":  "partial",
            "summary": f"Balance audit queued: {audit_type} — '{target}'. No LLM available.",
            "metrics": {"audit_type": audit_type, "target": target, "queued": True},
            "action_items": [{"priority": "low",
                               "description": "Start Ollama to process balance audit.",
                               "requires_matthew": False}],
            "escalate": False,
        }

    prompt = f"Audit type: {AUDIT_TYPES[audit_type]}\nTarget: {target}"
    if data_context:
        prompt += f"\n\nGame data for context:\n{data_context}"

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user",   "content": prompt},
    ]

    try:
        result = chat_json(MODEL_7B, messages, host=OLLAMA_HOST, temperature=0.3, max_tokens=1500)
        if not isinstance(result, dict):
            raise ValueError(f"Unexpected LLM response type: {type(result)}")

        findings        = result.get("findings", [])
        recommendations = result.get("recommendations", [])
        risk_level      = result.get("risk_level", "medium")
        action_items    = result.get("action_items", [])

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename  = f"{timestamp}_{audit_type}.json"
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out_path  = OUTPUT_DIR / filename
        out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

        escalate = risk_level in ("high", "critical")
        log.info("balance_audit: wrote %s (%d findings, risk=%s)", filename, len(findings), risk_level)
        return {
            "status":  "success",
            "summary": (
                f"Balance audit complete: {audit_type} — '{target}'. "
                f"{len(findings)} findings, {len(recommendations)} recommendations. "
                f"Risk level: {risk_level}."
            ),
            "metrics": {
                "audit_type":      audit_type,
                "target":          target,
                "findings":        len(findings),
                "recommendations": len(recommendations),
                "risk_level":      risk_level,
                "output_path":     str(out_path.relative_to(BASE_DIR)),
            },
            "action_items": [
                {"priority": "high" if escalate else "low",
                 "description": f"Review balance audit ({risk_level} risk): {filename}",
                 "requires_matthew": True}
            ],
            "escalate": escalate,
        }

    except Exception as exc:
        log.error("balance_audit: LLM call failed — %s", exc)
        return {
            "status":  "failed",
            "summary": f"Balance audit generation failed: {exc}",
            "metrics": {"audit_type": audit_type, "target": target},
            "action_items": [], "escalate": False,
        }

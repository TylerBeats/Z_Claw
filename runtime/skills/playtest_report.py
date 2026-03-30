"""
Playtest Analyst — generates structured playtest session reports and balancing recommendations.

Uses local LLM (Tier 1 7B) to analyze playtest notes and produce actionable findings.

Output saved to divisions/gamedev/playtests/.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from runtime.config import MODEL_7B, OLLAMA_HOST, BASE_DIR
from runtime.ollama_client import chat_json, is_available

log = logging.getLogger(__name__)

OUTPUT_DIR = BASE_DIR / "divisions" / "gamedev" / "playtests"
QUEUE_FILE = BASE_DIR / "state" / "playtest-queue.json"

SESSION_TYPES = {
    "full_playthrough": "full game playthrough session",
    "combat_test":      "combat system focused test",
    "economy_test":     "economy and progression test",
    "ux_test":          "UI/UX and accessibility test",
    "stress_test":      "performance and stress test",
    "tutorial_test":    "tutorial and onboarding test",
    "multiplayer_test": "multiplayer and networking test",
}

_SYSTEM_PROMPT = """\
You are the Playtest Analyst for ARDENT's Studio — J_Claw's game development division.
Analyze playtest sessions and produce actionable reports that improve the game.
Return ONLY valid JSON with this exact structure:
{
  "session_type": "type of session",
  "focus_area": "area being tested",
  "findings": [
    {
      "area": "system or feature name",
      "severity": "blocker | major | minor | suggestion",
      "description": "what was observed",
      "recommendation": "what to fix or improve"
    }
  ],
  "metrics_snapshot": {
    "session_duration_min": 0,
    "bugs_found": 0,
    "balance_issues": 0,
    "ux_friction_points": 0
  },
  "overall_health": "poor | needs_work | acceptable | good | excellent",
  "priority_fixes": ["most critical fix #1", "most critical fix #2"],
  "next_session_focus": "recommendation for next playtest focus"
}
Be direct. Flag blockers clearly.\
"""


def _load_queue() -> list:
    if not QUEUE_FILE.exists():
        return []
    try:
        return json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_queue(queue: list) -> None:
    QUEUE_FILE.parent.mkdir(exist_ok=True)
    QUEUE_FILE.write_text(json.dumps(queue, indent=2), encoding="utf-8")


def run(session_type: str = "full_playthrough", focus_area: str = "", notes: str = "") -> dict:
    """Playtest Analyst skill entry point."""
    if session_type not in SESSION_TYPES:
        valid = ", ".join(sorted(SESSION_TYPES))
        return {
            "status": "failed",
            "summary": f"Unknown session_type '{session_type}'. Valid: {valid}",
            "metrics": {}, "action_items": [], "escalate": False,
        }

    if not focus_area:
        focus_area = SESSION_TYPES[session_type]

    if not is_available(MODEL_7B, host=OLLAMA_HOST):
        queue = _load_queue()
        queue.append({"session_type": session_type, "focus_area": focus_area, "notes": notes,
                      "queued_at": datetime.now(timezone.utc).isoformat()})
        _save_queue(queue)
        return {
            "status": "partial",
            "summary": f"Playtest report queued: {session_type} — '{focus_area}'. No LLM available.",
            "metrics": {"session_type": session_type, "focus_area": focus_area, "queued": True},
            "action_items": [{"priority": "low",
                               "description": "Start Ollama to process playtest queue.",
                               "requires_matthew": False}],
            "escalate": False,
        }

    prompt = f"Session type: {SESSION_TYPES[session_type]}\nFocus area: {focus_area}"
    if notes:
        prompt += f"\nPlaytest notes: {notes}"

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user",   "content": prompt},
    ]

    try:
        result = chat_json(MODEL_7B, messages, host=OLLAMA_HOST, temperature=0.3, max_tokens=1500)
        if not isinstance(result, dict):
            raise ValueError(f"Unexpected LLM response type: {type(result)}")

        findings      = result.get("findings", [])
        health        = result.get("overall_health", "acceptable")
        priority_fixes = result.get("priority_fixes", [])
        blockers = [f for f in findings if f.get("severity") == "blocker"]

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename  = f"{timestamp}_{session_type}.json"
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out_path  = OUTPUT_DIR / filename
        out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

        escalate = len(blockers) > 0 or health in ("poor",)
        log.info("playtest_report: wrote %s (%d findings, health=%s)", filename, len(findings), health)
        return {
            "status":  "success",
            "summary": (
                f"Playtest report: {session_type} — '{focus_area}'. "
                f"{len(findings)} findings ({len(blockers)} blockers). "
                f"Overall health: {health}."
            ),
            "metrics": {
                "session_type":   session_type,
                "focus_area":     focus_area,
                "findings":       len(findings),
                "blockers":       len(blockers),
                "overall_health": health,
                "priority_fixes": len(priority_fixes),
                "output_path":    str(out_path.relative_to(BASE_DIR)),
            },
            "action_items": [
                {"priority": "high" if escalate else "low",
                 "description": f"Review playtest report ({health}): {filename}",
                 "requires_matthew": True}
            ],
            "escalate": escalate,
        }

    except Exception as exc:
        log.error("playtest_report: LLM call failed — %s", exc)
        return {
            "status":  "failed",
            "summary": f"Playtest report generation failed: {exc}",
            "metrics": {"session_type": session_type, "focus_area": focus_area},
            "action_items": [], "escalate": False,
        }

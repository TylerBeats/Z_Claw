"""
Gamedev Digest — ARDENT's daily studio report.

Scans all gamedev division output directories, counts today's production,
and uses LLM to synthesize a concise executive summary for J_Claw.

Output saved to divisions/gamedev/digests/.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

from runtime.config import MODEL_7B, OLLAMA_HOST, BASE_DIR
from runtime.ollama_client import chat_json, is_available

log = logging.getLogger(__name__)

OUTPUT_DIR  = BASE_DIR / "divisions" / "gamedev" / "digests"
GAMEDEV_DIR = BASE_DIR / "divisions" / "gamedev"

SUBDIRS = {
    "game-design":   "design docs",
    "mechanics":     "mechanic prototypes",
    "audits":        "balance audits",
    "tech-specs":    "tech specs",
    "playtests":     "playtest reports",
    "integration":   "integration plans",
    "levels":        "level designs",
}

_SYSTEM_PROMPT = """\
You are ARDENT, Director of the Ardent Studio — J_Claw's game development division.
Write a concise daily studio report for Matthew.
Return ONLY valid JSON:
{
  "date": "today's date",
  "total_docs_today": 0,
  "pipeline_health": "idle | active | productive | overloaded",
  "summary": "2-3 sentence executive summary of today's studio output",
  "highlights": ["notable output or milestone"],
  "blockers": ["anything blocking progress"],
  "next_priorities": ["top 2-3 things to work on next"],
  "ardent_note": "ARDENT's personal assessment in-character (1 sentence)"
}
Be direct. Flag blockers clearly.\
"""


def _count_today(subdir: Path) -> int:
    """Count files created today in a subdirectory."""
    if not subdir.exists():
        return 0
    today = datetime.now(timezone.utc).date()
    count = 0
    for f in subdir.iterdir():
        if f.is_file():
            try:
                mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc).date()
                if mtime == today:
                    count += 1
            except Exception:
                pass
    return count


def run() -> dict:
    """Gamedev Digest skill entry point."""
    counts = {}
    total_today = 0
    for subdir_name, label in SUBDIRS.items():
        subdir = GAMEDEV_DIR / subdir_name
        n = _count_today(subdir)
        counts[label] = n
        total_today += n

    if not is_available(MODEL_7B, host=OLLAMA_HOST):
        summary = f"Studio output today: {total_today} docs across {len(SUBDIRS)} tracks."
        return {
            "status": "partial",
            "summary": summary,
            "metrics": {"total_today": total_today, "breakdown": counts},
            "action_items": [],
            "escalate": False,
        }

    context = (
        f"Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}\n"
        f"Total documents produced today: {total_today}\n"
        f"Breakdown by track:\n"
        + "\n".join(f"  {label}: {n}" for label, n in counts.items())
    )

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user",   "content": context},
    ]

    try:
        result = chat_json(MODEL_7B, messages, host=OLLAMA_HOST, temperature=0.4, max_tokens=800)
        if not isinstance(result, dict):
            raise ValueError(f"Unexpected LLM response type: {type(result)}")

        summary    = result.get("summary", f"Studio: {total_today} docs today.")
        health     = result.get("pipeline_health", "idle")
        blockers   = result.get("blockers", [])

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename  = f"{timestamp}_gamedev_digest.json"
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out_path  = OUTPUT_DIR / filename
        out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

        log.info("gamedev_digest: wrote %s (total=%d, health=%s)", filename, total_today, health)
        return {
            "status":  "success",
            "summary": summary,
            "metrics": {
                "total_today":     total_today,
                "breakdown":       counts,
                "pipeline_health": health,
                "blockers":        len(blockers),
                "output_path":     str(out_path.relative_to(BASE_DIR)),
            },
            "action_items": [
                {"priority": "high", "description": f"Blocker: {b}", "requires_matthew": True}
                for b in blockers
            ],
            "escalate": len(blockers) > 0,
        }

    except Exception as exc:
        log.error("gamedev_digest: LLM call failed — %s", exc)
        return {
            "status":  "partial",
            "summary": f"Studio: {total_today} docs today. (digest synthesis unavailable)",
            "metrics": {"total_today": total_today, "breakdown": counts},
            "action_items": [], "escalate": False,
        }

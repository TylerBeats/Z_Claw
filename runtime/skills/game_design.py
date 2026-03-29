"""
Game Designer — generates Game Design Documents, mechanics specs, and system designs.

Uses local LLM (Tier 1 7B) to draft structured design documents for game features,
mechanics, level specs, progression systems, and design bible entries.

Output saved to divisions/production/game-design/.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from runtime.config import MODEL_7B, OLLAMA_HOST, BASE_DIR
from runtime.ollama_client import chat_json, is_available

log = logging.getLogger(__name__)

OUTPUT_DIR  = BASE_DIR / "divisions" / "production" / "game-design"
QUEUE_FILE  = BASE_DIR / "state" / "design-queue.json"

DESIGN_TYPES = {
    "gdd":           "full Game Design Document",
    "mechanics":     "game mechanics specification",
    "level_spec":    "level design specification",
    "system_design": "game system design document",
    "progression":   "progression and XP system design",
    "ui_spec":       "UI/UX flow and wireframe spec",
    "enemy_design":  "enemy / boss design document",
    "world_bible":   "world-building bible entry",
}

_SYSTEM_PROMPT = """\
You are the Game Designer for the Lykeon Forge — J_Claw's game production division.
Write clear, structured game design documents that balance creative vision with technical feasibility.
Return ONLY valid JSON with this structure:
{
  "title": "document title",
  "design_type": "the type of design document",
  "summary": "1-2 sentence overview",
  "sections": [
    {"heading": "section name", "content": "detailed section content"}
  ],
  "open_questions": ["design questions still unresolved"],
  "next_steps": ["immediate implementation tasks"],
  "estimated_complexity": "low | medium | high"
}
Be specific, actionable, and game-ready. No fluff.\
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


def run(design_type: str = "mechanics", topic: str = "", context: str = "") -> dict:
    """Game Designer skill entry point."""
    if design_type not in DESIGN_TYPES:
        valid = ", ".join(sorted(DESIGN_TYPES))
        return {
            "status": "failed",
            "summary": f"Unknown design_type '{design_type}'. Valid: {valid}",
            "metrics": {}, "action_items": [], "escalate": False,
        }

    if not topic:
        topic = f"default {DESIGN_TYPES[design_type]}"

    if not is_available(MODEL_7B, host=OLLAMA_HOST):
        queue = _load_queue()
        queue.append({"design_type": design_type, "topic": topic, "context": context,
                       "queued_at": datetime.now(timezone.utc).isoformat()})
        _save_queue(queue)
        return {
            "status": "partial",
            "summary": f"Design request queued: {design_type} — '{topic}'. No LLM available.",
            "metrics": {"design_type": design_type, "topic": topic, "queued": True},
            "action_items": [{"priority": "low",
                               "description": "Start Ollama to process design queue.",
                               "requires_matthew": False}],
            "escalate": False,
        }

    prompt = f"Design type: {DESIGN_TYPES[design_type]}\nTopic: {topic}"
    if context:
        prompt += f"\nContext: {context}"

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user",   "content": prompt},
    ]

    try:
        result = chat_json(MODEL_7B, messages, host=OLLAMA_HOST, temperature=0.7, max_tokens=2000)
        if not isinstance(result, dict):
            raise ValueError(f"Unexpected LLM response type: {type(result)}")

        title      = result.get("title", f"{design_type}: {topic}")
        sections   = result.get("sections", [])
        complexity = result.get("estimated_complexity", "medium")
        open_qs    = len(result.get("open_questions", []))

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        slug      = topic.lower().replace(" ", "_")[:30] if topic else design_type
        filename  = f"{timestamp}_{design_type}_{slug}.json"
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out_path  = OUTPUT_DIR / filename
        out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

        log.info("game_design: wrote %s (%d sections, %s complexity)", filename, len(sections), complexity)
        return {
            "status":  "success",
            "summary": (
                f"Game design document created: '{title}'. "
                f"{len(sections)} sections, {open_qs} open questions. "
                f"Complexity: {complexity}."
            ),
            "metrics": {
                "title":       title,
                "design_type": design_type,
                "sections":    len(sections),
                "open_questions": open_qs,
                "complexity":  complexity,
                "output_path": str(out_path.relative_to(BASE_DIR)),
            },
            "action_items": [
                {"priority": "low",
                 "description": f"Review design doc: {filename}",
                 "requires_matthew": True}
            ] if open_qs > 0 else [],
            "escalate": False,
        }

    except Exception as exc:
        log.error("game_design: LLM call failed — %s", exc)
        return {
            "status":  "failed",
            "summary": f"Game design generation failed: {exc}",
            "metrics": {"design_type": design_type, "topic": topic},
            "action_items": [], "escalate": False,
        }

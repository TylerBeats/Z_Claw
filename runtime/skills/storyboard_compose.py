"""
Storyboard Composer — converts theater animation queue events into structured
visual shot lists. Feeds image_generate and video_generate with scene direction.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from runtime.config import STATE_DIR, BASE_DIR

log = logging.getLogger(__name__)

ANIM_QUEUE_FILE  = STATE_DIR / "anim-queue.json"
STORYBOARD_FILE  = BASE_DIR / "divisions" / "production" / "packets" / "storyboard.json"

# Shot templates per event type
_SHOT_TEMPLATES = {
    "skill_complete": {
        "shot_type":   "battle_scene",
        "description": "{commander} defeats {enemy_name} — {skill} completed",
        "mood":        "triumphant, dynamic",
        "angle":       "medium shot, slight upward angle",
        "lighting":    "dramatic side-lighting, victory glow",
    },
    "rank_up": {
        "shot_type":   "portrait_bust",
        "description": "{commander} ascends to {new_rank} — evolution moment",
        "mood":        "awe-inspiring, transformative",
        "angle":       "bust portrait, straight on",
        "lighting":    "radiant backlight, rank-up aura",
    },
    "achievement": {
        "shot_type":   "ui_element",
        "description": "Achievement unlocked: {achievement_name}",
        "mood":        "celebratory, golden",
        "angle":       "centered, flat design",
        "lighting":    "golden glow, achievement shimmer",
    },
}


def _load_queue() -> list:
    if not ANIM_QUEUE_FILE.exists():
        return []
    try:
        with open(ANIM_QUEUE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _event_to_shot(event: dict) -> dict:
    etype    = event.get("type", "skill_complete")
    template = _SHOT_TEMPLATES.get(etype, _SHOT_TEMPLATES["skill_complete"]).copy()

    # Fill in template vars
    description = template["description"].format(
        commander      = event.get("commander", "Unknown"),
        enemy_name     = event.get("enemy_name", "the enemy"),
        skill          = event.get("skill", ""),
        new_rank       = event.get("new_rank", ""),
        achievement_name = event.get("achievement_name", ""),
    )
    template["description"] = description

    return {
        "event_id":   event.get("id", ""),
        "event_type": etype,
        "division":   event.get("division", ""),
        "commander":  event.get("commander", ""),
        "color":      event.get("color", "#7c3aed"),
        "shot":       template,
        "chapter":    event.get("chapter", {}),
        "composed_at": datetime.now(timezone.utc).isoformat(),
    }


def run() -> dict:
    """Storyboard Composer skill entry point."""
    queue = _load_queue()
    if not queue:
        return {
            "status":  "success",
            "summary": "No pending theater events in queue. Storyboard is empty.",
            "metrics": {"events_composed": 0},
            "action_items": [],
            "escalate": False,
        }

    shots = [_event_to_shot(e) for e in queue]

    storyboard = {
        "composed_at":    datetime.now(timezone.utc).isoformat(),
        "total_shots":    len(shots),
        "shots":          shots,
        "source_events":  len(queue),
    }

    STORYBOARD_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STORYBOARD_FILE, "w", encoding="utf-8") as f:
        json.dump(storyboard, f, indent=2)

    log.info("storyboard_compose: %d shots from %d events", len(shots), len(queue))

    # Summarize by type
    type_counts = {}
    for s in shots:
        t = s["event_type"]
        type_counts[t] = type_counts.get(t, 0) + 1

    return {
        "status":  "success",
        "summary": (
            f"Storyboard composed: {len(shots)} shots from {len(queue)} theater events. "
            f"Ready for production. Types: {type_counts}"
        ),
        "metrics": {
            "shots_composed":   len(shots),
            "source_events":    len(queue),
            "by_type":          type_counts,
            "storyboard_path":  str(STORYBOARD_FILE.relative_to(BASE_DIR)),
        },
        "action_items": [],
        "escalate": False,
    }

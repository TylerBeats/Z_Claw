"""
Level Designer — generates level layouts, dungeon maps, and world design specs.

Uses local LLM (Tier 1 7B) to create structured level design documents:
room layouts, encounter tables, loot placement, narrative hooks, flow diagrams.

Output saved to divisions/production/levels/.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from runtime.config import MODEL_7B, OLLAMA_HOST, BASE_DIR
from runtime.ollama_client import chat_json, is_available

log = logging.getLogger(__name__)

OUTPUT_DIR = BASE_DIR / "divisions" / "production" / "levels"

LEVEL_TYPES = {
    "dungeon":     "dungeon level with rooms and combat encounters",
    "overworld":   "overworld map section or open-world zone",
    "town":        "town / hub area with NPCs and services",
    "boss_arena":  "boss battle arena with mechanics",
    "tutorial":    "tutorial level / onboarding area",
    "puzzle_room": "puzzle chamber design",
    "hub_world":   "central hub world connecting multiple areas",
}

_SYSTEM_PROMPT = """\
You are the Level Designer for the Lykeon Forge — J_Claw's game production division.
Design tight, player-serving levels with clear flow and memorable moments.
Return ONLY valid JSON:
{
  "level_name": "name of the level",
  "level_type": "type of level",
  "theme": "visual and narrative theme",
  "flow_description": "how the player moves through the level start to finish",
  "rooms": [
    {
      "id": "room_01",
      "name": "room name",
      "description": "what is in this room and why it is interesting",
      "encounters": ["enemy groups, traps, or events"],
      "loot": ["items, currency, or rewards"],
      "connections": ["room_02"],
      "notes": "design notes or special mechanics"
    }
  ],
  "key_moments": ["memorable set-piece moments in the level"],
  "music_cue": "suggested music track type (e.g. battle_theme, ambient)",
  "estimated_playtime_minutes": 0,
  "complexity": "low | medium | high"
}
Design for fun first. Encounters and loot should be specific and balanced.\
"""


def run(level_type: str = "dungeon", theme: str = "", constraints: str = "") -> dict:
    """Level Designer skill entry point."""
    if level_type not in LEVEL_TYPES:
        valid = ", ".join(sorted(LEVEL_TYPES))
        return {
            "status": "failed",
            "summary": f"Unknown level_type '{level_type}'. Valid: {valid}",
            "metrics": {}, "action_items": [], "escalate": False,
        }

    if not theme:
        theme = f"generic {level_type}"

    if not is_available(MODEL_7B, host=OLLAMA_HOST):
        return {
            "status": "partial",
            "summary": f"Level design queued: {level_type} — '{theme}'. No LLM available.",
            "metrics": {"level_type": level_type, "theme": theme},
            "action_items": [{"priority": "low",
                               "description": "Start Ollama to generate level design.",
                               "requires_matthew": False}],
            "escalate": False,
        }

    prompt = f"Level type: {LEVEL_TYPES[level_type]}\nTheme: {theme}"
    if constraints:
        prompt += f"\nConstraints: {constraints}"

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user",   "content": prompt},
    ]

    try:
        result = chat_json(MODEL_7B, messages, host=OLLAMA_HOST, temperature=0.7, max_tokens=3000)
        if not isinstance(result, dict):
            raise ValueError(f"Unexpected LLM response type: {type(result)}")

        level_name = result.get("level_name", f"{level_type}: {theme}")
        rooms      = result.get("rooms", [])
        complexity = result.get("complexity", "medium")
        playtime   = result.get("estimated_playtime_minutes", 0)
        moments    = len(result.get("key_moments", []))

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        slug      = theme.lower().replace(" ", "_")[:30] if theme else level_type
        filename  = f"{timestamp}_{level_type}_{slug}.json"
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out_path  = OUTPUT_DIR / filename
        out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

        log.info("level_design: wrote %s (%d rooms, %s complexity, ~%dm)", filename, len(rooms), complexity, playtime)
        return {
            "status":  "success",
            "summary": (
                f"Level designed: '{level_name}'. "
                f"{len(rooms)} rooms, {moments} key moments, "
                f"~{playtime}min playtime. Complexity: {complexity}."
            ),
            "metrics": {
                "level_name":     level_name,
                "level_type":     level_type,
                "room_count":     len(rooms),
                "key_moments":    moments,
                "complexity":     complexity,
                "playtime_min":   playtime,
                "output_path":    str(out_path.relative_to(BASE_DIR)),
            },
            "action_items": [
                {"priority": "low",
                 "description": f"Review level design: {filename}",
                 "requires_matthew": True}
            ],
            "escalate": False,
        }

    except Exception as exc:
        log.error("level_design: LLM call failed — %s", exc)
        return {
            "status":  "failed",
            "summary": f"Level design generation failed: {exc}",
            "metrics": {"level_type": level_type, "theme": theme},
            "action_items": [], "escalate": False,
        }

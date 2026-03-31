"""
Data Populate — generates balance data tables from game design context.

Reads game design packets and character/enemy definitions, then uses an LLM
to produce a structured balance JSON (items, enemy XP, level scaling, economy).
Run this skill after the content design phase to seed balance spreadsheets.

Output saved to state/gamedev/balance/balance_{timestamp}.json.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from runtime.config import MODEL_7B, OLLAMA_HOST, BASE_DIR
from runtime.ollama_client import chat_json, is_available

log = logging.getLogger(__name__)

DESIGN_PACKET   = BASE_DIR / "divisions" / "gamedev" / "packets" / "game-design.json"
CHARACTERS_DIR  = BASE_DIR / "divisions" / "gamedev" / "characters"
ENEMIES_DIR     = BASE_DIR / "divisions" / "gamedev" / "enemies"
OUTPUT_DIR      = BASE_DIR / "state" / "gamedev" / "balance"

_SYSTEM_PROMPT = """\
You are a senior game balance designer working on a 2-D action RPG.
Given the game design context below, generate comprehensive balance data.
Return ONLY valid JSON with this exact structure:
{
  "item_table": [
    {"name": "...", "type": "weapon|armor|consumable", "rarity": "common|rare|epic|legendary", "stats": {}}
  ],
  "enemy_xp_table": [
    {"enemy": "...", "base_xp": 0, "scaling": 1.2}
  ],
  "level_scaling": {
    "xp_per_level": [100, 200, 350],
    "stat_growth": {}
  },
  "economy": {
    "gold_per_enemy": {},
    "shop_prices": {}
  }
}
Generate at least 8 items, 6 enemies, and xp_per_level for 20 levels.
All numbers must be realistic and balanced for a progressive difficulty curve.
Return ONLY the JSON object — no markdown, no commentary.\
"""


def _latest_file(directory: Path) -> Path | None:
    """Return the most-recently-modified file in a directory, or None."""
    if not directory.exists():
        return None
    files = [f for f in directory.iterdir() if f.is_file()]
    if not files:
        return None
    return max(files, key=lambda f: f.stat().st_mtime)


def _safe_load_json(path: Path) -> dict | list | None:
    """Load JSON from path, return None on any failure."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("data_populate: could not load %s — %s", path, exc)
        return None


def run(game_context: str = "") -> dict:
    """Data Populate skill entry point.

    Args:
        game_context: Optional free-text description of the game. Merged with
                      any design packet found on disk.

    Returns:
        Standard J_Claw skill result dict.
    """
    context_parts: list[str] = []

    # 1. Merge caller-supplied context
    if game_context.strip():
        context_parts.append(f"Game Context (caller-supplied):\n{game_context.strip()}")

    # 2. Read game-design packet if present
    if DESIGN_PACKET.exists():
        data = _safe_load_json(DESIGN_PACKET)
        if data:
            context_parts.append(
                f"Game Design Packet:\n{json.dumps(data, indent=2)}"
            )
            log.info("data_populate: loaded design packet from %s", DESIGN_PACKET)

    # 3. Read latest character file
    char_file = _latest_file(CHARACTERS_DIR)
    if char_file:
        data = _safe_load_json(char_file)
        if data:
            context_parts.append(
                f"Characters ({char_file.name}):\n{json.dumps(data, indent=2)}"
            )

    # 4. Read latest enemy file
    enemy_file = _latest_file(ENEMIES_DIR)
    if enemy_file:
        data = _safe_load_json(enemy_file)
        if data:
            context_parts.append(
                f"Enemies ({enemy_file.name}):\n{json.dumps(data, indent=2)}"
            )

    if not context_parts:
        context_parts.append(
            "No design documents found. Generate a generic fantasy action-RPG balance table."
        )

    full_context = "\n\n".join(context_parts)

    # 5. Fallback if model unavailable
    if not is_available(MODEL_7B, host=OLLAMA_HOST):
        log.warning("data_populate: model %s unavailable", MODEL_7B)
        return {
            "status": "partial",
            "summary": "Balance data generation skipped — LLM model unavailable.",
            "metrics": {
                "item_count": 0,
                "enemy_count": 0,
                "max_level": 0,
                "output_path": "",
            },
            "action_items": [
                {
                    "priority": "high",
                    "description": f"Start Ollama and ensure model '{MODEL_7B}' is pulled.",
                    "requires_matthew": True,
                }
            ],
            "escalate": True,
        }

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user",   "content": full_context},
    ]

    try:
        result = chat_json(
            MODEL_7B, messages,
            host=OLLAMA_HOST,
            temperature=0.3,
            max_tokens=2000,
        )
        if not isinstance(result, dict):
            raise ValueError(f"Unexpected LLM response type: {type(result)}")

        # 6. Persist output
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        out_path  = OUTPUT_DIR / f"balance_{timestamp}.json"
        out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        log.info("data_populate: wrote balance data to %s", out_path)

        # 7. Collect metrics
        item_table   = result.get("item_table", [])
        enemy_table  = result.get("enemy_xp_table", [])
        level_data   = result.get("level_scaling", {})
        xp_curve     = level_data.get("xp_per_level", [])
        item_count   = len(item_table)
        enemy_count  = len(enemy_table)
        max_level    = len(xp_curve)

        summary = (
            f"Balance tables generated: {item_count} items, "
            f"{enemy_count} enemies, {max_level} levels."
        )

        action_items = []
        if item_count < 8:
            action_items.append({
                "priority": "medium",
                "description": f"Item table is thin ({item_count} items). Consider expanding.",
                "requires_matthew": False,
            })
        if enemy_count < 6:
            action_items.append({
                "priority": "medium",
                "description": f"Enemy XP table is thin ({enemy_count} entries). Add more enemies.",
                "requires_matthew": False,
            })

        return {
            "status": "success",
            "summary": summary,
            "metrics": {
                "item_count":  item_count,
                "enemy_count": enemy_count,
                "max_level":   max_level,
                "output_path": str(out_path.relative_to(BASE_DIR)),
            },
            "action_items": action_items,
            "escalate": False,
        }

    except Exception as exc:
        log.error("data_populate: LLM call failed — %s", exc)
        return {
            "status": "error",
            "summary": f"Balance data generation failed: {exc}",
            "metrics": {
                "item_count":  0,
                "enemy_count": 0,
                "max_level":   0,
                "output_path": "",
            },
            "action_items": [
                {
                    "priority": "high",
                    "description": f"Investigate data_populate LLM error: {exc}",
                    "requires_matthew": True,
                }
            ],
            "escalate": True,
        }

"""
Mechanic Prototypist — generates structured game mechanic prototypes.

Uses local LLM (Tier 1 7B) to design detailed mechanic specifications
covering core loops, inputs/outputs, states, edge cases, and hints.

Output saved to divisions/gamedev/mechanics/.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from runtime.config import MODEL_7B, OLLAMA_HOST, BASE_DIR
from runtime.ollama_client import chat_json, is_available

log = logging.getLogger(__name__)

OUTPUT_DIR = BASE_DIR / "divisions" / "gamedev" / "mechanics"

MECHANIC_TYPES = {
    "movement":    "player movement mechanic",
    "combat":      "combat mechanic",
    "inventory":   "inventory management mechanic",
    "crafting":    "crafting system mechanic",
    "dialogue":    "dialogue / conversation mechanic",
    "puzzle":      "puzzle mechanic",
    "progression": "progression / leveling mechanic",
    "stealth":     "stealth mechanic",
}

_SYSTEM_PROMPT = """\
You are a Game Mechanic Prototypist for ARDENT's Engine Hearth — J_Claw's game development division.
Design precise, playable mechanic prototypes that can be implemented immediately.
Return ONLY valid JSON with this exact structure:
{
  "name": "mechanic name",
  "mechanic_type": "the type of mechanic",
  "summary": "1-2 sentence overview of the mechanic",
  "core_loop": "the fundamental gameplay loop — what the player does repeatedly",
  "inputs": ["player actions / controls that trigger this mechanic"],
  "outputs": ["results, state changes, or feedback the player receives"],
  "states": ["discrete states the mechanic can be in"],
  "edge_cases": ["edge cases that must be handled"],
  "implementation_hints": ["specific code or engine hints for implementing this"],
  "estimated_complexity": "low | medium | high"
}
Be specific and implementation-ready. No fluff.\
"""


def run(
    mechanic_type: str = "combat",
    concept: str = "",
    constraints: str = "",
) -> dict:
    """Mechanic Prototypist skill entry point."""
    if mechanic_type not in MECHANIC_TYPES:
        valid = ", ".join(sorted(MECHANIC_TYPES))
        return {
            "status": "failed",
            "summary": f"Unknown mechanic_type '{mechanic_type}'. Valid: {valid}",
            "metrics": {}, "action_items": [], "escalate": False,
        }

    if not concept:
        concept = f"default {MECHANIC_TYPES[mechanic_type]}"

    if not is_available(MODEL_7B, host=OLLAMA_HOST):
        log.info("mechanic_prototype: no LLM — queuing concept '%s'", concept)
        return {
            "status":  "partial",
            "summary": f"Mechanic prototype queued: {mechanic_type} — '{concept}'. No LLM available.",
            "metrics": {"mechanic_type": mechanic_type, "concept": concept, "queued": True},
            "action_items": [{"priority": "low",
                               "description": "Start Ollama to process mechanic prototype.",
                               "requires_matthew": False}],
            "escalate": False,
        }

    prompt = f"Mechanic type: {MECHANIC_TYPES[mechanic_type]}\nConcept: {concept}"
    if constraints:
        prompt += f"\nConstraints: {constraints}"

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user",   "content": prompt},
    ]

    try:
        result = chat_json(MODEL_7B, messages, host=OLLAMA_HOST, temperature=0.7, max_tokens=2000)
        if not isinstance(result, dict):
            raise ValueError(f"Unexpected LLM response type: {type(result)}")

        name       = result.get("name", f"{mechanic_type}: {concept}")
        complexity = result.get("estimated_complexity", "medium")
        states     = result.get("states", [])
        hints      = result.get("implementation_hints", [])

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        slug      = concept.lower().replace(" ", "_")[:30] if concept else mechanic_type
        filename  = f"{timestamp}_{mechanic_type}_{slug}.json"
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out_path  = OUTPUT_DIR / filename
        out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

        log.info("mechanic_prototype: wrote %s (%d states, %s complexity)", filename, len(states), complexity)
        return {
            "status":  "success",
            "summary": (
                f"Mechanic prototype created: '{name}'. "
                f"{len(states)} states, {len(hints)} implementation hints. "
                f"Complexity: {complexity}."
            ),
            "metrics": {
                "name":          name,
                "mechanic_type": mechanic_type,
                "states":        len(states),
                "hints":         len(hints),
                "complexity":    complexity,
                "output_path":   str(out_path.relative_to(BASE_DIR)),
            },
            "action_items": [
                {"priority": "low",
                 "description": f"Review mechanic prototype: {filename}",
                 "requires_matthew": True}
            ],
            "escalate": False,
        }

    except Exception as exc:
        log.error("mechanic_prototype: LLM call failed — %s", exc)
        return {
            "status":  "failed",
            "summary": f"Mechanic prototype generation failed: {exc}",
            "metrics": {"mechanic_type": mechanic_type, "concept": concept},
            "action_items": [], "escalate": False,
        }

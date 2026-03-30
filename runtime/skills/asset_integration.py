"""
Asset Integration Planner — maps generated assets to their in-engine integration points.

Uses local LLM (Tier 1 7B) to produce step-by-step integration guides for each asset type.

Output saved to divisions/gamedev/integration/.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from runtime.config import MODEL_7B, OLLAMA_HOST, BASE_DIR
from runtime.ollama_client import chat_json, is_available

log = logging.getLogger(__name__)

OUTPUT_DIR = BASE_DIR / "divisions" / "gamedev" / "integration"
QUEUE_FILE = BASE_DIR / "state" / "integration-queue.json"

ASSET_TYPES = {
    "character_sprite": "character sprite sheet",
    "background":       "background/environment art",
    "ui_element":       "UI element or HUD component",
    "audio_sfx":        "sound effect file",
    "music_track":      "music/ambient audio track",
    "shader_code":      "shader or visual effect code",
    "tilemap":          "tilemap or level tileset",
    "animation":        "animation clip or controller",
    "font":             "custom font asset",
}

ENGINES = ["godot", "unity", "pygame", "phaser", "generic"]

_SYSTEM_PROMPT = """\
You are the Asset Integration Specialist for ARDENT's Studio — J_Claw's game development division.
Produce precise, step-by-step integration guides for bringing generated assets into the game engine.
Return ONLY valid JSON with this exact structure:
{
  "asset_type": "the type of asset",
  "asset_path": "the source file path",
  "engine": "target engine",
  "integration_steps": [
    {
      "step": 1,
      "action": "Import to engine",
      "file_path": "res://assets/characters/",
      "code_snippet": "# Optional code or config snippet",
      "notes": "any important notes for this step"
    }
  ],
  "dependencies": ["other assets or systems this integration depends on"],
  "engine_settings": {"key": "value"},
  "estimated_effort": "15 minutes | 1 hour | half day",
  "gotchas": ["common mistakes to avoid"]
}
Be specific to the engine. Use engine-native terminology.\
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


def run(asset_type: str = "character_sprite", asset_path: str = "", engine: str = "godot") -> dict:
    """Asset Integration Planner skill entry point."""
    if asset_type not in ASSET_TYPES:
        valid = ", ".join(sorted(ASSET_TYPES))
        return {
            "status": "failed",
            "summary": f"Unknown asset_type '{asset_type}'. Valid: {valid}",
            "metrics": {}, "action_items": [], "escalate": False,
        }

    if engine not in ENGINES:
        engine = "generic"

    if not asset_path:
        asset_path = f"<{asset_type} file path>"

    if not is_available(MODEL_7B, host=OLLAMA_HOST):
        queue = _load_queue()
        queue.append({"asset_type": asset_type, "asset_path": asset_path, "engine": engine,
                      "queued_at": datetime.now(timezone.utc).isoformat()})
        _save_queue(queue)
        return {
            "status": "partial",
            "summary": f"Integration plan queued: {asset_type} for {engine}. No LLM available.",
            "metrics": {"asset_type": asset_type, "engine": engine, "queued": True},
            "action_items": [{"priority": "low",
                               "description": "Start Ollama to process integration queue.",
                               "requires_matthew": False}],
            "escalate": False,
        }

    prompt = (
        f"Asset type: {ASSET_TYPES[asset_type]}\n"
        f"Asset path: {asset_path}\n"
        f"Target engine: {engine}"
    )

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user",   "content": prompt},
    ]

    try:
        result = chat_json(MODEL_7B, messages, host=OLLAMA_HOST, temperature=0.3, max_tokens=1500)
        if not isinstance(result, dict):
            raise ValueError(f"Unexpected LLM response type: {type(result)}")

        steps  = result.get("integration_steps", [])
        effort = result.get("estimated_effort", "unknown")

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        slug      = asset_type.replace(" ", "_")
        filename  = f"{timestamp}_{slug}_{engine}.json"
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out_path  = OUTPUT_DIR / filename
        out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

        log.info("asset_integration: wrote %s (%d steps, effort=%s)", filename, len(steps), effort)
        return {
            "status":  "success",
            "summary": (
                f"Integration plan: {asset_type} → {engine}. "
                f"{len(steps)} steps. Estimated effort: {effort}."
            ),
            "metrics": {
                "asset_type":  asset_type,
                "asset_path":  asset_path,
                "engine":      engine,
                "steps":       len(steps),
                "effort":      effort,
                "output_path": str(out_path.relative_to(BASE_DIR)),
            },
            "action_items": [],
            "escalate": False,
        }

    except Exception as exc:
        log.error("asset_integration: LLM call failed — %s", exc)
        return {
            "status":  "failed",
            "summary": f"Integration plan generation failed: {exc}",
            "metrics": {"asset_type": asset_type, "engine": engine},
            "action_items": [], "escalate": False,
        }

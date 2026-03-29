"""
Technical Artist — generates VFX specs, particle system configs, and shader descriptions.

Uses local LLM (Tier 1 7B) to produce structured VFX specifications ready to
implement in Godot, Unity, or other engines.

Output saved to divisions/production/vfx/.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from runtime.config import MODEL_7B, OLLAMA_HOST, BASE_DIR
from runtime.ollama_client import chat_json, is_available

log = logging.getLogger(__name__)

OUTPUT_DIR = BASE_DIR / "divisions" / "production" / "vfx"

VFX_TYPES = {
    "particle_system": "particle system configuration",
    "shader_material": "shader material specification",
    "screen_effect":   "full-screen post-processing effect",
    "weather_effect":  "environmental weather particle effect",
    "hit_effect":      "combat hit flash / impact burst",
    "aura_effect":     "character aura / status effect glow",
    "trail_effect":    "motion trail or projectile trail",
    "ambient_vfx":     "ambient environmental particles (dust, fireflies, sparks)",
}

_SYSTEM_PROMPT = """\
You are the Technical Artist for the Lykeon Forge — J_Claw's game production division.
Generate precise, implementable VFX specifications with exact parameter values.
Return ONLY valid JSON:
{
  "name": "effect name",
  "vfx_type": "the type of effect",
  "engine_target": "Godot 4 | Unity | Generic",
  "description": "what this effect looks like in motion",
  "parameters": {
    "key": "value — use concrete numbers, not ranges"
  },
  "implementation_notes": "step-by-step guide to implement in the engine",
  "performance_tier": "low | medium | high",
  "color_palette": ["#hexcolor"]
}
Parameters should be plug-and-play values ready for the engine inspector.\
"""


def run(vfx_type: str = "particle_system", effect: str = "", style: str = "", engine: str = "godot") -> dict:
    """Technical Artist skill entry point."""
    if vfx_type not in VFX_TYPES:
        valid = ", ".join(sorted(VFX_TYPES))
        return {
            "status": "failed",
            "summary": f"Unknown vfx_type '{vfx_type}'. Valid: {valid}",
            "metrics": {}, "action_items": [], "escalate": False,
        }

    if not effect:
        effect = f"default {VFX_TYPES[vfx_type]}"

    if not is_available(MODEL_7B, host=OLLAMA_HOST):
        return {
            "status": "partial",
            "summary": f"VFX spec queued: {vfx_type} — '{effect}'. No LLM available.",
            "metrics": {"vfx_type": vfx_type, "effect": effect},
            "action_items": [{"priority": "low",
                               "description": "Start Ollama to generate VFX specs.",
                               "requires_matthew": False}],
            "escalate": False,
        }

    prompt = f"VFX type: {VFX_TYPES[vfx_type]}\nEffect: {effect}\nEngine: {engine}"
    if style:
        prompt += f"\nStyle/theme: {style}"

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user",   "content": prompt},
    ]

    try:
        result = chat_json(MODEL_7B, messages, host=OLLAMA_HOST, temperature=0.5, max_tokens=1500)
        if not isinstance(result, dict):
            raise ValueError(f"Unexpected LLM response type: {type(result)}")

        name         = result.get("name", f"{vfx_type}_{effect}")
        perf         = result.get("performance_tier", "medium")
        params_count = len(result.get("parameters", {}))

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        slug      = effect.lower().replace(" ", "_")[:30] if effect else vfx_type
        filename  = f"{timestamp}_{vfx_type}_{slug}.json"
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out_path  = OUTPUT_DIR / filename
        out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

        log.info("vfx_compose: wrote %s (%d params, %s perf)", filename, params_count, perf)
        return {
            "status":  "success",
            "summary": f"VFX spec created: '{name}'. {params_count} parameters. Performance: {perf}.",
            "metrics": {
                "name":             name,
                "vfx_type":         vfx_type,
                "parameters":       params_count,
                "performance_tier": perf,
                "engine":           result.get("engine_target", engine),
                "output_path":      str(out_path.relative_to(BASE_DIR)),
            },
            "action_items": [
                {"priority": "low",
                 "description": f"Implement VFX spec: {filename}",
                 "requires_matthew": True}
            ],
            "escalate": False,
        }

    except Exception as exc:
        log.error("vfx_compose: LLM call failed — %s", exc)
        return {
            "status":  "failed",
            "summary": f"VFX spec generation failed: {exc}",
            "metrics": {"vfx_type": vfx_type, "effect": effect},
            "action_items": [], "escalate": False,
        }

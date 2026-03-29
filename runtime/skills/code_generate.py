"""
Game Programmer — generates game code for various engines.

Uses Qwen2.5-Coder 14B (Tier 2) with 7B coder fallback.
Outputs ready-to-use code for Godot (GDScript), Unity (C#), Pygame, Phaser, or generic Python.

Generated files saved to divisions/production/code/{engine}/.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from runtime.config import (
    MODEL_CODER_14B, MODEL_CODER_7B,
    MODEL_14B_HOST, OLLAMA_HOST, BASE_DIR,
)
from runtime.ollama_client import chat_json, is_available

log = logging.getLogger(__name__)

OUTPUT_DIR = BASE_DIR / "divisions" / "production" / "code"

ENGINES = {
    "godot":   {"lang": "GDScript",   "ext": ".gd",  "desc": "Godot 4.x GDScript"},
    "unity":   {"lang": "C#",         "ext": ".cs",  "desc": "Unity C# (MonoBehaviour)"},
    "pygame":  {"lang": "Python",     "ext": ".py",  "desc": "Pygame / Python"},
    "phaser":  {"lang": "JavaScript", "ext": ".js",  "desc": "Phaser 3 JavaScript"},
    "generic": {"lang": "Python",     "ext": ".py",  "desc": "Generic Python game logic"},
}

_SYSTEM_PROMPT_TEMPLATE = """\
You are the Game Programmer for the Lykeon Forge — J_Claw's game production division.
Write clean, production-quality {lang} code for {engine_desc}.
Return ONLY valid JSON:
{{
  "filename": "suggested filename with extension",
  "engine": "{engine}",
  "language": "{lang}",
  "code": "the complete code as a string",
  "description": "what this code does in one sentence",
  "dependencies": ["required imports / plugins / packages"],
  "integration_notes": "how to integrate this into the project",
  "test_cases": ["how to verify it works"]
}}
Write complete, runnable code. No placeholders. No unfinished functions.\
"""


def run(engine: str = "godot", feature: str = "", spec: str = "") -> dict:
    """Game Programmer skill entry point."""
    if engine not in ENGINES:
        valid = ", ".join(sorted(ENGINES))
        return {
            "status": "failed",
            "summary": f"Unknown engine '{engine}'. Valid: {valid}",
            "metrics": {}, "action_items": [], "escalate": False,
        }

    eng = ENGINES[engine]
    if not feature:
        feature = f"basic {engine} game component"

    # Prefer coder 14B, fall back to coder 7B
    if is_available(MODEL_CODER_14B, host=MODEL_14B_HOST):
        use_model, use_host, tier = MODEL_CODER_14B, MODEL_14B_HOST, "coder_14b"
    elif is_available(MODEL_CODER_7B, host=OLLAMA_HOST):
        log.info("code_generate: 14B unavailable, falling back to coder 7B")
        use_model, use_host, tier = MODEL_CODER_7B, OLLAMA_HOST, "coder_7b_fallback"
    else:
        return {
            "status": "partial",
            "summary": f"Code generation queued: {engine}/{feature}. No coder model available.",
            "metrics": {"engine": engine, "feature": feature},
            "action_items": [{"priority": "medium",
                               "description": "Start Ollama with a coder model to generate game code.",
                               "requires_matthew": False}],
            "escalate": False,
        }

    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(
        lang=eng["lang"], engine_desc=eng["desc"], engine=engine
    )
    prompt = f"Feature to implement: {feature}"
    if spec:
        prompt += f"\nSpec/requirements: {spec}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": prompt},
    ]

    try:
        result = chat_json(use_model, messages, host=use_host, temperature=0.2, max_tokens=4000)
        if not isinstance(result, dict):
            raise ValueError(f"Unexpected LLM response type: {type(result)}")

        code        = result.get("code", "")
        filename    = result.get("filename", f"{feature.lower().replace(' ', '_')}{eng['ext']}")
        description = result.get("description", "")
        line_count  = len(code.splitlines())

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        out_dir   = OUTPUT_DIR / engine
        out_dir.mkdir(parents=True, exist_ok=True)

        code_path = out_dir / f"{timestamp}_{filename}"
        code_path.write_text(code, encoding="utf-8")

        meta_path = out_dir / f"{timestamp}_{filename}.meta.json"
        meta_path.write_text(
            json.dumps({k: v for k, v in result.items() if k != "code"}, indent=2),
            encoding="utf-8",
        )

        log.info("code_generate: wrote %s (%d lines, %s, %s)", code_path.name, line_count, engine, tier)
        return {
            "status":  "success",
            "summary": (
                f"Game code generated: '{filename}'. "
                f"{line_count} lines of {eng['lang']} for {engine}. "
                f"{description}"
            ),
            "metrics": {
                "filename":    filename,
                "engine":      engine,
                "language":    eng["lang"],
                "line_count":  line_count,
                "model_tier":  tier,
                "output_path": str(code_path.relative_to(BASE_DIR)),
            },
            "action_items": [
                {"priority": "medium",
                 "description": f"Review and integrate: {filename}",
                 "requires_matthew": True}
            ],
            "escalate": False,
        }

    except Exception as exc:
        log.error("code_generate: LLM call failed — %s", exc)
        return {
            "status":  "failed",
            "summary": f"Code generation failed: {exc}",
            "metrics": {"engine": engine, "feature": feature},
            "action_items": [], "escalate": False,
        }

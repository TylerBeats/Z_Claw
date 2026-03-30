"""
Tech Spec Writer — converts game design docs into implementable technical specifications.

Uses local LLM (Tier 1 7B) to produce structured engine-ready specs covering
class design, system architecture, data models, API contracts, and shader specs.

Output saved to divisions/gamedev/tech-specs/.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from runtime.config import MODEL_7B, OLLAMA_HOST, BASE_DIR
from runtime.ollama_client import chat_json, is_available

log = logging.getLogger(__name__)

OUTPUT_DIR = BASE_DIR / "divisions" / "gamedev" / "tech-specs"
QUEUE_FILE = BASE_DIR / "state" / "tech-spec-queue.json"

SPEC_TYPES = {
    "class_design":       "class/object design specification",
    "system_architecture":"system architecture document",
    "data_model":         "data model and schema specification",
    "api_contract":       "internal API contract specification",
    "shader_spec":        "shader and visual effect specification",
    "save_system":        "save/load system specification",
    "network_spec":       "networking and multiplayer specification",
}

_SYSTEM_PROMPT = """\
You are the Tech Spec Writer for ARDENT's Studio — J_Claw's game development division.
Convert design intent into precise, engine-ready technical specifications.
Return ONLY valid JSON with this exact structure:
{
  "title": "specification title",
  "feature": "the feature or system being specified",
  "engine": "target engine (godot/unity/pygame/generic)",
  "spec_type": "type of spec",
  "components": [
    {
      "name": "ComponentName",
      "type": "class|system|resource|shader|data",
      "properties": ["property: Type = default"],
      "methods": ["method_name(params) -> ReturnType: description"],
      "dependencies": ["OtherComponent"]
    }
  ],
  "data_flows": ["description of how data moves between components"],
  "performance_notes": ["performance considerations and budgets"],
  "implementation_order": ["step 1", "step 2", "step 3"],
  "estimated_complexity": "low | medium | high"
}
Be precise. GDScript syntax for Godot, C# for Unity.\
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


def run(feature: str = "", design_context: str = "", engine: str = "godot", spec_type: str = "class_design") -> dict:
    """Tech Spec Writer skill entry point."""
    if spec_type not in SPEC_TYPES:
        valid = ", ".join(sorted(SPEC_TYPES))
        return {
            "status": "failed",
            "summary": f"Unknown spec_type '{spec_type}'. Valid: {valid}",
            "metrics": {}, "action_items": [], "escalate": False,
        }

    if not feature:
        feature = f"default {SPEC_TYPES[spec_type]}"

    if not is_available(MODEL_7B, host=OLLAMA_HOST):
        queue = _load_queue()
        queue.append({"spec_type": spec_type, "feature": feature, "engine": engine,
                      "design_context": design_context,
                      "queued_at": datetime.now(timezone.utc).isoformat()})
        _save_queue(queue)
        return {
            "status": "partial",
            "summary": f"Tech spec queued: {spec_type} — '{feature}'. No LLM available.",
            "metrics": {"spec_type": spec_type, "feature": feature, "queued": True},
            "action_items": [{"priority": "low",
                               "description": "Start Ollama to process tech spec queue.",
                               "requires_matthew": False}],
            "escalate": False,
        }

    prompt = f"Spec type: {SPEC_TYPES[spec_type]}\nFeature: {feature}\nEngine: {engine}"
    if design_context:
        prompt += f"\nDesign context: {design_context}"

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user",   "content": prompt},
    ]

    try:
        result = chat_json(MODEL_7B, messages, host=OLLAMA_HOST, temperature=0.3, max_tokens=2000)
        if not isinstance(result, dict):
            raise ValueError(f"Unexpected LLM response type: {type(result)}")

        title       = result.get("title", f"{spec_type}: {feature}")
        components  = result.get("components", [])
        complexity  = result.get("estimated_complexity", "medium")

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        slug      = feature.lower().replace(" ", "_")[:30] if feature else spec_type
        filename  = f"{timestamp}_{spec_type}_{slug}.json"
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out_path  = OUTPUT_DIR / filename
        out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

        log.info("tech_spec: wrote %s (%d components, %s complexity)", filename, len(components), complexity)
        return {
            "status":  "success",
            "summary": (
                f"Tech spec created: '{title}'. "
                f"{len(components)} components. Complexity: {complexity}."
            ),
            "metrics": {
                "title":       title,
                "spec_type":   spec_type,
                "feature":     feature,
                "engine":      engine,
                "components":  len(components),
                "complexity":  complexity,
                "output_path": str(out_path.relative_to(BASE_DIR)),
            },
            "action_items": [
                {"priority": "low",
                 "description": f"Review tech spec: {filename}",
                 "requires_matthew": True}
            ],
            "escalate": False,
        }

    except Exception as exc:
        log.error("tech_spec: LLM call failed — %s", exc)
        return {
            "status":  "failed",
            "summary": f"Tech spec generation failed: {exc}",
            "metrics": {"spec_type": spec_type, "feature": feature},
            "action_items": [], "escalate": False,
        }

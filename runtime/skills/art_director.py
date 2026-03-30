"""
Art Director — visual style review and direction skill.

Reviews generated asset batches for style consistency, quality,
and alignment with commander/division visual guidelines.
Flags mismatches and provides direction notes for re-generation.

Output saved to divisions/production/art-direction/.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from runtime.config import MODEL_7B, OLLAMA_HOST, BASE_DIR
from runtime.ollama_client import chat_json, is_available

log = logging.getLogger(__name__)

OUTPUT_DIR = BASE_DIR / "divisions" / "production" / "art-direction"
QUEUE_FILE = BASE_DIR / "state" / "art-director-queue.json"

REVIEW_TYPES = {
    "style_audit":     "Review asset batch for visual style consistency",
    "commander_check": "Verify asset matches commander visual archetype",
    "batch_review":    "Batch quality review across multiple asset types",
    "palette_check":   "Check color palette alignment with division theme",
    "composition_review": "Review composition, framing, and focal point",
}

_SYSTEM_PROMPT = """\
You are LYKE's Art Director — the creative lead of the Lykeon Forge.
Review the provided asset batch context and provide artistic direction.
Return ONLY valid JSON:
{
  "review_type": "style_audit | commander_check | batch_review | palette_check | composition_review",
  "overall_grade": "A | B | C | D | F",
  "style_consistency": 0.0,
  "quality_score": 0.0,
  "approved_count": 0,
  "flagged_count": 0,
  "direction_notes": ["specific visual direction note"],
  "regeneration_needed": ["asset types that need to be regenerated"],
  "style_guide_updates": ["any updates needed to the style guide"],
  "next_batch_focus": "what to focus on in the next generation run",
  "lyke_note": "LYKE's personal art direction in-character (1 sentence)"
}
Be specific. Grade honestly. Good art requires high standards.\
"""


def run(
    review_type: str = "style_audit",
    commander: str = "generic",
    asset_types: str = "portrait,sprite",
    context: str = "",
) -> dict:
    """
    Art Director skill entry point.

    Args:
        review_type:  Type of art review to conduct
        commander:    Commander whose assets are being reviewed
        asset_types:  Comma-separated list of asset types in the batch
        context:      Optional additional context (recent generation notes, etc.)
    """
    if review_type not in REVIEW_TYPES:
        review_type = "style_audit"

    asset_list = [a.strip() for a in asset_types.split(",") if a.strip()]

    if not is_available(MODEL_7B, host=OLLAMA_HOST):
        try:
            QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
            QUEUE_FILE.write_text(json.dumps({
                "review_type": review_type,
                "commander": commander,
                "asset_types": asset_list,
            }), encoding="utf-8")
        except Exception:
            pass
        return {
            "status":  "partial",
            "summary": f"art-director: queued {review_type} for {commander} (LLM offline).",
            "metrics": {"review_type": review_type, "commander": commander, "queued": True},
            "action_items": [],
            "escalate": False,
        }

    user_prompt = (
        f"Review type: {review_type} — {REVIEW_TYPES.get(review_type, '')}\n"
        f"Commander: {commander}\n"
        f"Asset types in batch: {', '.join(asset_list)}\n"
        f"Context: {context or 'Standard production run, no special notes.'}\n"
    )

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user",   "content": user_prompt},
    ]

    try:
        result = chat_json(
            MODEL_7B, messages, host=OLLAMA_HOST, temperature=0.4, max_tokens=800,
            _capture_skill="art-director", _capture_division="production",
        )
        if not isinstance(result, dict):
            raise ValueError(f"Unexpected type: {type(result)}")

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        ts       = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"{ts}_{commander}_{review_type}.json"
        (OUTPUT_DIR / filename).write_text(json.dumps(result, indent=2), encoding="utf-8")

        grade    = result.get("overall_grade", "C")
        flagged  = result.get("flagged_count", 0)
        approved = result.get("approved_count", 0)
        summary  = (
            f"Art direction: grade {grade} for {commander} ({review_type}). "
            f"{approved} approved, {flagged} flagged. "
            f"{result.get('lyke_note', '')}"
        )

        regen    = result.get("regeneration_needed", [])
        actions  = [
            {"priority": "normal", "description": f"Regenerate {a} assets", "requires_matthew": False}
            for a in regen
        ]
        actions += [
            {"priority": "low", "description": f"Direction: {n}", "requires_matthew": False}
            for n in result.get("direction_notes", [])[:2]
        ]

        log.info("art_director: %s/%s → grade %s, flagged=%d", commander, review_type, grade, flagged)
        return {
            "status":  "success",
            "summary": summary,
            "metrics": {
                "review_type":     review_type,
                "commander":       commander,
                "grade":           grade,
                "quality_score":   result.get("quality_score", 0),
                "approved_count":  approved,
                "flagged_count":   flagged,
                "output_path":     str((OUTPUT_DIR / filename).relative_to(BASE_DIR)),
            },
            "action_items": actions,
            "escalate": grade in ("D", "F") or flagged > 3,
        }

    except Exception as exc:
        log.error("art_director: LLM call failed — %s", exc)
        return {
            "status":  "partial",
            "summary": f"art-director: review failed for {commander} — {exc}",
            "metrics": {"review_type": review_type, "commander": commander},
            "action_items": [], "escalate": False,
        }

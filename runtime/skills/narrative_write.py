"""
Narrative Writer — generates game narrative content.

Dialogue trees, quest descriptions, lore texts, character backstories,
cutscene scripts, and in-game flavor text.

Uses local LLM (Tier 1 7B). Output saved to divisions/production/narrative/.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from runtime.config import MODEL_7B, OLLAMA_HOST, BASE_DIR
from runtime.ollama_client import chat_json, is_available

log = logging.getLogger(__name__)

OUTPUT_DIR = BASE_DIR / "divisions" / "production" / "narrative"

CONTENT_TYPES = {
    "dialogue":        "NPC dialogue tree with player choices",
    "quest":           "quest description with objectives and narrative hook",
    "lore":            "lore entry (codex / world-building text)",
    "character_bio":   "character biography and personality profile",
    "cutscene_script": "cutscene script with stage directions",
    "item_desc":       "in-game item descriptions and flavor text",
    "loading_tip":     "loading screen tips and world-building hints",
    "journal_entry":   "in-world journal / diary entry",
}

_SYSTEM_PROMPT = """\
You are the Narrative Writer for the Lykeon Forge — J_Claw's game production division.
Write compelling, lore-consistent narrative content.
Return ONLY valid JSON:
{
  "title": "piece title",
  "content_type": "the content type",
  "narrative": "the main written content",
  "metadata": {
    "word_count": 0,
    "tone": "dark | light | epic | mysterious | warm | tense",
    "characters": ["names of characters involved"]
  },
  "lore_tags": ["searchable lore tags"],
  "continuity_notes": "any continuity constraints or connections to existing lore"
}
Write with the gravitas of a seasoned RPG narrative designer. No fluff.\
"""


def run(content_type: str = "lore", subject: str = "", context: str = "") -> dict:
    """Narrative Writer skill entry point."""
    if content_type not in CONTENT_TYPES:
        valid = ", ".join(sorted(CONTENT_TYPES))
        return {
            "status": "failed",
            "summary": f"Unknown content_type '{content_type}'. Valid: {valid}",
            "metrics": {}, "action_items": [], "escalate": False,
        }

    if not subject:
        subject = f"generic {CONTENT_TYPES[content_type]}"

    if not is_available(MODEL_7B, host=OLLAMA_HOST):
        return {
            "status": "partial",
            "summary": f"Narrative request queued: {content_type} — '{subject}'. No LLM available.",
            "metrics": {"content_type": content_type, "subject": subject},
            "action_items": [{"priority": "low",
                               "description": "Start Ollama to write narrative content.",
                               "requires_matthew": False}],
            "escalate": False,
        }

    prompt = f"Content type: {CONTENT_TYPES[content_type]}\nSubject: {subject}"
    if context:
        prompt += f"\nContext/constraints: {context}"

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user",   "content": prompt},
    ]

    try:
        result = chat_json(MODEL_7B, messages, host=OLLAMA_HOST, temperature=0.8, max_tokens=2000)
        if not isinstance(result, dict):
            raise ValueError(f"Unexpected LLM response type: {type(result)}")

        title     = result.get("title", f"{content_type}: {subject}")
        meta      = result.get("metadata", {})
        word_count = meta.get("word_count", 0)
        tone      = meta.get("tone", "unknown")
        lore_tags = result.get("lore_tags", [])

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        slug      = subject.lower().replace(" ", "_")[:30] if subject else content_type
        filename  = f"{timestamp}_{content_type}_{slug}.json"
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out_path  = OUTPUT_DIR / filename
        out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

        log.info("narrative_write: wrote %s (%s tone, %d tags)", filename, tone, len(lore_tags))
        return {
            "status":  "success",
            "summary": (
                f"Narrative content written: '{title}'. "
                f"Tone: {tone}. {word_count} words. "
                f"Tags: {', '.join(lore_tags[:3]) if lore_tags else 'none'}."
            ),
            "metrics": {
                "title":        title,
                "content_type": content_type,
                "word_count":   word_count,
                "tone":         tone,
                "lore_tags":    lore_tags,
                "output_path":  str(out_path.relative_to(BASE_DIR)),
            },
            "action_items": [
                {"priority": "low",
                 "description": f"Review narrative content: {filename}",
                 "requires_matthew": True}
            ],
            "escalate": False,
        }

    except Exception as exc:
        log.error("narrative_write: LLM call failed — %s", exc)
        return {
            "status":  "failed",
            "summary": f"Narrative generation failed: {exc}",
            "metrics": {"content_type": content_type, "subject": subject},
            "action_items": [], "escalate": False,
        }

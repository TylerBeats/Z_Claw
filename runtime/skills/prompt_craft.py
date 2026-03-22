"""
Prompt Architect — builds and refines generation prompts per asset type.
Maintains templates in divisions/production/workflows/prompt_templates.json.
"""

import json
import logging
from pathlib import Path
from datetime import datetime, timezone

from runtime.config import BASE_DIR
from runtime.realm.config import DIVISIONS

log = logging.getLogger(__name__)

TEMPLATES_FILE = BASE_DIR / "divisions" / "production" / "workflows" / "prompt_templates.json"

_DIV_PALETTES = {
    "vael":         {"style": "fire emblem, amber and brown tones, dark hood, scout armor, bow"},
    "seren":        {"style": "fire emblem, silver and cyan tones, peaked hat, oracle robes, staff"},
    "kaelen":       {"style": "fire emblem, purple and dark metal tones, mech eye, iron armor, wrench"},
    "lyrin":        {"style": "fire emblem, green and white tones, leaf crown, healer robes, orb"},
    "zeth":         {"style": "fire emblem, dark shadow, red glowing eyes, hood, twin blades"},
    "lyke":         {"style": "fire emblem, deep orange and iron tones, architect armor, blueprint scroll"},
    "generic":      {"style": "fire emblem, fantasy, detailed character art"},
}

_BASE_QUALITY = "masterpiece, best quality, official art, ultra detailed"
_BASE_NEGATIVE = (
    "lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, "
    "fewer digits, cropped, worst quality, low quality, jpeg artifacts, "
    "signature, watermark, username, blurry, nsfw"
)

_TEMPLATES = {
    "portrait_bust": {
        "positive": "{quality}, {style}, 1{gender}, bust portrait, detailed face, large expressive eyes, "
                    "soft lighting, game character art, {subject}",
        "negative": _BASE_NEGATIVE,
        "width": 512,
        "height": 768,
        "steps": 28,
        "cfg": 7.0,
        "sampler": "euler",
        "scheduler": "karras",
    },
    "chibi_sprite": {
        "positive": "{quality}, {style}, chibi, super deformed, SD proportions, 1{gender}, "
                    "full body sprite, white background, game sprite, {subject}",
        "negative": _BASE_NEGATIVE + ", realistic proportions",
        "width": 512,
        "height": 512,
        "steps": 24,
        "cfg": 7.5,
        "sampler": "euler",
        "scheduler": "karras",
    },
    "battle_scene": {
        "positive": "{quality}, dynamic battle scene, {style}, fantasy combat, dramatic lighting, "
                    "{subject}",
        "negative": _BASE_NEGATIVE,
        "width": 832,
        "height": 512,
        "steps": 30,
        "cfg": 7.0,
        "sampler": "euler",
        "scheduler": "karras",
    },
    "ui_element": {
        "positive": "{quality}, game UI element, fantasy ornate border, {style}, {subject}, "
                    "transparent background, decorative frame",
        "negative": _BASE_NEGATIVE + ", characters, people",
        "width": 512,
        "height": 512,
        "steps": 20,
        "cfg": 6.5,
        "sampler": "euler",
        "scheduler": "karras",
    },
}


def _load_templates() -> dict:
    if TEMPLATES_FILE.exists():
        try:
            with open(TEMPLATES_FILE, encoding="utf-8") as f:
                saved = json.load(f)
                return {**_TEMPLATES, **saved}
        except Exception:
            pass
    return _TEMPLATES.copy()


def _save_templates(templates: dict) -> None:
    TEMPLATES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TEMPLATES_FILE, "w", encoding="utf-8") as f:
        json.dump(templates, f, indent=2)


def build_prompt(
    asset_type: str = "portrait_bust",
    commander: str = "generic",
    subject: str = "",
    gender: str = "girl",
) -> dict:
    """Build a complete generation prompt for a given asset type and commander."""
    templates = _load_templates()
    template = templates.get(asset_type, templates["portrait_bust"])
    palette = _DIV_PALETTES.get(commander.lower(), _DIV_PALETTES["generic"])

    positive = template["positive"].format(
        quality=_BASE_QUALITY,
        style=palette["style"],
        subject=subject or commander,
        gender=gender,
    )

    return {
        "positive":  positive,
        "negative":  template["negative"],
        "width":     template["width"],
        "height":    template["height"],
        "steps":     template["steps"],
        "cfg":       template["cfg"],
        "sampler":   template["sampler"],
        "scheduler": template["scheduler"],
        "asset_type": asset_type,
        "commander": commander,
    }


def run(asset_type: str = "portrait_bust", commander: str = "generic", subject: str = "") -> dict:
    """Prompt Architect skill entry point."""
    try:
        prompt = build_prompt(asset_type=asset_type, commander=commander, subject=subject)
        _save_templates(_load_templates())  # ensure templates file exists

        log.info("Prompt crafted: %s / %s", asset_type, commander)
        return {
            "status":    "success",
            "summary":   f"Prompt crafted for {asset_type} ({commander}). Ready for generation.",
            "metrics":   {"asset_type": asset_type, "commander": commander},
            "prompt":    prompt,
            "action_items": [],
            "escalate":  False,
        }
    except Exception as e:
        log.error("prompt_craft failed: %s", e)
        return {
            "status":    "failed",
            "summary":   f"Prompt craft failed: {e}",
            "metrics":   {},
            "action_items": [{"priority": "normal", "description": str(e), "requires_matthew": False}],
            "escalate":  False,
        }

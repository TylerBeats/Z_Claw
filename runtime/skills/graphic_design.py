"""
Graphic Designer — generates UI elements, card borders, overlays, and decorative
assets via ComfyUI. Focused on game UI/UX assets rather than characters.
"""

import logging
from runtime.skills.image_generate import run as _generate

log = logging.getLogger(__name__)

_UI_SUBJECTS = {
    "card_border":    "ornate fantasy card border, fire emblem style, decorative frame, gold trim, gemstones",
    "achievement":    "achievement badge, fantasy seal, ornate medallion, glowing runes, fire emblem style",
    "rank_banner":    "rank promotion banner, fantasy heraldry, fire emblem style, ornate ribbon",
    "division_crest": "division crest emblem, fantasy coat of arms, fire emblem style, detailed heraldry",
    "background":     "fantasy landscape background, fire emblem style, atmospheric, no characters",
    "button_ui":      "fantasy UI button, ornate, fire emblem style, crystal gem accent",
}


def run(
    ui_type:   str = "card_border",
    theme:     str = "generic",
    subject:   str = "",
) -> dict:
    """Graphic Designer skill entry point."""
    base_subject = _UI_SUBJECTS.get(ui_type, ui_type)
    full_subject = f"{base_subject}, {subject}" if subject else base_subject

    result = _generate(
        asset_type="ui_element",
        commander=theme,
        subject=full_subject,
    )

    if result["status"] == "success":
        result["summary"] = f"UI element generated: {ui_type} ({theme} theme). Pending review."
        result["metrics"]["ui_type"] = ui_type
        result["metrics"]["theme"]   = theme

    log.info("graphic_design: %s / %s → %s", ui_type, theme, result["status"])
    return result

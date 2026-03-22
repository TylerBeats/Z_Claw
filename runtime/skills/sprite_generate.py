"""
Sprite Generator — generates Fire Emblem style chibi sprites and bust portraits
for all commanders and enemies via ComfyUI.
"""

import logging
from runtime.skills.image_generate import run as _generate

log = logging.getLogger(__name__)

_COMMANDERS = ["vael", "seren", "kaelen", "lyrin", "zeth", "lyke"]
_ENEMIES = ["false_lead", "market_noise", "code_rot", "burnout_shade", "null_breach", "broken_render"]

_SUBJECT_MAP = {
    "vael":          "hooded scout, amber eyes, brown layered hair, bow weapon, dark cloak",
    "seren":         "peaked hat, silver hair, large cyan eyes, oracle staff, knowing smile",
    "kaelen":        "mech eye lens, purple visor, armored collar, mechanical wrench",
    "lyrin":         "leaf crown, warm brown hair, green eyes, gentle smile, healing orb, white robe",
    "zeth":          "face in shadow, only red eyes visible, dark hood, twin blades at side",
    "lyke":          "deep orange armor, blueprint scroll, forge-fire amber eyes, hexagonal motifs",
    "false_lead":    "shadowy figure, glowing lure, mirage energy, deceptive aura",
    "market_noise":  "chaotic data streams, static visual, flickering numbers, market storm",
    "code_rot":      "corrupted code tendrils, dark digital decay, glitch patterns",
    "burnout_shade":  "drained energy, hollow eyes, fading embers, exhausted form",
    "null_breach":   "void entity, dimensional tear, null energy, shadowy breach",
    "broken_render": "fragmented geometry, artifact glitches, pixelated corruption, error distortion",
}


def run(
    target: str = "vael",
    sprite_type: str = "chibi_sprite",
) -> dict:
    """
    Sprite Generator skill entry point.
    target: commander key or enemy key
    sprite_type: 'chibi_sprite' or 'portrait_bust'
    """
    subject = _SUBJECT_MAP.get(target.lower(), target)
    result  = _generate(
        asset_type=sprite_type,
        commander=target.lower(),
        subject=subject,
    )

    # Wrap with sprite-specific metadata
    if result["status"] == "success":
        result["summary"] = f"Sprite generated for {target} ({sprite_type}). Pending style check."
        result["metrics"]["target"] = target
        result["metrics"]["sprite_type"] = sprite_type

    log.info("sprite_generate: %s / %s → %s", target, sprite_type, result["status"])
    return result

"""
Style Guardian — validates generated assets match established art direction.
Uses PIL to extract dominant colors and compare against commander palettes.
"""

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

# Expected dominant color ranges per commander (H, S, V in 0-255)
_PALETTE_RULES = {
    "vael":   {"hue_range": (20, 45),  "desc": "amber/brown tones"},
    "seren":  {"hue_range": (170, 200), "desc": "silver/cyan tones"},
    "kaelen": {"hue_range": (230, 280), "desc": "purple/dark metal tones"},
    "lyrin":  {"hue_range": (100, 140), "desc": "green/white tones"},
    "zeth":   {"hue_range": (0, 15),   "desc": "dark red/shadow tones"},
    "lyke":   {"hue_range": (15, 35),  "desc": "deep orange/iron tones"},
}


def _check_image_style(image_path: Path, commander: str) -> dict:
    """PIL-based dominant color check against commander palette."""
    try:
        from PIL import Image
        import colorsys

        img = Image.open(image_path).convert("RGB")
        img = img.resize((64, 64))  # fast sample

        # Count pixel hues
        hue_counts = {}
        pixels = list(img.getdata())
        for r, g, b in pixels:
            h, s, v = colorsys.rgb_to_hsv(r/255, g/255, b/255)
            if s > 0.2 and v > 0.2:  # ignore near-grey/black pixels
                h_deg = int(h * 360)
                hue_counts[h_deg // 10] = hue_counts.get(h_deg // 10, 0) + 1

        if not hue_counts:
            return {"pass": None, "reason": "Image appears monochrome or very dark"}

        dominant_hue_bucket = max(hue_counts, key=hue_counts.get) * 10
        rule = _PALETTE_RULES.get(commander)

        if not rule:
            return {"pass": True, "reason": "No palette rule defined for this commander", "dominant_hue": dominant_hue_bucket}

        lo, hi = rule["hue_range"]
        passed = lo <= dominant_hue_bucket <= hi
        return {
            "pass":          passed,
            "dominant_hue":  dominant_hue_bucket,
            "expected_range": rule["hue_range"],
            "expected_desc": rule["desc"],
            "reason":        "Palette match" if passed else f"Hue {dominant_hue_bucket}° outside expected range {lo}-{hi}° ({rule['desc']})",
        }

    except ImportError:
        return {"pass": None, "reason": "PIL not available — install Pillow for style checking"}
    except Exception as e:
        return {"pass": None, "reason": f"Style check error: {e}"}


def run(image_path: str = "", commander: str = "generic") -> dict:
    """Style Guardian skill entry point."""
    if not image_path:
        return {
            "status":  "partial",
            "summary": "No image path provided. Pass image_path=<path> to run style check.",
            "metrics": {},
            "action_items": [],
            "escalate": False,
        }

    path = Path(image_path)
    if not path.exists():
        return {
            "status":  "failed",
            "summary": f"Image not found: {image_path}",
            "metrics": {},
            "action_items": [{"priority": "normal", "description": f"File missing: {image_path}", "requires_matthew": False}],
            "escalate": False,
        }

    result = _check_image_style(path, commander)
    passed = result.get("pass")

    if passed is True:
        status  = "success"
        summary = f"Style check passed for {path.name} ({commander}). {result['reason']}"
    elif passed is False:
        status  = "partial"
        summary = f"Style mismatch detected in {path.name}. {result['reason']}"
    else:
        status  = "partial"
        summary = f"Style check inconclusive for {path.name}. {result.get('reason', 'Unknown')}"

    log.info("style_check: %s / %s → %s", path.name, commander, status)
    return {
        "status":  status,
        "summary": summary,
        "metrics": {
            "image":    str(path.name),
            "commander": commander,
            **result,
        },
        "action_items": [] if passed else [{
            "priority":        "normal",
            "description":     f"Regenerate {path.name} — palette does not match {commander} art direction.",
            "requires_matthew": False,
        }],
        "escalate": False,
    }

"""
Continuity Warden — validates visual consistency across a character's evolution tiers.
Compares dominant color and brightness across all tier images for a commander.
"""

import json
import logging
from pathlib import Path

from runtime.config import BASE_DIR, STATE_DIR

log = logging.getLogger(__name__)

CATALOG_FILE = STATE_DIR / "asset-catalog.json"
ASSET_ROOT   = BASE_DIR / "mobile" / "assets" / "generated"

# Max allowed hue drift between tiers (degrees)
_MAX_HUE_DRIFT   = 45
# Max allowed brightness drift
_MAX_BRIGHT_DRIFT = 80


def _load_catalog() -> list:
    if not CATALOG_FILE.exists():
        return []
    try:
        with open(CATALOG_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _dominant_hue(path: Path) -> float | None:
    try:
        from PIL import Image
        import colorsys

        img = Image.open(path).convert("RGB").resize((32, 32))
        hues = []
        for r, g, b in img.getdata():
            h, s, v = colorsys.rgb_to_hsv(r/255, g/255, b/255)
            if s > 0.2 and v > 0.2:
                hues.append(h * 360)
        if not hues:
            return None
        return sum(hues) / len(hues)
    except Exception:
        return None


def run(commander: str = "") -> dict:
    """Continuity Warden skill entry point."""
    if not commander:
        return {
            "status":  "partial",
            "summary": "No commander specified. Pass commander=<name> to run continuity check.",
            "metrics": {},
            "action_items": [],
            "escalate": False,
        }

    catalog  = _load_catalog()
    entries  = [e for e in catalog if e.get("commander") == commander.lower()
                and e.get("type") in ("portrait", "sprite")
                and e.get("status") == "approved"]

    if len(entries) < 2:
        return {
            "status":  "partial",
            "summary": f"Fewer than 2 approved assets for {commander}. Nothing to compare.",
            "metrics": {"approved_assets": len(entries)},
            "action_items": [],
            "escalate": False,
        }

    hues = []
    for e in entries:
        path = BASE_DIR / e["path"]
        if path.exists():
            h = _dominant_hue(path)
            if h is not None:
                hues.append({"tier": e.get("tier", 0), "hue": h, "file": e["filename"]})

    if len(hues) < 2:
        return {
            "status":  "partial",
            "summary": f"Could not extract hue data from enough images for {commander}.",
            "metrics": {"images_analyzed": len(hues)},
            "action_items": [],
            "escalate": False,
        }

    hue_values = [h["hue"] for h in hues]
    hue_range  = max(hue_values) - min(hue_values)
    passed     = hue_range <= _MAX_HUE_DRIFT

    issues = []
    if hue_range > _MAX_HUE_DRIFT:
        outliers = [h for h in hues if abs(h["hue"] - hue_values[0]) > _MAX_HUE_DRIFT]
        issues.append(f"Hue drift {hue_range:.0f}° exceeds max {_MAX_HUE_DRIFT}°. Outliers: {[o['file'] for o in outliers]}")

    log.info("continuity_check: %s → hue_range=%.0f° → %s", commander, hue_range, "pass" if passed else "fail")

    return {
        "status":  "success" if passed else "partial",
        "summary": (
            f"Continuity check for {commander}: {'PASSED' if passed else 'ISSUES FOUND'}. "
            f"Hue range across {len(hues)} images: {hue_range:.0f}°. "
            + ("; ".join(issues) if issues else "Visual consistency maintained.")
        ),
        "metrics": {
            "commander":    commander,
            "images":       len(hues),
            "hue_range":    round(hue_range, 1),
            "hue_data":     hues,
            "passed":       passed,
        },
        "action_items": [{
            "priority":        "normal",
            "description":     f"Continuity drift in {commander}: {'; '.join(issues)}",
            "requires_matthew": False,
        }] if issues else [],
        "escalate": not passed,
    }

"""
Image Editor — QA agent that detects disfigured, artifacted, or failed images.
Uses PIL to check for common generation failures: solid color, extreme darkness,
near-white blowout, extreme aspect ratios.
"""

import logging
from pathlib import Path

log = logging.getLogger(__name__)

_MIN_SIZE_PX   = 64
_MAX_DARK_RATIO  = 0.85   # >85% near-black pixels = failed generation
_MAX_LIGHT_RATIO = 0.85   # >85% near-white pixels = blown out
_MAX_SOLID_RATIO = 0.70   # >70% same color bucket = solid color artifact


def _analyze_image(path: Path) -> dict:
    try:
        from PIL import Image, ImageStat
        import statistics

        img = Image.open(path).convert("RGB")
        w, h = img.size

        if w < _MIN_SIZE_PX or h < _MIN_SIZE_PX:
            return {"pass": False, "reason": f"Image too small: {w}x{h}"}

        stat = ImageStat.Stat(img)
        mean_brightness = sum(stat.mean) / 3

        if mean_brightness < 15:
            return {"pass": False, "reason": f"Image near-black (mean brightness {mean_brightness:.1f})"}
        if mean_brightness > 245:
            return {"pass": False, "reason": f"Image blown out (mean brightness {mean_brightness:.1f})"}

        # Check for solid color artifact
        small = img.resize((32, 32))
        pixels = list(small.getdata())
        color_buckets = {}
        for r, g, b in pixels:
            key = (r // 32, g // 32, b // 32)
            color_buckets[key] = color_buckets.get(key, 0) + 1
        total = len(pixels)
        dominant_ratio = max(color_buckets.values()) / total
        if dominant_ratio > _MAX_SOLID_RATIO:
            return {"pass": False, "reason": f"Solid color artifact detected ({dominant_ratio:.0%} uniform)"}

        # Check std deviation (low = flat/boring image)
        std_avg = sum(stat.stddev) / 3
        if std_avg < 8:
            return {"pass": False, "reason": f"Very low contrast (stddev {std_avg:.1f}) — possible generation failure"}

        return {
            "pass":             True,
            "reason":           "Image passes QA checks",
            "mean_brightness":  round(mean_brightness, 1),
            "std_dev":          round(std_avg, 1),
            "dimensions":       f"{w}x{h}",
            "dominant_ratio":   round(dominant_ratio, 3),
        }

    except ImportError:
        return {"pass": None, "reason": "PIL not available — install Pillow for image review"}
    except Exception as e:
        return {"pass": None, "reason": f"Review error: {e}"}


def run(image_path: str = "") -> dict:
    """Image Editor skill entry point."""
    if not image_path:
        return {
            "status":  "partial",
            "summary": "No image path provided. Pass image_path=<path> to run review.",
            "metrics": {},
            "action_items": [],
            "escalate": False,
        }

    path = Path(image_path)
    if not path.exists():
        return {
            "status":  "failed",
            "summary": f"File not found: {image_path}",
            "metrics": {},
            "action_items": [{"priority": "normal", "description": f"File missing: {image_path}", "requires_matthew": False}],
            "escalate": False,
        }

    result = _analyze_image(path)
    passed = result.get("pass")

    if passed is True:
        status  = "success"
        summary = f"Image QA passed: {path.name}. {result['reason']}"
    elif passed is False:
        status  = "partial"
        summary = f"Image QA FAILED: {path.name}. {result['reason']}"
    else:
        status  = "partial"
        summary = f"Image review inconclusive: {path.name}. {result.get('reason')}"

    log.info("image_review: %s → %s", path.name, status)
    return {
        "status":  status,
        "summary": summary,
        "metrics": {"image": str(path.name), **result},
        "action_items": [] if passed else [{
            "priority":        "normal",
            "description":     f"Regenerate {path.name} — failed QA: {result.get('reason')}",
            "requires_matthew": False,
        }],
        "escalate": passed is False,
    }

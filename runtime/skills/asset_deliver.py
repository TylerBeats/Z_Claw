"""
Asset Delivery Agent — routes approved, undelivered assets to their correct
game directories under mobile/assets/ and updates the catalog.
"""

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

from runtime.config import BASE_DIR, STATE_DIR

log = logging.getLogger(__name__)

CATALOG_FILE = STATE_DIR / "asset-catalog.json"
DEST_ROOT    = BASE_DIR / "mobile" / "assets"

_TYPE_DIRS = {
    "portrait":   "portraits",
    "sprite":     "sprites",
    "video":      "video",
    "audio":      "audio",
    "graphic":    "graphics",
    "ui":         "ui",
    "background": "backgrounds",
}


def _load_catalog() -> list:
    if not CATALOG_FILE.exists():
        return []
    try:
        with open(CATALOG_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_catalog(catalog: list) -> None:
    CATALOG_FILE.parent.mkdir(exist_ok=True)
    with open(CATALOG_FILE, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2)


def run() -> dict:
    """Asset Delivery skill entry point."""
    catalog   = _load_catalog()
    to_deliver = [
        e for e in catalog
        if e.get("status") == "approved" and not e.get("delivered")
    ]

    if not to_deliver:
        return {
            "status":  "success",
            "summary": "No approved assets pending delivery. All caught up.",
            "metrics": {"delivered": 0},
            "action_items": [],
            "escalate": False,
        }

    delivered   = []
    failed      = []

    for entry in to_deliver:
        src_path = BASE_DIR / entry["path"]
        if not src_path.exists():
            log.warning("asset_deliver: source missing %s", entry["path"])
            failed.append(entry["filename"])
            continue

        type_dir  = _TYPE_DIRS.get(entry.get("type", "graphic"), "graphics")
        commander = entry.get("commander", "generic")
        dest_dir  = DEST_ROOT / type_dir / commander
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / entry["filename"]

        try:
            shutil.copy2(src_path, dest_path)
            entry["delivered"]    = True
            entry["delivered_at"] = datetime.now(timezone.utc).isoformat()
            entry["dest_path"]    = str(dest_path.relative_to(BASE_DIR)).replace("\\", "/")
            delivered.append(entry["filename"])
            log.info("asset_deliver: %s → %s", entry["filename"], entry["dest_path"])
        except Exception as e:
            log.error("asset_deliver: failed %s — %s", entry["filename"], e)
            failed.append(entry["filename"])

    _save_catalog(catalog)

    return {
        "status":  "success" if not failed else "partial",
        "summary": (
            f"Delivered {len(delivered)} asset(s) to mobile/assets/. "
            + (f"{len(failed)} failed: {failed}" if failed else "All deliveries successful.")
        ),
        "metrics": {
            "delivered":  len(delivered),
            "failed":     len(failed),
            "files":      delivered,
        },
        "action_items": [{
            "priority":        "normal",
            "description":     f"Delivery failed for: {failed}",
            "requires_matthew": False,
        }] if failed else [],
        "escalate": len(failed) > 0,
    }

"""
Asset Delivery Agent — routes approved, undelivered assets to their correct
game directories under mobile/assets/ and updates the catalog.
"""

import json
import logging
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from runtime.config import BASE_DIR, STATE_DIR
from runtime.skills import asset_catalog

log = logging.getLogger(__name__)

CATALOG_FILE  = STATE_DIR / "asset-catalog.json"
DEST_ROOT     = BASE_DIR / "mobile" / "assets"
GENERATED_DIR = BASE_DIR / "mobile" / "assets" / "generated"
HOT_ROOT      = BASE_DIR / "divisions" / "production" / "hot"

# Read hot_ttl_hours from production config; fall back to 72 if unavailable.
def _hot_ttl_hours() -> int:
    cfg_path = BASE_DIR / "divisions" / "production" / "config.json"
    try:
        with open(cfg_path, encoding="utf-8") as f:
            data = json.load(f)
        return int(data.get("asset_policy", {}).get("hot_ttl_hours", 72))
    except Exception:
        return 72

_MEDIA_EXTS = {".png", ".jpg", ".webp", ".wav", ".mp3", ".ogg"}

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


def _promote_generated_to_hot() -> int:
    """
    Copy newly generated media files from mobile/assets/generated/ into
    divisions/production/hot/, preserving relative path structure, and
    register each one in the asset catalog with status='pending' and
    lifecycle='hot'.

    Only files younger than hot_ttl_hours that do not already have a
    corresponding file in hot/ are promoted.

    Returns the number of files promoted.
    """
    if not GENERATED_DIR.exists():
        return 0

    ttl_hours = _hot_ttl_hours()
    cutoff    = datetime.now(timezone.utc) - timedelta(hours=ttl_hours)
    promoted  = 0

    for src in GENERATED_DIR.rglob("*"):
        if not src.is_file():
            continue
        if src.suffix.lower() not in _MEDIA_EXTS:
            continue

        # Skip files older than the TTL window.
        mtime = datetime.fromtimestamp(src.stat().st_mtime, tz=timezone.utc)
        if mtime < cutoff:
            continue

        # Determine destination inside hot/, preserving relative structure.
        rel      = src.relative_to(GENERATED_DIR)
        dest     = HOT_ROOT / rel

        # Skip if already promoted.
        if dest.exists():
            continue

        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
        except Exception as e:
            log.error("asset_deliver: promote failed %s — %s", src, e)
            continue

        # Register / update the catalog entry via asset_catalog.add_entry().
        hot_rel_path = str(dest.relative_to(BASE_DIR)).replace("\\", "/")
        asset_catalog.add_entry(
            path=hot_rel_path,
            status="pending",
        )

        # Patch lifecycle="hot" onto the entry that add_entry() just wrote.
        catalog = _load_catalog()
        for entry in catalog:
            if entry.get("path") == hot_rel_path:
                entry["lifecycle"] = "hot"
                break
        _save_catalog(catalog)

        promoted += 1
        log.info("asset_deliver: promoted %s → %s", rel, hot_rel_path)

    return promoted


def run() -> dict:
    """Asset Delivery skill entry point."""
    # Promote any new generated files into hot/ before doing delivery work.
    promoted = _promote_generated_to_hot()

    catalog   = _load_catalog()
    to_deliver = [
        e for e in catalog
        if e.get("status") == "approved" and not e.get("delivered")
    ]

    if not to_deliver:
        return {
            "status":  "success",
            "summary": (
                f"No approved assets pending delivery. All caught up. "
                f"{promoted} file(s) promoted to hot/."
            ),
            "metrics": {"delivered": 0, "promoted": promoted},
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
            f"Promoted {promoted} file(s) to hot/. "
            f"Delivered {len(delivered)} asset(s) to mobile/assets/. "
            + (f"{len(failed)} failed: {failed}" if failed else "All deliveries successful.")
        ),
        "metrics": {
            "promoted":   promoted,
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

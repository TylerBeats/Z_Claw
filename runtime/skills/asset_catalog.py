"""
Asset Cataloger — indexes all generated assets by type, commander, tier, and status.
Writes to state/asset-catalog.json. Source of truth for the production pipeline.
"""

import json
import logging
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from runtime.config import BASE_DIR, STATE_DIR

log = logging.getLogger(__name__)

CATALOG_FILE = STATE_DIR / "asset-catalog.json"
ASSET_ROOT   = BASE_DIR / "mobile" / "assets" / "generated"
HOT_ROOT     = BASE_DIR / "divisions" / "production" / "hot"
COLD_ROOT    = BASE_DIR / "divisions" / "production" / "cold"
HOT_TTL_DAYS = 7

_VALID_TYPES    = {"portrait", "sprite", "video", "audio", "graphic", "background", "ui"}
_VALID_STATUSES = {"pending", "approved", "rejected", "delivered"}
_IMG_EXTS       = {".png", ".jpg", ".jpeg", ".webp"}
_VID_EXTS       = {".mp4", ".webm", ".mov"}
_AUD_EXTS       = {".wav", ".mp3", ".ogg"}


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


def _infer_type(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in _IMG_EXTS:
        parent = path.parent.name.lower()
        if "sprite" in parent or "chibi" in parent:
            return "sprite"
        if "portrait" in parent or "bust" in parent:
            return "portrait"
        if "ui" in parent or "graphic" in parent:
            return "ui"
        return "graphic"
    if ext in _VID_EXTS:
        return "video"
    if ext in _AUD_EXTS:
        return "audio"
    return "graphic"


def _scan_assets() -> list:
    """Scan ASSET_ROOT for all media files and return entry list."""
    entries = []
    if not ASSET_ROOT.exists():
        return entries
    for f in ASSET_ROOT.rglob("*"):
        if f.is_file() and f.suffix.lower() in (_IMG_EXTS | _VID_EXTS | _AUD_EXTS):
            parts = f.relative_to(ASSET_ROOT).parts
            commander = parts[0] if len(parts) > 1 else "generic"
            entries.append({
                "id":           str(uuid.uuid4())[:8],
                "type":         _infer_type(f),
                "commander":    commander,
                "tier":         0,
                "path":         str(f.relative_to(BASE_DIR)).replace("\\", "/"),
                "filename":     f.name,
                "size_kb":      round(f.stat().st_size / 1024, 1),
                "status":       "pending",
                "generated_at": datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc).isoformat(),
                "delivered":    False,
            })
    return entries


def _age_hot_to_cold() -> dict:
    """Move assets older than HOT_TTL_DAYS from hot/ to cold/."""
    if not HOT_ROOT.exists():
        return {"moved": 0}
    catalog  = _load_catalog()
    cutoff   = datetime.now(timezone.utc) - timedelta(days=HOT_TTL_DAYS)
    moved    = 0
    for f in HOT_ROOT.rglob("*"):
        if not f.is_file():
            continue
        mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
        if mtime >= cutoff:
            continue
        rel     = f.relative_to(HOT_ROOT)
        dest    = COLD_ROOT / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(f), str(dest))
        moved  += 1
        rel_hot  = str(f.relative_to(BASE_DIR)).replace("\\", "/")
        rel_cold = str(dest.relative_to(BASE_DIR)).replace("\\", "/")
        entry = next((e for e in catalog if e["path"] == rel_hot), None)
        if entry:
            entry["path"]          = rel_cold
            entry["lifecycle"]     = "cold"
            entry["cold_moved_at"] = datetime.now(timezone.utc).isoformat()
        else:
            catalog.append({
                "id":           str(uuid.uuid4())[:8],
                "type":         _infer_type(dest),
                "commander":    "generic",
                "tier":         0,
                "path":         rel_cold,
                "filename":     dest.name,
                "size_kb":      round(dest.stat().st_size / 1024, 1),
                "status":       "approved",
                "generated_at": mtime.isoformat(),
                "delivered":    True,
                "lifecycle":    "cold",
                "cold_moved_at": datetime.now(timezone.utc).isoformat(),
            })
    if moved > 0:
        _save_catalog(catalog)
        log.info("asset_catalog: aged %d file(s) from hot/ to cold/", moved)
    return {"moved": moved}


def run() -> dict:
    """Asset Cataloger skill entry point — scans and syncs the asset catalog."""
    catalog       = _load_catalog()
    existing_paths = {e["path"] for e in catalog}

    scanned  = _scan_assets()
    new_entries = [e for e in scanned if e["path"] not in existing_paths]

    # Add new entries
    catalog.extend(new_entries)
    _save_catalog(catalog)

    # Age hot assets to cold storage
    aged = _age_hot_to_cold()

    total     = len(catalog)
    pending   = sum(1 for e in catalog if e["status"] == "pending")
    approved  = sum(1 for e in catalog if e["status"] == "approved")
    delivered = sum(1 for e in catalog if e.get("delivered"))

    log.info("asset_catalog: total=%d, new=%d, pending=%d, approved=%d, aged_to_cold=%d",
             total, len(new_entries), pending, approved, aged["moved"])

    return {
        "status":  "success",
        "summary": (
            f"Asset catalog synced. {total} total assets, {len(new_entries)} newly indexed. "
            f"{pending} pending review, {approved} approved, {delivered} delivered. "
            f"{aged['moved']} aged from hot to cold."
        ),
        "metrics": {
            "total":          total,
            "new_indexed":    len(new_entries),
            "pending":        pending,
            "approved":       approved,
            "delivered":      delivered,
            "aged_to_cold":   aged["moved"],
        },
        "action_items": [{
            "priority":        "normal",
            "description":     f"{pending} asset(s) awaiting approval in state/asset-catalog.json",
            "requires_matthew": True,
        }] if pending > 0 else [],
        "escalate": False,
    }


def add_entry(
    path: str,
    asset_type: str = "graphic",
    commander: str  = "generic",
    tier: int       = 0,
    status: str     = "pending",
) -> dict:
    """Manually add or update a catalog entry."""
    catalog = _load_catalog()
    existing = next((e for e in catalog if e["path"] == path), None)
    if existing:
        existing["status"] = status
        existing["type"]   = asset_type
    else:
        catalog.append({
            "id":           str(uuid.uuid4())[:8],
            "type":         asset_type,
            "commander":    commander,
            "tier":         tier,
            "path":         path,
            "filename":     Path(path).name,
            "size_kb":      0,
            "status":       status,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "delivered":    False,
        })
    _save_catalog(catalog)
    return {"added": path, "status": status}

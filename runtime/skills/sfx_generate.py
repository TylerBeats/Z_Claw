"""
Sound Designer — generates sound effects via Meta AudioGen.

When the audiocraft library is installed the skill synthesizes SFX from a text
description using facebook/audiogen-medium (~1.5 GB).
On AMD/Windows the model runs on DirectML (torch-directml) if available,
otherwise falls back to CPU.

If the backend is not installed the request is queued to state/sfx-queue.json
for later processing.

Install:
    pip install audiocraft scipy
    pip install torch-directml  # optional AMD GPU acceleration
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from runtime.config import BASE_DIR

log = logging.getLogger(__name__)

QUEUE_FILE = BASE_DIR / "state" / "sfx-queue.json"
SFX_OUT    = BASE_DIR / "mobile" / "assets" / "generated" / "sfx"

# ── Optional backend detection ────────────────────────────────────────────────

_AUDIOCRAFT_OK = False
_dml_device    = None

try:
    import audiocraft as _audiocraft  # noqa: F401
    _AUDIOCRAFT_OK = True
except ImportError:
    pass

if _AUDIOCRAFT_OK:
    try:
        import torch_directml as _torch_directml
        _dml_device = _torch_directml.device()
        log.info("sfx_generate: torch-directml device available.")
    except ImportError:
        log.info("sfx_generate: torch-directml not found, using CPU.")

_BACKEND_AVAILABLE = _AUDIOCRAFT_OK

# Lazy model singleton
_model = None


def _load_audiogen():
    global _model
    if _model is None:
        from audiocraft.models import AudioGen
        log.info("sfx_generate: loading facebook/audiogen-medium — first run will download ~1.5 GB...")
        _model = AudioGen.get_pretrained("facebook/audiogen-medium")
        if _dml_device is not None:
            _model = _model.to(_dml_device)
        log.info("sfx_generate: model loaded.")
    return _model


# ── SFX type library ──────────────────────────────────────────────────────────

SFX_LIBRARY = {
    "footstep":     {"base": "footstep on stone floor, single step, RPG game sound effect",          "duration": 1.0},
    "attack":       {"base": "sword swing attack, whoosh, game combat sound effect",                  "duration": 1.5},
    "explosion":    {"base": "large explosion blast, impact, game sound effect",                       "duration": 2.5},
    "ui_click":     {"base": "menu button click, clean interface sound, game UI",                     "duration": 0.3},
    "level_up":     {"base": "triumphant level up chime, ascending tones, game notification",         "duration": 2.0},
    "ambient":      {"base": "atmospheric ambient background loop, fantasy environment, loopable",    "duration": 5.0},
    "magic_cast":   {"base": "magic spell cast, arcane energy release, fantasy game effect",          "duration": 1.5},
    "door_open":    {"base": "wooden door creaking open, dungeon door, RPG game sound",               "duration": 1.5},
    "coin_pickup":  {"base": "coin collection chime, gold pickup jingle, game UI sound",              "duration": 0.5},
    "hurt":         {"base": "character hit pain grunt, damage taken, RPG game",                      "duration": 0.8},
    "death":        {"base": "character death sound, defeat sting, game over",                         "duration": 2.0},
    "victory":      {"base": "short victory fanfare, success chime, game achievement sound",          "duration": 3.0},
    "notification": {"base": "quest notification chime, journal update, soft bell, game UI",          "duration": 1.0},
    "custom":       {"base": "",                                                                        "duration": 3.0},
}

# ── Queue helpers ─────────────────────────────────────────────────────────────

def _load_queue() -> list:
    if not QUEUE_FILE.exists():
        return []
    try:
        with open(QUEUE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_queue(queue: list) -> None:
    QUEUE_FILE.parent.mkdir(exist_ok=True)
    with open(QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(queue, f, indent=2)


# ── Generation ────────────────────────────────────────────────────────────────

def _generate_sfx(entry: dict) -> str | None:
    try:
        import torch
        import numpy as np
        import scipy.io.wavfile

        model    = _load_audiogen()
        spec     = entry["spec"]
        duration = spec["duration_s"]
        prompt   = spec["prompt"]

        model.set_generation_params(duration=duration)
        with torch.no_grad():
            wav = model.generate([prompt])

        # wav shape: [batch, channels, samples]
        audio_np    = wav[0, 0].cpu().numpy()
        audio_norm  = audio_np / (abs(audio_np).max() + 1e-8)
        audio_int16 = (audio_norm * 32767).astype(np.int16)
        sample_rate = model.sample_rate

        sfx_type = spec.get("sfx_type", "sfx")
        queue_id = entry["id"]
        out_dir  = SFX_OUT / sfx_type
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{queue_id}.wav"

        scipy.io.wavfile.write(str(out_path), sample_rate, audio_int16)
        log.info("sfx_generate: wrote %s", out_path)
        return str(out_path)

    except Exception as exc:
        log.error("sfx_generate: generation failed for %s — %s", entry.get("id"), exc)
        return None


def _flush_queue(queue: list) -> None:
    for entry in queue:
        if entry.get("status") != "queued":
            continue
        out_path = _generate_sfx(entry)
        if out_path:
            entry["status"]       = "completed"
            entry["output_path"]  = out_path
            entry["completed_at"] = datetime.now(timezone.utc).isoformat()
        else:
            entry["status"]    = "failed"
            entry["failed_at"] = datetime.now(timezone.utc).isoformat()


# ── Skill entry point ─────────────────────────────────────────────────────────

def run(sfx_type: str = "ui_click", description: str = "", duration_s: float = 0.0) -> dict:
    """Sound Designer skill entry point."""
    if sfx_type not in SFX_LIBRARY:
        valid = ", ".join(sorted(SFX_LIBRARY))
        return {
            "status": "failed",
            "summary": f"Unknown sfx_type '{sfx_type}'. Valid: {valid}",
            "metrics": {}, "action_items": [], "escalate": False,
        }

    template = SFX_LIBRARY[sfx_type]
    base     = template["base"]
    dur      = duration_s if duration_s > 0 else template["duration"]

    if sfx_type == "custom" and not description:
        return {
            "status": "failed",
            "summary": "sfx_type 'custom' requires a description.",
            "metrics": {}, "action_items": [], "escalate": False,
        }

    prompt = f"{base}, {description}" if description and base else (description or base)

    spec = {
        "sfx_type":    sfx_type,
        "prompt":      prompt,
        "duration_s":  dur,
        "description": description,
    }

    queue = _load_queue()

    if _BACKEND_AVAILABLE and queue:
        _flush_queue(queue)
        _save_queue(queue)

    queue_id = f"sfx-{len(queue)+1:04d}"
    entry = {
        "id":        queue_id,
        "spec":      spec,
        "status":    "queued",
        "queued_at": datetime.now(timezone.utc).isoformat(),
    }
    queue.append(entry)

    if _BACKEND_AVAILABLE:
        out_path = _generate_sfx(entry)
        if out_path:
            entry["status"]       = "completed"
            entry["output_path"]  = out_path
            entry["completed_at"] = datetime.now(timezone.utc).isoformat()
            _save_queue(queue)
            return {
                "status":  "success",
                "summary": f"SFX generated ({queue_id}): {sfx_type}, {dur}s. Output: {out_path}",
                "metrics": {"queue_id": queue_id, "sfx_type": sfx_type, "duration_s": dur,
                             "output_path": out_path, "queue_depth": len(queue)},
                "action_items": [], "escalate": False,
            }
        else:
            entry["status"]    = "failed"
            entry["failed_at"] = datetime.now(timezone.utc).isoformat()
            _save_queue(queue)
            return {
                "status":  "failed",
                "summary": f"SFX generation failed ({queue_id}). Check logs for AudioGen error.",
                "metrics": {"queue_id": queue_id, "sfx_type": sfx_type, "queue_depth": len(queue)},
                "action_items": [{"priority": "medium",
                                   "description": "AudioGen SFX generation failed — check logs.",
                                   "requires_matthew": True}],
                "escalate": False,
            }

    _save_queue(queue)
    log.info("sfx_generate: queued %s [%s %.1fs] (backend not active)", queue_id, sfx_type, dur)
    return {
        "status":  "partial",
        "summary": (
            f"SFX request queued ({queue_id}): {sfx_type}, {dur}s. "
            "Backend not active — install: pip install audiocraft scipy"
        ),
        "metrics": {"queue_id": queue_id, "sfx_type": sfx_type, "duration_s": dur,
                    "queue_depth": len(queue)},
        "action_items": [{"priority": "low",
                           "description": "Install AudioGen backend: pip install audiocraft scipy",
                           "requires_matthew": True}],
        "escalate": False,
    }

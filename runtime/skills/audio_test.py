"""
Audio Tester — verifies audio files for distortion, clipping, silence, and errors.
Uses scipy/wave for analysis; falls back to basic checks if scipy unavailable.
"""

import logging
import wave
import struct
from pathlib import Path

log = logging.getLogger(__name__)

_CLIPPING_THRESHOLD = 0.98   # amplitude ratio that counts as clipping
_SILENCE_THRESHOLD  = 0.02   # RMS below this = mostly silent
_MIN_DURATION_S     = 0.1    # files under 100ms are suspicious


def _analyze_wav(path: Path) -> dict:
    """Basic wave analysis without scipy."""
    try:
        with wave.open(str(path), "rb") as wf:
            n_channels  = wf.getnchannels()
            sample_width = wf.getsampwidth()
            framerate   = wf.getframerate()
            n_frames    = wf.getnframes()
            duration_s  = n_frames / framerate

            if duration_s < _MIN_DURATION_S:
                return {"pass": False, "reason": f"Audio too short: {duration_s:.3f}s"}

            raw = wf.readframes(n_frames)

        # Parse samples
        fmt = {1: "B", 2: "h", 4: "i"}.get(sample_width, "h")
        samples = struct.unpack(f"{len(raw)//sample_width}{fmt}", raw)
        max_val = 2 ** (sample_width * 8 - 1) - 1 if sample_width > 1 else 255

        # Check clipping
        clipped = sum(1 for s in samples if abs(s) >= max_val * _CLIPPING_THRESHOLD)
        clip_ratio = clipped / len(samples) if samples else 0

        # Check RMS
        rms = (sum(s*s for s in samples) / len(samples)) ** 0.5 if samples else 0
        rms_ratio = rms / max_val if max_val else 0

        issues = []
        if clip_ratio > 0.01:
            issues.append(f"Clipping: {clip_ratio:.1%} of samples")
        if rms_ratio < _SILENCE_THRESHOLD:
            issues.append(f"Near-silent: RMS ratio {rms_ratio:.3f}")

        return {
            "pass":         len(issues) == 0,
            "reason":       "Audio QA passed" if not issues else "; ".join(issues),
            "duration_s":   round(duration_s, 2),
            "channels":     n_channels,
            "sample_rate":  framerate,
            "clip_ratio":   round(clip_ratio, 4),
            "rms_ratio":    round(rms_ratio, 4),
        }

    except Exception as e:
        return {"pass": None, "reason": f"Audio analysis error: {e}"}


def _analyze_any(path: Path) -> dict:
    """Try scipy first, fall back to wave."""
    try:
        import scipy.io.wavfile as wavfile
        import numpy as np

        rate, data = wavfile.read(str(path))
        if data.ndim > 1:
            data = data.mean(axis=1)
        data = data.astype(float)
        max_val = np.iinfo(data.dtype).max if hasattr(np.iinfo(data.dtype), 'max') else 1.0

        duration_s = len(data) / rate
        if duration_s < _MIN_DURATION_S:
            return {"pass": False, "reason": f"Audio too short: {duration_s:.3f}s"}

        norm = data / max_val
        clip_ratio = float(np.mean(np.abs(norm) >= _CLIPPING_THRESHOLD))
        rms = float(np.sqrt(np.mean(norm ** 2)))

        issues = []
        if clip_ratio > 0.01:
            issues.append(f"Clipping: {clip_ratio:.1%}")
        if rms < _SILENCE_THRESHOLD:
            issues.append(f"Near-silent RMS {rms:.3f}")

        return {
            "pass":        len(issues) == 0,
            "reason":      "Audio QA passed" if not issues else "; ".join(issues),
            "duration_s":  round(duration_s, 2),
            "sample_rate": rate,
            "clip_ratio":  round(clip_ratio, 4),
            "rms":         round(rms, 4),
        }
    except ImportError:
        if path.suffix.lower() == ".wav":
            return _analyze_wav(path)
        return {"pass": None, "reason": "scipy not available and file is not .wav — install scipy for full audio testing"}
    except Exception as e:
        return {"pass": None, "reason": f"Audio analysis error: {e}"}


def run(audio_path: str = "") -> dict:
    """Audio Tester skill entry point."""
    if not audio_path:
        return {
            "status":  "partial",
            "summary": "No audio path provided. Pass audio_path=<path> to run test.",
            "metrics": {},
            "action_items": [],
            "escalate": False,
        }

    path = Path(audio_path)
    if not path.exists():
        return {
            "status":  "failed",
            "summary": f"File not found: {audio_path}",
            "metrics": {},
            "action_items": [{"priority": "normal", "description": f"File missing: {audio_path}", "requires_matthew": False}],
            "escalate": False,
        }

    result = _analyze_any(path)
    passed = result.get("pass")

    if passed is True:
        status  = "success"
        summary = f"Audio QA passed: {path.name}. {result['reason']}"
    elif passed is False:
        status  = "partial"
        summary = f"Audio QA FAILED: {path.name}. {result['reason']}"
    else:
        status  = "partial"
        summary = f"Audio test inconclusive: {path.name}. {result.get('reason')}"

    log.info("audio_test: %s → %s", path.name, status)
    return {
        "status":  status,
        "summary": summary,
        "metrics": {"file": str(path.name), **result},
        "action_items": [] if passed else [{
            "priority":        "normal",
            "description":     f"Fix audio {path.name}: {result.get('reason')}",
            "requires_matthew": False,
        }],
        "escalate": passed is False,
    }

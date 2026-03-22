"""
Video Editor — reviews video files for disfigurations, errors, and quality issues.
Uses ffprobe if available; falls back to basic file inspection.
"""

import json
import logging
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

_MIN_DURATION_S  = 0.5
_MIN_FRAMES      = 10
_VALID_CODECS    = {"h264", "hevc", "vp9", "vp8", "av1", "mpeg4", "prores"}


def _probe_ffprobe(path: Path) -> dict:
    """Use ffprobe to extract video metadata."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_streams", "-show_format", str(path)
            ],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            return None
        return json.loads(result.stdout)
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return None


def _analyze_video(path: Path) -> dict:
    probe = _probe_ffprobe(path)

    if probe is None:
        # ffprobe not available — basic file checks only
        size_mb = path.stat().st_size / (1024 * 1024)
        if size_mb < 0.001:
            return {"pass": False, "reason": "File is empty or near-empty"}
        return {
            "pass":   None,
            "reason": "ffprobe not available — basic check only (file exists, non-empty)",
            "size_mb": round(size_mb, 2),
        }

    streams = probe.get("streams", [])
    fmt     = probe.get("format", {})

    video_streams = [s for s in streams if s.get("codec_type") == "video"]
    if not video_streams:
        return {"pass": False, "reason": "No video stream found in file"}

    vs         = video_streams[0]
    codec      = vs.get("codec_name", "unknown").lower()
    duration_s = float(fmt.get("duration", 0))
    nb_frames  = int(vs.get("nb_frames", 0) or 0)
    width      = vs.get("width", 0)
    height     = vs.get("height", 0)

    issues = []
    if duration_s < _MIN_DURATION_S:
        issues.append(f"Too short: {duration_s:.2f}s")
    if nb_frames > 0 and nb_frames < _MIN_FRAMES:
        issues.append(f"Too few frames: {nb_frames}")
    if width == 0 or height == 0:
        issues.append("Invalid dimensions")
    if codec not in _VALID_CODECS:
        issues.append(f"Unusual codec: {codec}")

    return {
        "pass":        len(issues) == 0,
        "reason":      "Video QA passed" if not issues else "; ".join(issues),
        "codec":       codec,
        "duration_s":  round(duration_s, 2),
        "frames":      nb_frames,
        "dimensions":  f"{width}x{height}",
        "size_mb":     round(path.stat().st_size / (1024*1024), 2),
    }


def run(video_path: str = "") -> dict:
    """Video Editor skill entry point."""
    if not video_path:
        return {
            "status":  "partial",
            "summary": "No video path provided. Pass video_path=<path> to run review.",
            "metrics": {},
            "action_items": [],
            "escalate": False,
        }

    path = Path(video_path)
    if not path.exists():
        return {
            "status":  "failed",
            "summary": f"File not found: {video_path}",
            "metrics": {},
            "action_items": [{"priority": "normal", "description": f"File missing: {video_path}", "requires_matthew": False}],
            "escalate": False,
        }

    result = _analyze_video(path)
    passed = result.get("pass")

    if passed is True:
        status  = "success"
        summary = f"Video QA passed: {path.name}. {result['reason']}"
    elif passed is False:
        status  = "partial"
        summary = f"Video QA FAILED: {path.name}. {result['reason']}"
    else:
        status  = "partial"
        summary = f"Video review partial: {path.name}. {result.get('reason')}"

    log.info("video_review: %s → %s", path.name, status)
    return {
        "status":  status,
        "summary": summary,
        "metrics": {"file": str(path.name), **result},
        "action_items": [] if passed else [{
            "priority":        "normal",
            "description":     f"Fix video {path.name}: {result.get('reason')}",
            "requires_matthew": False,
        }],
        "escalate": passed is False,
    }

"""
CaptureProvider — QVAC training data capture tool.

Logs LLM prompts + responses to a JSONL capture log for later
review and fine-tuning export. Called as a hook from ollama_client
after successful chat_json responses.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from runtime.config import BASE_DIR

log = logging.getLogger(__name__)

CAPTURE_LOG = BASE_DIR / "state" / "qvac-captures.jsonl"
MAX_LOG_SIZE_MB = 50  # rotate after 50 MB


def _rotate_if_needed() -> None:
    if CAPTURE_LOG.exists():
        size_mb = CAPTURE_LOG.stat().st_size / (1024 * 1024)
        if size_mb >= MAX_LOG_SIZE_MB:
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            archive = CAPTURE_LOG.parent / f"qvac-captures-{ts}.jsonl"
            CAPTURE_LOG.rename(archive)
            log.info("CaptureProvider: rotated capture log → %s", archive.name)


def record(
    model: str,
    messages: list[dict],
    response: object,
    skill: str = "",
    division: str = "",
) -> None:
    """
    Append one capture record to the JSONL log.

    Args:
        model:    Ollama model name used for the call
        messages: The messages list passed to the model
        response: The parsed JSON response from chat_json (dict/list/str)
        skill:    Optional skill name (for filtering during export)
        division: Optional division name (for filtering during export)
    """
    try:
        _rotate_if_needed()
        CAPTURE_LOG.parent.mkdir(parents=True, exist_ok=True)

        entry = {
            "ts":       datetime.now(timezone.utc).isoformat(),
            "model":    model,
            "skill":    skill,
            "division": division,
            "messages": messages,
            "response": response,
        }
        with CAPTURE_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")

    except Exception as exc:
        # Never let capture failure break the main skill call
        log.debug("CaptureProvider: write failed — %s", exc)


def count_captures() -> int:
    """Return number of capture records in the active log."""
    if not CAPTURE_LOG.exists():
        return 0
    try:
        return sum(1 for _ in CAPTURE_LOG.open(encoding="utf-8"))
    except Exception:
        return 0


def load_captures(limit: int = 500) -> list[dict]:
    """Load the most-recent N capture records."""
    if not CAPTURE_LOG.exists():
        return []
    records = []
    try:
        with CAPTURE_LOG.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    except Exception as exc:
        log.warning("CaptureProvider: load failed — %s", exc)
    return records[-limit:]

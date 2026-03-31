"""
Dev Digest — KAELEN's daily dev-automation report.

Scans dev-automation division packet outputs, reads today's tool results,
and uses LLM to synthesize a concise executive summary for J_Claw.

Output saved to divisions/dev-automation/packets/ (dev-digest.json)
and a timestamped copy to divisions/dev-automation/digests/.

Schedule: daily 15:00
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from runtime.config import MODEL_7B, OLLAMA_HOST, BASE_DIR
from runtime.ollama_client import chat_json, is_available

log = logging.getLogger(__name__)

PACKETS_DIR = BASE_DIR / "divisions" / "dev-automation" / "packets"
OUTPUT_DIR  = BASE_DIR / "divisions" / "dev-automation" / "digests"

PACKET_FILES = [
    "repo-monitor.json",
    "refactor-scan.json",
    "doc-update.json",
    "artifact-manager.json",
]

_SYSTEM_PROMPT = """\
You are KAELEN, Iron Codex Director — J_Claw's dev-automation division commander.
Synthesize the incoming packet data into a concise daily code health report for Matthew.
Return ONLY valid JSON:
{
  "date": "today's date",
  "code_health": "healthy | degraded | critical | unknown",
  "summary": "2-3 sentence executive summary covering code health, refactors, doc debt, and artifact pressure",
  "open_refactors": ["list of open or pending refactor items"],
  "doc_debt": ["documentation gaps or stale docs flagged"],
  "artifact_pressure": "low | medium | high | unknown",
  "action_items": ["top 2-3 recommended actions"],
  "escalate": false,
  "kaelen_note": "KAELEN's in-character assessment (1 sentence)"
}
Be precise. Flag open refactors and doc debt clearly. Escalate if critical issues exist.\
"""


def _load_packet(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        return {}


def run() -> dict:
    """Dev Digest skill entry point."""
    packets = {}
    for fname in PACKET_FILES:
        key = fname.replace(".json", "").replace("-", "_")
        packets[key] = _load_packet(PACKETS_DIR / fname)

    packet_summary_lines = []
    for fname in PACKET_FILES:
        key = fname.replace(".json", "").replace("-", "_")
        data = packets[key]
        if data:
            status = data.get("status", "unknown")
            summary = data.get("summary", "no summary")
            packet_summary_lines.append(f"  [{fname}] status={status} — {summary}")
        else:
            packet_summary_lines.append(f"  [{fname}] not found / empty")

    packets_found = sum(1 for k in packets.values() if k)

    if not is_available(MODEL_7B, host=OLLAMA_HOST):
        summary = (
            f"Dev-automation packets scanned: {packets_found}/{len(PACKET_FILES)} present. "
            "LLM unavailable — raw packet data only."
        )
        return {
            "status": "partial",
            "summary": summary,
            "metrics": {
                "packets_found": packets_found,
                "packets_total": len(PACKET_FILES),
                "raw_packets": packets,
            },
            "action_items": [],
            "escalate": False,
        }

    context = (
        f"Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}\n"
        f"Dev-automation division packet scan ({packets_found}/{len(PACKET_FILES)} packets present):\n"
        + "\n".join(packet_summary_lines)
        + "\n\nFull packet data:\n"
        + json.dumps(packets, indent=2)
    )

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user",   "content": context},
    ]

    try:
        result = chat_json(MODEL_7B, messages, host=OLLAMA_HOST, temperature=0.4, max_tokens=800)
        if not isinstance(result, dict):
            raise ValueError(f"Unexpected LLM response type: {type(result)}")

        summary           = result.get("summary", f"Dev-automation: {packets_found} packets scanned.")
        code_health       = result.get("code_health", "unknown")
        artifact_pressure = result.get("artifact_pressure", "unknown")
        open_refactors    = result.get("open_refactors", [])
        escalate          = bool(result.get("escalate", False))
        action_items_raw  = result.get("action_items", [])

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

        # Write latest packet
        PACKETS_DIR.mkdir(parents=True, exist_ok=True)
        packet_path = PACKETS_DIR / "dev-digest.json"
        packet_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

        # Write timestamped digest copy
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        digest_filename = f"{timestamp}_dev_digest.json"
        digest_path = OUTPUT_DIR / digest_filename
        digest_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

        log.info(
            "dev_digest: wrote %s (health=%s, refactors=%d, pressure=%s)",
            digest_filename, code_health, len(open_refactors), artifact_pressure,
        )

        return {
            "status": "success",
            "summary": summary,
            "metrics": {
                "packets_found":      packets_found,
                "packets_total":      len(PACKET_FILES),
                "code_health":        code_health,
                "open_refactors":     len(open_refactors),
                "artifact_pressure":  artifact_pressure,
                "output_path":        str(digest_path.relative_to(BASE_DIR)),
            },
            "action_items": [
                {"priority": "high", "description": str(item), "requires_matthew": escalate}
                for item in action_items_raw
            ],
            "escalate": escalate,
        }

    except Exception as exc:
        log.error("dev_digest: LLM call failed — %s", exc)
        return {
            "status": "partial",
            "summary": f"Dev-automation: {packets_found} packets scanned. (digest synthesis unavailable)",
            "metrics": {
                "packets_found": packets_found,
                "packets_total": len(PACKET_FILES),
                "raw_packets": packets,
            },
            "action_items": [],
            "escalate": False,
        }

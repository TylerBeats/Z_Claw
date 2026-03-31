"""
OpSec Digest — ZETH's weekly security posture report.

Scans op-sec division packet outputs, reads latest tool results,
and uses LLM to synthesize a concise threat posture summary for J_Claw.

Output saved to divisions/op-sec/packets/ (opsec-digest.json)
and a timestamped copy to divisions/op-sec/digests/.

Schedule: weekly Sunday 16:00
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from runtime.config import MODEL_7B, OLLAMA_HOST, BASE_DIR
from runtime.ollama_client import chat_json, is_available

log = logging.getLogger(__name__)

PACKETS_DIR = BASE_DIR / "divisions" / "op-sec" / "packets"
OUTPUT_DIR  = BASE_DIR / "divisions" / "op-sec" / "digests"

PACKET_FILES = [
    "device-posture.json",
    "threat-surface.json",
    "breach-check.json",
    "cred-audit.json",
    "privacy-scan.json",
    "security-scan.json",
    "network-monitor.json",
]

_SYSTEM_PROMPT = """\
You are ZETH, Nullward Commander — J_Claw's op-sec division commander.
Synthesize the incoming packet data into a concise weekly security posture report for Matthew.
Return ONLY valid JSON:
{
  "date": "today's date",
  "threat_posture": "secure | elevated | compromised | critical | unknown",
  "summary": "2-3 sentence executive summary covering threat posture, breach status, credential exposure, and network anomalies",
  "breach_status": "none | suspected | confirmed | unknown",
  "credential_exposure": "none | low | medium | high | unknown",
  "network_anomalies": ["list of detected network anomalies or suspicious activity"],
  "top_threats": ["list of top identified threats or risks"],
  "action_items": ["top 2-3 recommended security actions"],
  "escalate": false,
  "zeth_note": "ZETH's in-character threat assessment (1 sentence)"
}
Be precise and clinical. Flag all breaches and exposures immediately. Escalate if posture is compromised or critical.\
"""


def _load_packet(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        return {}


def run() -> dict:
    """OpSec Digest skill entry point."""
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
            f"Op-sec packets scanned: {packets_found}/{len(PACKET_FILES)} present. "
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
        f"Op-sec division packet scan ({packets_found}/{len(PACKET_FILES)} packets present):\n"
        + "\n".join(packet_summary_lines)
        + "\n\nFull packet data:\n"
        + json.dumps(packets, indent=2)
    )

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user",   "content": context},
    ]

    try:
        result = chat_json(MODEL_7B, messages, host=OLLAMA_HOST, temperature=0.3, max_tokens=900)
        if not isinstance(result, dict):
            raise ValueError(f"Unexpected LLM response type: {type(result)}")

        summary             = result.get("summary", f"Op-sec: {packets_found} packets scanned.")
        threat_posture      = result.get("threat_posture", "unknown")
        breach_status       = result.get("breach_status", "unknown")
        credential_exposure = result.get("credential_exposure", "unknown")
        network_anomalies   = result.get("network_anomalies", [])
        escalate            = bool(result.get("escalate", False))
        action_items_raw    = result.get("action_items", [])

        # Auto-escalate on critical posture or confirmed breach
        if threat_posture in ("compromised", "critical") or breach_status == "confirmed":
            escalate = True

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

        # Write latest packet
        PACKETS_DIR.mkdir(parents=True, exist_ok=True)
        packet_path = PACKETS_DIR / "opsec-digest.json"
        packet_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

        # Write timestamped digest copy
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        digest_filename = f"{timestamp}_opsec_digest.json"
        digest_path = OUTPUT_DIR / digest_filename
        digest_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

        log.info(
            "opsec_digest: wrote %s (posture=%s, breach=%s, exposure=%s, anomalies=%d)",
            digest_filename, threat_posture, breach_status, credential_exposure, len(network_anomalies),
        )

        return {
            "status": "success",
            "summary": summary,
            "metrics": {
                "packets_found":        packets_found,
                "packets_total":        len(PACKET_FILES),
                "threat_posture":       threat_posture,
                "breach_status":        breach_status,
                "credential_exposure":  credential_exposure,
                "network_anomalies":    len(network_anomalies),
                "output_path":          str(digest_path.relative_to(BASE_DIR)),
            },
            "action_items": [
                {"priority": "high", "description": str(item), "requires_matthew": escalate}
                for item in action_items_raw
            ],
            "escalate": escalate,
        }

    except Exception as exc:
        log.error("opsec_digest: LLM call failed — %s", exc)
        return {
            "status": "partial",
            "summary": f"Op-sec: {packets_found} packets scanned. (digest synthesis unavailable)",
            "metrics": {
                "packets_found": packets_found,
                "packets_total": len(PACKET_FILES),
                "raw_packets": packets,
            },
            "action_items": [],
            "escalate": False,
        }

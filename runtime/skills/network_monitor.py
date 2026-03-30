"""
network-monitor skill — OP-Sec Division, Tier 1 LLM (7B local).
Monitors local network connections: active ports, listening services,
and unexpected external connections. Runs daily at 3:30 AM.
Local only — no external calls.
"""

import json
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from runtime.config import MODEL_7B, OLLAMA_HOST, ROOT
from runtime.ollama_client import chat_json, is_available

log        = logging.getLogger(__name__)
MODEL      = MODEL_7B
PACKET_DIR = ROOT / "divisions" / "op-sec" / "packets"

# Ports we expect to be listening locally
EXPECTED_PORTS = {3000, 18789}

# Port ranges that are suspicious if listening externally (0.0.0.0 / ::)
SUSPICIOUS_EXTERNAL_PORTS = {
    # Common remote access / attack vectors
    23, 135, 137, 138, 139, 445, 3389, 5900, 5985, 5986,
}

# Well-known local / loopback addresses — connections to these are safe
SAFE_REMOTE = {"127.0.0.1", "::1", "0.0.0.0", "[::]", "*"}


def _get_connections_psutil() -> tuple[list[dict], bool]:
    """Gather active connections via psutil. Returns (connections, ok)."""
    try:
        import psutil  # type: ignore
        conns = []
        for c in psutil.net_connections(kind="inet"):
            laddr = f"{c.laddr.ip}:{c.laddr.port}" if c.laddr else ""
            raddr = f"{c.raddr.ip}:{c.raddr.port}" if c.raddr else ""
            conns.append({
                "fd":      c.fd,
                "family":  str(c.family),
                "type":    str(c.type),
                "laddr":   laddr,
                "raddr":   raddr,
                "status":  c.status or "",
                "pid":     c.pid,
            })
        return conns, True
    except ImportError:
        return [], False
    except Exception as e:
        log.warning("network-monitor: psutil error — %s", e)
        return [], False


def _get_connections_netstat() -> tuple[list[dict], bool]:
    """Fallback: parse netstat -an output. Returns (connections, ok)."""
    try:
        r = subprocess.run(
            ["netstat", "-an"],
            capture_output=True, text=True, timeout=15,
        )
        if r.returncode != 0:
            return [], False

        conns = []
        for line in r.stdout.splitlines():
            parts = line.split()
            # netstat -an on Windows: Proto  Local Address  Foreign Address  State
            if len(parts) >= 4 and parts[0].upper() in ("TCP", "UDP"):
                proto   = parts[0].upper()
                laddr   = parts[1]
                raddr   = parts[2]
                status  = parts[3] if len(parts) > 3 else ""
                conns.append({
                    "proto":  proto,
                    "laddr":  laddr,
                    "raddr":  raddr,
                    "status": status,
                    "pid":    None,
                })
        return conns, True
    except Exception as e:
        log.warning("network-monitor: netstat error — %s", e)
        return [], False


def _gather_connections() -> tuple[list[dict], str]:
    """Try psutil first, fall back to netstat. Returns (connections, source)."""
    conns, ok = _get_connections_psutil()
    if ok:
        return conns, "psutil"
    conns, ok = _get_connections_netstat()
    if ok:
        return conns, "netstat"
    return [], "unavailable"


def _analyse_connections(conns: list[dict]) -> tuple[list[dict], list[str], dict]:
    """
    Scan connections for anomalies.
    Returns (suspicious_list, service_status_issues, ports_summary).
    """
    suspicious: list[dict] = []
    ports_listening: set[int] = set()

    for c in conns:
        laddr = c.get("laddr", "")
        raddr = c.get("raddr", "")
        status = c.get("status", "")

        # Extract local port
        try:
            lport = int(laddr.rsplit(":", 1)[-1])
        except (ValueError, IndexError):
            lport = 0

        # Track all listening ports
        if "LISTEN" in status.upper() or (not raddr or raddr in SAFE_REMOTE):
            if lport:
                ports_listening.add(lport)

        # Flag listening on all interfaces for suspicious port numbers
        listen_ip = laddr.rsplit(":", 1)[0] if ":" in laddr else ""
        is_external_listen = listen_ip in ("0.0.0.0", "::", "[::]", "")
        if is_external_listen and lport in SUSPICIOUS_EXTERNAL_PORTS and "LISTEN" in status.upper():
            suspicious.append({
                "type":   "suspicious_listen_port",
                "detail": f"Port {lport} listening on all interfaces ({laddr})",
                "severity": "HIGH",
            })

        # Flag established connections to non-local, non-empty remote addresses
        if "ESTABLISH" in status.upper() and raddr and raddr not in SAFE_REMOTE:
            remote_ip = raddr.rsplit(":", 1)[0] if ":" in raddr else raddr
            if remote_ip not in SAFE_REMOTE and not remote_ip.startswith("192.168.") \
                    and not remote_ip.startswith("10.") and not remote_ip.startswith("172."):
                suspicious.append({
                    "type":   "external_established",
                    "detail": f"Established connection to external address {raddr}",
                    "severity": "NORMAL",
                    "local":  laddr,
                    "remote": raddr,
                })

    # Check expected services
    service_issues: list[str] = []
    for port in EXPECTED_PORTS:
        if port not in ports_listening:
            service_issues.append(f"Expected service on port {port} is NOT listening")

    ports_summary = {
        "listening": sorted(ports_listening),
        "expected":  sorted(EXPECTED_PORTS),
        "expected_found": sorted(EXPECTED_PORTS & ports_listening),
        "expected_missing": sorted(EXPECTED_PORTS - ports_listening),
    }

    return suspicious, service_issues, ports_summary


def _llm_summarize(
    total: int,
    suspicious: list[dict],
    service_issues: list[str],
    ports_summary: dict,
    source: str,
) -> str:
    """Use LLM to produce a 2-sentence network posture summary if available."""
    high_count = sum(1 for s in suspicious if s.get("severity") == "HIGH")

    if not is_available(MODEL, host=OLLAMA_HOST):
        if suspicious or service_issues:
            issues_text = "; ".join(
                [s["detail"] for s in suspicious[:3]] + service_issues[:2]
            )
            return (
                f"Network monitor: {total} active connection(s) scanned via {source}. "
                f"Issues detected — {issues_text}."
            )
        return (
            f"Network monitor: {total} active connection(s) scanned via {source}. "
            f"All expected services up, no suspicious activity detected."
        )

    context = (
        f"Network monitor scan results:\n"
        f"Collection method: {source}\n"
        f"Total connections scanned: {total}\n"
        f"Suspicious entries: {len(suspicious)} ({high_count} HIGH severity)\n"
        f"Service issues: {len(service_issues)}\n"
        f"Expected ports: {ports_summary['expected']}\n"
        f"Ports found listening: {ports_summary['listening'][:20]}\n"
        f"Missing expected ports: {ports_summary['expected_missing']}\n"
        f"Top suspicious items: {json.dumps(suspicious[:3], indent=2) if suspicious else 'none'}\n"
        f"Service issues: {'; '.join(service_issues) or 'none'}"
    )

    messages = [
        {
            "role": "system",
            "content": (
                "You are the OP-Sec network monitor for J_Claw. "
                "Given the local network scan results, write a 2-sentence security posture statement. "
                "Lead with overall status (CLEAN/WARNING/ALERT). "
                "If issues are present, name the top concern. "
                "Be direct — no preamble, no labels. "
                "Respond with JSON: {\"summary\": \"<statement>\"}"
            ),
        },
        {"role": "user", "content": context},
    ]

    try:
        result = chat_json(
            MODEL, messages, host=OLLAMA_HOST,
            temperature=0.1, max_tokens=150,
            _capture_skill="network-monitor",
            _capture_division="op-sec",
        )
        if isinstance(result, dict):
            return result.get("summary", str(result)).strip()
        return str(result).strip()
    except Exception as e:
        log.warning("network-monitor: LLM summary failed — %s", e)
        if suspicious or service_issues:
            return f"Network monitor: {len(suspicious)} suspicious item(s) detected — review required."
        return f"Network monitor: {total} connection(s) scanned, no anomalies detected."


# ── Main entry point ───────────────────────────────────────────────────────────

def run(**kwargs) -> dict:
    """
    Monitors local network connections for suspicious activity.
    Flags unusual listening ports and unexpected external connections.
    Checks that expected local services (port 3000, 18789) are running.
    XP: 8.
    """
    PACKET_DIR.mkdir(parents=True, exist_ok=True)

    try:
        conns, source = _gather_connections()

        if source == "unavailable":
            result = {
                "division":     "op_sec",
                "skill":        "network-monitor",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "status":       "partial",
                "summary":      "Network monitor: unable to collect connection data — psutil and netstat both unavailable.",
                "action_items": [{"priority": "normal", "description": "Install psutil (pip install psutil) for reliable network monitoring."}],
                "metrics":      {"connections": 0, "suspicious": 0, "ports_checked": 0},
                "escalate":     False,
                "urgency":      "normal",
                "confidence":   0.0,
                "provider_used": "none",
            }
            with open(PACKET_DIR / "network-monitor.json", "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2)
            return result

        suspicious, service_issues, ports_summary = _analyse_connections(conns)

        high_count   = sum(1 for s in suspicious if s.get("severity") == "HIGH")
        escalate     = high_count > 0
        urgency      = "critical" if high_count > 2 else ("high" if high_count > 0 else "normal")
        status       = "success"

        # LLM or fallback summary
        summary = _llm_summarize(
            total=len(conns),
            suspicious=suspicious,
            service_issues=service_issues,
            ports_summary=ports_summary,
            source=source,
        )

        # Build action items
        action_items = []
        for s in suspicious[:6]:
            action_items.append({
                "priority":    "high" if s.get("severity") == "HIGH" else "normal",
                "description": s["detail"],
            })
        for issue in service_issues:
            action_items.append({"priority": "normal", "description": issue})

        result = {
            "division":     "op_sec",
            "skill":        "network-monitor",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status":       status,
            "summary":      summary,
            "action_items": action_items,
            "metrics": {
                "connections":    len(conns),
                "suspicious":     len(suspicious),
                "ports_checked":  len(ports_summary["listening"]),
            },
            "escalate":      escalate,
            "urgency":       urgency,
            "confidence":    0.9 if source == "psutil" else 0.75,
            "provider_used": f"local/{source}",
        }

        with open(PACKET_DIR / "network-monitor.json", "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)

        log.info(
            "network-monitor: %d connection(s), %d suspicious, source=%s",
            len(conns), len(suspicious), source,
        )
        return result

    except Exception as e:
        log.error("network-monitor: unexpected error — %s", e, exc_info=True)
        result = {
            "division":     "op_sec",
            "skill":        "network-monitor",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status":       "failed",
            "summary":      f"Network monitor failed: {e}",
            "action_items": [],
            "metrics":      {"connections": 0, "suspicious": 0, "ports_checked": 0},
            "escalate":     False,
            "urgency":      "normal",
            "confidence":   0.0,
            "provider_used": "none",
        }
        try:
            PACKET_DIR.mkdir(parents=True, exist_ok=True)
            with open(PACKET_DIR / "network-monitor.json", "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2)
        except Exception:
            pass
        return result

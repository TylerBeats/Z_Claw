"""
QVAC Adapter Manager — LoRA adapter lifecycle management.

Tracks available LoRA adapters, their training metadata, and
activation status. Provides reports on adapter readiness
and recommends which adapter to load for current tasks.

Output saved to divisions/production/adapters/.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from runtime.config import MODEL_7B, OLLAMA_HOST, BASE_DIR
from runtime.ollama_client import chat_json, is_available

log = logging.getLogger(__name__)

OUTPUT_DIR   = BASE_DIR / "divisions" / "production" / "adapters"
ADAPTER_REGISTRY = BASE_DIR / "state" / "adapter-registry.json"
QUEUE_FILE   = BASE_DIR / "state" / "adapter-manager-queue.json"

_SYSTEM_PROMPT = """\
You are QVAC Adapter Manager, responsible for LoRA adapter lifecycle.
Analyze the provided adapter registry and task context.
Return ONLY valid JSON:
{
  "total_adapters": 0,
  "active_adapter": "adapter name or null",
  "recommended_adapter": "adapter name or null",
  "adapter_health": "none | degraded | healthy | optimal",
  "adapters_ready": ["list of ready adapter names"],
  "adapters_stale": ["list of adapters needing retraining"],
  "recommendation": "1-2 sentence recommendation for adapter strategy",
  "action": "load | retrain | export_needed | standby"
}
Be precise.\
"""

_DEFAULT_REGISTRY = {
    "adapters": [],
    "active":   None,
    "last_updated": None,
}


def _load_registry() -> dict:
    if ADAPTER_REGISTRY.exists():
        try:
            return json.loads(ADAPTER_REGISTRY.read_text(encoding="utf-8"))
        except Exception:
            pass
    return dict(_DEFAULT_REGISTRY)


def _save_registry(reg: dict) -> None:
    ADAPTER_REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    reg["last_updated"] = datetime.now(timezone.utc).isoformat()
    ADAPTER_REGISTRY.write_text(json.dumps(reg, indent=2), encoding="utf-8")


def register_adapter(
    name: str,
    base_model: str,
    training_file: str,
    sample_count: int,
    skill_focus: str = "",
) -> dict:
    """Register a newly trained adapter in the registry."""
    reg = _load_registry()
    # Remove existing entry with same name
    reg["adapters"] = [a for a in reg["adapters"] if a.get("name") != name]
    reg["adapters"].append({
        "name":          name,
        "base_model":    base_model,
        "training_file": training_file,
        "sample_count":  sample_count,
        "skill_focus":   skill_focus,
        "trained_at":    datetime.now(timezone.utc).isoformat(),
        "status":        "ready",
    })
    _save_registry(reg)
    return reg


def run(
    action: str = "status",
    adapter_name: str = "",
    task_context: str = "",
) -> dict:
    """
    QVAC Adapter Manager skill entry point.

    Args:
        action:       "status" (report), "activate" (set active), "deactivate", "list"
        adapter_name: Adapter name for activate/deactivate actions
        task_context: Optional description of current task for recommendation
    """
    reg = _load_registry()
    adapters   = reg.get("adapters", [])
    active     = reg.get("active")

    if action == "activate":
        if not adapter_name:
            return {
                "status":  "failed",
                "summary": "adapter-manager: activate requires adapter_name",
                "metrics": {}, "action_items": [], "escalate": False,
            }
        match = next((a for a in adapters if a.get("name") == adapter_name), None)
        if not match:
            return {
                "status":  "failed",
                "summary": f"adapter-manager: adapter '{adapter_name}' not found in registry",
                "metrics": {}, "action_items": [], "escalate": False,
            }
        reg["active"] = adapter_name
        _save_registry(reg)
        return {
            "status":  "success",
            "summary": f"QVAC: adapter '{adapter_name}' activated (base: {match.get('base_model')}).",
            "metrics": {"active_adapter": adapter_name, "total_adapters": len(adapters)},
            "action_items": [],
            "escalate": False,
        }

    if action == "deactivate":
        reg["active"] = None
        _save_registry(reg)
        return {
            "status":  "success",
            "summary": "QVAC: adapter deactivated. Running base model.",
            "metrics": {"active_adapter": None, "total_adapters": len(adapters)},
            "action_items": [],
            "escalate": False,
        }

    # action == "status" or "list" — generate report
    if not is_available(MODEL_7B, host=OLLAMA_HOST):
        ready_count = sum(1 for a in adapters if a.get("status") == "ready")
        summary = (
            f"QVAC Adapter Registry: {len(adapters)} adapters, "
            f"{ready_count} ready, active={active or 'none'}."
        )
        return {
            "status":  "partial",
            "summary": summary,
            "metrics": {
                "total_adapters": len(adapters),
                "ready_count":    ready_count,
                "active_adapter": active,
            },
            "action_items": [],
            "escalate": False,
        }

    context = (
        f"Total adapters: {len(adapters)}\n"
        f"Active adapter: {active or 'none'}\n"
        f"Task context: {task_context or 'general use'}\n"
        f"Adapter list:\n"
        + "\n".join(
            f"  - {a.get('name')} | base={a.get('base_model')} | "
            f"samples={a.get('sample_count',0)} | focus={a.get('skill_focus','')} | "
            f"status={a.get('status','?')} | trained={a.get('trained_at','?')[:10]}"
            for a in adapters
        ) if adapters else "  (none registered)"
    )

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user",   "content": context},
    ]

    try:
        result = chat_json(MODEL_7B, messages, host=OLLAMA_HOST, temperature=0.2, max_tokens=500)
        if not isinstance(result, dict):
            raise ValueError(f"Unexpected type: {type(result)}")

        # Save report
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        ts       = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"{ts}_adapter_status.json"
        (OUTPUT_DIR / filename).write_text(json.dumps(result, indent=2), encoding="utf-8")

        health  = result.get("adapter_health", "none")
        rec_act = result.get("action", "standby")
        summary = (
            f"QVAC adapters: {result.get('total_adapters', len(adapters))} registered, "
            f"health={health}, active={result.get('active_adapter') or 'none'}. "
            f"{result.get('recommendation', '')}"
        )

        actions = []
        if rec_act in ("retrain", "export_needed"):
            actions.append({
                "priority":         "normal",
                "description":      f"QVAC: {rec_act} needed — run model-trainer export first",
                "requires_matthew": True,
            })
        if rec_act == "load" and result.get("recommended_adapter"):
            actions.append({
                "priority":         "normal",
                "description":      f"Load adapter '{result['recommended_adapter']}' for optimal performance",
                "requires_matthew": False,
            })

        log.info("adapter_manager: status — health=%s, adapters=%d", health, len(adapters))
        return {
            "status":  "success",
            "summary": summary,
            "metrics": {
                "total_adapters":      len(adapters),
                "active_adapter":      active,
                "adapter_health":      health,
                "recommended_adapter": result.get("recommended_adapter"),
                "stale_count":         len(result.get("adapters_stale", [])),
            },
            "action_items": actions,
            "escalate": health == "degraded",
        }

    except Exception as exc:
        log.error("adapter_manager: LLM call failed — %s", exc)
        return {
            "status":  "partial",
            "summary": f"QVAC: {len(adapters)} adapters registered. Status report unavailable.",
            "metrics": {"total_adapters": len(adapters), "active_adapter": active},
            "action_items": [], "escalate": False,
        }

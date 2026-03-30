"""
QVAC Model Trainer — self-improvement skill.

Reads captured LLM interactions from the CaptureProvider log,
reviews them for quality, and exports a fine-tuning dataset
(Alpaca-style JSONL) ready for LoRA training with Vulkan/QVAC Fabric.

Output saved to divisions/production/qvac-exports/.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from runtime.config import MODEL_7B, OLLAMA_HOST, BASE_DIR
from runtime.ollama_client import chat_json, is_available
from runtime.tools.capture import load_captures, count_captures

log = logging.getLogger(__name__)

OUTPUT_DIR = BASE_DIR / "divisions" / "production" / "qvac-exports"
QUEUE_FILE = BASE_DIR / "state" / "model-trainer-queue.json"

_SYSTEM_PROMPT = """\
You are QVAC, an AI self-improvement analyst.
Review the provided LLM interaction samples and evaluate their quality for fine-tuning.
Return ONLY valid JSON:
{
  "total_reviewed": 0,
  "quality_pass": 0,
  "quality_fail": 0,
  "export_count": 0,
  "quality_issues": ["list of recurring quality patterns to fix"],
  "recommended_focus": "what skill/domain would benefit most from fine-tuning",
  "training_readiness": "not_ready | marginal | ready | excellent",
  "notes": "brief analyst note on the capture batch quality"
}
Be concise and accurate.\
"""


def _export_training_data(captures: list[dict]) -> tuple[int, Path]:
    """Convert captures to Alpaca-style training JSONL. Returns (count, path)."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = OUTPUT_DIR / f"{ts}_training_export.jsonl"

    count = 0
    with out_path.open("w", encoding="utf-8") as fh:
        for cap in captures:
            messages = cap.get("messages", [])
            response = cap.get("response", {})
            if not messages or not response:
                continue
            # Build Alpaca-style record
            system_msg = next((m["content"] for m in messages if m.get("role") == "system"), "")
            user_msg   = next((m["content"] for m in messages if m.get("role") == "user"), "")
            if not user_msg:
                continue
            record = {
                "instruction": system_msg or "Complete the following task.",
                "input":       user_msg,
                "output":      json.dumps(response) if isinstance(response, dict) else str(response),
                "skill":       cap.get("skill", ""),
                "model":       cap.get("model", ""),
                "ts":          cap.get("ts", ""),
            }
            fh.write(json.dumps(record) + "\n")
            count += 1

    return count, out_path


def run(
    mode: str = "review",
    min_captures: int = 50,
    export_limit: int = 500,
) -> dict:
    """
    QVAC Model Trainer skill entry point.

    Args:
        mode:          "review" (analyze quality) or "export" (write training JSONL)
        min_captures:  Minimum captures required to proceed
        export_limit:  Max captures to include in one export
    """
    total = count_captures()

    if total < min_captures:
        msg = f"QVAC: only {total} captures logged (need {min_captures} minimum to train)."
        return {
            "status":       "partial",
            "summary":      msg,
            "metrics":      {"captures_logged": total, "captures_needed": min_captures},
            "action_items": [{"priority": "low", "description": msg, "requires_matthew": False}],
            "escalate":     False,
        }

    captures = load_captures(limit=export_limit)

    if mode == "export":
        export_count, out_path = _export_training_data(captures)
        summary = (
            f"QVAC: exported {export_count} training samples to {out_path.name}. "
            f"Ready for LoRA adapter training."
        )
        return {
            "status":  "success",
            "summary": summary,
            "metrics": {
                "captures_reviewed": len(captures),
                "export_count":      export_count,
                "export_path":       str(out_path.relative_to(BASE_DIR)),
            },
            "action_items": [{
                "priority":         "normal",
                "description":      f"Run LoRA training on {out_path.name} with QVAC Fabric/Vulkan",
                "requires_matthew": True,
            }],
            "escalate": False,
        }

    # mode == "review" — use LLM to evaluate batch quality
    if not is_available(MODEL_7B, host=OLLAMA_HOST):
        summary = f"QVAC: {total} captures logged. LLM unavailable for quality review."
        # Queue for later
        try:
            QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
            QUEUE_FILE.write_text(json.dumps({"mode": mode, "total": total}), encoding="utf-8")
        except Exception:
            pass
        return {
            "status":  "partial",
            "summary": summary,
            "metrics": {"captures_logged": total},
            "action_items": [],
            "escalate": False,
        }

    # Sample captures for LLM review (send last 20 as representative)
    sample = captures[-20:]
    context = (
        f"Total captures in log: {total}\n"
        f"Reviewing sample of {len(sample)} recent interactions.\n"
        f"Skills represented: {sorted(set(c.get('skill','?') for c in sample))}\n"
        f"Models used: {sorted(set(c.get('model','?') for c in sample))}\n"
    )

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user",   "content": context},
    ]

    try:
        result = chat_json(MODEL_7B, messages, host=OLLAMA_HOST, temperature=0.3, max_tokens=600)
        if not isinstance(result, dict):
            raise ValueError(f"Unexpected type: {type(result)}")

        readiness = result.get("training_readiness", "marginal")
        exported  = 0

        if readiness in ("ready", "excellent") and mode == "review":
            # Auto-export if data is ready
            exported, out_path = _export_training_data(captures)
            result["export_path"] = str(out_path.relative_to(BASE_DIR))
            result["export_count"] = exported

        summary = (
            f"QVAC review: {total} captures, readiness={readiness}, "
            f"{result.get('quality_pass', 0)} pass / {result.get('quality_fail', 0)} fail. "
            + (f"Auto-exported {exported} samples." if exported else "")
        )

        issues   = result.get("quality_issues", [])
        actions  = [
            {"priority": "normal", "description": f"Quality issue: {i}", "requires_matthew": False}
            for i in issues[:3]
        ]
        if exported:
            actions.append({
                "priority":         "normal",
                "description":      f"Run LoRA training on {result.get('export_path', '')}",
                "requires_matthew": True,
            })

        log.info("model_trainer: review complete — readiness=%s, captures=%d", readiness, total)
        return {
            "status":  "success",
            "summary": summary,
            "metrics": {
                "captures_logged":   total,
                "quality_pass":      result.get("quality_pass", 0),
                "quality_fail":      result.get("quality_fail", 0),
                "training_readiness": readiness,
                "export_count":      exported,
                "recommended_focus": result.get("recommended_focus", ""),
            },
            "action_items": actions,
            "escalate": readiness == "not_ready",
        }

    except Exception as exc:
        log.error("model_trainer: LLM review failed — %s", exc)
        return {
            "status":  "partial",
            "summary": f"QVAC: {total} captures logged. Review failed: {exc}",
            "metrics": {"captures_logged": total},
            "action_items": [], "escalate": False,
        }

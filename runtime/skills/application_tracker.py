"""
application-tracker skill — Tier 1 LLM (Qwen2.5 7B via Ollama).
Reads state/applications.json, computes pipeline metrics, flags stale
applications, and generates LLM insights + action items.
"""

import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

from runtime.config import SKILL_MODELS, STATE_DIR, MODEL_7B
from runtime.ollama_client import chat_json, is_available
from runtime.tools.state import load_applications

log = logging.getLogger(__name__)
MODEL = SKILL_MODELS.get("application-tracker", MODEL_7B)

STALE_DAYS = 14  # applied more than this many days ago with no update → stale

# ── Helpers ───────────────────────────────────────────────────────────────────

def _count_by_status(pipeline: list) -> dict:
    counts = {
        "total":        len(pipeline),
        "pending":      0,
        "pending_review": 0,
        "applied":      0,
        "waiting":      0,
        "interviewing": 0,
        "rejected":     0,
        "filtered":     0,
        "other":        0,
        "stale":        0,
    }
    now = datetime.now(timezone.utc)
    stale_cutoff = now - timedelta(days=STALE_DAYS)

    for app in pipeline:
        status = (app.get("status") or "other").lower()
        if status in counts:
            counts[status] += 1
        else:
            counts["other"] += 1

        # Flag stale: applied status with no update in STALE_DAYS
        if status == "applied":
            fetched_raw = app.get("fetched_at") or app.get("updated_at") or ""
            if fetched_raw:
                try:
                    fetched_dt = datetime.fromisoformat(fetched_raw.replace("Z", "+00:00"))
                    if fetched_dt.tzinfo is None:
                        fetched_dt = fetched_dt.replace(tzinfo=timezone.utc)
                    if fetched_dt < stale_cutoff:
                        counts["stale"] += 1
                except Exception:
                    pass

    return counts


def _build_pipeline_summary(counts: dict) -> str:
    lines = []
    active = counts["applied"] + counts["waiting"] + counts["interviewing"]
    lines.append(f"Total in pipeline: {counts['total']}")
    lines.append(f"Active (applied/waiting/interviewing): {active}")
    lines.append(f"Pending review: {counts.get('pending_review', 0) + counts.get('pending', 0)}")
    lines.append(f"Rejected: {counts['rejected']}")
    lines.append(f"Stale (applied >{STALE_DAYS}d no update): {counts['stale']}")
    return "\n".join(lines)


# ── LLM insights ──────────────────────────────────────────────────────────────

INSIGHTS_PROMPT = """You are the Opportunity Division orchestrator for J_Claw.
Matthew is a solo developer/trader in Campbellton, NB, Canada actively job-hunting for remote work.

Analyze the provided job application pipeline metrics and generate actionable insights.
Return a JSON object with exactly these fields:

{
  "summary": "1-2 sentence executive summary of the pipeline health",
  "action_items": [
    {"priority": "high|normal|low", "description": "specific action to take"}
  ],
  "urgency": "normal|high|critical",
  "confidence": 0.85
}

Rules:
- urgency = "high" if stale > 3 or interviewing > 0
- urgency = "critical" if interviewing > 2
- action_items should be specific and actionable (follow up with X, update resume for Y, etc.)
- Keep action_items to 3-5 items max
- confidence reflects your certainty given the data (0.0-1.0)
- Return ONLY valid JSON. No markdown, no explanation."""


def _get_llm_insights(counts: dict, top_apps: list) -> dict:
    """Ask LLM to produce a summary and action items from pipeline metrics."""
    if not is_available(MODEL):
        log.warning("application-tracker: model unavailable, using deterministic fallback")
        return _deterministic_insights(counts)

    active = counts["applied"] + counts["waiting"] + counts["interviewing"]
    top_titles = [
        f"{a.get('title','?')} at {a.get('company','?')} [{a.get('status','?')}]"
        for a in top_apps[:5]
    ]

    context = (
        f"Pipeline metrics:\n{_build_pipeline_summary(counts)}\n\n"
        f"Notable active applications:\n"
        + ("\n".join(f"- {t}" for t in top_titles) if top_titles else "- None")
    )

    messages = [
        {"role": "system", "content": INSIGHTS_PROMPT},
        {"role": "user", "content": context},
    ]

    try:
        result = chat_json(
            MODEL, messages, temperature=0.1, max_tokens=512,
            _capture_skill="application-tracker", _capture_division="opportunity",
        )
        if isinstance(result, dict) and "summary" in result:
            return result
        return _deterministic_insights(counts)
    except Exception as e:
        log.error("application-tracker LLM insights failed: %s", e)
        return _deterministic_insights(counts)


def _deterministic_insights(counts: dict) -> dict:
    """Fallback insights without LLM."""
    active = counts["applied"] + counts["waiting"] + counts["interviewing"]
    stale  = counts["stale"]

    if counts["interviewing"] > 0:
        urgency = "high"
        summary = (
            f"{counts['interviewing']} interview(s) in progress — priority follow-up required. "
            f"{active} total active applications."
        )
    elif stale > 3:
        urgency = "high"
        summary = (
            f"{stale} stale application(s) need follow-up. "
            f"{active} active applications in the pipeline."
        )
    elif active == 0:
        urgency = "normal"
        summary = "No active applications. Pipeline may need new job intake run."
    else:
        urgency = "normal"
        summary = (
            f"{active} active application(s) in the pipeline. "
            f"Pending review: {counts.get('pending_review', 0) + counts.get('pending', 0)}."
        )

    action_items = []
    if stale > 0:
        action_items.append({
            "priority": "high",
            "description": f"Follow up on {stale} stale application(s) that have been pending over {STALE_DAYS} days.",
        })
    if counts["interviewing"] > 0:
        action_items.append({
            "priority": "high",
            "description": f"Prepare for {counts['interviewing']} active interview(s) — research companies and practice responses.",
        })
    if counts.get("pending_review", 0) + counts.get("pending", 0) > 5:
        n = counts.get("pending_review", 0) + counts.get("pending", 0)
        action_items.append({
            "priority": "normal",
            "description": f"Review {n} pending job(s) and decide which to apply for.",
        })
    if active == 0:
        action_items.append({
            "priority": "normal",
            "description": "No active applications — run job-intake to find new opportunities.",
        })

    return {
        "summary":      summary,
        "action_items": action_items or [{"priority": "low", "description": "Pipeline looks healthy — continue monitoring."}],
        "urgency":      urgency,
        "confidence":   0.7,
    }


# ── Main entry point ──────────────────────────────────────────────────────────

def run() -> dict:
    """
    Load applications, compute metrics, get LLM insights, return result dict
    for the opportunity orchestrator.
    """
    apps_state = load_applications()
    pipeline   = apps_state.get("pipeline", [])

    if not pipeline:
        log.info("application-tracker: no applications in pipeline yet")
        return {
            "counts":    {"total": 0, "pending": 0, "pending_review": 0, "applied": 0,
                          "waiting": 0, "interviewing": 0, "rejected": 0, "filtered": 0,
                          "other": 0, "stale": 0},
            "insights":  {"summary": "No applications tracked yet.", "action_items": [],
                          "urgency": "normal", "confidence": 1.0},
            "no_data":   True,
            "model_available": is_available(MODEL),
        }

    counts = _count_by_status(pipeline)

    # Surface the most interesting apps for LLM context (active > pending > others)
    active_apps = [
        a for a in pipeline
        if (a.get("status") or "").lower() in ("applied", "waiting", "interviewing")
    ]

    insights = _get_llm_insights(counts, active_apps)

    return {
        "counts":        counts,
        "insights":      insights,
        "no_data":       False,
        "model_available": is_available(MODEL),
    }

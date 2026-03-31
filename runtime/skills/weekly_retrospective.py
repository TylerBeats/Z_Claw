"""
weekly-retrospective skill — Personal Division, Tier 1 LLM (7B local).
Weekly synthesis of health, performance, burnout, and XP/game-event data.
Runs every Sunday evening. Health data stays local — no external calls.
"""

import json
import logging
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from statistics import mean

from runtime.config import MODEL_7B, OLLAMA_HOST, BASE_DIR
from runtime.ollama_client import chat_json, is_available

log = logging.getLogger(__name__)
MODEL = MODEL_7B

STATE_DIR   = BASE_DIR / "state"
DIV_DIR     = BASE_DIR / "divisions" / "personal" / "retrospectives"
QUEUE_FILE  = STATE_DIR / "retrospective-queue.json"

LOOKBACK_DAYS = 7


# ── Helpers ────────────────────────────────────────────────────────────────────

def _load_json(path: Path) -> dict | list | None:
    """Load a JSON file, return None gracefully if missing or corrupt."""
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("weekly-retrospective: could not load %s — %s", path.name, e)
    return None


def _cutoff_dt() -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)


def _recent_health_entries(health_state: dict | None) -> list:
    if not health_state:
        return []
    cutoff = _cutoff_dt()
    entries = []
    for e in health_state.get("entries", []):
        try:
            ts = datetime.fromisoformat(e.get("logged_at", "").replace("Z", "+00:00"))
            if ts > cutoff:
                entries.append(e)
        except Exception:
            pass
    return entries


def _parse_game_events(jsonl_path: Path) -> list:
    """Read game-events.jsonl and return events from the past 7 days."""
    if not jsonl_path.exists():
        return []
    cutoff = _cutoff_dt()
    events = []
    try:
        with open(jsonl_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                    ts_str = ev.get("timestamp") or ev.get("ts") or ev.get("at") or ""
                    if ts_str:
                        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        if ts > cutoff:
                            events.append(ev)
                    else:
                        events.append(ev)  # include if no timestamp (best effort)
                except Exception:
                    pass
    except Exception as e:
        log.warning("weekly-retrospective: could not read game-events.jsonl — %s", e)
    return events


def _calculate_week_metrics(health_entries: list, game_events: list) -> dict:
    """Pure-Python metric calculations from raw data."""
    # Skill completions (all activity lives under "event": "skill_complete")
    skill_events = [e for e in game_events if e.get("event") in ("skill_complete", "skill_run", "skill")]
    skills_done  = len(skill_events)
    skill_names  = list({e.get("skill", e.get("name", "")) for e in skill_events if e.get("skill") or e.get("name")})

    # XP — primary field is "xp_granted" on skill_complete events
    xp_events = skill_events + [e for e in game_events if e.get("event") in ("xp_grant", "skill_xp", "xp")]
    total_xp  = sum(e.get("xp_granted", e.get("amount", e.get("xp", 0))) for e in xp_events)

    # Rank-ups
    rankup_events = [e for e in game_events if e.get("event") in ("rank_up", "rankup", "level_up")]
    rank_ups      = len(rankup_events)

    # Daily breakdown for streak analysis
    daily: dict[str, int] = {}
    for e in skill_events:
        ts_str = e.get("timestamp") or e.get("ts") or e.get("at") or ""
        try:
            ts  = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            day = ts.date().isoformat()
            daily[day] = daily.get(day, 0) + 1
        except Exception:
            pass

    # Most / least active days
    most_active_day  = max(daily, key=daily.get) if daily else None
    least_active_day = min(daily, key=daily.get) if daily else None

    # Streak: 7 consecutive days all with at least one completion
    today    = date.today()
    week_days = [(today - timedelta(days=i)).isoformat() for i in range(LOOKBACK_DAYS - 1, -1, -1)]
    streak_7  = all(daily.get(d, 0) > 0 for d in week_days) if daily else False

    avg_daily = round(skills_done / LOOKBACK_DAYS, 2)

    # Health metrics
    sleep_values = [e["sleep_hours"] for e in health_entries if e.get("sleep_hours") is not None]
    avg_sleep    = round(mean(sleep_values), 2) if sleep_values else None
    skipped_logs = sum(1 for e in health_entries if e.get("skipped"))

    # Division activity from skill events
    div_counts: dict[str, int] = {}
    for e in skill_events:
        div = e.get("division") or e.get("div") or ""
        if div:
            div_counts[div] = div_counts.get(div, 0) + 1
    top_divisions = sorted(div_counts.items(), key=lambda x: x[1], reverse=True)
    top_active_divisions = [d for d, _ in top_divisions[:3]]

    return {
        "total_xp_earned":       int(total_xp),
        "skills_completed":      skills_done,
        "rank_ups":              rank_ups,
        "avg_daily_completions": avg_daily,
        "streak_7_days":         streak_7,
        "most_active_day":       most_active_day,
        "least_active_day":      least_active_day,
        "avg_sleep_hours":       avg_sleep,
        "skipped_health_logs":   skipped_logs,
        "health_entries_found":  len(health_entries),
        "top_active_divisions":  top_active_divisions,
        "skill_names_run":       skill_names[:10],
        "daily_breakdown":       daily,
    }


def _llm_synthesize(metrics: dict, health_entries: list, burnout_state: dict | None) -> dict:
    """Ask the LLM for a weekly narrative synthesis."""
    default = {
        "week_summary":               "Weekly retrospective complete.",
        "health_trend":               "Insufficient data for health trend.",
        "performance_trend":          "Insufficient data for performance trend.",
        "burnout_risk":               "unknown",
        "achievements_unlocked":      [],
        "xp_earned":                  metrics.get("total_xp_earned", 0),
        "top_active_divisions":       metrics.get("top_active_divisions", []),
        "recommended_focus_next_week": "Review division goals and maintain current pace.",
        "action_items":               [],
    }

    if not is_available(MODEL, host=OLLAMA_HOST):
        log.info("weekly-retrospective: model unavailable — using default synthesis")
        return default

    burnout_summary = "No burnout data."
    if burnout_state:
        level = burnout_state.get("level", burnout_state.get("status", "ok"))
        burnout_summary = f"Level: {level}. {burnout_state.get('recommendation', '')}"

    sleep_str = f"avg {metrics['avg_sleep_hours']}h" if metrics["avg_sleep_hours"] else "no data"
    context = (
        f"Weekly retrospective — past 7 days:\n"
        f"Total XP earned: {metrics['total_xp_earned']}\n"
        f"Skills completed: {metrics['skills_completed']} (avg {metrics['avg_daily_completions']}/day)\n"
        f"Rank-ups: {metrics['rank_ups']}\n"
        f"7-day streak achieved: {metrics['streak_7_days']}\n"
        f"Most active day: {metrics['most_active_day'] or 'unknown'}\n"
        f"Least active day: {metrics['least_active_day'] or 'unknown'}\n"
        f"Sleep: {sleep_str} ({metrics['skipped_health_logs']} health logs skipped)\n"
        f"Top divisions: {', '.join(metrics['top_active_divisions']) or 'none tracked'}\n"
        f"Burnout monitor: {burnout_summary}"
    )

    messages = [
        {
            "role": "system",
            "content": (
                "You are the Personal Division orchestrator for J_Claw performing a weekly retrospective. "
                "Given the past 7 days of data, produce a JSON analysis. "
                "Return ONLY valid JSON with exactly these fields:\n"
                '{"week_summary": "2-3 sentence narrative", '
                '"health_trend": "improving|stable|declining|insufficient_data", '
                '"performance_trend": "improving|stable|declining|insufficient_data", '
                '"burnout_risk": "low|moderate|high|critical", '
                '"achievements_unlocked": ["list any notable achievements this week"], '
                '"xp_earned": <number>, '
                '"top_active_divisions": ["list"], '
                '"recommended_focus_next_week": "1 sentence", '
                '"action_items": ["up to 3 concrete actions"]}\n'
                "Do NOT include specific medication data. Keep week_summary safe for Telegram."
            ),
        },
        {"role": "user", "content": context},
    ]

    try:
        result = chat_json(MODEL, messages, host=OLLAMA_HOST, temperature=0.2, max_tokens=600)
        if isinstance(result, dict) and result.get("week_summary"):
            # Merge LLM result with computed xp/divisions (trust metrics over LLM)
            result["xp_earned"]           = metrics["total_xp_earned"]
            result["top_active_divisions"] = metrics["top_active_divisions"] or result.get("top_active_divisions", [])
            return result
    except Exception as e:
        log.warning("weekly-retrospective LLM failed: %s", e)

    return default


# ── Main entry point ───────────────────────────────────────────────────────────

def run(**kwargs) -> dict:
    """
    Weekly retrospective synthesis for the Personal Division.
    Reads health, burnout, and game-event data for the past 7 days.
    Saves to divisions/personal/retrospectives/YYYYMMDD_weekly.json.
    XP: 15.
    """
    today_str = date.today().strftime("%Y%m%d")

    # ── Load state files (all graceful) ────────────────────────────────────────
    health_state  = _load_json(STATE_DIR / "health-log.json")
    burnout_state = _load_json(STATE_DIR / "burnout-state.json")
    # perf-log may or may not exist — load if present
    perf_state    = _load_json(STATE_DIR / "perf-log.json")

    health_entries = _recent_health_entries(health_state)
    game_events    = _parse_game_events(STATE_DIR / "game-events.jsonl")

    # ── Compute metrics ────────────────────────────────────────────────────────
    metrics = _calculate_week_metrics(health_entries, game_events)

    # ── LLM synthesis ─────────────────────────────────────────────────────────
    synthesis = _llm_synthesize(metrics, health_entries, burnout_state)

    # ── Build full report ──────────────────────────────────────────────────────
    report = {
        "date":              date.today().isoformat(),
        "generated_at":      datetime.now(timezone.utc).isoformat(),
        "period_days":       LOOKBACK_DAYS,
        "week_summary":      synthesis.get("week_summary", ""),
        "health_trend":      synthesis.get("health_trend", "insufficient_data"),
        "performance_trend": synthesis.get("performance_trend", "insufficient_data"),
        "burnout_risk":      synthesis.get("burnout_risk", "unknown"),
        "achievements_unlocked": synthesis.get("achievements_unlocked", []),
        "xp_earned":         metrics["total_xp_earned"],
        "skills_completed":  metrics["skills_completed"],
        "rank_ups":          metrics["rank_ups"],
        "avg_daily_completions": metrics["avg_daily_completions"],
        "streak_7_days":     metrics["streak_7_days"],
        "most_active_day":   metrics["most_active_day"],
        "least_active_day":  metrics["least_active_day"],
        "top_active_divisions": metrics["top_active_divisions"],
        "recommended_focus_next_week": synthesis.get("recommended_focus_next_week", ""),
        "action_items":      synthesis.get("action_items", []),
        "raw_metrics":       metrics,
    }

    # ── Save report ────────────────────────────────────────────────────────────
    DIV_DIR.mkdir(parents=True, exist_ok=True)
    report_path = DIV_DIR / f"{today_str}_weekly.json"
    try:
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        log.info("weekly-retrospective: saved to %s", report_path)
    except Exception as e:
        log.error("weekly-retrospective: failed to save report — %s", e)

    # ── Update queue file ──────────────────────────────────────────────────────
    try:
        queue = _load_json(QUEUE_FILE) or {"retrospectives": []}
        if not isinstance(queue, dict):
            queue = {"retrospectives": []}
        queue.setdefault("retrospectives", [])
        queue["retrospectives"].append({
            "date":   date.today().isoformat(),
            "path":   str(report_path),
            "status": "complete",
        })
        # Keep last 52 (one year)
        queue["retrospectives"] = queue["retrospectives"][-52:]
        QUEUE_FILE.write_text(json.dumps(queue, indent=2), encoding="utf-8")
    except Exception as e:
        log.warning("weekly-retrospective: queue update failed — %s", e)

    # Build summary for orchestrator packet
    streak_note = " 7-day streak achieved!" if metrics["streak_7_days"] else ""
    summary = (
        f"Week of {date.today().isoformat()}: "
        f"{metrics['total_xp_earned']} XP earned, "
        f"{metrics['skills_completed']} skills run, "
        f"{metrics['rank_ups']} rank-up(s).{streak_note} "
        f"Burnout risk: {synthesis.get('burnout_risk', 'unknown')}."
    )

    action_items = synthesis.get("action_items", [])

    return {
        "status":      "success",
        "summary":     summary,
        "metrics":     {
            "xp_earned":             metrics["total_xp_earned"],
            "skills_completed":      metrics["skills_completed"],
            "rank_ups":              metrics["rank_ups"],
            "avg_daily_completions": metrics["avg_daily_completions"],
            "streak_7_days":         metrics["streak_7_days"],
            "burnout_risk":          synthesis.get("burnout_risk", "unknown"),
            "health_entries":        metrics["health_entries_found"],
        },
        "action_items":    action_items,
        "escalate":        synthesis.get("burnout_risk") in ("high", "critical"),
        "escalation_reason": (
            f"Weekly burnout risk: {synthesis.get('burnout_risk')}"
            if synthesis.get("burnout_risk") in ("high", "critical") else ""
        ),
        "report_path":     str(report_path),
        "model_available": is_available(MODEL, host=OLLAMA_HOST),
    }

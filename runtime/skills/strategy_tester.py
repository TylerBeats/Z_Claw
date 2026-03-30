"""
Strategy Tester — backtesting analysis skill.

Loads a strategy schema from the strategies directory and runs
an LLM-powered backtesting evaluation against historical context.
Produces a test report with pass/fail verdict and improvement notes.

Output saved to divisions/trading/strategy-tests/.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from runtime.config import MODEL_7B, OLLAMA_HOST, BASE_DIR
from runtime.ollama_client import chat_json, is_available

log = logging.getLogger(__name__)

STRATEGIES_DIR = BASE_DIR / "divisions" / "trading" / "strategies"
OUTPUT_DIR     = BASE_DIR / "divisions" / "trading" / "strategy-tests"
QUEUE_FILE     = BASE_DIR / "state" / "strategy-tester-queue.json"

_SYSTEM_PROMPT = """\
You are a quantitative trading risk analyst for J_Claw's paper trading system.
Evaluate the provided strategy schema for robustness, logic consistency, and risk.
Return ONLY valid JSON:
{
  "strategy_name": "strategy name",
  "verdict": "pass | fail | conditional_pass",
  "confidence": 0.0,
  "strengths": ["what this strategy does well"],
  "weaknesses": ["potential failure modes or risks"],
  "risk_rating": "low | medium | high | extreme",
  "recommended_max_risk_pct": 1.0,
  "market_conditions_best": "when this strategy performs best",
  "market_conditions_worst": "when this strategy fails",
  "improvements": ["specific suggested improvements"],
  "ready_for_paper_trading": true,
  "notes": "1-2 sentence analyst verdict"
}
Be rigorous. Reject strategies with unclear rules, excessive risk, or no edge thesis.\
"""


def _load_strategy(strategy_name: str) -> dict | None:
    """Find and load a strategy JSON file by name."""
    if not STRATEGIES_DIR.exists():
        return None
    for f in sorted(STRATEGIES_DIR.iterdir(), reverse=True):
        if f.suffix == ".json":
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if strategy_name.lower() in (data.get("strategy_name", "").lower() or f.stem.lower()):
                    return data
            except Exception:
                pass
    return None


def _load_latest_strategy() -> dict | None:
    """Load the most recently created strategy file."""
    if not STRATEGIES_DIR.exists():
        return None
    files = sorted(
        [f for f in STRATEGIES_DIR.iterdir() if f.suffix == ".json"],
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    if not files:
        return None
    try:
        return json.loads(files[0].read_text(encoding="utf-8"))
    except Exception:
        return None


def run(
    strategy_name: str = "",
    strategy_json: str = "",
) -> dict:
    """
    Strategy Tester skill entry point.

    Args:
        strategy_name: Name of strategy to load from strategies dir (or "" for latest)
        strategy_json: Raw JSON string of a strategy schema to test directly
    """
    # Load strategy
    strategy = None
    if strategy_json:
        try:
            strategy = json.loads(strategy_json)
        except json.JSONDecodeError:
            pass
    if strategy is None and strategy_name:
        strategy = _load_strategy(strategy_name)
    if strategy is None:
        strategy = _load_latest_strategy()

    if strategy is None:
        return {
            "status":  "failed",
            "summary": "strategy-tester: no strategy found to test.",
            "metrics": {}, "action_items": [], "escalate": False,
        }

    strat_name = strategy.get("strategy_name", "unknown")

    if not is_available(MODEL_7B, host=OLLAMA_HOST):
        try:
            QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
            QUEUE_FILE.write_text(json.dumps({"strategy_name": strat_name}), encoding="utf-8")
        except Exception:
            pass
        return {
            "status":  "partial",
            "summary": f"strategy-tester: queued test for '{strat_name}' (LLM offline).",
            "metrics": {"strategy_name": strat_name, "queued": True},
            "action_items": [],
            "escalate": False,
        }

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user",   "content": f"Strategy to evaluate:\n{json.dumps(strategy, indent=2)}"},
    ]

    try:
        result = chat_json(
            MODEL_7B, messages, host=OLLAMA_HOST, temperature=0.3, max_tokens=1000,
            _capture_skill="strategy-tester", _capture_division="trading",
        )
        if not isinstance(result, dict):
            raise ValueError(f"Unexpected type: {type(result)}")

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        ts       = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"{ts}_{strat_name.replace(' ', '_')}_test.json"
        (OUTPUT_DIR / filename).write_text(json.dumps(result, indent=2), encoding="utf-8")

        verdict  = result.get("verdict", "fail")
        risk     = result.get("risk_rating", "medium")
        ready    = result.get("ready_for_paper_trading", False)

        summary = (
            f"Strategy '{strat_name}' test: {verdict.upper()}, risk={risk}. "
            f"{'Ready for paper trading.' if ready else 'NOT ready for paper trading.'} "
            f"{result.get('notes', '')}"
        )

        actions = [
            {"priority": "normal", "description": f"Improvement: {imp}", "requires_matthew": False}
            for imp in result.get("improvements", [])[:3]
        ]

        log.info("strategy_tester: %s → %s (risk=%s)", strat_name, verdict, risk)
        return {
            "status":  "success",
            "summary": summary,
            "metrics": {
                "strategy_name": strat_name,
                "verdict":       verdict,
                "risk_rating":   risk,
                "confidence":    result.get("confidence", 0),
                "ready":         ready,
                "output_path":   str((OUTPUT_DIR / filename).relative_to(BASE_DIR)),
            },
            "action_items": actions,
            "escalate": verdict == "fail" or risk == "extreme",
        }

    except Exception as exc:
        log.error("strategy_tester: LLM call failed — %s", exc)
        return {
            "status":  "partial",
            "summary": f"strategy-tester: test failed for '{strat_name}' — {exc}",
            "metrics": {"strategy_name": strat_name},
            "action_items": [], "escalate": False,
        }

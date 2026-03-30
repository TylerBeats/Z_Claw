"""
Strategy Search — strategy discovery and ranking skill.

Scans the strategies directory, evaluates all available strategies,
and recommends the best candidate for the current market regime.

Output saved to divisions/trading/strategy-search/.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from runtime.config import MODEL_7B, OLLAMA_HOST, BASE_DIR
from runtime.ollama_client import chat_json, is_available

log = logging.getLogger(__name__)

STRATEGIES_DIR   = BASE_DIR / "divisions" / "trading" / "strategies"
TESTS_DIR        = BASE_DIR / "divisions" / "trading" / "strategy-tests"
OUTPUT_DIR       = BASE_DIR / "divisions" / "trading" / "strategy-search"
ACTIVE_STRAT_FILE = BASE_DIR / "state" / "active-strategy.json"

_SYSTEM_PROMPT = """\
You are a trading strategy selection analyst for J_Claw's automated paper trading system.
Given the available strategies and current market context, rank them and pick the best.
Return ONLY valid JSON:
{
  "market_regime": "trending | ranging | volatile | mixed",
  "best_strategy": "strategy name",
  "ranking": [
    {"name": "strategy name", "score": 8.5, "reason": "why ranked here"}
  ],
  "confidence": 0.0,
  "switch_recommended": true,
  "switch_reason": "why to switch now (or why to stay)",
  "notes": "1-2 sentence analyst note"
}
Score from 0-10. Be selective — only recommend a switch if confidence >= 0.7.\
"""


def _load_all_strategies() -> list[dict]:
    """Load all strategy JSON files from the strategies directory."""
    if not STRATEGIES_DIR.exists():
        return []
    strategies = []
    for f in sorted(STRATEGIES_DIR.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if f.suffix == ".json":
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if "strategy_name" in data:
                    strategies.append(data)
            except Exception:
                pass
    return strategies[:10]  # max 10 candidates


def _load_active_strategy() -> dict | None:
    if ACTIVE_STRAT_FILE.exists():
        try:
            return json.loads(ACTIVE_STRAT_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


def _save_active_strategy(strategy: dict) -> None:
    ACTIVE_STRAT_FILE.parent.mkdir(parents=True, exist_ok=True)
    ACTIVE_STRAT_FILE.write_text(json.dumps(strategy, indent=2), encoding="utf-8")


def run(
    market_context: str = "",
    auto_activate: bool = False,
) -> dict:
    """
    Strategy Search skill entry point.

    Args:
        market_context: Optional description of current market regime
        auto_activate:  If True and switch_recommended, auto-write to active-strategy.json
    """
    strategies = _load_all_strategies()

    if not strategies:
        return {
            "status":  "partial",
            "summary": "strategy-search: no strategies found. Run strategy-builder first.",
            "metrics": {"strategies_found": 0},
            "action_items": [{
                "priority":         "normal",
                "description":      "Run strategy-builder to generate trading strategies",
                "requires_matthew": False,
            }],
            "escalate": False,
        }

    active = _load_active_strategy()
    active_name = active.get("strategy_name", "none") if active else "none"

    if not is_available(MODEL_7B, host=OLLAMA_HOST):
        # Without LLM, return inventory summary
        return {
            "status":  "partial",
            "summary": (
                f"strategy-search: {len(strategies)} strategies available. "
                f"Active: {active_name}. (LLM offline — no ranking)"
            ),
            "metrics": {
                "strategies_found": len(strategies),
                "active_strategy":  active_name,
            },
            "action_items": [],
            "escalate": False,
        }

    strat_summary = "\n".join(
        f"  - {s.get('strategy_name', '?')} | type={s.get('strategy_type', '?')} "
        f"| tf={s.get('metadata', {}).get('timeframe', '?')} "
        f"| expected_wr={s.get('expected_win_rate', '?')} "
        f"| expected_r={s.get('expected_avg_r', '?')} "
        f"| thesis={s.get('edge_thesis', '')[:60]}"
        for s in strategies
    )

    user_prompt = (
        f"Available strategies ({len(strategies)} total):\n{strat_summary}\n\n"
        f"Currently active strategy: {active_name}\n"
        f"Market context: {market_context or 'general — no specific regime noted'}\n"
    )

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user",   "content": user_prompt},
    ]

    try:
        result = chat_json(
            MODEL_7B, messages, host=OLLAMA_HOST, temperature=0.3, max_tokens=800,
            _capture_skill="strategy-search", _capture_division="trading",
        )
        if not isinstance(result, dict):
            raise ValueError(f"Unexpected type: {type(result)}")

        best_name = result.get("best_strategy", "")
        switch    = result.get("switch_recommended", False)
        regime    = result.get("market_regime", "mixed")
        conf      = result.get("confidence", 0.0)

        # Auto-activate if requested and confident
        activated = False
        if auto_activate and switch and conf >= 0.7 and best_name:
            best_strat = next((s for s in strategies if s.get("strategy_name") == best_name), None)
            if best_strat:
                _save_active_strategy(best_strat)
                activated = True
                log.info("strategy_search: auto-activated '%s'", best_name)

        # Save search report
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        ts       = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"{ts}_strategy_search.json"
        (OUTPUT_DIR / filename).write_text(json.dumps(result, indent=2), encoding="utf-8")

        summary = (
            f"Strategy search: {len(strategies)} candidates, regime={regime}. "
            f"Best: '{best_name}' (confidence={conf:.0%}). "
            + (f"Switch recommended: {result.get('switch_reason', '')}" if switch else f"Stay on '{active_name}'.")
            + (" Auto-activated." if activated else "")
        )

        actions = []
        if switch and not activated:
            actions.append({
                "priority":         "normal",
                "description":      f"Activate strategy '{best_name}' — {result.get('switch_reason', '')}",
                "requires_matthew": True,
            })

        log.info("strategy_search: regime=%s best=%s switch=%s", regime, best_name, switch)
        return {
            "status":  "success",
            "summary": summary,
            "metrics": {
                "strategies_found": len(strategies),
                "best_strategy":    best_name,
                "active_strategy":  active_name,
                "market_regime":    regime,
                "confidence":       conf,
                "switch_recommended": switch,
                "activated":        activated,
            },
            "action_items": actions,
            "escalate": False,
        }

    except Exception as exc:
        log.error("strategy_search: LLM call failed — %s", exc)
        return {
            "status":  "partial",
            "summary": f"strategy-search: {len(strategies)} strategies found. Ranking unavailable.",
            "metrics": {"strategies_found": len(strategies), "active_strategy": active_name},
            "action_items": [], "escalate": False,
        }

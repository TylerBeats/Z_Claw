"""
Strategy Builder — trading strategy design skill.

Generates new trading strategy definitions (entry/exit rules, filters,
risk parameters) using LLM reasoning. Strategies are saved as JSON
schemas compatible with the virtual_trader and backtester.

Output saved to divisions/trading/strategies/.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from runtime.config import MODEL_7B, OLLAMA_HOST, BASE_DIR
from runtime.ollama_client import chat_json, is_available

log = logging.getLogger(__name__)

OUTPUT_DIR = BASE_DIR / "divisions" / "trading" / "strategies"
QUEUE_FILE = BASE_DIR / "state" / "strategy-builder-queue.json"

STRATEGY_TYPES = {
    "trend_following":   "Ride established trends using moving average crossovers and momentum",
    "mean_reversion":    "Fade extreme moves, buy oversold / sell overbought conditions",
    "breakout":          "Enter on price breakouts from consolidation zones with volume confirm",
    "momentum":          "Buy strongest assets over a lookback window, sell weakest",
    "carry":             "Systematic risk-on / risk-off based on volatility regime",
    "hybrid":            "Combine two approaches (e.g., trend + mean-reversion filter)",
}

_SYSTEM_PROMPT = """\
You are a quantitative trading strategy designer for J_Claw's automated paper trading system.
Design a complete, coherent trading strategy schema.
Return ONLY valid JSON:
{
  "strategy_name": "unique descriptive name",
  "strategy_type": "trend_following | mean_reversion | breakout | momentum | carry | hybrid",
  "description": "2-3 sentence description of the approach",
  "metadata": {
    "timeframe": "15m | 1h | 4h | 1d",
    "instruments": ["SPX500", "Gold", "NAS100"],
    "risk_per_trade_pct": 1.0,
    "max_open_positions": 2,
    "stop_loss_pct": 0.01,
    "take_profit_r": 2.0
  },
  "entry_rules": [
    {"rule": "description of entry condition", "indicator": "EMA/RSI/etc", "params": {}}
  ],
  "exit_rules": [
    {"rule": "description of exit condition", "type": "stop_loss | take_profit | signal"}
  ],
  "filters": [
    {"filter": "market condition filter", "purpose": "why this filter matters"}
  ],
  "risk_notes": "key risk considerations",
  "expected_win_rate": 0.5,
  "expected_avg_r": 1.5,
  "edge_thesis": "1 sentence explaining why this strategy has edge"
}
Be specific. Use realistic parameters for the given market.\
"""


def run(
    strategy_type: str = "trend_following",
    instruments: str = "SPX500,Gold",
    timeframe: str = "1d",
    context: str = "",
) -> dict:
    """
    Strategy Builder skill entry point.

    Args:
        strategy_type: One of the STRATEGY_TYPES keys
        instruments:   Comma-separated instrument list
        timeframe:     Candle timeframe (15m, 1h, 4h, 1d)
        context:       Optional extra context (current market regime, etc.)
    """
    if strategy_type not in STRATEGY_TYPES:
        strategy_type = "trend_following"

    instrument_list = [i.strip() for i in instruments.split(",") if i.strip()]

    if not is_available(MODEL_7B, host=OLLAMA_HOST):
        try:
            QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
            QUEUE_FILE.write_text(json.dumps({
                "strategy_type": strategy_type,
                "instruments": instrument_list,
                "timeframe": timeframe,
                "context": context,
            }), encoding="utf-8")
        except Exception:
            pass
        return {
            "status":  "partial",
            "summary": f"strategy-builder: queued {strategy_type} strategy for {instruments} (LLM offline).",
            "metrics": {"strategy_type": strategy_type, "queued": True},
            "action_items": [],
            "escalate": False,
        }

    user_prompt = (
        f"Strategy type: {strategy_type} — {STRATEGY_TYPES.get(strategy_type, '')}\n"
        f"Target instruments: {', '.join(instrument_list)}\n"
        f"Timeframe: {timeframe}\n"
        + (f"Additional context: {context}\n" if context else "")
    )

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user",   "content": user_prompt},
    ]

    try:
        result = chat_json(
            MODEL_7B, messages, host=OLLAMA_HOST, temperature=0.6, max_tokens=1200,
            _capture_skill="strategy-builder", _capture_division="trading",
        )
        if not isinstance(result, dict):
            raise ValueError(f"Unexpected type: {type(result)}")

        # Save strategy file
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        ts           = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        strat_name   = result.get("strategy_name", f"{strategy_type}_{ts}").replace(" ", "_")
        filename     = f"{ts}_{strat_name}.json"
        out_path     = OUTPUT_DIR / filename
        out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

        summary = (
            f"Strategy '{result.get('strategy_name', strat_name)}' designed "
            f"({result.get('strategy_type', strategy_type)}, {timeframe}). "
            f"Expected win rate: {result.get('expected_win_rate', '?')}, "
            f"avg R: {result.get('expected_avg_r', '?')}. "
            f"Thesis: {result.get('edge_thesis', '')}"
        )

        log.info("strategy_builder: wrote %s", filename)
        return {
            "status":  "success",
            "summary": summary,
            "metrics": {
                "strategy_name":   result.get("strategy_name", strat_name),
                "strategy_type":   result.get("strategy_type", strategy_type),
                "timeframe":       result.get("metadata", {}).get("timeframe", timeframe),
                "expected_win_rate": result.get("expected_win_rate"),
                "expected_avg_r":  result.get("expected_avg_r"),
                "output_path":     str(out_path.relative_to(BASE_DIR)),
            },
            "action_items": [{
                "priority":         "normal",
                "description":      f"Run strategy-tester on '{result.get('strategy_name', strat_name)}' to validate",
                "requires_matthew": False,
            }],
            "escalate": False,
        }

    except Exception as exc:
        log.error("strategy_builder: LLM call failed — %s", exc)
        return {
            "status":  "partial",
            "summary": f"strategy-builder: design failed — {exc}",
            "metrics": {"strategy_type": strategy_type},
            "action_items": [], "escalate": False,
        }

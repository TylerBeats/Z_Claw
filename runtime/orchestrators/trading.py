"""
Trading Division Orchestrator — LLM agent (Qwen2.5 7B).
Skills handle data collection + individual analysis.
The orchestrator synthesizes across skills, adds market context to session results,
and writes the executive packet that J_Claw reads.
"""

import logging

from runtime.config import SKILL_MODELS, OLLAMA_HOST
from runtime.ollama_client import chat, is_available
from runtime.skills import trading_report, market_scan, virtual_trader, backtester, strategy_builder, strategy_tester, strategy_search
from runtime import packet
from runtime.tools.xp import grant_skill_xp
from runtime.tools.trading import load_cycle_state, load_active_strategy
from runtime.tools.virtual_account import load_virtual_account

log   = logging.getLogger(__name__)
MODEL = SKILL_MODELS["trading-report"]


# ── Orchestrator reasoning ─────────────────────────────────────────────────────

def _synthesize_trading_session(
    trade_result: dict,
    market_pkt: dict | None,
) -> str:
    """
    Cross-skill synthesis: combine session stats with market conditions.
    The orchestrator sees what the individual skills can't — the full picture.
    """
    stats = trade_result.get("stats", {})

    if not is_available(MODEL):
        parts = []
        if trade_result.get("interpretation"):
            parts.append(trade_result["interpretation"])
        if market_pkt:
            parts.append(f"Market: {market_pkt.get('summary', '')}")
        return " | ".join(parts) if parts else "Session complete."

    # Build context from both skill outputs
    trades_n = stats.get("total_trades", 0)
    if trades_n == 0:
        session_text = "No closed trades this session."
    else:
        session_text = (
            f"{trades_n} trade(s): "
            f"{stats.get('wins', 0)}W/{stats.get('losses', 0)}L "
            f"({stats.get('win_rate', '?')}% win rate), "
            f"avg R={stats.get('avg_r', '?')}, "
            f"PnL=${stats.get('total_pnl', '?')}"
        )
        if trade_result.get("interpretation"):
            session_text += f"\nSkill note: {trade_result['interpretation']}"

    market_text = (
        market_pkt.get("summary", "Market scan not available.")
        if market_pkt else "Market scan not available."
    )

    market_signals = (
        market_pkt.get("metrics", {}).get("signals", 0)
        if market_pkt else 0
    )

    context = (
        f"Trading session:\n{session_text}\n\n"
        f"Current market ({market_signals} signal(s) detected):\n{market_text}"
    )

    messages = [
        {
            "role": "system",
            "content": (
                "You are the Trading Division orchestrator for J_Claw. "
                "Given today's session results and current market conditions, "
                "write a 2-3 sentence executive summary for Matthew. "
                "Connect the session performance to market context where relevant. "
                "Flag anything worth watching tomorrow. Be direct — no filler."
            ),
        },
        {"role": "user", "content": context},
    ]
    try:
        result = chat(MODEL, messages, temperature=0.2, max_tokens=180)
        lines = result.strip().splitlines()
        if lines and lines[0].rstrip().endswith(":"):
            result = "\n".join(lines[1:]).lstrip()
        return result
    except Exception as e:
        log.warning("trading orchestrator synthesis failed: %s", e)
        return session_text


# ── Individual skill runners ───────────────────────────────────────────────────

def run_trading_report() -> dict:
    """Run trading session stats + orchestrator synthesis with market context."""
    log.info("=== Trading Division: trading-report run ===")

    result      = trading_report.run()
    stats       = result.get("stats", {})
    market_pkt  = packet.read("trading", "market-scan")  # read latest market-scan if available

    if result["source"] == "none":
        summary = "Trading system not yet activated — no session data found."
        status  = "partial"
    elif stats.get("total_trades", 0) == 0:
        # Load account state here so we can include balance/open positions in summary
        _v = load_virtual_account()
        _bal   = _v.get("account_balance", 10_000.0)
        _init  = _v.get("initial_balance", 10_000.0)
        _pnl   = round(_bal - _init, 2)
        _open  = len(_v.get("open_positions", []))
        _pos_label = f"{_open} open position{'s' if _open != 1 else ''}" if _open else "no open positions"
        summary = (
            f"No closed trades today. Balance: ${_bal:,.2f} "
            f"(Total PnL: ${_pnl:+.2f}) — {_pos_label}."
        )
        if market_pkt:
            summary += f" Market: {market_pkt.get('summary', '')}"
        status  = "success"
    else:
        # Orchestrator synthesizes session + market together
        summary = _synthesize_trading_session(result, market_pkt)
        status  = result["status"]

    # Load virtual account state — always include balance/growth even with no closed trades
    v_acct          = load_virtual_account()
    acct_balance    = v_acct.get("account_balance", 10_000.0)
    acct_initial    = v_acct.get("initial_balance", 10_000.0)
    acct_pnl        = round(acct_balance - acct_initial, 2)
    open_pos_count  = len(v_acct.get("open_positions", []))

    # Enrich with agent-network cycle state
    cycle = load_cycle_state()
    active_strat = load_active_strategy()
    cycle_metrics = {}
    if cycle:
        cycle_metrics = {
            "cycle_number":    cycle.get("cycle_number"),
            "risk_multiplier": cycle.get("risk_multiplier", 1.0),
        }
    if active_strat:
        cycle_metrics["active_strategy"] = active_strat.get("strategy_name", "")
        cycle_metrics["strategy_sharpe"]  = active_strat.get("sharpe")
        cycle_metrics["strategy_win_rate_pct"] = round(
            (active_strat.get("win_rate") or 0) * 100, 1
        )

    pkt = packet.build(
        division="trading",
        skill="trading-report",
        status=status,
        summary=summary,
        metrics={
            "total_trades":   stats.get("total_trades", 0),
            "wins":           stats.get("wins", 0),
            "losses":         stats.get("losses", 0),
            "win_rate":       stats.get("win_rate"),
            "avg_r":          stats.get("avg_r"),
            "best_r":         stats.get("best_r"),
            "worst_r":        stats.get("worst_r"),
            "total_pnl":      stats.get("total_pnl"),
            "source":         result.get("source", "none"),
            "market_context": bool(market_pkt),
            "account_balance": acct_balance,
            "account_pnl":     acct_pnl,
            "open_positions":  open_pos_count,
            **cycle_metrics,
        },
        artifact_refs=[{"bundle_id": "trade-session-today", "location": "hot"}],
        escalate=result.get("escalate", False),
        escalation_reason=result.get("escalation_reason", ""),
    )

    packet.write(pkt)
    grant_skill_xp("trading-report")
    log.info("Trading packet written. Status=%s trades=%d", status, stats.get("total_trades", 0))
    return pkt


def run_virtual_trader() -> dict:
    """Run virtual paper trader for SPX500/Gold and write packet."""
    log.info("=== Trading Division: virtual-trader run ===")

    result = virtual_trader.run()

    pkt = packet.build(
        division="trading",
        skill="virtual-trader",
        status=result["status"],
        summary=result.get("summary", "Virtual trader run complete."),
        metrics={
            "trades_made":     result.get("trades_made", 0),
            "open_positions":  result.get("open_positions", 0),
            "account_balance": result.get("account_balance"),
            "strategy_id":     result.get("strategy_id", ""),
        },
        escalate=result.get("escalate", False),
        escalation_reason=result.get("escalation_reason", ""),
    )

    packet.write(pkt)
    if result["status"] == "success":
        grant_skill_xp("virtual-trader")
    log.info(
        "Virtual-trader packet written. Status=%s trades=%d balance=%.2f",
        result["status"],
        result.get("trades_made", 0),
        result.get("account_balance", 0.0),
    )
    return pkt


def run_backtester() -> dict:
    """Run backtester skill — reads cycle state, evaluates strategy quality."""
    log.info("=== Trading Division: backtester run ===")

    result = backtester.run()

    pkt = packet.build(
        division="trading",
        skill="backtester",
        status=result["status"],
        summary=result.get("summary", "Backtester run complete."),
        metrics=result.get("metrics", {}),
        escalate=result.get("escalate", False),
        escalation_reason=result.get("escalation_reason", ""),
    )

    packet.write(pkt)
    if result["status"] == "success":
        grant_skill_xp("backtester")
    log.info(
        "Backtester packet written. Status=%s changed=%s escalate=%s",
        result["status"],
        result.get("strategy_changed"),
        result.get("escalate", False),
    )
    return pkt


def run_market_scan() -> dict:
    """Hourly crypto market scan — silent unless high-priority signals detected."""
    log.info("=== Trading Division: market-scan run ===")

    result  = market_scan.run()
    signals = result.get("signals", [])

    if result["status"] == "failed":
        pkt = packet.build(
            division="trading",
            skill="market-scan",
            status="failed",
            summary=result.get("summary", "Market data fetch failed."),
        )
        packet.write(pkt)
        return pkt

    pkt = packet.build(
        division="trading",
        skill="market-scan",
        status=result["status"],
        summary=result.get("summary", ""),
        metrics=result.get("counts", {}),
        escalate=result.get("escalate", False),
        escalation_reason=result.get("escalation_reason", ""),
    )

    packet.write(pkt)
    if signals:
        grant_skill_xp("market-scan")
    log.info(
        "Market-scan packet written. Signals=%d High=%d",
        len(signals), result["counts"].get("high", 0),
    )
    return pkt


def _build_packet(skill: str, result: dict) -> dict:
    return packet.build(
        division      = "trading",
        skill         = skill,
        status        = result.get("status", "failed"),
        summary       = result.get("summary", ""),
        action_items  = result.get("action_items", []),
        metrics       = result.get("metrics", {}),
        escalate      = result.get("escalate", False),
        urgency       = "high" if result.get("escalate") else "normal",
    )


def run_strategy_builder(strategy_type: str = "trend_following", instruments: str = "SPX500,Gold", timeframe: str = "1d", context: str = "") -> dict:
    result = strategy_builder.run(strategy_type=strategy_type, instruments=instruments, timeframe=timeframe, context=context)
    pkt    = _build_packet("strategy-builder", result)
    packet.write(pkt)
    if result.get("status") in ("success", "partial"):
        grant_skill_xp("strategy-builder")
    log.info("Trading: strategy-builder %s/%s → %s", strategy_type, timeframe, result.get("status"))
    return pkt


def run_strategy_tester(strategy_name: str = "", strategy_json: str = "") -> dict:
    result = strategy_tester.run(strategy_name=strategy_name, strategy_json=strategy_json)
    pkt    = _build_packet("strategy-tester", result)
    packet.write(pkt)
    if result.get("status") in ("success", "partial"):
        grant_skill_xp("strategy-tester")
    log.info("Trading: strategy-tester '%s' → %s", strategy_name, result.get("status"))
    return pkt


def run_strategy_search(market_context: str = "", auto_activate: bool = False) -> dict:
    result = strategy_search.run(market_context=market_context, auto_activate=auto_activate)
    pkt    = _build_packet("strategy-search", result)
    packet.write(pkt)
    if result.get("status") in ("success", "partial"):
        grant_skill_xp("strategy-search")
    log.info("Trading: strategy-search → %s (best=%s)", result.get("status"), result.get("metrics", {}).get("best_strategy", ""))
    return pkt

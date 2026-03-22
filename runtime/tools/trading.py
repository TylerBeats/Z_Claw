"""
Trading data tools — pure Python, no LLM.
Reads agent-network state files and calculates session stats.
Bridges Z_Claw's trading division with the agent-network trading system.
"""

import json
import logging
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from typing import Optional

from runtime.tools.state import load_trade_log, STATE_DIR
from runtime.config import ROOT

log = logging.getLogger(__name__)

AGENT_NETWORK_ROOT  = Path("C:/Users/Tyler/agent-network")
AGENT_NETWORK_STATE = AGENT_NETWORK_ROOT / "state"
AGENT_NETWORK_ENV   = AGENT_NETWORK_ROOT / ".env"

ALPACA_STATE = AGENT_NETWORK_STATE / "alpaca_paper_state.json"
VIRTUAL_ACCT = AGENT_NETWORK_STATE / "virtual_account.json"
HOT_DIR      = ROOT / "divisions" / "trading" / "hot"


def _load_state_file(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception as e:
        log.error("Failed to load %s: %s", path, e)
        return None


def _today_str() -> str:
    return date.today().isoformat()


def _read_agent_env() -> dict:
    """Read agent-network .env for active asset config."""
    env = {}
    try:
        for line in AGENT_NETWORK_ENV.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    except Exception:
        pass
    return env


# ── Agent-network cycle state ─────────────────────────────────────────────────

def load_cycle_state() -> Optional[dict]:
    """
    Load the agent-network cycle state for the active asset.
    Contains: active_strategy, trade_log (exits), weekly/monthly reviews,
    performance_history, risk_multiplier, cycle_number.
    """
    env = _read_agent_env()
    asset_chain = env.get("ASSET_CHAIN", "spx500")

    # Primary: asset-named state file
    candidate = AGENT_NETWORK_STATE / f"{asset_chain}_cycle_state.json"
    if not candidate.exists():
        # Fallback: any *_cycle_state.json, most recently modified
        files = list(AGENT_NETWORK_STATE.glob("*_cycle_state.json"))
        if not files:
            log.warning("No cycle state file found in agent-network/state/")
            return None
        candidate = max(files, key=lambda p: p.stat().st_mtime)

    state = _load_state_file(candidate)
    if state:
        log.info("Loaded cycle state: %s (cycle %s)", candidate.name, state.get("cycle_number", "?"))
    return state


def load_active_strategy() -> Optional[dict]:
    """Return the currently active trading strategy from agent-network."""
    state = load_cycle_state()
    return state.get("active_strategy") if state else None


def load_recent_weekly_reviews(n: int = 4) -> list:
    """Return the last N weekly performance reviews from agent-network."""
    state = load_cycle_state()
    if not state:
        return []
    return state.get("weekly_reviews", [])[-n:]


def load_recent_monthly_reviews(n: int = 3) -> list:
    """Return the last N monthly performance reviews from agent-network."""
    state = load_cycle_state()
    if not state:
        return []
    return state.get("monthly_reviews", [])[-n:]


def load_all_time_trades(days: int = 90) -> list:
    """
    Load historical exit trades from agent-network cycle state.
    Used by perf-correlation for long-range health vs trading patterns.
    Returns list of dicts with 'date', 'pnl', 'r_multiple', 'result', 'strategy_id'.
    """
    state = load_cycle_state()
    if not state:
        return []
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    result = []
    for t in state.get("trade_log", []):
        ts = t.get("timestamp", 0)
        if not ts:
            continue
        trade_date = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).date().isoformat()
        if trade_date >= cutoff:
            result.append({
                "date":        trade_date,
                "pnl":         t.get("pnl", 0),
                "r_multiple":  t.get("r_multiple", 0),
                "result":      "win" if (t.get("pnl") or 0) > 0 else "loss",
                "strategy_id": t.get("strategy_id", ""),
                "symbol":      t.get("symbol", ""),
                "reason":      t.get("reason", ""),
            })
    return result


def load_today_trades() -> tuple[list, str]:
    """
    Load today's closed trade records from Alpaca or virtual account.
    Returns (trades_list, source_name).
    """
    today = _today_str()

    # Try Alpaca paper first
    alpaca = _load_state_file(ALPACA_STATE)
    if alpaca:
        trades = [
            t for t in alpaca.get("trade_log", [])
            if t and t.get("timestamp", "").startswith(today)
        ]
        if trades:
            log.info("Loaded %d trades from alpaca_paper_state.json", len(trades))
            return trades, "alpaca_paper"

    # Fall back to virtual account
    virtual = _load_state_file(VIRTUAL_ACCT)
    if virtual:
        trades = [
            t for t in virtual.get("trade_log", [])
            if t and t.get("timestamp", "").startswith(today)
        ]
        log.info("Loaded %d trades from virtual_account.json", len(trades))
        return trades, "virtual_account"

    # Last resort: read today's exit trades from cycle state trade_log
    cycle = load_cycle_state()
    if cycle:
        today = _today_str()
        trades = []
        for t in cycle.get("trade_log", []):
            ts = t.get("timestamp", 0)
            if ts:
                trade_date = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).date().isoformat()
                if trade_date == today:
                    trades.append(t)
        if trades:
            log.info("Loaded %d trades from cycle state trade_log", len(trades))
            return trades, "cycle_state"

    log.warning("No trade data found — trading system not yet activated")
    return [], "none"


def pair_trades(trades: list) -> list:
    """
    Pair entry + exit records into completed trade sessions.
    Returns list of paired trade dicts.
    """
    entries = {t["order_id"]: t for t in trades if t.get("type") == "entry"}
    exits   = [t for t in trades if t.get("type") == "exit"]

    paired = []
    for ex in exits:
        oid = ex.get("order_id", "")
        en = entries.get(oid)
        pnl = ex.get("pnl") or 0
        risk = (en or ex).get("risk_usd") or 1
        r_mult = ex.get("r_multiple") or (pnl / risk if risk else 0)
        result = "win" if pnl > 0 else ("loss" if pnl < 0 else "breakeven")
        paired.append({
            "order_id":    oid,
            "symbol":      ex.get("symbol") or (en or {}).get("symbol", ""),
            "strategy_id": ex.get("strategy_id") or (en or {}).get("strategy_id", ""),
            "side":        (en or ex).get("side", ""),
            "entry_price": (en or {}).get("filled_price"),
            "exit_price":  ex.get("filled_price"),
            "qty":         ex.get("qty"),
            "risk_usd":    risk,
            "pnl":         pnl,
            "r_multiple":  round(r_mult, 2),
            "result":      result,
            "entry_time":  (en or {}).get("timestamp", ""),
            "exit_time":   ex.get("timestamp", ""),
            "entry_reason": (en or {}).get("reason", ""),
            "exit_reason":  ex.get("reason", ""),
        })
    return paired


def calc_session_stats(paired: list) -> dict:
    """Calculate session stats from paired trades."""
    if not paired:
        return {
            "total_trades": 0, "wins": 0, "losses": 0, "breakevens": 0,
            "win_rate": None, "avg_r": None, "best_r": None, "worst_r": None,
            "total_pnl": None,
        }

    wins  = sum(1 for t in paired if t["result"] == "win")
    losses = sum(1 for t in paired if t["result"] == "loss")
    bes   = sum(1 for t in paired if t["result"] == "breakeven")
    total = len(paired)
    rs    = [t["r_multiple"] for t in paired if t["r_multiple"] is not None]
    pnls  = [t["pnl"] for t in paired if t["pnl"] is not None]

    return {
        "total_trades": total,
        "wins":         wins,
        "losses":       losses,
        "breakevens":   bes,
        "win_rate":     round(wins / total * 100, 1) if total else None,
        "avg_r":        round(sum(rs) / len(rs), 2) if rs else None,
        "best_r":       round(max(rs), 2) if rs else None,
        "worst_r":      round(min(rs), 2) if rs else None,
        "total_pnl":    round(sum(pnls), 2) if pnls else None,
    }


def save_session(paired: list, stats: dict, source: str) -> Path:
    """Save today's session bundle to hot cache."""
    HOT_DIR.mkdir(parents=True, exist_ok=True)
    today = _today_str()
    out = HOT_DIR / f"trade-session-{today}.json"
    payload = {
        "date": today,
        "logged_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "trades": paired,
        "stats": stats,
    }
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    log.info("Trade session saved: %s", out)
    return out


def append_to_trade_log(paired: list, stats: dict, source: str) -> None:
    """Append today's session to state/trade-log.json."""
    try:
        with open(STATE_DIR / "trade-log.json", encoding="utf-8-sig") as f:
            log_data = json.load(f)
    except Exception:
        log_data = {"sessions": [], "last_updated": None}

    today = _today_str()
    # Remove existing entry for today if re-running
    log_data["sessions"] = [s for s in log_data.get("sessions", [])
                             if s.get("date") != today]
    log_data["sessions"].append({
        "date": today,
        "logged_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "trades": paired,
        "stats": stats,
    })
    log_data["last_updated"] = datetime.now(timezone.utc).isoformat()

    with open(STATE_DIR / "trade-log.json", "w", encoding="utf-8") as f:
        json.dump(log_data, f, indent=2)

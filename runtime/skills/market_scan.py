"""
market-scan skill — Tier 0 (pure Python signals) + Tier 1 LLM interpretation.
Uses CoinGecko free API (no key required) for crypto price data.
Detects significant moves, volume anomalies, and momentum continuation signals.
"""

import json
import logging
import requests
from datetime import datetime, timezone

from runtime.config import SKILL_MODELS, LOGS_DIR, ROOT
from runtime.ollama_client import chat, is_available

log   = logging.getLogger(__name__)
MODEL = SKILL_MODELS["market-scan"]
HOT_DIR = ROOT / "divisions" / "trading" / "hot"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; OpenClaw/2.0)"}
TIMEOUT = 15

# CoinGecko IDs for instruments to track
CRYPTO_IDS = ["bitcoin", "ethereum", "solana", "binancecoin"]
CRYPTO_SYMBOLS = {
    "bitcoin":    "BTC",
    "ethereum":   "ETH",
    "solana":     "SOL",
    "binancecoin": "BNB",
}

MOVE_NOTABLE   = 5.0    # ±5% 24h = notable
MOVE_STRONG    = 10.0   # ±10% 24h = strong / high priority
VOL_CAP_SPIKE  = 0.15   # volume/market-cap ratio > 15% = unusual activity


def _fetch_market_data() -> tuple[list, str | None]:
    """Fetch current prices and stats from CoinGecko. Returns (data, error)."""
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "ids": ",".join(CRYPTO_IDS),
        "order": "market_cap_desc",
        "price_change_percentage": "1h,24h,7d",
        "sparkline": "false",
    }
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.json(), None
    except Exception as e:
        return [], str(e)


def _detect_signals(market_data: list) -> list:
    """Pure Python rule-based signal detection."""
    signals = []
    for coin in market_data:
        symbol    = CRYPTO_SYMBOLS.get(coin["id"], coin.get("symbol", "?").upper())
        price     = coin.get("current_price", 0)
        ch_24h    = coin.get("price_change_percentage_24h") or 0.0
        ch_1h     = coin.get("price_change_percentage_1h_in_currency") or 0.0
        volume    = coin.get("total_volume", 0)
        mkt_cap   = coin.get("market_cap", 1)
        vol_ratio = volume / mkt_cap if mkt_cap else 0

        # Strong 24h move
        if abs(ch_24h) >= MOVE_STRONG:
            direction = "up" if ch_24h > 0 else "down"
            signals.append({
                "type":       "strong_move",
                "instrument": symbol,
                "direction":  direction,
                "change_pct": round(ch_24h, 2),
                "timeframe":  "24h",
                "price":      price,
                "detail":     f"{symbol} {direction} {abs(ch_24h):.1f}% in 24h — ${price:,.2f}",
                "priority":   "high",
            })
        elif abs(ch_24h) >= MOVE_NOTABLE:
            direction = "up" if ch_24h > 0 else "down"
            signals.append({
                "type":       "notable_move",
                "instrument": symbol,
                "direction":  direction,
                "change_pct": round(ch_24h, 2),
                "timeframe":  "24h",
                "price":      price,
                "detail":     f"{symbol} {direction} {abs(ch_24h):.1f}% in 24h — ${price:,.2f}",
                "priority":   "medium",
            })

        # High volume-to-cap ratio
        if vol_ratio > VOL_CAP_SPIKE:
            signals.append({
                "type":       "volume_spike",
                "instrument": symbol,
                "direction":  "n/a",
                "change_pct": round(vol_ratio * 100, 1),
                "timeframe":  "24h",
                "price":      price,
                "detail":     f"{symbol} high volume activity: {vol_ratio*100:.1f}% vol/cap ratio",
                "priority":   "medium",
            })

        # 1h momentum continuation (1h move in same direction as 24h, both significant)
        if abs(ch_1h) >= 1.5 and abs(ch_24h) >= MOVE_NOTABLE and ch_1h * ch_24h > 0:
            direction = "up" if ch_1h > 0 else "down"
            signals.append({
                "type":       "momentum",
                "instrument": symbol,
                "direction":  direction,
                "change_pct": round(ch_1h, 2),
                "timeframe":  "1h",
                "price":      price,
                "detail":     (
                    f"{symbol} momentum {direction}: "
                    f"{abs(ch_1h):.1f}% (1h) continuing {abs(ch_24h):.1f}% (24h) move"
                ),
                "priority":   "medium",
            })

    return signals


def _llm_interpret(signals: list, market_data: list) -> str:
    """Ask LLM to summarize signals for Matthew."""
    if not is_available(MODEL):
        return "; ".join(s["detail"] for s in signals[:3]) if signals else "No signals."

    signal_text = "\n".join(f"- {s['detail']}" for s in signals[:6])
    snapshot = "\n".join(
        f"  {CRYPTO_SYMBOLS.get(c['id'], c['id'])}: "
        f"${c.get('current_price', 0):,.2f} "
        f"({c.get('price_change_percentage_24h', 0):+.1f}% 24h)"
        for c in market_data
    )
    messages = [
        {
            "role": "system",
            "content": (
                "You are the Trading Division market scanner for J_Claw. "
                "Given these crypto signals, write 1–2 sentences for Matthew — "
                "a trader focused on DeFi and crypto. Highlight what's actionable. "
                "Be direct. No filler."
            ),
        },
        {
            "role": "user",
            "content": f"Snapshot:\n{snapshot}\n\nSignals:\n{signal_text}",
        },
    ]
    try:
        return chat(MODEL, messages, temperature=0.2, max_tokens=120)
    except Exception as e:
        log.warning("market-scan LLM failed: %s", e)
        return "; ".join(s["detail"] for s in signals[:3])


def run() -> dict:
    LOGS_DIR.mkdir(exist_ok=True)
    HOT_DIR.mkdir(parents=True, exist_ok=True)

    market_data, fetch_error = _fetch_market_data()
    if fetch_error or not market_data:
        return {
            "status":          "failed",
            "escalate":        False,
            "signals":         [],
            "summary":         f"Market data fetch failed: {fetch_error}",
            "model_available": is_available(MODEL),
            "counts":          {"signals": 0, "instruments": 0, "high": 0},
        }

    signals      = _detect_signals(market_data)
    high_signals = [s for s in signals if s["priority"] == "high"]

    if signals:
        summary = _llm_interpret(signals, market_data)
    else:
        snapshot = ", ".join(
            f"{CRYPTO_SYMBOLS.get(c['id'], c['id'])} "
            f"${c.get('current_price', 0):,.0f} "
            f"({c.get('price_change_percentage_24h', 0):+.1f}%)"
            for c in market_data[:3]
        )
        summary = f"No significant moves. {snapshot}"

    # Save snapshot
    now = datetime.now(timezone.utc)
    snap_file = HOT_DIR / f"market-{now.strftime('%Y%m%d-%H%M')}.json"
    with open(snap_file, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": now.isoformat(),
            "market_data":  market_data,
            "signals":      signals,
            "summary":      summary,
        }, f, indent=2)

    return {
        "status":            "success",
        "escalate":          len(high_signals) > 0,
        "escalation_reason": f"{len(high_signals)} high-priority signal(s)" if high_signals else "",
        "signals":           signals,
        "summary":           summary,
        "model_available":   is_available(MODEL),
        "counts": {
            "signals":     len(signals),
            "instruments": len(market_data),
            "high":        len(high_signals),
        },
    }

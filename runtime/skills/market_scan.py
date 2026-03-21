"""
market-scan skill — Tier 0 (pure Python signals) + Tier 1 LLM interpretation.
Tracks two asset classes:
  - Crypto (BTC, ETH, BNB, SOL) via CoinGecko free API (no key required)
  - Traditional markets (SPX500, Gold) via yfinance (no key required)
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

# Traditional market instruments (yfinance tickers)
TRADITIONAL_INSTRUMENTS = {
    "SPX500": "^GSPC",
    "GOLD":   "GC=F",
}

MOVE_NOTABLE   = 5.0    # ±5% 24h = notable (crypto)
MOVE_STRONG    = 10.0   # ±10% 24h = strong / high priority (crypto)
VOL_CAP_SPIKE  = 0.15   # volume/market-cap ratio > 15% = unusual activity (crypto)

# Traditional market thresholds (tighter — SPX/Gold move less than crypto)
TRAD_NOTABLE   = 1.5    # ±1.5% daily = notable for SPX500/Gold
TRAD_STRONG    = 3.0    # ±3.0% daily = strong move for SPX500/Gold


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


def _fetch_traditional_markets() -> tuple[list, list[str]]:
    """
    Fetch SPX500 and Gold prices via yfinance.
    Returns (market_list, errors).
    Each item: {"id": str, "symbol": str, "current_price": float,
                "price_change_percentage_24h": float, "total_volume": float,
                "asset_class": "traditional"}
    """
    results = []
    errors  = []
    try:
        import yfinance as yf
        for display_name, ticker in TRADITIONAL_INSTRUMENTS.items():
            try:
                info = yf.download(ticker, period="5d", interval="1d",
                                   auto_adjust=True, progress=False)
                if info.empty or len(info) < 2:
                    errors.append(f"{display_name}: no data returned")
                    continue
                # Flatten MultiIndex columns if present
                if hasattr(info.columns, "levels"):
                    info.columns = info.columns.get_level_values(0)
                closes  = info["Close"].tolist()
                volumes = info["Volume"].tolist()
                current = float(closes[-1])
                prev    = float(closes[-2])
                chg_pct = ((current - prev) / prev * 100) if prev else 0.0
                results.append({
                    "id":                         ticker,
                    "symbol":                     display_name,
                    "current_price":              round(current, 2),
                    "price_change_percentage_24h": round(chg_pct, 2),
                    "price_change_percentage_1h_in_currency": None,
                    "total_volume":               float(volumes[-1]) if volumes else 0,
                    "market_cap":                 None,
                    "asset_class":                "traditional",
                })
            except Exception as e:
                errors.append(f"{display_name}: {e}")
    except ImportError:
        errors.append("yfinance not installed — traditional markets unavailable")
    except Exception as e:
        errors.append(f"traditional market fetch error: {e}")
    return results, errors


def _detect_signals(market_data: list) -> list:
    """Pure Python rule-based signal detection for crypto instruments."""
    signals = []
    for coin in market_data:
        if coin.get("asset_class") == "traditional":
            continue  # handled by _detect_traditional_signals
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
                "asset_class": "crypto",
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
                "asset_class": "crypto",
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
                "asset_class": "crypto",
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
                "asset_class": "crypto",
            })

    return signals


def _detect_traditional_signals(trad_data: list) -> list:
    """Signal detection for SPX500 and Gold (tighter thresholds than crypto)."""
    signals = []
    for item in trad_data:
        symbol  = item.get("symbol", "?")
        price   = item.get("current_price", 0)
        ch_24h  = item.get("price_change_percentage_24h") or 0.0

        if abs(ch_24h) >= TRAD_STRONG:
            direction = "up" if ch_24h > 0 else "down"
            signals.append({
                "type":       "strong_move",
                "instrument": symbol,
                "direction":  direction,
                "change_pct": round(ch_24h, 2),
                "timeframe":  "1d",
                "price":      price,
                "detail":     f"{symbol} {direction} {abs(ch_24h):.1f}% today — ${price:,.2f}",
                "priority":   "high",
                "asset_class": "traditional",
            })
        elif abs(ch_24h) >= TRAD_NOTABLE:
            direction = "up" if ch_24h > 0 else "down"
            signals.append({
                "type":       "notable_move",
                "instrument": symbol,
                "direction":  direction,
                "change_pct": round(ch_24h, 2),
                "timeframe":  "1d",
                "price":      price,
                "detail":     f"{symbol} {direction} {abs(ch_24h):.1f}% today — ${price:,.2f}",
                "priority":   "medium",
                "asset_class": "traditional",
            })

    return signals


def _llm_interpret(signals: list, market_data: list, trad_data: list) -> str:
    """Ask LLM to summarize signals across all tracked instruments."""
    if not is_available(MODEL):
        return "; ".join(s["detail"] for s in signals[:3]) if signals else "No signals."

    signal_text = "\n".join(f"- {s['detail']}" for s in signals[:8])
    crypto_snap = "\n".join(
        f"  {CRYPTO_SYMBOLS.get(c['id'], c['id'])}: "
        f"${c.get('current_price', 0):,.2f} "
        f"({c.get('price_change_percentage_24h', 0):+.1f}% 24h)"
        for c in market_data
    )
    trad_snap = "\n".join(
        f"  {t['symbol']}: ${t['current_price']:,.2f} ({t['price_change_percentage_24h']:+.1f}% today)"
        for t in trad_data
    )
    snapshot = ""
    if crypto_snap:
        snapshot += f"Crypto:\n{crypto_snap}\n"
    if trad_snap:
        snapshot += f"Traditional:\n{trad_snap}"

    messages = [
        {
            "role": "system",
            "content": (
                "You are the Trading Division market scanner for J_Claw. "
                "You track crypto (BTC, ETH, BNB, SOL) and traditional markets (SPX500, Gold). "
                "Given these market signals, write 1–2 sentences for Matthew — "
                "highlighting what's actionable across all instruments. "
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

    # ── Fetch crypto (CoinGecko) ───────────────────────────────────────────────
    market_data, fetch_error = _fetch_market_data()
    if fetch_error or not market_data:
        log.warning("CoinGecko fetch failed: %s", fetch_error)
        # Don't hard-fail — traditional markets may still be available
        market_data = []

    # ── Fetch traditional markets (yfinance) ──────────────────────────────────
    trad_data, trad_errors = _fetch_traditional_markets()
    if trad_errors:
        for err in trad_errors:
            log.warning("Traditional market fetch: %s", err)

    all_data = market_data + trad_data

    if not all_data:
        return {
            "status":          "failed",
            "escalate":        False,
            "signals":         [],
            "summary":         f"All market data unavailable. CoinGecko: {fetch_error}",
            "model_available": is_available(MODEL),
            "counts":          {"signals": 0, "instruments": 0, "high": 0},
        }

    # ── Signal detection ──────────────────────────────────────────────────────
    crypto_signals = _detect_signals(market_data)
    trad_signals   = _detect_traditional_signals(trad_data)
    signals        = crypto_signals + trad_signals
    high_signals   = [s for s in signals if s["priority"] == "high"]

    # ── Summary ───────────────────────────────────────────────────────────────
    if signals:
        summary = _llm_interpret(signals, market_data, trad_data)
    else:
        crypto_snap = ", ".join(
            f"{CRYPTO_SYMBOLS.get(c['id'], c['id'])} "
            f"${c.get('current_price', 0):,.0f} "
            f"({c.get('price_change_percentage_24h', 0):+.1f}%)"
            for c in market_data[:3]
        )
        trad_snap = ", ".join(
            f"{t['symbol']} ${t['current_price']:,.0f} ({t['price_change_percentage_24h']:+.1f}%)"
            for t in trad_data
        )
        parts = [p for p in [crypto_snap, trad_snap] if p]
        summary = "No significant moves. " + " | ".join(parts) if parts else "No market data."

    # ── Save snapshot ─────────────────────────────────────────────────────────
    now = datetime.now(timezone.utc)
    snap_file = HOT_DIR / f"market-{now.strftime('%Y%m%d-%H%M')}.json"
    with open(snap_file, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at":     now.isoformat(),
            "market_data":      market_data,
            "traditional_data": trad_data,
            "signals":          signals,
            "summary":          summary,
        }, f, indent=2)

    status = "success" if (market_data or trad_data) else "failed"
    if market_data and not trad_data:
        status = "partial"  # crypto only

    return {
        "status":            status,
        "escalate":          len(high_signals) > 0,
        "escalation_reason": f"{len(high_signals)} high-priority signal(s)" if high_signals else "",
        "signals":           signals,
        "summary":           summary,
        "model_available":   is_available(MODEL),
        "counts": {
            "signals":     len(signals),
            "instruments": len(all_data),
            "high":        len(high_signals),
        },
    }

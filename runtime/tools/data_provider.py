"""
Data Provider Abstraction Layer — wraps market data sources behind a common interface.

Default provider: TwelveData (requires TWELVEDATA_API_KEY in .env).
Fallback provider: yfinance (used automatically when key is missing or API fails).

All trading skills consume fetch_ohlcv() — the provider can be swapped at
runtime via set_provider() without touching any skill code.
"""

import json
import logging
import os
import time
import urllib.request
import urllib.error
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

ASSETS_FILE = Path("divisions/trading/assets.json")

# ── TwelveData interval map ───────────────────────────────────────────────────
# Note: 4h is supported natively by Twelve Data (no resampling needed).
_TD_INTERVAL_MAP: dict[str, str] = {
    "1m":  "1min",
    "5m":  "5min",
    "15m": "15min",
    "1h":  "1h",
    "4h":  "4h",
    "1d":  "1day",
}

# ── yfinance fallback interval map ────────────────────────────────────────────
# Note: 1m data is limited to a 7-day rolling window by yfinance.
_YF_TF_MAP: dict[str, tuple[str, str]] = {
    "1m":  ("1m",  "7d"),
    "5m":  ("5m",  "60d"),
    "15m": ("15m", "5d"),
    "1h":  ("1h",  "30d"),
    "4h":  ("1h",  "30d"),   # fetch 1h, resample → ~120 4h bars
    "1d":  ("1d",  "3mo"),
}


class BaseDataProvider(ABC):
    """Abstract base class for OHLCV market data providers."""

    @abstractmethod
    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        bars: int = 500,
    ) -> Optional[dict]:
        """
        Fetch OHLCV bars for the given symbol and timeframe.

        Args:
            symbol:    Instrument name (e.g. "SPX500") or raw ticker.
            timeframe: One of: 1m, 5m, 15m, 1h, 4h, 1d
            bars:      Requested bar count (advisory — providers may return more/fewer).

        Returns:
            Dict with lists: {ticker, timestamps, open, high, low, close, volume}
            or None on failure.
        """
        ...


# ── Helper: load assets.json ──────────────────────────────────────────────────

def _load_assets() -> list[dict]:
    try:
        with open(ASSETS_FILE, encoding="utf-8") as f:
            return json.load(f).get("instruments", [])
    except Exception as e:
        log.warning("data_provider: could not load assets.json (%s)", e)
        return []


# ── TwelveData Provider ───────────────────────────────────────────────────────

class TwelveDataProvider(BaseDataProvider):
    """
    OHLCV provider backed by the Twelve Data REST API.

    Reads divisions/trading/assets.json to map instrument names (e.g. "SPX500")
    to Twelve Data symbols (e.g. "SPX"). Raises on missing API key so the
    module-level singleton can fall back to yfinance automatically.

    Rate limits (free tier): 8 req/min, 800 req/day.
    """

    API_BASE = "https://api.twelvedata.com"
    TIMEOUT   = 15  # seconds

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ValueError("TwelveDataProvider: TWELVEDATA_API_KEY is not set")
        self._api_key = api_key
        self._symbol_map: dict[str, str] = self._build_symbol_map()

    @staticmethod
    def _build_symbol_map() -> dict[str, str]:
        """Build name → td_symbol mapping from assets.json."""
        assets = _load_assets()
        result = {}
        for inst in assets:
            name = inst.get("name", "")
            td   = inst.get("td_symbol", "")
            if name and td:
                result[name] = td
        return result

    def _resolve_symbol(self, symbol: str) -> str:
        """Map instrument name to Twelve Data symbol if registered; else pass through."""
        return self._symbol_map.get(symbol, symbol)

    # Twelve Data sits behind Cloudflare — the default Python-urllib user-agent
    # gets a 403 (CF error 1010). A browser UA bypasses this cleanly.
    _HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
    }

    def _get(self, endpoint: str, params: dict) -> dict:
        """Make a GET request to the Twelve Data API, return parsed JSON."""
        params["apikey"] = self._api_key
        query = "&".join(f"{k}={urllib.request.quote(str(v))}" for k, v in params.items())
        url   = f"{self.API_BASE}{endpoint}?{query}"
        req   = urllib.request.Request(url, headers=self._HEADERS)
        with urllib.request.urlopen(req, timeout=self.TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        bars: int = 500,
    ) -> Optional[dict]:
        """
        Fetch OHLCV from Twelve Data.

        Values are returned newest-first by the API and reversed here so
        index 0 is the oldest bar (same convention as yfinance / backtester).
        """
        td_symbol = self._resolve_symbol(symbol)
        interval  = _TD_INTERVAL_MAP.get(timeframe, "1h")
        outputsize = min(bars, 5000)

        try:
            data = self._get("/time_series", {
                "symbol":     td_symbol,
                "interval":   interval,
                "outputsize": outputsize,
                "timezone":   "UTC",
            })

            if data.get("status") == "error":
                log.warning(
                    "TwelveDataProvider: API error for %s/%s: %s",
                    td_symbol, interval, data.get("message", "unknown"),
                )
                return None

            values = data.get("values", [])
            if not values:
                log.warning("TwelveDataProvider: no values returned for %s/%s", td_symbol, interval)
                return None

            # API returns newest-first — reverse so index 0 = oldest
            values = list(reversed(values))

            ohlcv = {
                "ticker":     td_symbol,
                "timestamps": [v["datetime"] for v in values],
                "open":       [float(v["open"])   for v in values],
                "high":       [float(v["high"])   for v in values],
                "low":        [float(v["low"])    for v in values],
                "close":      [float(v["close"])  for v in values],
                "volume":     [float(v.get("volume", 0) or 0) for v in values],
            }

            log.debug(
                "TwelveDataProvider: fetched %d %s bars for %s",
                len(ohlcv["close"]), timeframe, td_symbol,
            )
            return ohlcv

        except urllib.error.HTTPError as e:
            log.error("TwelveDataProvider: HTTP %d for %s/%s", e.code, td_symbol, interval)
            return None
        except urllib.error.URLError as e:
            log.error("TwelveDataProvider: network error for %s/%s: %s", td_symbol, interval, e)
            return None
        except Exception as e:
            log.error("TwelveDataProvider: unexpected error for %s/%s: %s", td_symbol, interval, e)
            return None


# ── yfinance Fallback Provider ────────────────────────────────────────────────

class YfinanceProvider(BaseDataProvider):
    """
    OHLCV provider backed by yfinance.

    Used as automatic fallback when TWELVEDATA_API_KEY is not configured.
    Reads divisions/trading/assets.json to map instrument names to yfinance
    tickers (e.g. "SPX500" → "^GSPC").
    """

    def __init__(self) -> None:
        self._ticker_map: dict[str, str] = self._load_ticker_map()

    @staticmethod
    def _load_ticker_map() -> dict[str, str]:
        assets = _load_assets()
        return {inst["name"]: inst["ticker"] for inst in assets if inst.get("name") and inst.get("ticker")}

    def _resolve_ticker(self, symbol: str) -> str:
        return self._ticker_map.get(symbol, symbol)

    @staticmethod
    def _resample_4h(ohlcv: dict) -> dict:
        """Aggregate 1h OHLCV dict into 4h candles (every 4 bars)."""
        dates  = ohlcv["timestamps"]
        opens  = ohlcv["open"]
        highs  = ohlcv["high"]
        lows   = ohlcv["low"]
        closes = ohlcv["close"]
        vols   = ohlcv["volume"]
        n = len(dates)
        r_d, r_o, r_h, r_l, r_c, r_v = [], [], [], [], [], []
        i = 0
        while i < n:
            end = min(i + 4, n)
            r_d.append(dates[i])
            r_o.append(opens[i])
            r_h.append(max(highs[i:end]))
            r_l.append(min(lows[i:end]))
            r_c.append(closes[end - 1])
            r_v.append(sum(vols[i:end]))
            i += 4
        return {
            "ticker":     ohlcv["ticker"],
            "timestamps": r_d,
            "open":       r_o,
            "high":       r_h,
            "low":        r_l,
            "close":      r_c,
            "volume":     r_v,
        }

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        bars: int = 500,
    ) -> Optional[dict]:
        ticker = self._resolve_ticker(symbol)
        yf_interval, yf_period = _YF_TF_MAP.get(timeframe, ("1d", "3mo"))
        try:
            import yfinance as yf
            df = yf.download(
                ticker,
                period=yf_period,
                interval=yf_interval,
                auto_adjust=False,
                progress=False,
            )
            if df.empty:
                log.warning("YfinanceProvider: no data returned for %s", ticker)
                return None
            if hasattr(df.columns, "levels"):
                df.columns = df.columns.get_level_values(0)
            ohlcv = {
                "ticker":     ticker,
                "timestamps": [str(d) for d in df.index],
                "open":       [float(v) for v in df["Open"].tolist()],
                "high":       [float(v) for v in df["High"].tolist()],
                "low":        [float(v) for v in df["Low"].tolist()],
                "close":      [float(v) for v in df["Close"].tolist()],
                "volume":     [float(v) for v in df["Volume"].tolist()],
            }
            if timeframe == "4h":
                ohlcv = self._resample_4h(ohlcv)
            log.debug(
                "YfinanceProvider: fetched %d %s bars for %s",
                len(ohlcv["close"]), timeframe, ticker,
            )
            return ohlcv
        except ImportError:
            log.error("YfinanceProvider: yfinance not installed — run: pip install yfinance pandas")
            return None
        except Exception as e:
            log.error("YfinanceProvider: fetch failed for %s: %s", ticker, e)
            return None


# ── Module-level singleton — auto-selects provider ───────────────────────────

def _init_provider() -> BaseDataProvider:
    """
    Select the active provider based on available credentials.

    Priority:
      1. TwelveData  — if TWELVEDATA_API_KEY is set in environment
      2. yfinance    — automatic fallback (no key required)
    """
    td_key = os.getenv("TWELVEDATA_API_KEY", "").strip()
    if td_key:
        try:
            provider = TwelveDataProvider(td_key)
            log.info("data_provider: using TwelveData as market data source")
            return provider
        except Exception as e:
            log.warning("data_provider: TwelveData init failed (%s) — falling back to yfinance", e)
    log.info("data_provider: TWELVEDATA_API_KEY not set — using yfinance fallback")
    return YfinanceProvider()


_provider: BaseDataProvider = _init_provider()


def set_provider(p: BaseDataProvider) -> None:
    """Swap the active data provider at runtime (e.g. for backtesting or mocking)."""
    global _provider
    _provider = p


def fetch_ohlcv(symbol: str, timeframe: str, bars: int = 500) -> Optional[dict]:
    """
    Fetch OHLCV for the given symbol and timeframe via the active provider.

    Args:
        symbol:    Instrument name (e.g. "SPX500") or raw ticker.
        timeframe: One of: 1m, 5m, 15m, 1h, 4h, 1d
        bars:      Requested bar count (advisory).

    Returns:
        Dict with lists: {ticker, timestamps, open, high, low, close, volume}
        or None on failure.
    """
    return _provider.fetch_ohlcv(symbol, timeframe, bars)

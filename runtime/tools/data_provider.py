"""
Data Provider Abstraction Layer — wraps market data sources behind a common interface.

Default provider: TwelveData (requires TWELVEDATA_API_KEY in .env).
Fallback provider: yfinance (used automatically when key is missing or API fails).

All trading skills consume fetch_ohlcv() — the provider can be swapped at
runtime via set_provider() without touching any skill code.

Cache:
  OHLCV responses are cached to divisions/trading/cache/{symbol}_{timeframe}.json.
  TTL is per-timeframe (1m=2min, 5m=5min, 15m=15min, 1h=30min, 4h=2h, 1d=4h).
  This keeps all three consumers (market_scan, virtual_account, backtester)
  hitting the API at most once per window regardless of how many cycles run.
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
CACHE_DIR   = Path("divisions/trading/cache")

# ── Cache TTL per timeframe (seconds) ────────────────────────────────────────
_CACHE_TTL: dict[str, int] = {
    "1m":  2  * 60,       # 2 min  — intraday, refresh frequently
    "5m":  5  * 60,       # 5 min
    "15m": 15 * 60,       # 15 min
    "1h":  30 * 60,       # 30 min — one fresh fetch per half-hour session
    "4h":  2  * 3600,     # 2 h
    "1d":  4  * 3600,     # 4 h    — daily bars don't move intraday
}

# ── TwelveData interval map ───────────────────────────────────────────────────
_TD_INTERVAL_MAP: dict[str, str] = {
    "1m":  "1min",
    "5m":  "5min",
    "15m": "15min",
    "1h":  "1h",
    "4h":  "4h",
    "1d":  "1day",
}

# ── yfinance fallback interval map ────────────────────────────────────────────
_YF_TF_MAP: dict[str, tuple[str, str]] = {
    "1m":  ("1m",  "7d"),
    "5m":  ("5m",  "60d"),
    "15m": ("15m", "5d"),
    "1h":  ("1h",  "30d"),
    "4h":  ("1h",  "30d"),   # fetch 1h, resample → ~120 4h bars
    "1d":  ("1d",  "3mo"),
}


# ── Disk cache helpers ────────────────────────────────────────────────────────

def _cache_path(symbol: str, timeframe: str) -> Path:
    safe = symbol.replace("/", "-").replace("^", "").replace("=", "")
    return CACHE_DIR / f"{safe}_{timeframe}.json"


def _cache_read(symbol: str, timeframe: str) -> Optional[dict]:
    """Return cached OHLCV if it exists and is still fresh, else None."""
    path = _cache_path(symbol, timeframe)
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            entry = json.load(f)
        ttl     = _CACHE_TTL.get(timeframe, 3600)
        age     = time.time() - entry.get("cached_at", 0)
        if age < ttl:
            log.debug("data_provider: cache hit %s/%s (age %.0fs / ttl %ds)", symbol, timeframe, age, ttl)
            return entry["ohlcv"]
        log.debug("data_provider: cache expired %s/%s (age %.0fs)", symbol, timeframe, age)
    except Exception as e:
        log.warning("data_provider: cache read error %s/%s: %s", symbol, timeframe, e)
    return None


def _cache_write(symbol: str, timeframe: str, ohlcv: dict) -> None:
    """Write OHLCV to disk cache."""
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path  = _cache_path(symbol, timeframe)
        entry = {"cached_at": time.time(), "symbol": symbol, "timeframe": timeframe, "ohlcv": ohlcv}
        tmp   = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(entry, f)
        tmp.replace(path)
        log.debug("data_provider: cached %s/%s (%d bars)", symbol, timeframe, len(ohlcv.get("close", [])))
    except Exception as e:
        log.warning("data_provider: cache write error %s/%s: %s", symbol, timeframe, e)


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
    to Twelve Data symbols (e.g. "SPY"). Results are cached to disk so
    all consumers share one fetch per TTL window — keeps API calls minimal.

    Rate limits (free tier): 8 req/min, 800 req/day.
    """

    API_BASE = "https://api.twelvedata.com"
    TIMEOUT  = 15

    # Cloudflare blocks Python-urllib/3.x — browser UA bypasses it cleanly.
    _HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
    }

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ValueError("TwelveDataProvider: TWELVEDATA_API_KEY is not set")
        self._api_key    = api_key
        self._symbol_map = self._build_symbol_map()

    @staticmethod
    def _build_symbol_map() -> dict[str, str]:
        assets = _load_assets()
        return {inst["name"]: inst["td_symbol"] for inst in assets if inst.get("name") and inst.get("td_symbol")}

    def _resolve_symbol(self, symbol: str) -> str:
        return self._symbol_map.get(symbol, symbol)

    def _get(self, endpoint: str, params: dict) -> dict:
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
        # Check cache first — avoids hitting the API on every skill run
        cached = _cache_read(symbol, timeframe)
        if cached is not None:
            return cached

        td_symbol  = self._resolve_symbol(symbol)
        interval   = _TD_INTERVAL_MAP.get(timeframe, "1h")
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
                log.warning("TwelveDataProvider: no values for %s/%s", td_symbol, interval)
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

            _cache_write(symbol, timeframe, ohlcv)
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
    Results are also cached to disk on the same TTL schedule.
    """

    def __init__(self) -> None:
        self._ticker_map = self._load_ticker_map()

    @staticmethod
    def _load_ticker_map() -> dict[str, str]:
        assets = _load_assets()
        return {inst["name"]: inst["ticker"] for inst in assets if inst.get("name") and inst.get("ticker")}

    def _resolve_ticker(self, symbol: str) -> str:
        return self._ticker_map.get(symbol, symbol)

    @staticmethod
    def _resample_4h(ohlcv: dict) -> dict:
        dates, opens, highs, lows, closes, vols = (
            ohlcv["timestamps"], ohlcv["open"], ohlcv["high"],
            ohlcv["low"], ohlcv["close"], ohlcv["volume"],
        )
        n = len(dates)
        r_d, r_o, r_h, r_l, r_c, r_v = [], [], [], [], [], []
        i = 0
        while i < n:
            end = min(i + 4, n)
            r_d.append(dates[i]); r_o.append(opens[i])
            r_h.append(max(highs[i:end])); r_l.append(min(lows[i:end]))
            r_c.append(closes[end - 1]); r_v.append(sum(vols[i:end]))
            i += 4
        return {"ticker": ohlcv["ticker"], "timestamps": r_d,
                "open": r_o, "high": r_h, "low": r_l, "close": r_c, "volume": r_v}

    def fetch_ohlcv(self, symbol: str, timeframe: str, bars: int = 500) -> Optional[dict]:
        cached = _cache_read(symbol, timeframe)
        if cached is not None:
            return cached

        ticker = self._resolve_ticker(symbol)
        yf_interval, yf_period = _YF_TF_MAP.get(timeframe, ("1d", "3mo"))
        try:
            import yfinance as yf
            df = yf.download(ticker, period=yf_period, interval=yf_interval,
                             auto_adjust=False, progress=False)
            if df.empty:
                log.warning("YfinanceProvider: no data for %s", ticker)
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
            log.debug("YfinanceProvider: fetched %d %s bars for %s", len(ohlcv["close"]), timeframe, ticker)
            _cache_write(symbol, timeframe, ohlcv)
            return ohlcv
        except ImportError:
            log.error("YfinanceProvider: yfinance not installed")
            return None
        except Exception as e:
            log.error("YfinanceProvider: fetch failed for %s: %s", ticker, e)
            return None


# ── Module-level singleton — auto-selects provider ───────────────────────────

def _init_provider() -> BaseDataProvider:
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

    Results are served from disk cache when fresh (TTL per timeframe).
    A live API call is only made when the cache is missing or expired.

    Args:
        symbol:    Instrument name (e.g. "SPX500") or raw ticker.
        timeframe: One of: 1m, 5m, 15m, 1h, 4h, 1d
        bars:      Requested bar count (advisory).

    Returns:
        Dict with lists: {ticker, timestamps, open, high, low, close, volume}
        or None on failure.
    """
    return _provider.fetch_ohlcv(symbol, timeframe, bars)

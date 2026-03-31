"""
Data Provider Abstraction Layer — wraps market data sources behind a common interface.

Provides a BaseDataProvider ABC and a YfinanceProvider implementation.
The module-level fetch_ohlcv() delegates to a singleton provider that can be
swapped at runtime via set_provider() (useful for backtesting / mocking).
"""

import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

ASSETS_FILE = Path("divisions/trading/assets.json")

# Timeframe -> (yfinance interval, yfinance period)
# Note: 4h is fetched as 1h then resampled to 4h candles.
# Note: 1m data is limited to a 7-day rolling window by yfinance.
_TF_MAP: dict[str, tuple[str, str]] = {
    "1m":  ("1m",  "7d"),    # ~2730 1-min bars (yfinance hard limit: 7 days)
    "5m":  ("5m",  "60d"),   # ~3360 5-min bars
    "15m": ("15m", "5d"),    # ~130 intraday 15-min bars
    "1h":  ("1h",  "30d"),   # ~480 1h bars
    "4h":  ("1h",  "30d"),   # fetch 1h, resample → ~120 4h bars
    "1d":  ("1d",  "3mo"),   # daily
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
            symbol:    Instrument ticker or registered name (e.g. "^GSPC" or "SPX500").
            timeframe: One of: 1m, 5m, 15m, 1h, 4h, 1d
            bars:      Requested bar count (advisory — providers may return more/fewer).

        Returns:
            Dict with lists: {open, high, low, close, volume, timestamps}
            or None on failure.
        """
        ...


class YfinanceProvider(BaseDataProvider):
    """
    OHLCV provider backed by yfinance.

    Reads divisions/trading/assets.json to map registered instrument names
    (e.g. "SPX500") to their yfinance tickers (e.g. "^GSPC"). Symbols not
    found in the registry are passed through unchanged.
    """

    def __init__(self) -> None:
        self._ticker_map: dict[str, str] = self._load_ticker_map()

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _load_ticker_map() -> dict[str, str]:
        """Load name->ticker mapping from assets.json."""
        try:
            with open(ASSETS_FILE, encoding="utf-8") as f:
                data = json.load(f)
            return {inst["name"]: inst["ticker"] for inst in data.get("instruments", [])}
        except Exception as e:
            log.warning("YfinanceProvider: could not load assets.json (%s) — no name mapping", e)
            return {}

    def _resolve_ticker(self, symbol: str) -> str:
        """Map instrument name to yfinance ticker if registered; else pass through."""
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

    # ── Public interface ──────────────────────────────────────────────────────

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        bars: int = 500,
    ) -> Optional[dict]:
        """
        Fetch OHLCV via yfinance.

        4h is fetched as 1h then resampled. Returns dict with lists:
        timestamps, open, high, low, close, volume.
        """
        ticker = self._resolve_ticker(symbol)
        yf_interval, yf_period = _TF_MAP.get(timeframe, ("1d", "3mo"))
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
            # Flatten in case yfinance returns MultiIndex columns
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
            log.error("yfinance not installed — run: pip install yfinance pandas")
            return None
        except Exception as e:
            log.error("YfinanceProvider: fetch failed for %s: %s", ticker, e)
            return None


# ── Module-level singleton and public API ─────────────────────────────────────

_provider: BaseDataProvider = YfinanceProvider()


def set_provider(p: BaseDataProvider) -> None:
    """Swap the active data provider at runtime (e.g. for backtesting or mocking)."""
    global _provider
    _provider = p


def fetch_ohlcv(symbol: str, timeframe: str, bars: int = 500) -> Optional[dict]:
    """
    Fetch OHLCV for the given symbol and timeframe via the active provider.

    Args:
        symbol:    Instrument ticker or registered name (e.g. "^GSPC" or "SPX500").
        timeframe: One of: 1m, 5m, 15m, 1h, 4h, 1d
        bars:      Requested bar count (advisory).

    Returns:
        Dict with lists: {ticker, timestamps, open, high, low, close, volume}
        or None on failure.
    """
    return _provider.fetch_ohlcv(symbol, timeframe, bars)

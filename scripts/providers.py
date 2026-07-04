"""Data providers for the buy-the-dip project.

Two providers behind one duck-typed interface:

- NorgateProvider — the ONLY provider whose output is valid for results.
  Survivorship-bias-free: point-in-time index membership and delisted
  securities. Requires the Norgate Data Updater (NDU) Windows application to
  be running locally, and a US Stocks subscription (or 3-week trial) at
  Platinum level or above.

- YFinanceProvider — engine plumbing and development ONLY. Currently-listed
  names only, no point-in-time membership. Any statistic produced through
  this provider is survivorship-biased and must never be quoted.

Duck-typed interface:
    results_grade  : bool
    universe_symbols() -> list[str]
    price_history(symbol) -> DataFrame[Open, High, Low, Close, Volume],
                             ascending DatetimeIndex (tz-naive); empty
                             DataFrame if the symbol has no bars in range
    index_membership(symbol) -> Series of {0,1}
    describe() -> str
"""

from __future__ import annotations

import logging

import pandas as pd

log = logging.getLogger(__name__)

PRICE_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]


def _standardise(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise a raw provider frame to the PRICE_COLUMNS contract."""
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=PRICE_COLUMNS)
    out = df.copy()
    if getattr(out.index, "tz", None) is not None:
        out.index = out.index.tz_localize(None)
    for col in PRICE_COLUMNS:
        if col not in out.columns:
            out[col] = pd.NA
    out = out[PRICE_COLUMNS].sort_index()
    return out


class NorgateProvider:
    """Point-in-time S&P 500 universe from Norgate Data (via local NDU)."""

    results_grade = True

    def __init__(
        self,
        watchlist: str = "S&P 500 Current & Past",
        index_name: str = "S&P 500",
        adjustment: str = "TOTALRETURN",
        start_date: str = "1998-01-01",
    ):
        import norgatedata  # lazy: module stays importable without the package

        self._nd = norgatedata
        self.watchlist = watchlist
        self.index_name = index_name
        self.adjustment = adjustment
        self.start_date = start_date
        self._adj = getattr(norgatedata.StockPriceAdjustmentType, adjustment)
        self._pad = norgatedata.PaddingType.NONE
        try:
            ok = bool(norgatedata.status())
        except Exception:
            ok = False
        if not ok:
            raise RuntimeError(
                "Norgate Data Updater (NDU) is not running or not reachable. "
                "Start the NDU application, let it finish syncing, then retry. "
                "The Python package only proxies the local NDU database."
            )

    def describe(self) -> str:
        return (
            f"NorgateProvider(watchlist={self.watchlist!r}, index={self.index_name!r}, "
            f"adjustment={self.adjustment}, start={self.start_date}) [results-grade]"
        )

    def universe_symbols(self) -> list:
        symbols = self._nd.watchlist_symbols(self.watchlist)
        return list(symbols)

    def price_history(self, symbol: str) -> pd.DataFrame:
        df = self._nd.price_timeseries(
            symbol,
            stock_price_adjustment_setting=self._adj,
            padding_setting=self._pad,
            start_date=self.start_date,
            timeseriesformat="pandas-dataframe",
        )
        return _standardise(df)

    def price_history_unadjusted(self, symbol: str) -> pd.DataFrame:
        """Actual traded prices (no split/dividend back-adjustment). Absolute
        price and dollar-volume screens must read this series: back-adjusted
        prices shrink early history for the biggest compounders and would
        wrongly exclude them."""
        df = self._nd.price_timeseries(
            symbol,
            stock_price_adjustment_setting=self._nd.StockPriceAdjustmentType.NONE,
            padding_setting=self._pad,
            start_date=self.start_date,
            timeseriesformat="pandas-dataframe",
        )
        return _standardise(df)

    def index_membership(self, symbol: str) -> pd.Series:
        df = self._nd.index_constituent_timeseries(
            symbol,
            self.index_name,
            timeseriesformat="pandas-dataframe",
        )
        if df is None or len(df) == 0:
            return pd.Series(dtype="int64")
        col = df.columns[0]  # single flag column; name varies by version
        s = df[col].astype("int64")
        if getattr(s.index, "tz", None) is not None:
            s.index = s.index.tz_localize(None)
        return s.sort_index()


class YFinanceProvider:
    """Survivorship-BIASED convenience provider for engine development only."""

    results_grade = False

    _WARNING = (
        "YFinanceProvider is survivorship-biased (currently-listed names, no "
        "point-in-time membership). Plumbing only — never quote its output."
    )

    def __init__(self, symbols=None, start_date: str = "1998-01-01"):
        import yfinance  # lazy

        self._yf = yfinance
        self.start_date = start_date
        # Deliberately tiny default so nobody mistakes this for a universe.
        self._symbols = list(symbols) if symbols else ["AAPL", "MSFT", "KO", "JNJ", "XOM"]
        log.warning(self._WARNING)

    def describe(self) -> str:
        return f"YFinanceProvider({len(self._symbols)} symbols) [PLUMBING ONLY — biased]"

    def universe_symbols(self) -> list:
        return list(self._symbols)

    def price_history(self, symbol: str) -> pd.DataFrame:
        df = self._yf.Ticker(symbol).history(start=self.start_date, auto_adjust=True)
        return _standardise(df)

    def price_history_unadjusted(self, symbol: str) -> pd.DataFrame:
        df = self._yf.Ticker(symbol).history(start=self.start_date, auto_adjust=False)
        return _standardise(df)

    def index_membership(self, symbol: str) -> pd.Series:
        # No point-in-time data available: pretend always-member. This is the
        # exact bias the project exists to avoid — hence plumbing only.
        prices = self.price_history(symbol)
        return pd.Series(1, index=prices.index, dtype="int64")


def assert_cache_depth(fresh_start, cached_start, tolerance_days: int = 365) -> None:
    """Refuse to run when the local price cache is shallower than the data the
    provider now serves — the exact failure mode of upgrading the Norgate
    trial (2-year window) to a paid subscription (1990→) while the 2-year
    CSV cache is still warm. A silent pass here would produce trial-depth
    results labelled as full history.
    """
    if fresh_start is None or cached_start is None:
        return
    fresh_start = pd.Timestamp(fresh_start)
    cached_start = pd.Timestamp(cached_start)
    if fresh_start < cached_start - pd.Timedelta(days=tolerance_days):
        raise RuntimeError(
            f"Cache depth mismatch: the provider now serves history from "
            f"{fresh_start.date()} but the cache starts {cached_start.date()}. "
            "The cache predates a subscription upgrade. Rebuild the universe "
            "files (scripts/build_universe_fallback.py for each index) and "
            "re-run with --refresh-cache."
        )


def get_provider(name: str, **kwargs):
    name = name.lower()
    if name == "norgate":
        return NorgateProvider(**kwargs)
    if name == "yfinance":
        return YFinanceProvider(**kwargs)
    raise ValueError(f"Unknown provider {name!r} (expected 'norgate' or 'yfinance')")

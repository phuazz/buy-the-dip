"""Connectivity and data-coverage smoke test for Norgate Data.

Run AFTER:
  1. registering the Norgate free trial (US Stocks — 3 weeks, Platinum-level
     features, ~2 years of history),
  2. installing the Norgate Data Updater (NDU) Windows application,
  3. starting NDU and letting it finish its first database sync,
  4. `pip install norgatedata` (already in requirements.txt).

Usage:
    python scripts/norgate_smoke_test.py

Exit code 0 means every critical check passed. Output is ASCII-only so it
renders on any Windows console code page.
"""

from __future__ import annotations

import re
import sys

RESULTS = []


def check(name: str, fn, critical: bool = True):
    try:
        detail = fn()
        RESULTS.append((name, True, detail or ""))
        print(f"[PASS] {name}" + (f" -- {detail}" if detail else ""))
        return True
    except Exception as exc:
        RESULTS.append((name, not critical, f"{exc}"))
        tag = "FAIL" if critical else "WARN"
        print(f"[{tag}] {name} -- {exc}")
        return False


def main() -> int:
    try:
        import norgatedata
    except ImportError as exc:
        print(f"[FAIL] import norgatedata -- {exc}")
        print("Run: python -m pip install norgatedata")
        return 1
    print(f"[PASS] import norgatedata -- package v{getattr(norgatedata, 'version', lambda: '?')()}"
          if callable(getattr(norgatedata, "version", None))
          else "[PASS] import norgatedata")

    def ndu_status():
        ok = bool(norgatedata.status())
        if not ok:
            raise RuntimeError(
                "NDU not reachable. Start the Norgate Data Updater application, "
                "let it sync, then re-run this script."
            )
        return "NDU running"

    if not check("NDU status", ndu_status):
        print("\nNDU is the local database daemon; nothing else can pass without it.")
        return 1

    def databases():
        dbs = list(norgatedata.databases())
        need = [d for d in dbs if "Equities" in d]
        detail = f"{len(dbs)} databases: {', '.join(sorted(dbs))}"
        if not any("Delisted" in d for d in dbs):
            raise RuntimeError(
                f"'US Equities Delisted' not present ({detail}). The trial/subscription "
                "must be Platinum-level for delisted securities."
            )
        return detail

    check("databases include delisted equities", databases)

    watchlist_name = "S&P 500 Current & Past"

    def watchlists():
        names = list(norgatedata.watchlists())
        sp = [n for n in names if "S&P 500" in n]
        if watchlist_name not in names:
            raise RuntimeError(
                f"Watchlist {watchlist_name!r} not found. S&P-related watchlists "
                f"available: {sp}. In NDU, enable it under Watchlists."
            )
        return f"{len(names)} watchlists; S&P-related: {sp}"

    check("watchlist discovery", watchlists)

    def universe():
        syms = list(norgatedata.watchlist_symbols(watchlist_name))
        delisted = [s for s in syms if re.search(r"-\d{6}$", s)]
        if len(syms) < 500:
            raise RuntimeError(f"Only {len(syms)} symbols in {watchlist_name!r} — expected 500+.")
        return (f"{len(syms)} symbols, of which {len(delisted)} carry a delisted "
                f"suffix (e.g. {delisted[:3] if delisted else 'none'})")

    check("universe symbols (current & past)", universe)

    def prices():
        df = norgatedata.price_timeseries(
            "AAPL",
            stock_price_adjustment_setting=norgatedata.StockPriceAdjustmentType.TOTALRETURN,
            padding_setting=norgatedata.PaddingType.NONE,
            timeseriesformat="pandas-dataframe",
        )
        if df is None or len(df) == 0:
            raise RuntimeError("Empty AAPL price series.")
        return (f"AAPL {len(df)} bars, {df.index[0].date()} -> {df.index[-1].date()} "
                f"(trial exposes ~2 years; full history requires Platinum subscription)")

    check("price history (AAPL, total-return adjusted)", prices)

    def membership():
        df = norgatedata.index_constituent_timeseries(
            "MSFT", "S&P 500", timeseriesformat="pandas-dataframe",
        )
        if df is None or len(df) == 0:
            raise RuntimeError("Empty membership series for MSFT vs 'S&P 500'.")
        col = df.columns[0]
        days = int(df[col].sum())
        if days == 0:
            raise RuntimeError("MSFT shows zero S&P 500 membership days — index name mismatch?")
        return f"column {col!r}, {days} member-days in window {df.index[0].date()} -> {df.index[-1].date()}"

    check("point-in-time index membership (MSFT vs S&P 500)", membership)

    def delisted_prices():
        syms = list(norgatedata.watchlist_symbols(watchlist_name))
        cands = [s for s in syms if re.search(r"-\d{6}$", s)]
        if not cands:
            raise RuntimeError("No delisted-suffixed symbols in the watchlist.")
        sym = cands[0]
        df = norgatedata.price_timeseries(
            sym,
            stock_price_adjustment_setting=norgatedata.StockPriceAdjustmentType.TOTALRETURN,
            padding_setting=norgatedata.PaddingType.NONE,
            timeseriesformat="pandas-dataframe",
        )
        last = norgatedata.last_quoted_date(sym)
        n = 0 if df is None else len(df)
        return f"{sym}: {n} bars in window, last quoted {last}"

    check("delisted security readable", delisted_prices, critical=False)

    failed = [r for r in RESULTS if not r[1]]
    print("\n" + ("ALL CHECKS PASSED — ready for scripts/backtest_baseline.py --provider norgate"
                  if not failed else f"{len(failed)} CRITICAL CHECK(S) FAILED — fix before backtesting"))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

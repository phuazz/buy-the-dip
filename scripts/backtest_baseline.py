"""Phase 0/1 — published-baseline replication backtest.

Rules (verbatim from the CrackingMarkets "Buy the dip" article, 2024-09-19):
    Universe : S&P 500 members, point-in-time (historical constituents)
    Trend    : Close > 200-day simple moving average
    Dip      : RSI(5) < 20                [smoothing assumed Wilder]
    Entry    : at the close of the signal bar
    Exit     : at the close 5 trading bars later
    Sizing   : $1,000 notional per trade, overlapping trades allowed
    Costs    : none (the published baseline excludes fees)

Published anchors to validate against (2000 -> 2024-09):
    ~25,000 trades, 56.81% winners, average win > average loss.

Silent-failure defences implemented here:
    1. Point-in-time membership gate on the signal day (no survivorship);
       positions may persist past index removal, matching the source's
       "stocks that are no longer part of the S&P 500" language.
    2. Exit alignment is positional on each symbol's own bar index — month
       boundaries, year boundaries, holidays, halts and delistings cannot
       shift exits. A series ending before bar t+5 exits on its final bar
       (exit_reason='delisted_or_series_end') so delisting losses are
       realised, not dropped.
    3. Signals inside the indicator warm-up window are discarded
       (min_history); trend and dip are computed on the same adjusted close
       series that is traded.

Note on the entry convention: signal and fill share the same close, exactly
as published. This is optimistic for live execution (the signal is only
knowable at that close); Phase 2 tests next-open entry sensitivity.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import indicators  # noqa: E402


@dataclass
class BaselineParams:
    rsi_period: int = 5
    rsi_threshold: float = 20.0
    trend_sma: int = 200
    hold_bars: int = 5
    per_trade_usd: float = 1000.0
    min_history: int = 210          # bars before the first actionable signal
    commission_bps: float = 0.0     # one-way; applied at entry and exit
    # "no_reentry": one open position per symbol; a new signal is actionable
    # only after the previous trade's exit bar. This is the convention that
    # reproduces the published anchor trade count — the source's "overlapping
    # trades allowed" is portfolio-level concurrency, not same-symbol
    # pyramiding. "per_signal" stacks an entry on every signal bar, which
    # roughly doubles the trade count in RSI dip clusters.
    entry_overlap: str = "no_reentry"   # | "per_signal"


def compute_signals(prices: pd.DataFrame, membership: pd.Series, p: BaselineParams) -> pd.Series:
    """Boolean signal series on the symbol's own bar index."""
    close = prices["Close"]
    trend_ok = close > indicators.sma(close, p.trend_sma)
    dip = indicators.wilder_rsi(close, p.rsi_period) < p.rsi_threshold
    member = membership.reindex(close.index).fillna(0).astype(bool)
    warm = pd.Series(np.arange(len(close)) >= p.min_history, index=close.index)
    return trend_ok & dip & member & warm


def symbol_trades(symbol: str, prices: pd.DataFrame, membership: pd.Series,
                  p: BaselineParams) -> list:
    """All baseline trades for one symbol. Positional exits (see module doc)."""
    if len(prices) == 0:
        return []
    if p.entry_overlap not in ("no_reentry", "per_signal"):
        raise ValueError(f"Unknown entry_overlap {p.entry_overlap!r}")
    close = prices["Close"]
    sig = compute_signals(prices, membership, p)
    n = len(close)
    trades = []
    cost = 2.0 * p.commission_bps / 1e4
    last_exit_i = -1
    for i in np.flatnonzero(sig.to_numpy()):
        if p.entry_overlap == "no_reentry" and i <= last_exit_i:
            continue  # position still open (or exiting this close): no re-entry
        j = min(i + p.hold_bars, n - 1)
        if j <= i:
            continue  # signal on the final bar of the series: nothing tradable
        entry = float(close.iloc[i])
        exit_ = float(close.iloc[j])
        if not (entry > 0.0):
            continue
        last_exit_i = j
        ret = exit_ / entry - 1.0 - cost
        trades.append({
            "symbol": symbol,
            "entry_date": close.index[i].date().isoformat(),
            "exit_date": close.index[j].date().isoformat(),
            "entry_close": entry,
            "exit_close": exit_,
            "bars_held": int(j - i),
            "ret": ret,
            "pnl_usd": p.per_trade_usd * ret,
            "exit_reason": "time" if j == i + p.hold_bars else "delisted_or_series_end",
        })
    return trades


def summarise(trades: pd.DataFrame, eval_start: str, eval_end: str | None = None) -> dict:
    """Summary statistics over trades entered on/after eval_start (and, when
    eval_end is given, on/before it — the published anchor window ends
    2024-09, so comparing against an unbounded window overstates the count)."""
    if len(trades) == 0:
        return {"n_trades": 0, "note": "no trades"}
    t = trades[trades["entry_date"] >= eval_start]
    if eval_end is not None:
        t = t[t["entry_date"] <= eval_end]
    if len(t) == 0:
        return {"n_trades": 0, "note": f"no trades on/after {eval_start}"}
    wins = t[t["ret"] > 0]
    losses = t[t["ret"] <= 0]
    gross_win = wins["ret"].sum()
    gross_loss = -losses["ret"].sum()
    return {
        "eval_start": eval_start,
        "eval_end": eval_end,
        "entries_by_year": t["entry_date"].str.slice(0, 4).value_counts().sort_index().to_dict(),
        "n_trades": int(len(t)),
        "first_entry": t["entry_date"].min(),
        "last_entry": t["entry_date"].max(),
        "win_rate_pct": round(100.0 * len(wins) / len(t), 2),
        "avg_win_pct": round(100.0 * wins["ret"].mean(), 3) if len(wins) else None,
        "avg_loss_pct": round(100.0 * losses["ret"].mean(), 3) if len(losses) else None,
        "expectancy_pct": round(100.0 * t["ret"].mean(), 3),
        "median_ret_pct": round(100.0 * t["ret"].median(), 3),
        "profit_factor": round(gross_win / gross_loss, 3) if gross_loss > 0 else None,
        "total_pnl_usd": round(t["pnl_usd"].sum(), 2),
        "delisted_or_series_end_exits": int((t["exit_reason"] != "time").sum()),
        "symbols_traded": int(t["symbol"].nunique()),
    }


ANCHORS = {"n_trades": "~25,000 (2000 -> 2024-09)", "win_rate_pct": "56.81"}


def run(provider, p: BaselineParams, eval_start: str, cache_dir: Path | None,
        max_symbols: int | None = None, refresh_cache: bool = False,
        symbols: list | None = None, eval_end: str | None = None) -> tuple:
    if symbols is None:
        symbols = provider.universe_symbols()
    if max_symbols:
        symbols = symbols[:max_symbols]
    print(f"Provider : {provider.describe()}")
    print(f"Universe : {len(symbols)} symbols")
    if not provider.results_grade:
        print("!! PLUMBING-ONLY PROVIDER — output is survivorship-biased, not a result !!")

    # Post-subscription depth gate (same contract as the portfolio engines):
    # refuse to sweep a cache that is shallower than what the provider now
    # serves. The probe pays one live index fetch instead of discovering the
    # mismatch after a full sweep.
    if cache_dir is not None and not refresh_cache and provider.results_grade:
        cached_start = _cached_min_start(cache_dir, symbols)
        if cached_start is not None:
            probe = provider.price_history(DEPTH_PROBE_SYMBOL)
            if len(probe) == 0:
                raise RuntimeError(
                    f"Depth probe {DEPTH_PROBE_SYMBOL!r} returned no data; cannot "
                    "verify cache depth. Check NDU before running against a cache."
                )
            from scripts.providers import assert_cache_depth
            assert_cache_depth(probe.index[0], cached_start)

    all_trades = []
    skipped, failed = 0, []
    for k, sym in enumerate(symbols, 1):
        try:
            prices, membership = _load_symbol(provider, sym, cache_dir, refresh_cache)
            if len(prices) == 0:
                skipped += 1
                continue
            all_trades.extend(symbol_trades(sym, prices, membership, p))
        except Exception as exc:  # keep the sweep alive; report at the end
            failed.append((sym, str(exc)[:120]))
        if k % 50 == 0:
            print(f"  ... {k}/{len(symbols)} symbols, {len(all_trades)} trades so far")

    trades = pd.DataFrame(all_trades)
    if len(trades):
        trades = trades.sort_values(["entry_date", "symbol"]).reset_index(drop=True)
    summary = summarise(trades, eval_start, eval_end)
    summary["params"] = asdict(p)
    summary["provider"] = provider.describe()
    summary["symbols_total"] = len(symbols)
    summary["symbols_no_data_in_window"] = skipped
    summary["symbols_failed"] = len(failed)
    if failed:
        summary["failed_examples"] = failed[:10]
    return trades, summary


DEPTH_PROBE_SYMBOL = "$SPX"


def _cache_paths(cache_dir: Path, sym: str) -> tuple:
    safe = sym.replace("/", "_").replace("\\", "_")
    return cache_dir / f"{safe}.prices.csv", cache_dir / f"{safe}.member.csv"


def _unadj_cache_path(cache_dir: Path, sym: str) -> Path:
    safe = sym.replace("/", "_").replace("\\", "_")
    return cache_dir / f"{safe}.prices_unadj.csv"


def _cached_min_start(cache_dir: Path, symbols: list) -> pd.Timestamp | None:
    """Earliest first-bar date across the existing cached price files, reading
    only each file's first data row (a full parse of every CSV would cost more
    than the sweep it protects)."""
    starts = []
    for sym in symbols:
        pp, _ = _cache_paths(cache_dir, sym)
        if not pp.exists():
            continue
        with open(pp, "r", encoding="utf-8") as fh:
            fh.readline()
            line = fh.readline().strip()
        if not line:
            continue
        try:
            starts.append(pd.Timestamp(line.split(",", 1)[0]))
        except ValueError:
            continue
    return min(starts) if starts else None


def _load_symbol(provider, sym: str, cache_dir: Path | None, refresh: bool) -> tuple:
    if cache_dir is not None:
        pp, mp = _cache_paths(cache_dir, sym)
        if not refresh and pp.exists() and mp.exists():
            prices = pd.read_csv(pp, index_col=0, parse_dates=True)
            member = pd.read_csv(mp, index_col=0, parse_dates=True).iloc[:, 0]
            return prices, member
    prices = provider.price_history(sym)
    member = provider.index_membership(sym)
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        pp, mp = _cache_paths(cache_dir, sym)
        prices.to_csv(pp)
        member.rename("member").to_frame().to_csv(mp)
    return prices, member


def _load_unadjusted(provider, sym: str, cache_dir: Path | None, refresh: bool) -> pd.DataFrame:
    """Unadjusted (actual traded) series for absolute price / dollar-volume
    screens; cached beside the adjusted files."""
    if cache_dir is not None:
        up = _unadj_cache_path(cache_dir, sym)
        if not refresh and up.exists():
            return pd.read_csv(up, index_col=0, parse_dates=True)
    unadj = provider.price_history_unadjusted(sym)
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        unadj.to_csv(_unadj_cache_path(cache_dir, sym))
    return unadj


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--provider", choices=["norgate", "yfinance"], default="norgate")
    ap.add_argument("--watchlist", default="S&P 500 Current & Past")
    ap.add_argument("--index-name", default="S&P 500")
    ap.add_argument("--adjustment", default="TOTALRETURN",
                    help="Norgate StockPriceAdjustmentType name (e.g. TOTALRETURN, CAPITAL)")
    ap.add_argument("--fetch-start", default="1998-01-01",
                    help="History fetch start (indicator warm-up runs from here)")
    ap.add_argument("--eval-start", default="2000-01-01",
                    help="Trades entered before this date are excluded from the summary")
    ap.add_argument("--eval-end", default=None,
                    help="Trades entered after this date are excluded from the summary "
                         "(the published anchor window ends 2024-09)")
    ap.add_argument("--rsi-threshold", type=float, default=20.0)
    ap.add_argument("--hold-bars", type=int, default=5)
    ap.add_argument("--commission-bps", type=float, default=0.0)
    ap.add_argument("--entry-overlap", choices=["no_reentry", "per_signal"],
                    default="no_reentry",
                    help="no_reentry reproduces the published anchor; per_signal "
                         "stacks a trade on every signal bar")
    ap.add_argument("--symbols-file", default=None,
                    help="Path to a newline-delimited symbol list overriding the "
                         "provider universe (see scripts/build_universe_fallback.py)")
    ap.add_argument("--max-symbols", type=int, default=None, help="Debug: truncate universe")
    ap.add_argument("--cache-dir", default="data/cache/norgate_totalreturn")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--refresh-cache", action="store_true")
    ap.add_argument("--out-prefix", default="baseline",
                    help="Output file prefix under data/ (keeps committed artefacts intact)")
    args = ap.parse_args(argv)

    root = Path(__file__).resolve().parents[1]
    from scripts.providers import get_provider  # noqa: E402

    if args.provider == "norgate":
        provider = get_provider(
            "norgate", watchlist=args.watchlist, index_name=args.index_name,
            adjustment=args.adjustment, start_date=args.fetch_start,
        )
    else:
        provider = get_provider("yfinance", start_date=args.fetch_start)

    p = BaselineParams(
        rsi_threshold=args.rsi_threshold,
        hold_bars=args.hold_bars,
        commission_bps=args.commission_bps,
        entry_overlap=args.entry_overlap,
    )
    if args.provider == "yfinance" and args.cache_dir == "data/cache/norgate_totalreturn":
        # Plumbing runs must never write survivorship-biased series into the
        # results-grade cache.
        args.cache_dir = "data/cache/yfinance"
        print("yfinance provider: cache redirected to data/cache/yfinance")
    cache_dir = None if args.no_cache else (root / args.cache_dir)
    symbols = None
    if args.symbols_file:
        symbols = [s.strip() for s in Path(args.symbols_file).read_text(encoding="utf-8").splitlines()
                   if s.strip()]
        print(f"Universe override: {len(symbols)} symbols from {args.symbols_file}")
    trades, summary = run(provider, p, args.eval_start, cache_dir,
                          max_symbols=args.max_symbols,
                          refresh_cache=args.refresh_cache,
                          symbols=symbols, eval_end=args.eval_end)

    out_dir = root / "data"
    out_dir.mkdir(exist_ok=True)
    trades_path = out_dir / f"{args.out_prefix}_trades.csv"
    summary_path = out_dir / f"{args.out_prefix}_summary.json"
    trades.to_csv(trades_path, index=False)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("\n=== Baseline summary ===")
    print(json.dumps(summary, indent=2))
    print("\n=== Published anchors (full window 2000 -> 2024-09) ===")
    for key, val in ANCHORS.items():
        print(f"  {key}: {val}")
    print("\nAnchor comparison is only meaningful on the FULL history (Platinum).")
    print(f"Wrote {trades_path} and {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

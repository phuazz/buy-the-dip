"""Phase 2 — weekly dip-buying portfolio engine.

Rules per PHASE2_DESIGN.md (v1 primary configuration). Decision cadence is
weekly (W-FRI labels); risk is monitored DAILY: stops and targets are checked
against each day's open/low/high with gap-aware fills and a stop-before-target
convention. Delistings mid-hold exit at the final available print.

Design discipline: on the 2-year trial window this engine produces MECHANICS
VALIDATION output only (the summary is labelled accordingly whenever the
window is shorter than 10 years). No rule choice may cite trial-window
performance — see PHASE2_DESIGN.md.

Conventions:
- Entry "close": at the symbol's weekly close of the decision label; such a
  position is first risk-checked the following trading day.
- Entry "next_open": queued at decision, filled at the symbol's next daily
  open, and risk-checked from that same bar (conservative).
- Daily equity marks use each symbol's daily close; a halted symbol carries
  its last mark. New entries appear in the equity record from the next day.
- All date alignment is positional on trading calendars; no calendar-day
  arithmetic. (Python/pandas datetime months are 1-indexed.)
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
class WeeklyParams:
    trend_weeks: int = 40
    rsi_weeks: int = 3
    rsi_threshold: float = 25.0
    rank_vol_weeks: int = 26
    max_positions: int = 10
    position_frac: float = 0.10
    stop_pct: float = 0.10
    target_pct: float = 0.15
    cost_bps_side: float = 7.0
    min_price: float = 5.0
    min_dollar_vol: float = 5e6
    dollar_vol_days: int = 63
    regime_sma_weeks: int = 40
    entry_at: str = "close"              # "close" | "next_open"
    time_stop_weeks: int | None = None   # registered alternate; None in v1
    initial_capital: float = 100_000.0
    min_weekly_history: int = 45
    min_cash_frac: float = 0.02
    # -- registered alternates and full-history controls (v1 defaults) --
    dip_trigger: str = "rsi"             # "rsi" | "lower_closes" | "below_high"
    below_high_weeks: int = 8
    below_high_min: float = -0.15        # band for "close 5-15% below the 8-week high"
    below_high_max: float = -0.05
    ranking: str = "low_vol"             # "low_vol" | "high_natr"
    natr_rank_weeks: int = 5
    regime_gate: str = "sma"             # "sma" | "breadth" (#SPX%MA200 > 50)
    regime_off_exit: bool = False        # registered alternate: force-exit when gate OFF
    monitor: str = "daily"               # "daily" | "weekly_close" (registered sensitivity)
    price_filter_basis: str = "unadjusted"  # "$5"/dollar-volume screens read actual traded prices
    sim_start: str | None = None         # no entries and no equity records before this date


WEEKLY_AGG = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}


def build_weekly(daily: pd.DataFrame) -> pd.DataFrame:
    """W-FRI weekly OHLCV from a daily frame (labels are Fridays; the last
    trading day of a holiday-shortened week rolls up to the same label)."""
    w = daily.resample("W-FRI").agg(WEEKLY_AGG)
    return w.dropna(subset=["Close"])


def _price_filter_series(daily: pd.DataFrame, p, unadj: pd.DataFrame | None) -> tuple:
    """(close, volume) the absolute price / dollar-volume screens must read.
    Back-adjusted series shrink early-history prices for split-heavy
    compounders (AAPL's total-return close in 2000 is around $0.11), so the
    registered "$5" rule means the actual traded price."""
    if p.price_filter_basis == "adjusted":
        return daily["Close"], daily["Volume"]
    if p.price_filter_basis != "unadjusted":
        raise ValueError(f"Unknown price_filter_basis {p.price_filter_basis!r}")
    if unadj is None:
        if p.min_price > 0 or p.min_dollar_vol > 0:
            raise ValueError(
                "price_filter_basis='unadjusted' with an active price or "
                "dollar-volume screen requires the unadjusted series"
            )
        return daily["Close"], daily["Volume"]
    return unadj["Close"].reindex(daily.index), unadj["Volume"].reindex(daily.index)


def precompute_symbol(daily: pd.DataFrame, membership_daily: pd.Series,
                      p: WeeklyParams, unadj: pd.DataFrame | None = None) -> pd.DataFrame:
    """Weekly frame + indicator/eligibility columns for one symbol."""
    w = build_weekly(daily)
    close = w["Close"]
    w["trend"] = close > indicators.sma(close, p.trend_weeks)
    w["rsi"] = indicators.wilder_rsi(close, p.rsi_weeks)
    w["vol"] = np.log(close).diff().rolling(p.rank_vol_weeks, min_periods=p.rank_vol_weeks).std()
    w["natr_rank"] = indicators.natr(w["High"], w["Low"], close, p.natr_rank_weeks)
    member = membership_daily.reindex(daily.index).ffill().fillna(0)
    w["member"] = member.resample("W-FRI").last().reindex(w.index).fillna(0).astype(bool)
    ref_close, ref_volume = _price_filter_series(daily, p, unadj)
    price_ref = ref_close.resample("W-FRI").last().reindex(w.index)
    dollar_vol = (ref_close * ref_volume).rolling(
        p.dollar_vol_days, min_periods=min(p.dollar_vol_days, 21)).median()
    w["dollar_vol"] = dollar_vol.resample("W-FRI").last().reindex(w.index)
    w["warm"] = np.arange(len(w)) >= p.min_weekly_history
    if p.dip_trigger == "rsi":
        dip = w["rsi"] < p.rsi_threshold
    elif p.dip_trigger == "lower_closes":
        down = close.diff() < 0
        dip = down & down.shift(1, fill_value=False)
    elif p.dip_trigger == "below_high":
        # Convention: 8-week high of weekly CLOSES, window ending at the
        # decision week (a new-high week can therefore never be a dip).
        high = close.rolling(p.below_high_weeks, min_periods=p.below_high_weeks).max()
        ratio = close / high - 1.0
        dip = (ratio >= p.below_high_min) & (ratio <= p.below_high_max)
    else:
        raise ValueError(f"Unknown dip_trigger {p.dip_trigger!r}")
    w["candidate"] = (
        w["trend"]
        & dip
        & w["member"]
        & w["warm"]
        & (price_ref > p.min_price)
        & (w["dollar_vol"].fillna(0) > p.min_dollar_vol)
    )
    return w


@dataclass
class _Position:
    symbol: str
    shares: float
    entry_px: float
    entry_date: pd.Timestamp
    entry_label_idx: int
    stop: float
    target: float
    cost_basis: float
    bars_held: int = 0


def _close_position(pos: _Position, exit_px: float, exit_date: pd.Timestamp,
                    reason: str, cost_side: float, trades: list) -> float:
    proceeds = pos.shares * exit_px * (1.0 - cost_side)
    ret = proceeds / pos.cost_basis - 1.0
    trades.append({
        "symbol": pos.symbol,
        "entry_date": pos.entry_date.date().isoformat(),
        "exit_date": exit_date.date().isoformat(),
        "entry_px": round(pos.entry_px, 6),
        "exit_px": round(float(exit_px), 6),
        "shares": round(pos.shares, 6),
        "bars_held": pos.bars_held,
        "ret_net": ret,
        "pnl_usd": proceeds - pos.cost_basis,
        "exit_reason": reason,
    })
    return proceeds


def simulate(panels: dict, memberships: dict, index_daily: pd.DataFrame,
             p: WeeklyParams, unadj_panels: dict | None = None,
             breadth_daily: pd.Series | None = None,
             cash_yield_daily: pd.Series | None = None) -> tuple:
    """Run the weekly portfolio simulation.

    panels           : {symbol: daily OHLCV DataFrame}
    memberships      : {symbol: daily 0/1 membership Series}
    index_daily      : daily OHLCV for the regime index ($SPX)
    unadj_panels     : {symbol: unadjusted OHLCV} for absolute price screens
    breadth_daily    : precomputed breadth series (regime_gate="breadth")
    cash_yield_daily : daily fractional cash accrual (registered alternate)

    Returns (trades DataFrame, equity DataFrame, summary dict).
    """
    if p.ranking not in ("low_vol", "high_natr"):
        raise ValueError(f"Unknown ranking {p.ranking!r}")
    if p.monitor not in ("daily", "weekly_close"):
        raise ValueError(f"Unknown monitor {p.monitor!r}")
    cost_side = p.cost_bps_side / 1e4
    calendar = index_daily.index
    index_weekly = build_weekly(index_daily)
    if p.regime_gate == "breadth":
        if breadth_daily is None:
            raise ValueError("regime_gate='breadth' requires breadth_daily")
        # Percent-above-MA breadth: gate ON while more than half the index
        # closes above its own 200-day MA. Weeks before the series starts
        # read NaN -> gate OFF (conservative).
        breadth_weekly = breadth_daily.resample("W-FRI").last()
        regime = (breadth_weekly > 50.0).reindex(index_weekly.index, fill_value=False)
    elif p.regime_gate == "sma":
        regime = index_weekly["Close"] > indicators.sma(index_weekly["Close"], p.regime_sma_weeks)
    else:
        raise ValueError(f"Unknown regime_gate {p.regime_gate!r}")
    labels = list(index_weekly.index)
    sim_start = pd.Timestamp(p.sim_start) if p.sim_start else None

    weekly = {}
    daily_row = {}
    last_bar = {}
    for sym, df in panels.items():
        if len(df) == 0:
            continue
        unadj = None if unadj_panels is None else unadj_panels.get(sym)
        weekly[sym] = precompute_symbol(df, memberships[sym], p, unadj)
        daily_row[sym] = {ts: i for i, ts in enumerate(df.index)}
        last_bar[sym] = df.index[-1]

    positions: dict = {}
    pending: list = []
    cash = p.initial_capital
    marks: dict = {}
    trades: list = []
    equity_rows: list = []
    pending_dropped = 0

    prev_label = None
    for label_idx, label in enumerate(labels):
        lo = calendar.searchsorted(prev_label, side="right") if prev_label is not None else 0
        hi = calendar.searchsorted(label, side="right")
        week_days = calendar[lo:hi]
        prev_label = label
        last_day = None

        for d in week_days:
            last_day = d
            if cash_yield_daily is not None and (sim_start is None or d >= sim_start):
                cash *= 1.0 + float(cash_yield_daily.get(d, 0.0))
            # 1. Fill queued next-open entries whose symbol trades today.
            if pending:
                still = []
                for order in pending:
                    sym = order["symbol"]
                    df = panels[sym]
                    if d > last_bar[sym]:
                        pending_dropped += 1
                        continue
                    i = daily_row[sym].get(d)
                    if i is None:
                        still.append(order)
                        continue
                    open_px = float(df["Open"].iloc[i])
                    if not (open_px > 0) or cash <= 0:
                        pending_dropped += 1
                        continue
                    size = min(order["dollar_size"], cash / (1.0 + cost_side))
                    shares = size / open_px
                    basis = shares * open_px * (1.0 + cost_side)
                    cash -= basis
                    positions[sym] = _Position(
                        symbol=sym, shares=shares, entry_px=open_px, entry_date=d,
                        entry_label_idx=order["label_idx"],
                        stop=open_px * (1.0 - p.stop_pct),
                        target=open_px * (1.0 + p.target_pct),
                        cost_basis=basis,
                    )
                    marks[sym] = open_px
                pending = still

            # 2. Daily risk pass over open positions (stop before target).
            for sym in list(positions.keys()):
                pos = positions[sym]
                df = panels[sym]
                if d > last_bar[sym]:
                    exit_px = float(df["Close"].iloc[-1])
                    cash += _close_position(pos, exit_px, last_bar[sym], "delist",
                                            cost_side, trades)
                    del positions[sym]
                    marks.pop(sym, None)
                    continue
                i = daily_row[sym].get(d)
                if i is None:
                    continue  # halted today: carry the last mark
                if pos.entry_date == d and p.entry_at == "close":
                    continue  # close-entry positions are risk-checked from the next bar
                row = df.iloc[i]
                o, h, l, c = (float(row["Open"]), float(row["High"]),
                              float(row["Low"]), float(row["Close"]))
                pos.bars_held += 1
                if p.monitor == "weekly_close":
                    # Registered sensitivity: breaches are only observable at
                    # the decision close; fills happen at that close.
                    if d != week_days[-1]:
                        marks[sym] = c
                    elif c <= pos.stop:
                        cash += _close_position(pos, c, d, "stop", cost_side, trades)
                        del positions[sym]; marks.pop(sym, None)
                    elif c >= pos.target:
                        cash += _close_position(pos, c, d, "target", cost_side, trades)
                        del positions[sym]; marks.pop(sym, None)
                    else:
                        marks[sym] = c
                elif o <= pos.stop:
                    cash += _close_position(pos, o, d, "stop_gap", cost_side, trades)
                    del positions[sym]; marks.pop(sym, None)
                elif l <= pos.stop:
                    cash += _close_position(pos, pos.stop, d, "stop", cost_side, trades)
                    del positions[sym]; marks.pop(sym, None)
                elif h >= pos.target:
                    cash += _close_position(pos, pos.target, d, "target", cost_side, trades)
                    del positions[sym]; marks.pop(sym, None)
                else:
                    marks[sym] = c

            if sim_start is None or d >= sim_start:
                invested = sum(positions[s].shares * marks.get(s, positions[s].entry_px)
                               for s in positions)
                equity_rows.append({"date": d, "equity": cash + invested,
                                    "invested_frac": invested / (cash + invested)})

        if last_day is None:
            continue  # no trading days rolled up to this label

        # 3. Registered alternate: time stop, evaluated at decision cadence.
        if p.time_stop_weeks is not None:
            for sym in list(positions.keys()):
                pos = positions[sym]
                if label_idx - pos.entry_label_idx >= p.time_stop_weeks:
                    w = weekly.get(sym)
                    px = float(w["Close"].get(label, marks.get(sym, pos.entry_px))) \
                        if w is not None else marks.get(sym, pos.entry_px)
                    cash += _close_position(pos, px, last_day, "time", cost_side, trades)
                    del positions[sym]; marks.pop(sym, None)

        # 4. Weekly decision at this label's close: new entries if regime ON.
        if sim_start is not None and label < sim_start:
            continue
        regime_on = bool(regime.get(label, False))
        if p.regime_off_exit and not regime_on:
            for sym in list(positions.keys()):
                pos = positions[sym]
                w = weekly.get(sym)
                px = float(w["Close"].get(label, marks.get(sym, pos.entry_px))) \
                    if w is not None else marks.get(sym, pos.entry_px)
                cash += _close_position(pos, px, last_day, "regime_off", cost_side, trades)
                del positions[sym]; marks.pop(sym, None)
        if not regime_on:
            continue
        free = p.max_positions - len(positions) - len(pending)
        if free <= 0:
            continue
        candidates = []
        for sym, w in weekly.items():
            if sym in positions or any(o["symbol"] == sym for o in pending):
                continue
            if label not in w.index:
                continue
            row = w.loc[label]
            metric = float(row["vol"]) if p.ranking == "low_vol" else float(row["natr_rank"])
            if bool(row["candidate"]) and np.isfinite(metric):
                key = metric if p.ranking == "low_vol" else -metric
                candidates.append((key, sym, float(row["Close"])))
        candidates.sort()  # low_vol: ascending volatility; high_natr: descending NATR
        equity_now = cash + sum(positions[s].shares * marks.get(s, positions[s].entry_px)
                                for s in positions)
        for vol, sym, close_px in candidates[:free]:
            if cash < p.min_cash_frac * equity_now:
                break
            size = p.position_frac * equity_now
            if p.entry_at == "next_open":
                pending.append({"symbol": sym, "dollar_size": size, "label_idx": label_idx})
                continue
            size = min(size, cash / (1.0 + cost_side))
            shares = size / close_px
            basis = shares * close_px * (1.0 + cost_side)
            cash -= basis
            positions[sym] = _Position(
                symbol=sym, shares=shares, entry_px=close_px, entry_date=last_day,
                entry_label_idx=label_idx,
                stop=close_px * (1.0 - p.stop_pct),
                target=close_px * (1.0 + p.target_pct),
                cost_basis=basis,
            )
            marks[sym] = close_px

    trades_df = pd.DataFrame(trades)
    if len(trades_df):
        trades_df = trades_df.sort_values(["entry_date", "symbol"]).reset_index(drop=True)
    equity_df = pd.DataFrame(equity_rows).set_index("date")
    summary = _summarise(trades_df, equity_df, positions, marks, index_daily, p)
    summary["pending_dropped"] = pending_dropped
    return trades_df, equity_df, summary


def _summarise(trades: pd.DataFrame, equity: pd.DataFrame, open_positions: dict,
               marks: dict, index_daily: pd.DataFrame, p: WeeklyParams) -> dict:
    out: dict = {"params": asdict(p)}
    if len(equity) == 0:
        out["note"] = "no equity history"
        return out
    eq = equity["equity"]
    n_days = len(eq)
    years = n_days / 252.0
    ret_daily = eq.pct_change().dropna()
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1.0 / years) - 1.0 if years > 0 else None
    sharpe = (float(ret_daily.mean() / ret_daily.std() * np.sqrt(252.0))
              if len(ret_daily) > 1 and ret_daily.std() > 0 else None)
    maxdd = float((eq / eq.cummax() - 1.0).min())
    out.update({
        "window": f"{equity.index[0].date()} -> {equity.index[-1].date()}",
        "window_years": round(years, 2),
        "mechanics_only": bool(years < 10.0),
        "final_equity": round(float(eq.iloc[-1]), 2),
        "ror_pct_pa": None if cagr is None else round(100.0 * cagr, 2),
        "sharpe": None if sharpe is None else round(sharpe, 3),
        "max_dd_pct": round(100.0 * maxdd, 2),
        "avg_usage_pct": round(100.0 * float(equity["invested_frac"].mean()), 2),
        "open_positions_at_end": sorted(open_positions.keys()),
    })
    if len(trades):
        wins = trades[trades["ret_net"] > 0]
        losses = trades[trades["ret_net"] <= 0]
        gross_win = wins["pnl_usd"].sum()
        gross_loss = -losses["pnl_usd"].sum()
        out.update({
            "n_trades": int(len(trades)),
            "trades_per_year": round(len(trades) / years, 1),
            "win_rate_pct": round(100.0 * len(wins) / len(trades), 2),
            "avg_win_pct": round(100.0 * wins["ret_net"].mean(), 2) if len(wins) else None,
            "avg_loss_pct": round(100.0 * losses["ret_net"].mean(), 2) if len(losses) else None,
            "expectancy_pct": round(100.0 * trades["ret_net"].mean(), 2),
            "profit_factor": round(gross_win / gross_loss, 3) if gross_loss > 0 else None,
            "win_len_bars": round(float(wins["bars_held"].mean()), 1) if len(wins) else None,
            "loss_len_bars": round(float(losses["bars_held"].mean()), 1) if len(losses) else None,
            "exit_reasons": trades["exit_reason"].value_counts().to_dict(),
        })
    else:
        out["n_trades"] = 0
    bench = index_daily["Close"]
    bench_years = len(bench) / 252.0
    out["benchmark_index_cagr_pct"] = round(
        float(100.0 * ((bench.iloc[-1] / bench.iloc[0]) ** (1.0 / bench_years) - 1.0)), 2)
    out["benchmark_index_maxdd_pct"] = round(
        100.0 * float((bench / bench.cummax() - 1.0).min()), 2)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--provider", choices=["norgate", "yfinance"], default="norgate")
    ap.add_argument("--symbols-file", default="data/cache/sp500_current_past_symbols.txt")
    ap.add_argument("--index-symbol", default="$SPX")
    ap.add_argument("--adjustment", default="TOTALRETURN")
    ap.add_argument("--fetch-start", default="1998-01-01")
    ap.add_argument("--entry-at", choices=["close", "next_open"], default="close")
    ap.add_argument("--cost-bps-side", type=float, default=7.0)
    ap.add_argument("--time-stop-weeks", type=int, default=None)
    ap.add_argument("--rsi-threshold", type=float, default=25.0,
                    help="Registered plateau: 20 / 25 / 30")
    ap.add_argument("--target-frac", type=float, default=0.15,
                    help="Profit target as a fraction (registered plateau: 0.10 / 0.15 / 0.20)")
    ap.add_argument("--dip-trigger", choices=["rsi", "lower_closes", "below_high"],
                    default="rsi")
    ap.add_argument("--ranking", choices=["low_vol", "high_natr"], default="low_vol")
    ap.add_argument("--regime-gate", choices=["sma", "breadth"], default="sma")
    ap.add_argument("--breadth-symbol", default="#SPX%MA200",
                    help="Norgate precomputed breadth series for --regime-gate breadth")
    ap.add_argument("--regime-off-exit", action="store_true",
                    help="Registered alternate: force-exit open positions when the gate is OFF")
    ap.add_argument("--monitor", choices=["daily", "weekly_close"], default="daily",
                    help="Registered sensitivity: stop/target monitoring convention")
    ap.add_argument("--cash", choices=["none", "tbill"], default="none",
                    help="Registered alternate: idle cash accrues at the T-bill rate")
    ap.add_argument("--tbill-symbol", default="%IRX",
                    help="Annualised percent yield series for --cash tbill "
                         "(Norgate Economic database; 13-week T-bill rate, 1960->)")
    ap.add_argument("--price-basis", choices=["unadjusted", "adjusted"], default="unadjusted",
                    help="Series read by the $5 price and dollar-volume screens")
    ap.add_argument("--sim-start", default=None,
                    help="No entries or equity records before this date (design segment)")
    ap.add_argument("--sim-end", default=None,
                    help="Truncate all series at this date (design segment)")
    ap.add_argument("--max-symbols", type=int, default=None)
    ap.add_argument("--cache-dir", default="data/cache/norgate_totalreturn")
    ap.add_argument("--refresh-cache", action="store_true",
                    help="Refetch all symbols (required once after a subscription upgrade)")
    ap.add_argument("--out-prefix", default="weekly")
    args = ap.parse_args(argv)

    root = Path(__file__).resolve().parents[1]
    from scripts.providers import get_provider  # noqa: E402
    from scripts.backtest_baseline import _load_symbol, _load_unadjusted  # noqa: E402

    provider = get_provider("norgate", adjustment=args.adjustment,
                            start_date=args.fetch_start) if args.provider == "norgate" \
        else get_provider("yfinance", start_date=args.fetch_start)
    print(f"Provider : {provider.describe()}")

    symbols = [s.strip() for s in (root / args.symbols_file).read_text(encoding="utf-8").splitlines()
               if s.strip()]
    if args.max_symbols:
        symbols = symbols[:args.max_symbols]
    print(f"Universe : {len(symbols)} symbols from {args.symbols_file}")

    index_daily = provider.price_history(args.index_symbol)
    if len(index_daily) == 0:
        print(f"FAIL: no data for index symbol {args.index_symbol}")
        return 1
    print(f"Regime index {args.index_symbol}: {index_daily.index[0].date()} -> {index_daily.index[-1].date()}")

    cache_dir = root / args.cache_dir
    panels, memberships, unadj_panels = {}, {}, {}
    failed = []
    for k, sym in enumerate(symbols, 1):
        try:
            prices, member = _load_symbol(provider, sym, cache_dir, refresh=args.refresh_cache)
            if len(prices):
                if args.price_basis == "unadjusted":
                    unadj_panels[sym] = _load_unadjusted(provider, sym, cache_dir,
                                                         refresh=args.refresh_cache)
                panels[sym] = prices
                memberships[sym] = member
        except Exception as exc:
            failed.append((sym, str(exc)[:100]))
        if k % 100 == 0:
            print(f"  ... loaded {k}/{len(symbols)}")
    print(f"Loaded {len(panels)} symbols ({len(failed)} failed)")

    from scripts.providers import assert_cache_depth  # noqa: E402
    if panels:
        assert_cache_depth(index_daily.index[0],
                           min(df.index[0] for df in panels.values()))

    breadth_daily = None
    if args.regime_gate == "breadth":
        breadth = provider.price_history(args.breadth_symbol)
        if len(breadth) == 0:
            print(f"FAIL: no data for breadth symbol {args.breadth_symbol}")
            return 1
        print(f"Breadth {args.breadth_symbol}: "
              f"{breadth.index[0].date()} -> {breadth.index[-1].date()}")
        breadth_daily = breadth["Close"]

    cash_yield_daily = None
    if args.cash == "tbill":
        tbill = provider.price_history(args.tbill_symbol)
        if len(tbill) == 0:
            print(f"FAIL: no data for T-bill symbol {args.tbill_symbol}")
            return 1
        print(f"T-bill {args.tbill_symbol}: {tbill.index[0].date()} -> {tbill.index[-1].date()}")
        # Annualised percent yield -> per-trading-day accrual (ACT/252
        # approximation; sensitivity-grade, not a money-market model).
        cash_yield_daily = (tbill["Close"].reindex(index_daily.index).ffill()
                            / 100.0 / 252.0).fillna(0.0)

    if args.sim_end:
        end = pd.Timestamp(args.sim_end)
        index_daily = index_daily.loc[:end]
        panels = {s: df.loc[:end] for s, df in panels.items()}
        print(f"Design-segment truncation: all series cut at {end.date()}")

    p = WeeklyParams(entry_at=args.entry_at, cost_bps_side=args.cost_bps_side,
                     time_stop_weeks=args.time_stop_weeks,
                     rsi_threshold=args.rsi_threshold, target_pct=args.target_frac,
                     dip_trigger=args.dip_trigger, ranking=args.ranking,
                     regime_gate=args.regime_gate, regime_off_exit=args.regime_off_exit,
                     monitor=args.monitor, price_filter_basis=args.price_basis,
                     sim_start=args.sim_start)
    trades, equity, summary = simulate(panels, memberships, index_daily, p,
                                       unadj_panels=unadj_panels or None,
                                       breadth_daily=breadth_daily,
                                       cash_yield_daily=cash_yield_daily)
    summary["symbols_loaded"] = len(panels)
    summary["symbols_failed"] = len(failed)
    summary["sim_end"] = args.sim_end
    if failed:
        summary["failed_examples"] = failed[:10]

    out_dir = root / "data"
    out_dir.mkdir(exist_ok=True)
    trades.to_csv(out_dir / f"{args.out_prefix}_trades.csv", index=False)
    equity.to_csv(out_dir / f"{args.out_prefix}_equity.csv")
    (out_dir / f"{args.out_prefix}_summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8")

    if summary.get("mechanics_only"):
        print("\n*** MECHANICS-ONLY RUN: window < 10 years — no evidential weight, "
              "per PHASE2_DESIGN.md ***")
    print("\n=== Weekly variant summary ===")
    print(json.dumps(summary, indent=2, default=str))
    print(f"\nWrote data/{args.out_prefix}_trades.csv, data/{args.out_prefix}_equity.csv, "
          f"data/{args.out_prefix}_summary.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

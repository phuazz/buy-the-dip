"""Phase 3 — daily limit-order dip variant (Nasdaq 100).

Rules per PHASE3_DESIGN.md v1 (the source's published defaults). Signal at a
close: PIT member, close > SMA200, one-day drop >= 3%, NATR(5) > 3%. A limit
buy at signal close - 0.9 x ATR(5) lives for exactly the next trading day
(fill iff low <= limit; fill price = min(open, limit)). Exits, in precedence:
gap-open target, intraday trailing target (close[d-1] + 0.5 x ATR5[d-1], from
the day AFTER entry), close above previous day's high (permitted from entry
day), 10-trading-day time stop at the close, delisting at the final print.
No stop-loss, as published. Orders are placed only for free slots, preferring
the HIGHEST NATR at signal (opposite ranking direction to the Phase 2 weekly
variant).

Discipline: on the 2-year trial window this engine produces MECHANICS
VALIDATION output only (summary labelled whenever the window is < 10 years).
All alignment is positional on trading calendars; no calendar-day arithmetic.
(Python/pandas datetime months are 1-indexed.)
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
class DailyLimitParams:
    trend_sma: int = 200
    drop_pct: float = 3.0            # one-day close-to-close fall, in percent
    atr_period: int = 5
    natr_min_pct: float = 3.0        # 100 * ATR / close must EXCEED this at signal
    entry_atr_mult: float = 0.9
    target_atr_mult: float = 0.5
    max_positions: int = 10
    position_frac: float = 0.10
    time_stop_days: int = 10         # bars held after entry day
    cost_bps_side: float = 7.0
    min_price: float = 5.0
    min_history: int = 210
    initial_capital: float = 100_000.0
    min_cash_frac: float = 0.02
    # -- registered alternates / sensitivities and full-history controls --
    min_dollar_vol: float = 0.0      # registered alternate 6; off in v1
    dollar_vol_days: int = 63
    fill_model: str = "min_open_limit"   # | "strict_touch" | "at_limit"
    target_touch: str = "gte"            # | "gt" (require high strictly above target)
    price_filter_basis: str = "unadjusted"  # the "$5" screen reads actual traded prices
    sim_start: str | None = None     # no order placement or equity records before this date
    # Pre-registered interpretation convention 3 places orders only for free
    # slots ("free_slots"). "all_signals" places an order for every signal and
    # enforces capacity at fill time (highest NATR first) — the anchor-miss
    # investigation variant: slot rationing at placement forfeits fills in
    # exactly the volatility clusters the model monetises.
    order_placement: str = "free_slots"  # | "all_signals"


def precompute_symbol_daily(daily: pd.DataFrame, membership_daily: pd.Series,
                            p: DailyLimitParams,
                            unadj: pd.DataFrame | None = None) -> pd.DataFrame:
    """Signal/level columns on the symbol's own daily index."""
    from scripts.backtest_weekly import _price_filter_series
    out = daily.copy()
    close = out["Close"]
    atr = indicators.wilder_atr(out["High"], out["Low"], close, p.atr_period)
    out["atr"] = atr
    out["natr_pct"] = 100.0 * atr / close
    out["prev_close"] = close.shift(1)
    out["prev_high"] = out["High"].shift(1)
    out["ret1"] = close / out["prev_close"] - 1.0
    member = membership_daily.reindex(out.index).ffill().fillna(0).astype(bool)
    warm = pd.Series(np.arange(len(out)) >= p.min_history, index=out.index)
    ref_close, ref_volume = _price_filter_series(daily, p, unadj)
    liquidity_ok = pd.Series(True, index=out.index)
    if p.min_dollar_vol > 0:
        dollar_vol = (ref_close * ref_volume).rolling(
            p.dollar_vol_days, min_periods=min(p.dollar_vol_days, 21)).median()
        liquidity_ok = dollar_vol.fillna(0) > p.min_dollar_vol
    out["signal"] = (
        member
        & (close > indicators.sma(close, p.trend_sma))
        & (out["ret1"] <= -p.drop_pct / 100.0)
        & (out["natr_pct"] > p.natr_min_pct)
        & (ref_close > p.min_price)
        & liquidity_ok
        & warm
    )
    out["limit_px"] = close - p.entry_atr_mult * atr
    # Trailing target, valid from the day AFTER it is computed:
    out["target_px"] = out["prev_close"] + p.target_atr_mult * atr.shift(1)
    return out


@dataclass
class _Position:
    symbol: str
    shares: float
    entry_px: float
    entry_date: pd.Timestamp
    cost_basis: float
    bars_held: int = 0


def _close_position(pos: _Position, exit_px: float, exit_date: pd.Timestamp,
                    reason: str, cost_side: float, trades: list) -> float:
    proceeds = pos.shares * exit_px * (1.0 - cost_side)
    trades.append({
        "symbol": pos.symbol,
        "entry_date": pos.entry_date.date().isoformat(),
        "exit_date": exit_date.date().isoformat(),
        "entry_px": round(pos.entry_px, 6),
        "exit_px": round(float(exit_px), 6),
        "shares": round(pos.shares, 6),
        "bars_held": pos.bars_held,
        "ret_net": proceeds / pos.cost_basis - 1.0,
        "pnl_usd": proceeds - pos.cost_basis,
        "exit_reason": reason,
    })
    return proceeds


def simulate(panels: dict, memberships: dict, index_daily: pd.DataFrame,
             p: DailyLimitParams, unadj_panels: dict | None = None) -> tuple:
    """Daily event loop. Returns (trades DataFrame, equity DataFrame, summary)."""
    if p.fill_model not in ("min_open_limit", "strict_touch", "at_limit"):
        raise ValueError(f"Unknown fill_model {p.fill_model!r}")
    if p.target_touch not in ("gte", "gt"):
        raise ValueError(f"Unknown target_touch {p.target_touch!r}")
    if p.order_placement not in ("free_slots", "all_signals"):
        raise ValueError(f"Unknown order_placement {p.order_placement!r}")
    cost_side = p.cost_bps_side / 1e4
    calendar = index_daily.index
    sim_start = pd.Timestamp(p.sim_start) if p.sim_start else None

    pre = {}
    daily_row = {}
    last_bar = {}
    for sym, df in panels.items():
        if len(df) == 0:
            continue
        unadj = None if unadj_panels is None else unadj_panels.get(sym)
        pre[sym] = precompute_symbol_daily(df, memberships[sym], p, unadj)
        daily_row[sym] = {ts: i for i, ts in enumerate(df.index)}
        last_bar[sym] = df.index[-1]

    positions: dict = {}
    orders: dict = {}          # for TODAY: sym -> (limit_px, dollar_size)
    cash = p.initial_capital
    marks: dict = {}
    trades: list = []
    equity_rows: list = []
    orders_expired = 0

    for d in calendar:
        # 1. Exits for positions entered before today (precedence per pre-reg).
        for sym in list(positions.keys()):
            pos = positions[sym]
            w = pre[sym]
            if d > last_bar[sym]:
                cash += _close_position(pos, float(w["Close"].iloc[-1]),
                                        last_bar[sym], "delist", cost_side, trades)
                del positions[sym]; marks.pop(sym, None)
                continue
            i = daily_row[sym].get(d)
            if i is None:
                continue  # halted: carry mark
            row = w.iloc[i]
            o, h, c = float(row["Open"]), float(row["High"]), float(row["Close"])
            pos.bars_held += 1
            tgt = row["target_px"]
            intraday_hit = pd.notna(tgt) and (h > float(tgt) if p.target_touch == "gt"
                                              else h >= float(tgt))
            if pd.notna(tgt) and o >= float(tgt):
                cash += _close_position(pos, o, d, "target_gap", cost_side, trades)
                del positions[sym]; marks.pop(sym, None)
            elif intraday_hit:
                cash += _close_position(pos, float(tgt), d, "target", cost_side, trades)
                del positions[sym]; marks.pop(sym, None)
            elif pd.notna(row["prev_high"]) and c > float(row["prev_high"]):
                cash += _close_position(pos, c, d, "price_action", cost_side, trades)
                del positions[sym]; marks.pop(sym, None)
            elif pos.bars_held >= p.time_stop_days:
                cash += _close_position(pos, c, d, "time", cost_side, trades)
                del positions[sym]; marks.pop(sym, None)
            else:
                marks[sym] = c

        # 2. Fill (or expire) today's one-day limit orders. Placement order is
        # NATR-descending, so capacity at fill time keeps that priority.
        for sym, (limit_px, size) in list(orders.items()):
            if len(positions) >= p.max_positions:
                orders_expired += 1
                continue
            w = pre[sym]
            i = daily_row[sym].get(d)
            if i is None or d > last_bar[sym]:
                orders_expired += 1
                continue
            row = w.iloc[i]
            o, h, l, c = (float(row["Open"]), float(row["High"]),
                          float(row["Low"]), float(row["Close"]))
            touched = l < limit_px if p.fill_model == "strict_touch" else l <= limit_px
            if not touched or cash <= 0:
                orders_expired += 1
                continue
            fill_px = limit_px if p.fill_model == "at_limit" else min(o, limit_px)
            usable = min(size, cash / (1.0 + cost_side))
            shares = usable / fill_px
            basis = shares * fill_px * (1.0 + cost_side)
            cash -= basis
            pos = _Position(symbol=sym, shares=shares, entry_px=fill_px,
                            entry_date=d, cost_basis=basis)
            # Same-day price-action exit is permitted (pre-reg convention 3);
            # the target is not (it applies from days after entry).
            if pd.notna(row["prev_high"]) and c > float(row["prev_high"]):
                cash += _close_position(pos, c, d, "price_action", cost_side, trades)
            else:
                positions[sym] = pos
                marks[sym] = c
        orders = {}

        # 3. Place orders for tomorrow, highest NATR first. Convention 3
        # ("free_slots", pre-registered) rations placement to free slots;
        # "all_signals" orders every signal and lets fill-time capacity bind.
        invested = sum(positions[s].shares * marks.get(s, positions[s].entry_px)
                       for s in positions)
        equity_now = cash + invested
        free = p.max_positions - len(positions)
        if sim_start is not None and d < sim_start:
            free = 0  # design segment not yet open: no orders, but exits above still run
        elif p.order_placement == "all_signals":
            free = len(pre)  # capacity binds at fill time instead
        if free > 0 and (p.order_placement == "all_signals"
                         or cash >= p.min_cash_frac * equity_now):
            candidates = []
            for sym, w in pre.items():
                if sym in positions:
                    continue
                i = daily_row[sym].get(d)
                if i is None:
                    continue
                row = w.iloc[i]
                if bool(row["signal"]) and pd.notna(row["limit_px"]):
                    candidates.append((-float(row["natr_pct"]), sym, float(row["limit_px"])))
            candidates.sort()  # most-negative first == highest NATR first
            for _, sym, limit_px in candidates[:free]:
                orders[sym] = (limit_px, p.position_frac * equity_now)

        if sim_start is None or d >= sim_start:
            equity_rows.append({"date": d, "equity": equity_now,
                                "invested_frac": invested / equity_now if equity_now > 0 else 0.0})

    trades_df = pd.DataFrame(trades)
    if len(trades_df):
        trades_df = trades_df.sort_values(["entry_date", "symbol"]).reset_index(drop=True)
    equity_df = pd.DataFrame(equity_rows).set_index("date")

    from scripts.backtest_weekly import _summarise  # same summary contract
    summary = _summarise(trades_df, equity_df, positions, marks, index_daily, p)
    summary["orders_expired_unfilled"] = orders_expired
    return trades_df, equity_df, summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--provider", choices=["norgate", "yfinance"], default="norgate")
    ap.add_argument("--symbols-file", default="data/cache/ndx100_current_past_symbols.txt")
    ap.add_argument("--index-name", default="Nasdaq 100",
                    help="Norgate index name for PIT membership")
    ap.add_argument("--index-symbol", default="$NDXTR",
                    help="Benchmark / calendar index symbol")
    ap.add_argument("--adjustment", default="TOTALRETURN")
    ap.add_argument("--fetch-start", default="1992-01-01")
    ap.add_argument("--cost-bps-side", type=float, default=7.0)
    ap.add_argument("--natr-min-pct", type=float, default=3.0)
    ap.add_argument("--drop-pct", type=float, default=3.0)
    ap.add_argument("--entry-atr-mult", type=float, default=0.9)
    ap.add_argument("--target-atr-mult", type=float, default=0.5)
    ap.add_argument("--max-positions", type=int, default=10,
                    help="Registered plateau: 5 / 10 / 20")
    ap.add_argument("--min-dollar-vol", type=float, default=0.0,
                    help="Registered alternate 6: median 63d dollar-volume screen (0 = off, v1)")
    ap.add_argument("--fill-model", choices=["min_open_limit", "strict_touch", "at_limit"],
                    default="min_open_limit",
                    help="Registered fill-model sensitivity")
    ap.add_argument("--target-touch", choices=["gte", "gt"], default="gte",
                    help="Registered sensitivity: require high strictly above target")
    ap.add_argument("--price-basis", choices=["unadjusted", "adjusted"], default="unadjusted",
                    help="Series read by the $5 price and dollar-volume screens")
    ap.add_argument("--order-placement", choices=["free_slots", "all_signals"],
                    default="free_slots",
                    help="free_slots = pre-registered convention 3; all_signals = "
                         "anchor-miss investigation variant (capacity binds at fill)")
    ap.add_argument("--sim-start", default=None,
                    help="No order placement or equity records before this date (design segment)")
    ap.add_argument("--sim-end", default=None,
                    help="Truncate all series at this date (design segment)")
    ap.add_argument("--max-symbols", type=int, default=None)
    ap.add_argument("--cache-dir", default="data/cache/norgate_totalreturn_ndx100",
                    help="Kept separate from the S&P 500 cache: membership files are index-specific")
    ap.add_argument("--refresh-cache", action="store_true",
                    help="Refetch all symbols (required once after a subscription upgrade)")
    ap.add_argument("--out-prefix", default="daily_limit")
    args = ap.parse_args(argv)

    root = Path(__file__).resolve().parents[1]
    from scripts.providers import get_provider  # noqa: E402
    from scripts.backtest_baseline import _load_symbol, _load_unadjusted  # noqa: E402

    provider = get_provider("norgate", index_name=args.index_name,
                            adjustment=args.adjustment, start_date=args.fetch_start) \
        if args.provider == "norgate" else get_provider("yfinance", start_date=args.fetch_start)
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
    print(f"Calendar/benchmark {args.index_symbol}: "
          f"{index_daily.index[0].date()} -> {index_daily.index[-1].date()}")

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
        if k % 50 == 0:
            print(f"  ... loaded {k}/{len(symbols)}")
    print(f"Loaded {len(panels)} symbols ({len(failed)} failed)")

    from scripts.providers import assert_cache_depth  # noqa: E402
    if panels:
        assert_cache_depth(index_daily.index[0],
                           min(df.index[0] for df in panels.values()))

    if args.sim_end:
        end = pd.Timestamp(args.sim_end)
        index_daily = index_daily.loc[:end]
        panels = {s: df.loc[:end] for s, df in panels.items()}
        print(f"Design-segment truncation: all series cut at {end.date()}")

    p = DailyLimitParams(cost_bps_side=args.cost_bps_side, natr_min_pct=args.natr_min_pct,
                         drop_pct=args.drop_pct, entry_atr_mult=args.entry_atr_mult,
                         target_atr_mult=args.target_atr_mult,
                         max_positions=args.max_positions,
                         min_dollar_vol=args.min_dollar_vol,
                         fill_model=args.fill_model, target_touch=args.target_touch,
                         price_filter_basis=args.price_basis,
                         order_placement=args.order_placement, sim_start=args.sim_start)
    trades, equity, summary = simulate(panels, memberships, index_daily, p,
                                       unadj_panels=unadj_panels or None)
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
              "per PHASE3_DESIGN.md ***")
    print("\n=== Daily limit variant summary ===")
    print(json.dumps(summary, indent=2, default=str))
    print(f"\nWrote data/{args.out_prefix}_trades.csv, data/{args.out_prefix}_equity.csv, "
          f"data/{args.out_prefix}_summary.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

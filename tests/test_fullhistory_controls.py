"""Tests for the full-history controls added on day one of Platinum: the
baseline depth-gate wiring, eval-window bounds, design-segment sim bounds,
the unadjusted price-filter basis, and the registered alternate/sensitivity
flags in both portfolio engines.

House rule: dates are ISO strings via pd.to_datetime / pd.bdate_range —
Python/pandas months are 1-indexed. Design-segment boundaries are exercised
mid-window so the gates are observably doing the work.
"""

import numpy as np
import pandas as pd
import pytest

from scripts import indicators
from scripts.backtest_baseline import (
    BaselineParams, _cache_paths, run, summarise, symbol_trades,
)
from scripts.backtest_daily_limit import (
    DailyLimitParams, precompute_symbol_daily,
)
from scripts.backtest_daily_limit import simulate as simulate_daily
from scripts.backtest_weekly import (
    WeeklyParams, precompute_symbol,
)
from scripts.backtest_weekly import simulate as simulate_weekly


# ---------------------------------------------------------------- baseline

BASE_DATES = [
    "2024-01-22", "2024-01-23", "2024-01-24", "2024-01-25", "2024-01-26",
    "2024-01-29", "2024-01-30", "2024-01-31", "2024-02-01", "2024-02-02",
    "2024-02-05", "2024-02-06",
]


def _base_panel(dates):
    idx = pd.to_datetime(dates)
    close = pd.Series(np.linspace(100.0, 120.0, len(idx)), index=idx)
    prices = pd.DataFrame({"Open": close, "High": close * 1.01,
                           "Low": close * 0.99, "Close": close, "Volume": 1e6})
    return prices, pd.Series(1, index=idx, dtype="int64")


PERMISSIVE = BaselineParams(rsi_period=2, rsi_threshold=101.0, trend_sma=2,
                            hold_bars=5, min_history=3, entry_overlap="per_signal")


def test_no_reentry_blocks_stacked_entries_until_exit_bar():
    prices, member = _base_panel(BASE_DATES)
    p = BaselineParams(rsi_period=2, rsi_threshold=101.0, trend_sma=2,
                       hold_bars=5, min_history=3)          # default: no_reentry
    trades = symbol_trades("TEST", prices, member, p)
    # First signal bar 3 exits at bar 8; the next admissible signal is bar 9,
    # which exits at the series end.
    assert [t["entry_date"] for t in trades] == ["2024-01-25", "2024-02-02"]
    assert [t["exit_reason"] for t in trades] == ["time", "delisted_or_series_end"]
    stacked = symbol_trades("TEST", prices, member, PERMISSIVE)
    assert len(stacked) == 8                                # every bar 3..10 enters


def test_eval_end_bounds_the_summary_window():
    prices, member = _base_panel(BASE_DATES)
    trades = pd.DataFrame(symbol_trades("TEST", prices, member, PERMISSIVE))
    unbounded = summarise(trades, "2024-01-25")
    bounded = summarise(trades, "2024-01-25", eval_end="2024-01-31")
    expected = len(trades[(trades["entry_date"] >= "2024-01-25")
                          & (trades["entry_date"] <= "2024-01-31")])
    assert bounded["n_trades"] == expected
    assert bounded["n_trades"] < unbounded["n_trades"]
    assert bounded["last_entry"] <= "2024-01-31"
    assert bounded["eval_end"] == "2024-01-31"
    assert bounded["entries_by_year"] == {"2024": expected}


class _DeepFakeProvider:
    """Results-grade duck type serving deep history for every symbol."""

    results_grade = True

    def __init__(self, idx):
        self._idx = idx

    def describe(self):
        return "DeepFakeProvider [test]"

    def price_history(self, symbol):
        close = pd.Series(np.linspace(100.0, 200.0, len(self._idx)), index=self._idx)
        return pd.DataFrame({"Open": close, "High": close * 1.01,
                             "Low": close * 0.99, "Close": close, "Volume": 1e6})

    def index_membership(self, symbol):
        return pd.Series(1, index=self._idx, dtype="int64")


def test_baseline_guard_raises_on_stale_trial_cache(tmp_path):
    shallow_idx = pd.bdate_range("2024-07-03", "2026-07-01")
    close = pd.Series(np.linspace(50.0, 60.0, len(shallow_idx)), index=shallow_idx)
    shallow = pd.DataFrame({"Open": close, "High": close, "Low": close,
                            "Close": close, "Volume": 1e6})
    pp, mp = _cache_paths(tmp_path, "AAA")
    shallow.to_csv(pp)
    pd.Series(1, index=shallow_idx, dtype="int64").rename("member").to_frame().to_csv(mp)

    deep = _DeepFakeProvider(pd.bdate_range("1998-01-02", "2000-06-30"))
    with pytest.raises(RuntimeError, match="refresh-cache"):
        run(deep, PERMISSIVE, "2000-01-01", tmp_path, symbols=["AAA"])
    # --refresh-cache is the sanctioned way through the gate.
    trades, summary = run(deep, PERMISSIVE, "1998-01-01", tmp_path,
                          symbols=["AAA"], refresh_cache=True)
    assert summary["symbols_failed"] == 0


# ------------------------------------------------------------------ weekly

def _wcal(start: str, weeks: int) -> pd.DatetimeIndex:
    return pd.bdate_range(start, periods=weeks * 5)


def _wdaily(cal: pd.DatetimeIndex, base=100.0, drift=0.10, amp=0.5) -> pd.DataFrame:
    t = np.arange(len(cal), dtype=float)
    close = base + drift * t + amp * 0.3 * np.sin(t)
    return pd.DataFrame({"Open": close - 0.05, "High": close + amp,
                         "Low": close - amp, "Close": close, "Volume": 1e6},
                        index=cal)


def _wdaily_levels(cal: pd.DatetimeIndex, weekly_levels) -> pd.DataFrame:
    close = np.repeat(np.asarray(weekly_levels, dtype=float), 5)[:len(cal)]
    return pd.DataFrame({"Open": close, "High": close + 0.2, "Low": close - 0.2,
                         "Close": close, "Volume": 1e6}, index=cal)


def _ones(idx) -> pd.Series:
    return pd.Series(1, index=idx, dtype="int64")


def _wparams(**overrides) -> WeeklyParams:
    base = dict(
        trend_weeks=4, rsi_weeks=2, rsi_threshold=101.0, rank_vol_weeks=3,
        max_positions=3, position_frac=0.10, stop_pct=0.10, target_pct=0.15,
        cost_bps_side=0.0, min_price=0.0, min_dollar_vol=0.0, dollar_vol_days=5,
        regime_sma_weeks=3, entry_at="close", initial_capital=100_000.0,
        min_weekly_history=5, min_cash_frac=0.0,
    )
    base.update(overrides)
    return WeeklyParams(**base)


WCAL = _wcal("2024-09-30", 24)
WINDEX = _wdaily(WCAL, base=5000.0, drift=1.0, amp=2.0)


def test_sim_start_blocks_entries_and_equity_before_date():
    p = _wparams(sim_start="2025-01-15")
    daily = _wdaily(WCAL)
    w = precompute_symbol(daily, _ones(WCAL), p)
    assert w.index[w["candidate"]][0] < pd.Timestamp("2025-01-15")  # gate is binding
    trades, equity, summary = simulate_weekly(
        {"AAA": daily}, {"AAA": _ones(WCAL)}, WINDEX, p)
    assert equity.index[0] >= pd.Timestamp("2025-01-15")
    if len(trades):
        assert trades["entry_date"].min() >= "2025-01-15"
    # The symbol is a persistent candidate, so it must be held after the gate.
    assert summary["open_positions_at_end"] == ["AAA"] or len(trades) > 0


def test_window_end_leaves_positions_open_not_delisted():
    # Panel and calendar end on the same bar (the sim-end truncation case):
    # the open position must remain open, not exit as a delisting.
    p = _wparams()
    daily = _wdaily(WCAL)
    trades, _, summary = simulate_weekly({"AAA": daily}, {"AAA": _ones(WCAL)},
                                         WINDEX, p)
    assert "AAA" in summary["open_positions_at_end"]
    if len(trades):
        assert not (trades["exit_reason"] == "delist").any()


def test_dip_trigger_two_consecutive_lower_closes():
    levels = [100, 102, 104, 106, 108, 110, 112, 114, 113.8, 113.6, 115, 117]
    cal = _wcal("2024-09-30", len(levels))
    daily = _wdaily_levels(cal, levels)
    p = _wparams(dip_trigger="lower_closes")
    w = precompute_symbol(daily, _ones(cal), p)
    labels = w.index
    assert not bool(w.loc[labels[8], "candidate"])   # only one lower close
    assert bool(w.loc[labels[9], "candidate"])       # second consecutive lower close
    assert not bool(w.loc[labels[10], "candidate"])  # sequence broken


def test_dip_trigger_below_high_band_edges():
    levels = [100, 104, 108, 112, 116, 95, 103, 105, 107, 109, 111, 117]
    cal = _wcal("2024-09-30", len(levels))
    daily = _wdaily_levels(cal, levels)
    p = _wparams(dip_trigger="below_high", min_weekly_history=3)
    w = precompute_symbol(daily, _ones(cal), p)
    labels = w.index
    assert bool(w.loc[labels[8], "candidate"])       # -7.8% below the 8w close-high
    assert bool(w.loc[labels[9], "candidate"])       # -6.0%
    assert not bool(w.loc[labels[10], "candidate"])  # -4.3%: above the -5% edge
    assert not bool(w.loc[labels[11], "candidate"])  # new high: ratio 0
    # Tighten the deep edge: -7.8% now falls outside the band, -6.0% stays in.
    p2 = _wparams(dip_trigger="below_high", min_weekly_history=3,
                  below_high_min=-0.07)
    w2 = precompute_symbol(daily, _ones(cal), p2)
    assert not bool(w2.loc[labels[8], "candidate"])
    assert bool(w2.loc[labels[9], "candidate"])


def test_ranking_high_natr_prefers_high_amplitude_names():
    p = _wparams(ranking="high_natr", max_positions=3)
    amps = {"S1": 0.2, "S2": 0.4, "S3": 0.6, "S4": 0.8, "S5": 1.0}
    panels = {s: _wdaily(WCAL, amp=a) for s, a in amps.items()}
    members = {s: _ones(WCAL) for s in panels}
    trades, _, summary = simulate_weekly(panels, members, WINDEX, p)
    label = precompute_symbol(panels["S1"], members["S1"], p).index[5]
    natrs = {s: float(precompute_symbol(df, members[s], p).loc[label, "natr_rank"])
             for s, df in panels.items()}
    expected = set(sorted(natrs, key=natrs.get, reverse=True)[:3])
    held_or_traded = set(summary["open_positions_at_end"])
    if len(trades):
        held_or_traded |= set(trades["symbol"])
    assert held_or_traded == expected


def test_regime_breadth_gate_blocks_and_admits():
    daily = _wdaily(WCAL)
    p = _wparams(regime_gate="breadth")
    below = pd.Series(40.0, index=WCAL)
    trades, equity, summary = simulate_weekly(
        {"AAA": daily}, {"AAA": _ones(WCAL)}, WINDEX, p, breadth_daily=below)
    assert len(trades) == 0 and summary["open_positions_at_end"] == []
    assert float(equity["invested_frac"].max()) == 0.0

    cutoff = WCAL[60]
    above_late = pd.Series(60.0, index=WCAL[WCAL >= cutoff])  # series starts mid-window
    trades2, equity2, _ = simulate_weekly(
        {"AAA": daily}, {"AAA": _ones(WCAL)}, WINDEX, p, breadth_daily=above_late)
    invested_days = equity2.index[equity2["invested_frac"] > 0]
    assert len(invested_days) > 0
    assert invested_days[0] >= cutoff  # NaN weeks before the series start stay OFF


def test_regime_off_exit_closes_open_positions():
    from scripts.backtest_weekly import build_weekly
    p = _wparams(regime_off_exit=True)
    daily = _wdaily(WCAL)
    w = precompute_symbol(daily, _ones(WCAL), p)
    entry_label = w.index[w["candidate"]][0]
    index = WINDEX.copy()
    labels = list(build_weekly(WINDEX).index)
    off_label = labels[labels.index(entry_label) + 1]
    dip_days = WCAL[(WCAL > entry_label) & (WCAL <= off_label)]
    index.loc[dip_days, "Close"] *= 0.94        # weekly close < 3w SMA that week
    trades, _, _ = simulate_weekly({"AAA": daily}, {"AAA": _ones(WCAL)}, index, p)
    t = trades.iloc[0]
    assert t["exit_reason"] == "regime_off"
    assert t["exit_date"] == dip_days[-1].date().isoformat()


def test_price_basis_unadjusted_reads_actual_prices():
    daily = _wdaily(WCAL, base=3.0, drift=0.005, amp=0.02)   # adjusted ~ $3
    unadj = daily * 1.0
    for col in ("Open", "High", "Low", "Close"):
        unadj[col] = daily[col] * 10.0                       # traded ~ $30
    unadj["Volume"] = daily["Volume"]
    p = _wparams(min_price=5.0)                              # basis: unadjusted (default)
    w = precompute_symbol(daily, _ones(WCAL), p, unadj=unadj)
    assert bool(w["candidate"].any())
    p_adj = _wparams(min_price=5.0, price_filter_basis="adjusted")
    w_adj = precompute_symbol(daily, _ones(WCAL), p_adj)
    assert not bool(w_adj["candidate"].any())


def test_unadjusted_basis_with_active_screen_requires_series():
    daily = _wdaily(WCAL)
    with pytest.raises(ValueError, match="unadjusted"):
        precompute_symbol(daily, _ones(WCAL), _wparams(min_price=5.0))


def test_weekly_close_monitoring_ignores_intraweek_breach():
    daily = _wdaily(WCAL)
    p_daily = _wparams()
    w = precompute_symbol(daily, _ones(WCAL), p_daily)
    entry_label = w.index[w["candidate"]][0]
    entry_px = float(w.loc[entry_label, "Close"])
    week_after = WCAL[WCAL > entry_label]
    breach_day = week_after[2]                               # intraweek low breach
    daily.loc[breach_day, "Low"] = entry_px * 0.85
    close_breach_fri = w.index[list(w.index).index(entry_label) + 2]
    fri_day = WCAL[WCAL <= close_breach_fri][-1]             # decision close breach
    daily.loc[fri_day, "Close"] = entry_px * 0.87
    daily.loc[fri_day, "Low"] = entry_px * 0.86

    trades_d, _, _ = simulate_weekly({"AAA": daily.copy()}, {"AAA": _ones(WCAL)},
                                     WINDEX, p_daily)
    td = trades_d.iloc[0]
    assert td["exit_reason"] == "stop"
    assert td["exit_date"] == breach_day.date().isoformat()
    assert td["exit_px"] == pytest.approx(entry_px * 0.90, abs=1e-4)

    p_weekly = _wparams(monitor="weekly_close")
    trades_w, _, _ = simulate_weekly({"AAA": daily.copy()}, {"AAA": _ones(WCAL)},
                                     WINDEX, p_weekly)
    tw = trades_w.iloc[0]
    assert tw["exit_reason"] == "stop"
    assert tw["exit_date"] == fri_day.date().isoformat()     # not the intraweek breach
    assert tw["exit_px"] == pytest.approx(entry_px * 0.87, abs=1e-4)  # fills at the close


def test_cash_tbill_accrual_compounds_idle_cash():
    p = _wparams(rsi_threshold=-1.0)                         # dip never true: all cash
    daily = _wdaily(WCAL)
    accrual = pd.Series(1e-4, index=WCAL)
    _, equity, summary = simulate_weekly({"AAA": daily}, {"AAA": _ones(WCAL)},
                                         WINDEX, p, cash_yield_daily=accrual)
    assert summary["n_trades"] == 0
    expected = 100_000.0 * (1.0 + 1e-4) ** len(equity)
    assert float(equity["equity"].iloc[-1]) == pytest.approx(expected, rel=1e-9)


# ------------------------------------------------------------- daily limit

DCAL = pd.bdate_range("2024-10-07", periods=55)
DIP = 14


def _dcloses() -> np.ndarray:
    c = np.concatenate([np.full(10, 100.0), np.full(4, 120.0), [115.2]])
    tail = np.full(len(DCAL) - len(c), 115.0)
    return np.concatenate([c, tail])


def _dframe(closes=None, h_off=0.3, l_off=3.7) -> pd.DataFrame:
    c = np.asarray(_dcloses() if closes is None else closes, dtype=float)
    return pd.DataFrame({"Open": c.copy(), "High": c + h_off, "Low": c - l_off,
                         "Close": c.copy(), "Volume": 1e6}, index=DCAL[:len(c)])


def _dparams(**overrides) -> DailyLimitParams:
    base = dict(
        trend_sma=10, drop_pct=3.0, atr_period=5, natr_min_pct=0.0,
        entry_atr_mult=0.9, target_atr_mult=0.5, max_positions=3,
        position_frac=0.10, time_stop_days=10, cost_bps_side=0.0,
        min_price=0.0, min_history=12, initial_capital=100_000.0,
        min_cash_frac=0.0,
    )
    base.update(overrides)
    return DailyLimitParams(**base)


DINDEX = pd.DataFrame({
    "Open": np.linspace(5000, 5200, len(DCAL)), "High": np.linspace(5001, 5201, len(DCAL)),
    "Low": np.linspace(4999, 5199, len(DCAL)), "Close": np.linspace(5000, 5200, len(DCAL)),
    "Volume": 1e6,
}, index=DCAL)


def _dlevels(df: pd.DataFrame, p: DailyLimitParams):
    atr = indicators.wilder_atr(df["High"], df["Low"], df["Close"], p.atr_period)
    limit = df["Close"] - p.entry_atr_mult * atr
    target = df["Close"].shift(1) + p.target_atr_mult * atr.shift(1)
    return limit, target


def _drun(df, p):
    return simulate_daily({"AAA": df}, {"AAA": _ones(df.index)}, DINDEX, p)


def test_daily_sim_start_blocks_order_placement():
    df = _dframe()
    limit, _ = _dlevels(df, _dparams())
    df.loc[DCAL[DIP + 1], "Low"] = float(limit.iloc[DIP]) - 0.5   # engineer the fill
    control, _, csum = _drun(df, _dparams())
    assert len(control) + len(csum["open_positions_at_end"]) > 0
    gated_start = DCAL[DIP + 1]                  # signal day falls before the gate
    trades, equity, summary = _drun(df, _dparams(sim_start=str(gated_start.date())))
    assert len(trades) == 0
    assert summary["open_positions_at_end"] == []
    assert equity.index[0] == gated_start


def test_fill_strict_touch_requires_strict_breach():
    df = _dframe()
    limit, _ = _dlevels(df, _dparams())
    fill_day = DCAL[DIP + 1]
    df.loc[fill_day, "Low"] = float(limit.iloc[DIP])         # touch exactly
    trades, _, summary = _drun(df.copy(), _dparams())
    assert len(trades) + len(summary["open_positions_at_end"]) > 0
    strict, _, ssum = _drun(df.copy(), _dparams(fill_model="strict_touch"))
    assert len(strict) == 0 and ssum["open_positions_at_end"] == []
    assert ssum["orders_expired_unfilled"] >= 1


def test_fill_at_limit_prices_gap_fill_at_limit_not_open():
    df = _dframe()
    limit, _ = _dlevels(df, _dparams())
    lim = float(limit.iloc[DIP])
    fill_day = DCAL[DIP + 1]
    df.loc[fill_day, "Open"] = lim - 2.0                     # gap through the limit
    df.loc[fill_day, "Low"] = lim - 3.0
    p = _dparams(time_stop_days=3)                           # force a closed trade record
    trades, _, _ = _drun(df.copy(), p)
    assert trades.iloc[0]["entry_px"] == pytest.approx(lim - 2.0, abs=1e-6)
    trades_al, _, _ = _drun(df.copy(), _dparams(time_stop_days=3, fill_model="at_limit"))
    assert trades_al.iloc[0]["entry_px"] == pytest.approx(lim, abs=1e-6)


def test_target_touch_gt_requires_strict_high():
    df = _dframe()
    limit, _ = _dlevels(df, _dparams())
    df.loc[DCAL[DIP + 1], "Low"] = float(limit.iloc[DIP]) - 0.5   # engineer the fill
    # The lowered fill-day low widens the ATR, so the trailing target must be
    # computed on the modified frame.
    _, target = _dlevels(df, _dparams())
    touch_day = DCAL[DIP + 2]                                # day after the fill day
    tgt = float(target.iloc[DIP + 2])
    df.loc[touch_day, "High"] = tgt                          # touch exactly
    trades, _, _ = _drun(df.copy(), _dparams())
    t = trades.iloc[0]
    assert t["exit_reason"] == "target"
    assert t["exit_date"] == touch_day.date().isoformat()
    trades_gt, _, _ = _drun(df.copy(), _dparams(target_touch="gt"))
    if len(trades_gt):
        t2 = trades_gt.iloc[0]
        assert not (t2["exit_reason"] == "target"
                    and t2["exit_date"] == touch_day.date().isoformat())


def test_all_signals_placement_uses_capacity_freed_by_exits():
    # A holds the only slot when B signals. Under the pre-registered
    # free_slots convention B never gets an order; under all_signals the
    # order exists and fills after A's exit releases the slot that morning.
    a = _dframe()
    limit_a, _ = _dlevels(a, _dparams())
    a.loc[DCAL[DIP + 1], "Low"] = float(limit_a.iloc[DIP]) - 0.5      # A fills day 15
    _, target_a = _dlevels(a, _dparams())
    a.loc[DCAL[DIP + 2], "Open"] = float(target_a.iloc[DIP + 2]) + 1.0  # A gap-target exit day 16

    b_closes = np.concatenate([np.full(11, 100.0), np.full(4, 120.0), [115.2],
                               np.full(len(DCAL) - 16, 115.0)])
    b = _dframe(closes=b_closes)                                      # B signals day 15
    limit_b, _ = _dlevels(b, _dparams())
    b.loc[DCAL[DIP + 2], "Low"] = float(limit_b.iloc[DIP + 1]) - 0.5  # B fillable day 16

    panels = {"AAA": a, "BBB": b}
    members = {s: _ones(df.index) for s, df in panels.items()}

    p = _dparams(max_positions=1)
    trades, _, summary = simulate_daily(panels, members, DINDEX, p)
    filled = set(trades["symbol"]) | set(summary["open_positions_at_end"])
    assert "BBB" not in filled                                        # rationed out

    p_all = _dparams(max_positions=1, order_placement="all_signals")
    trades2, _, summary2 = simulate_daily(panels, members, DINDEX, p_all)
    filled2 = set(trades2["symbol"]) | set(summary2["open_positions_at_end"])
    assert {"AAA", "BBB"} <= filled2
    a_exit = trades2[trades2["symbol"] == "AAA"].iloc[0]
    assert a_exit["exit_reason"] == "target_gap"
    b_entry = (trades2[trades2["symbol"] == "BBB"].iloc[0]["entry_date"]
               if (trades2["symbol"] == "BBB").any() else None)
    if b_entry is not None:
        assert b_entry == DCAL[DIP + 2].date().isoformat()            # fills the exit day


def test_min_dollar_vol_screen_blocks_illiquid_names():
    df = _dframe()
    liquid = precompute_symbol_daily(
        df, _ones(df.index),
        _dparams(min_dollar_vol=1e6, dollar_vol_days=10, price_filter_basis="adjusted"))
    assert bool(liquid["signal"].any())
    screened = precompute_symbol_daily(
        df, _ones(df.index),
        _dparams(min_dollar_vol=1e12, dollar_vol_days=10, price_filter_basis="adjusted"))
    assert not bool(screened["signal"].any())

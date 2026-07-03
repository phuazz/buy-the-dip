"""Mechanics tests for the weekly portfolio engine.

Fixtures are deterministic synthetic panels. The dip trigger is disabled
(rsi_threshold=101) in most tests so every warm, trending, member bar is a
candidate — that isolates the portfolio mechanics under test (fills, gaps,
slots, regime gate, delistings, costs, calendar boundaries). Signal
composition itself is tested separately at the end.

House rule: month/year boundary edge cases are covered explicitly
(test_stop_across_year_boundary uses a calendar with the New Year holiday
removed). Dates are ISO strings via pd.to_datetime — months are 1-indexed.
"""

import numpy as np
import pandas as pd
import pytest

from scripts import indicators
from scripts.backtest_weekly import (
    WeeklyParams, build_weekly, precompute_symbol, simulate,
)


def _calendar(start: str, end: str) -> pd.DatetimeIndex:
    days = pd.bdate_range(start, end)
    holidays = {pd.Timestamp("2024-12-25"), pd.Timestamp("2025-01-01")}
    return pd.DatetimeIndex([d for d in days if d not in holidays])


def _daily(cal: pd.DatetimeIndex, base: float = 100.0, drift: float = 0.10,
           amp: float = 0.5) -> pd.DataFrame:
    t = np.arange(len(cal), dtype=float)
    close = base + drift * t + amp * 0.3 * np.sin(t)
    return pd.DataFrame({
        "Open": close - 0.05,
        "High": close + amp,
        "Low": close - amp,
        "Close": close,
        "Volume": 1e6,
    }, index=cal)


def _ones(cal: pd.DatetimeIndex) -> pd.Series:
    return pd.Series(1, index=cal, dtype="int64")


def _params(**overrides) -> WeeklyParams:
    base = dict(
        trend_weeks=4, rsi_weeks=2, rsi_threshold=101.0, rank_vol_weeks=3,
        max_positions=3, position_frac=0.10, stop_pct=0.10, target_pct=0.15,
        cost_bps_side=0.0, min_price=0.0, min_dollar_vol=0.0, dollar_vol_days=5,
        regime_sma_weeks=3, entry_at="close", initial_capital=100_000.0,
        min_weekly_history=5, min_cash_frac=0.0,
    )
    base.update(overrides)
    return WeeklyParams(**base)


def _first_entry(daily: pd.DataFrame, p: WeeklyParams):
    """(entry label, weekly close, entry trading date) of the first candidacy."""
    w = precompute_symbol(daily, _ones(daily.index), p)
    label = w.index[w["candidate"]][0]
    entry_px = float(w.loc[label, "Close"])
    entry_date = daily.index[daily.index <= label][-1]
    return label, entry_px, entry_date


CAL = _calendar("2024-10-07", "2025-03-28")
INDEX = _daily(CAL, base=5000.0, drift=1.0, amp=2.0)


def _run_single(daily: pd.DataFrame, p: WeeklyParams, index_daily=None):
    trades, equity, summary = simulate(
        {"AAA": daily}, {"AAA": _ones(daily.index)},
        INDEX if index_daily is None else index_daily, p,
    )
    return trades, equity, summary


def test_intraday_stop_fills_at_stop_price():
    p = _params()
    daily = _daily(CAL)
    _, entry_px, entry_date = _first_entry(daily, p)
    stop_day = CAL[CAL > entry_date][1]
    daily.loc[stop_day, "Low"] = entry_px * 0.88   # breaches the 10% stop
    trades, _, _ = _run_single(daily, p)
    t = trades.iloc[0]
    assert t["exit_reason"] == "stop"
    assert t["exit_px"] == pytest.approx(entry_px * 0.90, abs=1e-4)
    assert t["exit_date"] == stop_day.date().isoformat()
    assert t["entry_px"] == pytest.approx(entry_px, abs=1e-4)


def test_gap_below_stop_fills_at_open():
    p = _params()
    daily = _daily(CAL)
    _, entry_px, entry_date = _first_entry(daily, p)
    gap_day = CAL[CAL > entry_date][0]
    daily.loc[gap_day, "Open"] = entry_px * 0.85
    daily.loc[gap_day, "Low"] = entry_px * 0.84
    trades, _, _ = _run_single(daily, p)
    t = trades.iloc[0]
    assert t["exit_reason"] == "stop_gap"
    assert t["exit_px"] == pytest.approx(entry_px * 0.85, abs=1e-4)
    assert t["exit_date"] == gap_day.date().isoformat()


def test_target_fills_at_target_price():
    p = _params()
    daily = _daily(CAL)
    _, entry_px, entry_date = _first_entry(daily, p)
    target_day = CAL[CAL > entry_date][2]
    daily.loc[target_day, "High"] = entry_px * 1.20
    trades, _, _ = _run_single(daily, p)
    t = trades.iloc[0]
    assert t["exit_reason"] == "target"
    assert t["exit_px"] == pytest.approx(entry_px * 1.15, abs=1e-4)
    assert t["ret_net"] == pytest.approx(0.15, abs=1e-4)  # zero costs here


def test_stop_checked_before_target_same_bar():
    p = _params()
    daily = _daily(CAL)
    _, entry_px, entry_date = _first_entry(daily, p)
    wild_day = CAL[CAL > entry_date][1]
    daily.loc[wild_day, "Low"] = entry_px * 0.88
    daily.loc[wild_day, "High"] = entry_px * 1.25
    trades, _, _ = _run_single(daily, p)
    t = trades.iloc[0]
    assert t["exit_reason"] == "stop"          # conservative convention
    assert t["exit_px"] == pytest.approx(entry_px * 0.90, abs=1e-4)


def test_slot_cap_and_low_vol_ranking():
    p = _params(max_positions=3)
    amps = {"S1": 0.2, "S2": 0.4, "S3": 0.6, "S4": 0.8, "S5": 1.0}
    panels = {s: _daily(CAL, amp=a) for s, a in amps.items()}
    members = {s: _ones(CAL) for s in panels}
    trades, equity, summary = simulate(panels, members, INDEX, p)
    # Expected: the three lowest-volatility names by the engine's own measure.
    label = precompute_symbol(panels["S1"], members["S1"], p).index[5]
    vols = {s: float(precompute_symbol(df, members[s], p).loc[label, "vol"])
            for s, df in panels.items()}
    expected = sorted(sorted(vols, key=vols.get)[:3])
    held_or_traded = set(summary["open_positions_at_end"]) | set(
        trades["symbol"]) if len(trades) else set(summary["open_positions_at_end"])
    assert held_or_traded == set(expected)
    assert equity["invested_frac"].max() < 0.35   # never more than 3 x 10% (+drift)


def test_regime_gate_blocks_new_entries_only():
    p = _params()
    daily_a = _daily(CAL)                        # candidate from weekly bar 5
    label_a, entry_a, date_a = _first_entry(daily_a, p)
    index = INDEX.copy()
    w_index = build_weekly(INDEX)
    labels = list(w_index.index)
    gate_off_label = labels[labels.index(label_a) + 1]
    dip_days = CAL[(CAL > label_a) & (CAL <= gate_off_label)]
    index.loc[dip_days, "Close"] *= 0.94         # weekly close < 3w SMA that week
    # Symbol B becomes warm exactly in the gate-off week (series starts 1 week later).
    daily_b = _daily(CAL[5:], base=200.0)
    panels = {"AAA": daily_a, "BBB": daily_b}
    members = {"AAA": _ones(daily_a.index), "BBB": _ones(daily_b.index)}
    # AAA's stop breaches during the gate-off week: exits must still fire.
    stop_day = dip_days[1]
    daily_a.loc[stop_day, "Low"] = entry_a * 0.88
    # BBB's first candidacy IS the gate-off week (it must be skipped there and
    # entered the following week). Engineer a target exit so its entry date is
    # captured in the trade record rather than hidden on an open position.
    wb = precompute_symbol(daily_b, members["BBB"], p)
    b_label = wb.index[wb["candidate"]][0]
    assert b_label == gate_off_label
    on_label = labels[labels.index(gate_off_label) + 1]
    b_entry_px = float(wb.loc[on_label, "Close"])
    b_entry_date = daily_b.index[daily_b.index <= on_label][-1]
    b_target_day = daily_b.index[daily_b.index > b_entry_date][2]
    daily_b.loc[b_target_day, "High"] = b_entry_px * 1.20
    trades, _, summary = simulate(panels, members, index, p)
    a = trades[trades["symbol"] == "AAA"].iloc[0]
    assert a["exit_reason"] == "stop"
    assert a["exit_date"] == stop_day.date().isoformat()
    b = trades[trades["symbol"] == "BBB"].iloc[0]
    assert b["entry_date"] == b_entry_date.date().isoformat()   # after the gate re-opens
    assert b["entry_date"] > gate_off_label.date().isoformat()
    assert b["exit_reason"] == "target"


def test_delisting_mid_hold_exits_at_final_print():
    p = _params()
    daily = _daily(CAL)
    _, entry_px, entry_date = _first_entry(daily, p)
    cut = CAL.get_loc(entry_date) + 4            # delists 4 bars after entry
    truncated = daily.iloc[:cut]
    trades, _, _ = simulate({"AAA": truncated}, {"AAA": _ones(truncated.index)},
                            INDEX, p)
    t = trades.iloc[0]
    assert t["exit_reason"] == "delist"
    assert t["exit_date"] == truncated.index[-1].date().isoformat()
    assert t["exit_px"] == pytest.approx(float(truncated["Close"].iloc[-1]), abs=1e-4)


def test_costs_reduce_net_return_exactly():
    p = _params(cost_bps_side=50.0)              # 0.5% per side, exaggerated
    daily = _daily(CAL)
    _, entry_px, entry_date = _first_entry(daily, p)
    target_day = CAL[CAL > entry_date][2]
    daily.loc[target_day, "High"] = entry_px * 1.20
    trades, _, _ = _run_single(daily, p)
    t = trades.iloc[0]
    expected = (1.15 * (1 - 0.005)) / (1.0 * (1 + 0.005)) - 1.0
    assert t["ret_net"] == pytest.approx(expected, abs=1e-4)


def test_stop_across_year_boundary_fills_after_holiday():
    cal = _calendar("2024-11-18", "2025-01-31")  # 6th Friday label = 2024-12-27
    index = _daily(cal, base=5000.0, drift=1.0, amp=2.0)
    p = _params()
    daily = _daily(cal)
    label, entry_px, entry_date = _first_entry(daily, p)
    assert label.date().isoformat() == "2024-12-27"
    stop_day = cal[cal > entry_date][2]          # 30 Dec, 31 Dec, then 2 Jan
    assert stop_day.date().isoformat() == "2025-01-02"  # 1 Jan removed from calendar
    daily.loc[stop_day, "Low"] = entry_px * 0.88
    trades, equity, _ = simulate({"AAA": daily}, {"AAA": _ones(cal)}, index, p)
    t = trades.iloc[0]
    assert t["exit_date"] == "2025-01-02"
    assert t["exit_px"] == pytest.approx(entry_px * 0.90, abs=1e-4)
    # Continuity: the equity record skips exactly the removed holidays.
    dates = pd.DatetimeIndex(equity.index)
    assert pd.Timestamp("2025-01-01") not in dates
    assert pd.Timestamp("2025-01-02") in dates and pd.Timestamp("2024-12-31") in dates


def test_time_stop_alternate_fires_at_decision():
    p = _params(time_stop_weeks=2, target_pct=10.0, stop_pct=0.90)  # exits unreachable
    daily = _daily(CAL)
    trades, _, _ = _run_single(daily, p)
    t = trades.iloc[0]
    assert t["exit_reason"] == "time"


def test_next_open_entry_fills_at_next_days_open():
    p = _params(entry_at="next_open")
    daily = _daily(CAL)
    label, _, entry_date = _first_entry(daily, p)
    fill_day = CAL[CAL > entry_date][0]
    fill_open = float(daily.loc[fill_day, "Open"])
    target_day = CAL[CAL > fill_day][2]
    daily.loc[target_day, "High"] = fill_open * 1.20   # force a closed trade record
    trades, _, _ = _run_single(daily, p)
    first = trades.iloc[0]
    assert first["entry_date"] == fill_day.date().isoformat()
    assert first["entry_px"] == pytest.approx(fill_open, abs=1e-4)
    assert first["exit_reason"] == "target"
    assert first["exit_px"] == pytest.approx(fill_open * 1.15, abs=1e-4)


def test_candidate_mask_composition_matches_independent_computation():
    p = _params(rsi_threshold=30.0)
    rng = np.random.default_rng(11)
    cal = CAL
    steps = rng.normal(0.05, 1.0, len(cal))
    close = pd.Series(100.0 + np.cumsum(steps), index=cal).clip(lower=5.0)
    daily = pd.DataFrame({"Open": close, "High": close * 1.01,
                          "Low": close * 0.99, "Close": close, "Volume": 1e6},
                         index=cal)
    got = precompute_symbol(daily, _ones(cal), p)["candidate"]
    w = build_weekly(daily)
    wclose = w["Close"]
    expected = (
        (wclose > indicators.sma(wclose, p.trend_weeks))
        & (indicators.wilder_rsi(wclose, p.rsi_weeks) < p.rsi_threshold)
        & pd.Series(np.arange(len(w)) >= p.min_weekly_history, index=w.index)
        & (wclose > p.min_price)
    )
    pd.testing.assert_series_equal(got, expected, check_names=False)
    # And the always-dip fixture must produce at least one candidate.
    assert precompute_symbol(_daily(cal), _ones(cal), _params())["candidate"].any()

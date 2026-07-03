"""Mechanics tests for the daily limit-order engine (Phase 3).

Fixture shape: 10 flat bars at 100, 4 bars at 120, then a -4% dip close —
this passes the SMA(10) trend filter ON the dip day while producing a
one-day drop > 3% (a plain rising series cannot do both). ATR-derived limit
and target levels are computed independently via scripts.indicators in each
test rather than hand-arithmetic. Default bar geometry (H = C + 0.3,
L = C - 3.7) keeps ATR wide enough that no exit fires unless engineered —
this engine has NO stop-loss, so deep lows are free.

House rule: the year-boundary case is covered explicitly
(test_order_day_skips_new_year_holiday). Dates via pd.to_datetime; months
are 1-indexed.
"""

import numpy as np
import pandas as pd
import pytest

from scripts import indicators
from scripts.backtest_daily_limit import (
    DailyLimitParams, precompute_symbol_daily, simulate,
)

DIP = 14  # index of the engineered signal day in the standard fixture


def _calendar(start: str, end: str) -> pd.DatetimeIndex:
    days = pd.bdate_range(start, end)
    holidays = {pd.Timestamp("2024-12-25"), pd.Timestamp("2025-01-01")}
    return pd.DatetimeIndex([d for d in days if d not in holidays])


CAL = _calendar("2024-10-07", "2024-12-20")  # 50+ trading days, no boundary


def _closes() -> np.ndarray:
    c = np.concatenate([np.full(10, 100.0), np.full(4, 120.0), [115.2]])
    tail = np.full(len(CAL) - len(c), 115.0)  # flat afterwards: no new signals
    return np.concatenate([c, tail])


def _frame(cal=None, closes=None, h_off=0.3, l_off=3.7) -> pd.DataFrame:
    cal = CAL if cal is None else cal
    c = _closes() if closes is None else closes
    c = np.asarray(c, dtype=float)
    return pd.DataFrame({
        "Open": c.copy(), "High": c + h_off, "Low": c - l_off,
        "Close": c.copy(), "Volume": 1e6,
    }, index=cal[:len(c)])


def _ones(idx) -> pd.Series:
    return pd.Series(1, index=idx, dtype="int64")


def _params(**overrides) -> DailyLimitParams:
    base = dict(
        trend_sma=10, drop_pct=3.0, atr_period=5, natr_min_pct=0.0,
        entry_atr_mult=0.9, target_atr_mult=0.5, max_positions=3,
        position_frac=0.10, time_stop_days=10, cost_bps_side=0.0,
        min_price=0.0, min_history=12, initial_capital=100_000.0,
        min_cash_frac=0.0,
    )
    base.update(overrides)
    return DailyLimitParams(**base)


def _levels(df: pd.DataFrame, p: DailyLimitParams):
    """Independent computation of the limit and trailing-target series."""
    atr = indicators.wilder_atr(df["High"], df["Low"], df["Close"], p.atr_period)
    limit = df["Close"] - p.entry_atr_mult * atr
    target = df["Close"].shift(1) + p.target_atr_mult * atr.shift(1)
    return limit, target


INDEX = pd.DataFrame({
    "Open": np.linspace(5000, 5200, len(CAL)), "High": np.linspace(5001, 5201, len(CAL)),
    "Low": np.linspace(4999, 5199, len(CAL)), "Close": np.linspace(5000, 5200, len(CAL)),
    "Volume": 1e6,
}, index=CAL)


def _run(df, p, index=None):
    return simulate({"AAA": df}, {"AAA": _ones(df.index)},
                    INDEX if index is None else index, p)


def test_signal_fires_on_engineered_dip_day():
    p = _params()
    pre = precompute_symbol_daily(_frame(), _ones(CAL), p)
    assert bool(pre["signal"].iloc[DIP])
    assert not pre["signal"].iloc[:DIP].any()   # nothing before the dip
    assert not pre["signal"].iloc[DIP + 1:].any()


def test_fill_at_limit_then_time_stop():
    p = _params(time_stop_days=2)
    df, lim, fill_day = _filled_fixture(p)
    d17 = CAL[DIP + 3]
    trades, _, _ = _run(df, p)
    t = trades.iloc[0]
    assert t["entry_date"] == fill_day.date().isoformat()
    assert t["entry_px"] == pytest.approx(lim, abs=1e-4)
    assert t["exit_reason"] == "time"
    assert t["exit_date"] == d17.date().isoformat()
    assert t["bars_held"] == 2


def test_gap_below_limit_fills_at_open():
    p = _params(time_stop_days=2)
    df, lim, fill_day = _filled_fixture(
        p, fill_row=None, tail_close=None)
    # Rebuild the fill day as a gap: open below the limit fills at the open.
    df.loc[fill_day, ["Open", "High", "Low", "Close"]] = [lim - 2, lim - 1.7, lim - 4, lim - 1]
    after = df.index[df.index > fill_day]
    df.loc[after, "Open"] = lim - 2
    df.loc[after, "High"] = lim - 1.7
    df.loc[after, "Low"] = lim - 5.7
    df.loc[after, "Close"] = lim - 2
    trades, _, _ = _run(df, p)
    t = trades.iloc[0]
    assert t["entry_px"] == pytest.approx(lim - 2, abs=1e-4)


def test_untouched_order_expires():
    p = _params()
    df = _frame()
    limit, _ = _levels(df, p)
    lim = float(limit.iloc[DIP])
    fill_day = CAL[DIP + 1]
    df.loc[fill_day, ["Open", "High", "Low", "Close"]] = [lim + 5, lim + 6, lim + 0.5, lim + 5]
    trades, _, summary = _run(df, p)
    assert len(trades) == 0
    assert summary["open_positions_at_end"] == []
    assert summary["orders_expired_unfilled"] >= 1


def _filled_fixture(p, fill_row=None, tail_close=None):
    """Standard fill at the limit on DIP+1; returns (df, lim, fill_day).

    The post-fill tail is flattened to hug the entry zone — the fill sits
    ~0.9 x ATR below the dip close, so leaving the tail at the pre-dip level
    would trigger an immediate close-above-previous-high exit on every test.
    """
    df = _frame()
    limit, _ = _levels(df, p)
    lim = float(limit.iloc[DIP])
    fill_day = CAL[DIP + 1]
    row = fill_row if fill_row is not None else [lim + 3, lim + 3.3, lim - 0.5, lim + 1]
    df.loc[fill_day, ["Open", "High", "Low", "Close"]] = row
    c = row[3] if tail_close is None else tail_close
    after = df.index[df.index > fill_day]
    df.loc[after, "Open"] = c
    df.loc[after, "High"] = c + 0.3
    df.loc[after, "Low"] = c - 3.7
    df.loc[after, "Close"] = c
    return df, lim, fill_day


def test_target_applies_only_from_day_after_entry():
    p = _params()
    df, lim, fill_day = _filled_fixture(p)
    # Entry-day high spikes far above any target: must NOT exit that day.
    df.loc[fill_day, "High"] = lim + 60
    d16 = CAL[DIP + 2]
    # Recompute levels AFTER mutations so the expected target matches the data.
    _, target = _levels(df, p)
    tgt16 = float(target.loc[d16])
    df.loc[d16, ["Open", "High", "Low", "Close"]] = [tgt16 - 1, tgt16 + 1, tgt16 - 3, tgt16 - 0.5]
    _, target2 = _levels(df, p)
    assert float(target2.loc[d16]) == pytest.approx(tgt16, abs=1e-9)  # mutation left basis intact
    trades, _, _ = _run(df, p)
    t = trades.iloc[0]
    assert t["exit_reason"] == "target"
    assert t["exit_date"] == d16.date().isoformat()
    assert t["exit_px"] == pytest.approx(tgt16, abs=1e-4)


def test_gap_open_above_target_fills_at_open():
    p = _params()
    df, lim, fill_day = _filled_fixture(p)
    d16 = CAL[DIP + 2]
    _, target = _levels(df, p)
    tgt16 = float(target.loc[d16])
    df.loc[d16, ["Open", "High", "Low", "Close"]] = [tgt16 + 2, tgt16 + 3, tgt16 + 1, tgt16 + 1.5]
    trades, _, _ = _run(df, p)
    t = trades.iloc[0]
    assert t["exit_reason"] == "target_gap"
    assert t["exit_px"] == pytest.approx(tgt16 + 2, abs=1e-4)


def test_close_above_previous_high_exits_at_close():
    p = _params()
    df, lim, fill_day = _filled_fixture(p)
    d16 = CAL[DIP + 2]
    h15 = float(df.loc[fill_day, "High"])
    _, target = _levels(df, p)
    tgt16 = float(target.loc[d16])
    c16 = h15 + 0.5
    assert c16 + 0.1 < tgt16  # geometry guard: target must not fire first
    df.loc[d16, ["Open", "High", "Low", "Close"]] = [c16 - 1, c16 + 0.1, c16 - 3, c16]
    trades, _, _ = _run(df, p)
    t = trades.iloc[0]
    assert t["exit_reason"] == "price_action"
    assert t["exit_px"] == pytest.approx(c16, abs=1e-4)


def test_same_day_price_action_exit_after_fill():
    p = _params()
    df = _frame()
    limit, _ = _levels(df, p)
    lim = float(limit.iloc[DIP])
    fill_day = CAL[DIP + 1]
    h14 = float(df.iloc[DIP]["High"])
    c15 = h14 + 1.0
    df.loc[fill_day, ["Open", "High", "Low", "Close"]] = [lim + 3, c15 + 0.3, lim - 0.5, c15]
    trades, _, _ = _run(df, p)
    t = trades.iloc[0]
    assert t["entry_date"] == t["exit_date"] == fill_day.date().isoformat()
    assert t["exit_reason"] == "price_action"
    assert t["bars_held"] == 0


def test_time_stop_fires_on_tenth_bar():
    p = _params(time_stop_days=10)
    df, lim, fill_day = _filled_fixture(p)
    trades, _, _ = _run(df, p)
    t = trades.iloc[0]
    assert t["exit_reason"] == "time"
    assert t["bars_held"] == 10
    assert t["exit_date"] == CAL[DIP + 11].date().isoformat()  # 10 bars after entry


def test_slot_cap_prefers_highest_natr():
    p = _params(max_positions=3, time_stop_days=2)
    widths = {"S1": 1.0, "S2": 2.0, "S3": 3.0, "S4": 4.0, "S5": 5.0}
    panels, members = {}, {}
    natr_at_dip = {}
    for sym, w in widths.items():
        df = _frame(h_off=0.3 * w, l_off=3.7 * w)
        limit, _ = _levels(df, p)
        lim = float(limit.iloc[DIP])
        fill_day = CAL[DIP + 1]
        df.loc[fill_day, ["Open", "High", "Low", "Close"]] = [lim + 3, lim + 3.3, lim - 0.5, lim + 1]
        panels[sym] = df
        members[sym] = _ones(df.index)
        pre = precompute_symbol_daily(df, members[sym], p)
        natr_at_dip[sym] = float(pre["natr_pct"].iloc[DIP])
    trades, _, summary = simulate(panels, members, INDEX, p)
    expected = set(sorted(natr_at_dip, key=natr_at_dip.get, reverse=True)[:3])
    touched = set(trades["symbol"]) | set(summary["open_positions_at_end"])
    assert touched == expected


def test_delisting_mid_hold_exits_at_final_print():
    p = _params()
    df, lim, fill_day = _filled_fixture(p)
    cut = CAL.get_loc(fill_day) + 4
    df = df.iloc[:cut]
    trades, _, _ = _run(df, p)
    t = trades.iloc[0]
    assert t["exit_reason"] == "delist"
    assert t["exit_date"] == df.index[-1].date().isoformat()
    assert t["exit_px"] == pytest.approx(float(df["Close"].iloc[-1]), abs=1e-4)


def test_costs_reduce_net_return_exactly():
    p = _params(cost_bps_side=50.0)
    df, lim, fill_day = _filled_fixture(p)
    d16 = CAL[DIP + 2]
    _, target = _levels(df, p)
    tgt16 = float(target.loc[d16])
    df.loc[d16, ["Open", "High", "Low", "Close"]] = [tgt16 - 1, tgt16 + 1, tgt16 - 3, tgt16 - 0.5]
    trades, _, _ = _run(df, p)
    t = trades.iloc[0]
    expected = (tgt16 * (1 - 0.005)) / (lim * (1 + 0.005)) - 1.0
    assert t["ret_net"] == pytest.approx(expected, rel=1e-6)


def test_order_day_skips_new_year_holiday():
    cal = _calendar("2024-12-10", "2025-01-31")
    assert cal[DIP].date().isoformat() == "2024-12-31"      # engineered signal day
    assert cal[DIP + 1].date().isoformat() == "2025-01-02"  # 1 Jan removed
    closes = _closes()[:len(cal)]
    df = _frame(cal=cal, closes=closes)
    p = _params(time_stop_days=2)
    limit, _ = _levels(df, p)
    lim = float(limit.iloc[DIP])
    fill_day = cal[DIP + 1]
    df.loc[fill_day, ["Open", "High", "Low", "Close"]] = [lim + 3, lim + 3.3, lim - 0.5, lim + 1]
    index = INDEX.copy()
    index.index = CAL  # wrong calendar — rebuild on cal instead
    index = pd.DataFrame({"Open": 5000.0, "High": 5001.0, "Low": 4999.0,
                          "Close": 5000.0, "Volume": 1e6}, index=cal)
    trades, _, _ = simulate({"AAA": df}, {"AAA": _ones(cal)}, index, p)
    t = trades.iloc[0]
    assert t["entry_date"] == "2025-01-02"


def test_membership_gate_blocks_signal_day():
    p = _params()
    df = _frame()
    member = _ones(CAL)
    member.iloc[DIP] = 0
    pre = precompute_symbol_daily(df, member, p)
    assert not bool(pre["signal"].iloc[DIP])
    trades, _, summary = simulate({"AAA": df}, {"AAA": member}, INDEX, p)
    assert len(trades) == 0 and summary["open_positions_at_end"] == []


def test_natr_filter_blocks_quiet_names():
    # Slow ramp + narrow ranges: the dip still clears trend and drop filters
    # but NATR(5) stays below 3% — the volatility filter must block it.
    t = np.arange(len(CAL), dtype=float)
    closes = 100.0 + 1.5 * np.minimum(t, 13)
    closes[DIP:] = closes[13] * 0.96
    df = _frame(closes=closes, h_off=0.1, l_off=0.1)
    quiet = precompute_symbol_daily(df, _ones(CAL), _params(natr_min_pct=3.0))
    loose = precompute_symbol_daily(df, _ones(CAL), _params(natr_min_pct=0.0))
    assert not bool(quiet["signal"].iloc[DIP])
    assert bool(loose["signal"].iloc[DIP])

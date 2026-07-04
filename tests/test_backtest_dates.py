"""Engine tests: positional exits across month/year boundaries, delisting
exits, and the membership gate.

House rule: date logic must carry explicit month-boundary and year-boundary
edge-case tests. All engine alignment is positional on the symbol's own bar
index; these tests prove calendar gaps (weekends, New Year holiday) cannot
shift an exit. Dates below are built with pd.to_datetime on ISO strings —
Python/pandas datetime months are 1-indexed (January == 1).
"""

import numpy as np
import pandas as pd

from scripts.backtest_baseline import BaselineParams, symbol_trades

# Permissive params: rising series -> trend filter passes; rsi_threshold=101
# -> the dip condition passes on every bar. Every bar after min_history
# therefore signals, letting the tests assert pure alignment mechanics
# (entry_overlap="per_signal" so each bar's entry is observable).
PERMISSIVE = BaselineParams(
    rsi_period=2, rsi_threshold=101.0, trend_sma=2, hold_bars=5,
    min_history=3, per_trade_usd=1000.0, entry_overlap="per_signal",
)


def _panel(dates):
    idx = pd.to_datetime(dates)
    close = pd.Series(np.linspace(100.0, 120.0, len(idx)), index=idx)
    prices = pd.DataFrame({
        "Open": close, "High": close * 1.01, "Low": close * 0.99,
        "Close": close, "Volume": 1e6,
    })
    member = pd.Series(1, index=idx, dtype="int64")
    return prices, member


# Trading days spanning the January -> February 2024 month boundary
# (2024-01-27/28 and 2024-02-03/04 are weekends).
MONTH_BOUNDARY_DATES = [
    "2024-01-22", "2024-01-23", "2024-01-24", "2024-01-25", "2024-01-26",
    "2024-01-29", "2024-01-30", "2024-01-31", "2024-02-01", "2024-02-02",
    "2024-02-05", "2024-02-06",
]

# Trading days spanning the 2024 -> 2025 year boundary (market closed
# 2024-12-25 Christmas and 2025-01-01 New Year; weekends omitted).
YEAR_BOUNDARY_DATES = [
    "2024-12-20", "2024-12-23", "2024-12-24", "2024-12-26", "2024-12-27",
    "2024-12-30", "2024-12-31", "2025-01-02", "2025-01-03", "2025-01-06",
    "2025-01-07", "2025-01-08",
]


def _trade_entered_on(trades, date_iso):
    match = [t for t in trades if t["entry_date"] == date_iso]
    assert match, f"expected a trade entered {date_iso}; got {[t['entry_date'] for t in trades]}"
    return match[0]


def test_exit_is_positional_across_month_boundary():
    prices, member = _panel(MONTH_BOUNDARY_DATES)
    trades = symbol_trades("TEST", prices, member, PERMISSIVE)
    t = _trade_entered_on(trades, "2024-01-26")
    # 5 bars after Fri 2024-01-26: 29, 30, 31 Jan, 1 Feb, 2 Feb.
    assert t["exit_date"] == "2024-02-02"
    assert t["bars_held"] == 5
    assert t["exit_reason"] == "time"
    # Calendar distance is 7 days; positional distance is 5 bars. If the
    # engine ever regresses to calendar arithmetic this assertion fires.
    gap = (pd.Timestamp(t["exit_date"]) - pd.Timestamp(t["entry_date"])).days
    assert gap == 7


def test_exit_is_positional_across_year_boundary():
    prices, member = _panel(YEAR_BOUNDARY_DATES)
    trades = symbol_trades("TEST", prices, member, PERMISSIVE)
    t = _trade_entered_on(trades, "2024-12-27")
    # 5 bars after Fri 2024-12-27: 30, 31 Dec, 2, 3, 6 Jan (1 Jan closed).
    assert t["exit_date"] == "2025-01-06"
    assert t["bars_held"] == 5
    gap = (pd.Timestamp(t["exit_date"]) - pd.Timestamp(t["entry_date"])).days
    assert gap == 10  # weekends + New Year holiday absorbed positionally


def test_delisting_exit_realises_final_print():
    # Series ends 3 bars after the 2024-12-27 signal — a delisting. The trade
    # must exit on the final bar with the dedicated reason, not vanish.
    prices, member = _panel(YEAR_BOUNDARY_DATES[:8])  # ends 2025-01-02
    trades = symbol_trades("TEST", prices, member, PERMISSIVE)
    t = _trade_entered_on(trades, "2024-12-27")
    assert t["exit_date"] == "2025-01-02"
    assert t["bars_held"] == 3
    assert t["exit_reason"] == "delisted_or_series_end"


def test_signal_on_final_bar_is_untradable():
    prices, member = _panel(MONTH_BOUNDARY_DATES)
    trades = symbol_trades("TEST", prices, member, PERMISSIVE)
    assert all(t["entry_date"] != "2024-02-06" for t in trades)


def test_membership_gate_blocks_non_member_days():
    prices, member = _panel(MONTH_BOUNDARY_DATES)
    member.loc[pd.Timestamp("2024-01-26")] = 0  # removed from index that day
    trades = symbol_trades("TEST", prices, member, PERMISSIVE)
    assert all(t["entry_date"] != "2024-01-26" for t in trades)
    # Neighbouring member days still trade.
    assert any(t["entry_date"] == "2024-01-25" for t in trades)


def test_signal_composition_requires_trend_and_dip():
    # Strictly falling series: RSI pinned at 0 (dip true) but price is below
    # any SMA -> trend filter must block every signal.
    idx = pd.to_datetime(MONTH_BOUNDARY_DATES)
    close = pd.Series(np.linspace(120.0, 100.0, len(idx)), index=idx)
    prices = pd.DataFrame({"Open": close, "High": close, "Low": close,
                           "Close": close, "Volume": 1e6})
    member = pd.Series(1, index=idx, dtype="int64")
    params = BaselineParams(rsi_period=2, rsi_threshold=20.0, trend_sma=2,
                            hold_bars=5, min_history=3)
    assert symbol_trades("TEST", prices, member, params) == []
    # Rising series: trend true but RSI ~100 -> dip blocks every signal.
    prices_up, member_up = _panel(MONTH_BOUNDARY_DATES)
    assert symbol_trades("TEST", prices_up, member_up, params) == []

"""Indicator correctness tests.

The RSI tests pin the implementation two ways:
  1. the vectorised ewm form must equal an explicit recursive loop of the
     same definition (catches vectorisation bugs), and
  2. it must converge to the SMA-seeded (TA-Lib style) variant well inside
     the engine's warm-up window (justifies the documented equivalence).
"""

import numpy as np
import pandas as pd

from scripts import indicators


def _random_walk(n: int, seed: int = 42) -> pd.Series:
    rng = np.random.default_rng(seed)
    steps = rng.normal(0.0, 1.0, n)
    return pd.Series(100.0 + np.cumsum(steps), index=pd.RangeIndex(n), name="close")


def _rsi_loop_ewm(close: pd.Series, period: int) -> pd.Series:
    """Reference: the same ewm recursion written as an explicit loop."""
    delta = close.diff().to_numpy()
    out = np.full(len(close), np.nan)
    avg_g = avg_l = None
    seen = 0
    for k in range(1, len(close)):
        g = max(delta[k], 0.0)
        l = max(-delta[k], 0.0)
        if avg_g is None:
            avg_g, avg_l = g, l
        else:
            avg_g += (g - avg_g) / period
            avg_l += (l - avg_l) / period
        seen += 1
        if seen < period:
            continue
        if avg_l == 0.0 and avg_g == 0.0:
            out[k] = 50.0
        elif avg_l == 0.0:
            out[k] = 100.0
        else:
            out[k] = 100.0 - 100.0 / (1.0 + avg_g / avg_l)
    return pd.Series(out, index=close.index)


def _rsi_sma_seeded(close: pd.Series, period: int) -> pd.Series:
    """Reference: TA-Lib / StockCharts convention (SMA seed, then recursion)."""
    delta = close.diff().to_numpy()
    out = np.full(len(close), np.nan)
    gains = np.clip(delta[1: period + 1], 0.0, None)
    losses = np.clip(-delta[1: period + 1], 0.0, None)
    avg_g, avg_l = gains.mean(), losses.mean()
    for k in range(period, len(close)):
        if k > period:
            g = max(delta[k], 0.0)
            l = max(-delta[k], 0.0)
            avg_g = (avg_g * (period - 1) + g) / period
            avg_l = (avg_l * (period - 1) + l) / period
        out[k] = 50.0 if (avg_l == 0.0 and avg_g == 0.0) else (
            100.0 if avg_l == 0.0 else 100.0 - 100.0 / (1.0 + avg_g / avg_l)
        )
    return pd.Series(out, index=close.index)


def test_rsi_matches_recursive_loop_exactly():
    close = _random_walk(400)
    for period in (2, 5, 14):
        vec = indicators.wilder_rsi(close, period)
        ref = _rsi_loop_ewm(close, period)
        pd.testing.assert_series_equal(vec, ref, check_names=False, atol=1e-10, rtol=0)


def test_rsi_converges_to_sma_seeded_variant_within_warmup():
    close = _random_walk(600, seed=7)
    period = 5
    vec = indicators.wilder_rsi(close, period).to_numpy()
    seeded = _rsi_sma_seeded(close, period).to_numpy()
    tail = slice(15 * period, None)  # engine min_history (210 bars) is far beyond this
    assert np.nanmax(np.abs(vec[tail] - seeded[tail])) < 1e-4


def test_rsi_extremes_and_bounds():
    up = pd.Series(np.arange(1.0, 61.0))          # strictly rising
    down = pd.Series(np.arange(60.0, 0.0, -1.0))  # strictly falling
    flat = pd.Series(np.full(60, 5.0))
    assert np.allclose(indicators.wilder_rsi(up, 5).iloc[10:], 100.0)
    assert np.allclose(indicators.wilder_rsi(down, 5).iloc[10:], 0.0)
    assert np.allclose(indicators.wilder_rsi(flat, 5).iloc[10:], 50.0)
    walk = _random_walk(300, seed=1)
    rsi = indicators.wilder_rsi(walk, 5).dropna()
    assert rsi.between(0.0, 100.0).all()


def test_sma_warmup_and_value():
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    out = indicators.sma(s, 3)
    assert out.isna().sum() == 2
    assert out.iloc[2] == 2.0 and out.iloc[4] == 4.0


def test_natr_positive_and_scaled():
    close = _random_walk(300, seed=3).abs() + 50.0
    high = close * 1.01
    low = close * 0.99
    n = indicators.natr(high, low, close, 5).dropna()
    assert (n > 0).all()
    assert (n < 0.5).all()  # sanity: normalised, not absolute

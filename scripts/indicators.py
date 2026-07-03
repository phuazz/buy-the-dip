"""Indicator primitives for the buy-the-dip engine.

All functions are pure and operate on pandas Series aligned to the caller's
index. Conventions:

- RSI uses Wilder smoothing implemented as ewm(alpha=1/period, adjust=False).
  Early values differ slightly from implementations that seed with a simple
  average of the first `period` changes (TA-Lib style); the difference decays
  geometrically and is negligible well before the engine's minimum-history
  requirement (>= 200 bars for the trend filter). The engine must never act
  on signals inside the indicator warm-up window.
- No calendar arithmetic happens in this module — everything is positional on
  the caller's index. (Python datetime months are 1-indexed where dates do
  appear in this project.)
"""

from __future__ import annotations

import pandas as pd


def sma(close: pd.Series, period: int) -> pd.Series:
    """Simple moving average; NaN until `period` observations exist."""
    if period < 1:
        raise ValueError("period must be >= 1")
    return close.rolling(period, min_periods=period).mean()


def wilder_rsi(close: pd.Series, period: int) -> pd.Series:
    """Relative Strength Index with Wilder smoothing.

    Degenerate windows: all-gain -> 100, all-loss -> 0 (both fall out of the
    formula), all-flat (zero gain and zero loss) -> 50 by convention.
    """
    if period < 1:
        raise ValueError("period must be >= 1")
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    rsi = 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
    rsi = rsi.mask((avg_loss == 0.0) & (avg_gain > 0.0), 100.0)
    rsi = rsi.mask((avg_loss == 0.0) & (avg_gain == 0.0), 50.0)
    return rsi


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    """True range: max(H-L, |H-prevC|, |L-prevC|). First bar falls back to H-L."""
    prev_close = close.shift(1)
    parts = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    )
    return parts.max(axis=1)


def wilder_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    """Average True Range, Wilder-smoothed (same smoothing note as RSI)."""
    if period < 1:
        raise ValueError("period must be >= 1")
    return true_range(high, low, close).ewm(
        alpha=1.0 / period, adjust=False, min_periods=period
    ).mean()


def natr(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    """Normalised ATR (ATR / close) — the signal-strength feature from the
    source article: higher values at entry associated with higher average
    profit per trade."""
    return wilder_atr(high, low, close, period) / close

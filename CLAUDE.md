# CLAUDE.md — buy-the-dip

Layers on top of `C:\dev\CLAUDE.md`. Only divergences and hard rules specific to this project.

## Data layer

- **Results come only from `NorgateProvider`.** It is the only survivorship-bias-free path (point-in-time S&P 500 membership + delisted securities). `YFinanceProvider` exists for engine plumbing only; never quote a statistic produced through it.
- **NDU must be running.** The `norgatedata` package proxies the local Norgate Data Updater Windows app. If a call fails with "Unable to obtain valid status", start NDU — do not debug the Python.
- **Norgate licence: never commit raw price or constituent data.** `data/cache/` is gitignored and stays that way. Derived aggregates (trade lists, equity curves, summary JSON) are acceptable to commit.
- **Trial window caveat**: the 3-week trial exposes only ~2 years of history at Platinum level. A backtest on the trial window is a plumbing check, never a strategy verdict. Full replication (2000→) requires a paid Platinum subscription.

## Engine discipline

- The published baseline is the engine's acceptance test: S&P 500 PIT, close > SMA200, Wilder RSI(5) < 20, hold 5 bars, close-to-close, no costs, since 2000 → **~25,000 trades, 56.81% winners**. Reproduce this before trusting any variant built on the engine.
- Exit alignment is positional on each symbol's own bar index (t+5 bars), never calendar-day arithmetic. Month-boundary and year-boundary behaviour is covered in `tests/test_backtest_dates.py` — keep those tests passing.
- Any portfolio-level result must include costs (commission + slippage). The costless run exists solely to match the published anchor.
- RSI is Wilder-smoothed. If a result is sensitive to the RSI variant, run the SMA/Cutler variant explicitly and report both.
- Delisted names: with padding NONE the series simply ends; an open trade exits at the final print with `exit_reason='delisted_or_series_end'`. Do not filter these trades out — they are the point of the exercise.

## Dashboard (Phase 4, later)

- Style per `C:\dev\design.md`; architecture template.html + `scripts/pipeline.py` → `docs/index.html`.
- Publish derived JSON only. No licensed raw data on GitHub Pages.

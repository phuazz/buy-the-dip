# Phase 2 pre-registration — weekly dip-buying portfolio variant

**Written 2026-07-03, while only the 2-year Norgate trial window (2024-07-03 →
2026-07-02) is available.** That is deliberate: the rule space, defaults and
evaluation protocol below are committed before any full-history result exists,
so the full-history evaluation cannot quietly become an in-sample fishing
expedition. The trial window is used for **mechanics validation only** — no
rule choice may cite trial-window performance as justification. Deviations
from this document must be logged in the README status section with a reason.

## Design constraints taken from the source material

From the CrackingMarkets weekly live model (shape disclosed, rules not):
weekly timeframe; trades only in a positive market regime; buys S&P 500 stocks
in an uptrend during a weekly-chart correction; up to 10 positions at 10%
each; favours lower-volatility stocks; 10% stop-loss; profit-target exits.
Published profile for calibration (not replication): ~19 trades/year, 62%
winners, AvgWin 16.08% vs AvgLoss 10.23%, WinLen ≈ 121 trading days, profit
factor 2.31, Sharpe 1.07, MaxDD −18.10%, average usage 80.95%.

## v1 primary configuration (fixed)

| Component | Rule |
|---|---|
| Universe | S&P 500 members, point-in-time at decision date; price > $5; median daily dollar volume (63d) > US$5m |
| Decision cadence | Weekly, at the last trading close of each calendar week (W-FRI labels) |
| Regime gate | `$SPX` weekly close > 40-week SMA → new entries allowed. Gate OFF blocks **new entries only**; open positions continue to their own exits |
| Stock trend | Weekly close > 40-week SMA of weekly closes |
| Dip trigger | Weekly Wilder RSI(3) < 25 at decision close |
| Ranking | When candidates exceed free slots: ascending 26-week volatility of weekly log returns (low-volatility preference, per the live model) |
| Sizing | 10% of portfolio equity per new position; fractional shares; maximum 10 concurrent; a new position is skipped if available cash is below 2% of equity |
| Entry | At the decision close (source convention). Registered sensitivity: next trading day's open |
| Stop-loss | 10% below entry, monitored **daily**: if open ≤ stop, fill at open (gap-aware); else if low ≤ stop, fill at stop. Stop is checked before target within any day (conservative) |
| Profit target | 15% above entry: if daily high ≥ target (after the stop check), fill at target |
| Time stop | None in v1 (published WinLen implies multi-month holds) |
| Delisting | Exit at the final available print |
| Costs | 7 bps per side (≈2 commission + 5 slippage) |
| Cash | Earns nothing (conservative) |
| Initial capital | US$100,000 (scale-free; fractional shares) |

## Registered alternates (evaluated on the design segment ONLY)

1. Dip trigger: (b) two consecutive lower weekly closes; (c) close 5–15% below the 8-week high.
2. Ranking: descending 5-week normalised ATR (the research-note finding that higher short-term volatility raises average profit per trade — the direct tension with the live model's low-volatility preference, to be resolved empirically).
3. Regime gate: `#SPX%MA200` breadth > 50% (Norgate ships this precomputed).
4. RSI threshold plateau: 20 / 25 / 30. Target plateau: 10% / 15% / 20%. Chosen value must sit on a flat plateau, not a spike.
5. Time stop: 26 weeks. Cash: T-bill accrual. Regime OFF variant: force-exit open positions.

## Evaluation protocol (full history, after Platinum subscription)

- **Design segment: 2000-01 → 2017-12.** Mirrors the vendor's own information
  set — their model went live in 2018, so everything from 2018 is their live
  period and our validation period.
- **Validation segment: 2018-01 → present.** Touched once, with the primary
  configuration plus at most two shortlisted alternates from the design
  segment. No iteration on validation results.
- Decision gates to take the variant forward: validation Sharpe ≥ 0.7;
  validation MaxDD no worse than −25%; profit factor ≥ 1.5; trade rate and
  holding periods within the published family (~15–25 trades/year, holds of
  months); parameter plateaus flat.
- Robustness battery: cost sensitivity (3 / 7 / 14 bps per side); entry
  execution (close vs next open); stop monitoring convention (daily vs
  weekly-close-only); regime slices 2008, 2020, 2022.
- Deployment, if ever, follows the house entry-point discipline: after a flat
  or negative stretch of the strategy's own equity curve, never after a strong
  run.

## Three ways Phase 2 could be silently wrong — and the defences

1. **In-sample seduction on the trial window** — a 2-year, one-regime sample
   would reward whatever suits 2025. Defence: this document; trial data is
   mechanics-only; all selection happens on the 2000-2017 design segment.
2. **Stop/target fill fiction on weekly bars** — evaluating stops at weekly
   closes hides intraweek breaches and flatters MaxDD. Defence: daily
   monitoring with gap-aware fills, stop-before-target convention, and a
   registered sensitivity comparing monitoring conventions.
3. **Regime-filter hindsight** — picking the gate that happens to dodge 2022
   after seeing 2022. Defence: gate candidates registered now, selected on the
   design segment only, and the gate blocks entries rather than forcing exits
   so its effect is structural, not a market-timing overlay fitted to crashes.

## Mechanics validation record (trial window — MECHANICS ONLY)

To be appended by `scripts/backtest_weekly.py` runs. Numbers in this section
carry no evidential weight for the strategy.

- **2026-07-03** — v1 primary, 542-name trial universe, entry=close, 7 bps per
  side, window 2024-07-03 → 2026-07-02 (1.99 years → MECHANICS ONLY). All
  paths exercised: 29 closed trades (22 target / 6 stop / 1 gap-stop), 10/10
  slots filled at window end, 0 symbol load failures, 0 dropped pending
  orders. Exit geometry visible exactly as designed: AvgWin +14.84%
  (target-capped), AvgLoss −10.15% (stop-anchored), 14.6 trades/year, average
  usage 52.97% (regime warm-up truncates the tradeable window). Full output in
  `data/weekly_summary.json`. These numbers carry no evidential weight.

## Validation record (single pass, executed 2026-07-04)

Per protocol: the primary plus two design-segment shortlisted alternates —
dip trigger (c) "below the 8-week high" (design Sharpe 1.02) and its
combination with the breadth regime gate (design Sharpe 1.10) — run once on
2018-01 → 2026-07 (data end), with no iteration on the results.

| configuration | ROR p.a. | Sharpe | MaxDD | PF | win% | trades/yr |
|---|---|---|---|---|---|---|
| v1 primary | 5.41% | 0.548 | −17.2% | 1.42 | 50.8 | 22.3 |
| below_high | 4.87% | 0.479 | −23.4% | 1.30 | 48.4 | 25.1 |
| below_high + breadth | 5.06% | 0.498 | −20.6% | 1.32 | 49.0 | 23.6 |

**Decision gates (Sharpe ≥ 0.7, MaxDD ≥ −25%, PF ≥ 1.5, 15-25 trades/yr):
FAILED for all three configurations** (MaxDD and trade rate passed; Sharpe
and profit factor did not). The design-segment ranking inverted
out-of-sample — the unmodified primary validated best. Decision per this
pre-registration: **the variant is not taken forward**; the validation
segment is closed; any successor idea requires a fresh pre-registration.
Full battery, slices and discussion in the filed review and README status.

*Pre-registered 2026-07-03. Any edit after full-history data exists must be
logged as a deviation.*

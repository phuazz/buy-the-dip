# Phase 3 pre-registration — daily limit-order dip variant (Nasdaq 100)

**Written 2026-07-03, while only the 2-year Norgate trial window (2024-07-03 →
2026-07-02) is available.** Same discipline as `PHASE2_DESIGN.md`: rules,
conventions and the evaluation protocol are committed before any full-history
result exists; the trial window is used for **mechanics validation only**;
deviations must be logged in the README status section with a reason.

## Source

CrackingMarkets, "Buying Short-Term Dips in Stocks [backtester]" (Interactive
Models, 2025-01-27; PDF captured 2026-07-03). Unlike the weekly live model,
this variant is **fully disclosed** — rules, default parameters, and
portfolio-level results — so Phase 3 is a *replication with stated fill
conventions*, not a rule-design exercise. Their stated out-of-sample boundary
is January 2024 (the model trades live from then).

## v1 primary configuration (fixed; their published defaults)

| Component | Rule |
|---|---|
| Universe | Nasdaq 100 members, point-in-time at signal date (Norgate index name "Nasdaq 100"); price > $5; no additional liquidity screen in v1 (NDX names are liquid; screen registered as an alternate for the delisted tail) |
| Trend filter | Signal-day close > 200-day SMA |
| Dip trigger | Signal-day close ≥ 3% below the previous close |
| Volatility filter | 100 × ATR(5) / Close > 3 at the signal close (Wilder ATR) |
| Order | Next trading day ONLY: limit buy at signal close − 0.9 × ATR(5, signal day). Unfilled orders expire at that day's close |
| Fill model | Filled iff next day's low ≤ limit; fill price = min(open, limit) — a gap open below the limit fills at the open |
| Capacity / ranking | Maximum 10 concurrent positions. Orders are placed only for free slots (10 − open − pending), preferring the **highest** ATR(5)/Close at signal (the opposite ranking direction to Phase 2's weekly variant, as published) |
| Sizing | 10% of portfolio equity at order placement; fractional shares; capped by available cash at fill; skip below 2% of equity |
| Exit — profit target | From the day AFTER entry (source: "triggered on days after the entry"): target_d = close(d−1) + 0.5 × ATR(5, d−1), recomputed daily (trailing). Gap open ≥ target fills at open; else intraday high ≥ target fills at target |
| Exit — price action | Close > previous day's high → exit at that close (permitted from entry day onward) |
| Exit — time stop | Still open at the close of the 10th trading day after entry → exit at that close |
| Exit — delisting | Final available print |
| Exit precedence within a day | gap-open target → intraday target → (at the close) price-action → time stop |
| Stop-loss | **None** (as published; risk is carried by the trend filter, the time stop and position sizing) |
| Costs | 7 bps per side (house default; the source states "commissions included" without disclosing the model). Sensitivities: 3 / 14 bps per side |
| Initial capital | US$100,000 (scale-free; the source form uses $10,000 — noted, irrelevant under fractional sizing) |

## Interpretation conventions registered as such

The source discloses rules but not an execution specification. Three
conventions are fixed here and count as deviations if later revised:

1. **Trailing target basis** — "last closing price + 0.5 × ATR(5)" is read as
   previous close + 0.5 × ATR(5, previous day), recomputed every day the
   position is open.
2. **Order lifetime** — the limit order exists for exactly one trading day
   (the day after the signal), per "on the day after the signal".
3. **Same-day interactions** — a just-filled position may exit via the
   price-action close rule the same day, but not via the target (source is
   explicit the target applies from days after entry). Exits are processed
   before new fills release capacity the same day at the portfolio level.

## Registered alternates (design segment only)

The dials the source's own backtester exposes, plus two data screens:

1. Dip threshold: −2% / −3% / −4%.
2. Entry distance: 0.5 / 0.9 / 1.2 × ATR(5).
3. Target distance: 0.3 / 0.5 / 0.8 × ATR(5).
4. Max positions: 5 / 10 / 20.
5. Volatility filter off (NATR floor 0) vs 3%.
6. Median dollar-volume screen for the pre-2005 delisted tail.
7. S&P 500 universe transplant (does the edge survive on the broader index?).

## Replication anchors (their full-history results, 1994 → early 2025)

- Annual return ≈ **19.17%** (index buy-and-hold 13.73%).
- Max drawdown ≈ **−22.55%** (index −82.90%).
- Average capital usage ≈ **13.9%**.
- Defaults: $10k capital, 10 slots, −3% drop, 0.9 ATR entry, 0.5 ATR exit.

**Acceptance gate for Phase 3 replication (full history, post-Platinum):**
CAGR within ±3 points, MaxDD within ±5 points, average usage within ±4 points
of the anchors, using their defaults and our stated fill conventions. Misses
are investigated in this order: fill model → universe construction (PIT
membership around index reshuffles) → adjustment basis → cost model.

## Evaluation protocol (full history, post-Platinum)

- The primary configuration is theirs, fully specified — the whole 1994→ run
  is a replication, not a fit. Parameter-plateau checks (alternates above) run
  on the **design segment 1994-2017 only**; the validation segment 2018→ is
  touched once. Their live boundary (2024-01) is additionally reported as a
  sub-slice.
- Robustness battery: cost sensitivity, fill-model sensitivity (require low <
  limit strictly; fill at limit always vs min(open, limit)), regime slices
  2000-02, 2008, 2020, 2022.
- Portfolio-fit question (the reason this variant exists): correlation and
  capital-sharing behaviour against the Phase 2 weekly variant — the source's
  ~13.9% average usage is the stacking argument. Deployment, if ever, follows
  house entry-point discipline.

## Three ways Phase 3 could be silently wrong — and the defences

1. **Limit-fill fiction** — assuming fills the market would not have given
   (touch ≠ fill at size). Defence: conservative fill only when low ≤ limit,
   fill-model sensitivity registered, and the limit price itself is the
   protection (entry 0.9 × ATR below an already −3% close).
2. **Universe look-ahead at reshuffles** — Nasdaq 100 membership churns
   heavily (dot-com era); wrong membership dating manufactures edge. Defence:
   point-in-time membership gate on the signal day from Norgate; delisted
   members included via the delisted database; the 1994-2003 sub-slice gets a
   dedicated look in Phase 3b.
3. **Trailing-target generosity** — an intraday target fill assumes the tick
   printed at our price. Defence: the stated convention mirrors a resting
   limit-sell (a gap open above the target fills at the open, exactly as a
   real resting order would); the intraday-touch case is sensitivity-tested
   (require high strictly above target), and the no-stop-loss design is
   stress-tested on the 2000-02 and 2008 slices where it hurts most.

## Mechanics validation record (trial window — MECHANICS ONLY)

To be appended by `scripts/backtest_daily_limit.py` runs. Numbers here carry
no evidential weight.

- **2026-07-03** — v1 primary, 125-name Nasdaq 100 PIT trial universe (current
  & past), window 2024-07-03 → 2026-07-02 (1.98 years → MECHANICS ONLY). All
  paths exercised: 93 closed trades across the full exit set (61 target /
  20 gap-target / 11 price-action / 1 time stop), 578 limit orders expired
  unfilled (the fill discipline that drives the published low capital usage),
  0 symbol failures. Character matches the published family: 77.4% winners,
  winners held 1.4 bars vs losers 3.9, average usage 3.77% on this quiet
  window, and the end-of-window book is the highest-NATR names (semis and
  storage) — the exact opposite of the Phase 2 weekly book, as designed.
  Full output in `data/daily_limit_summary.json`. No evidential weight.

*Pre-registered 2026-07-03. Any edit after full-history data exists must be
logged as a deviation.*

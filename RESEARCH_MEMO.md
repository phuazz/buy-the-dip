# Running memo — buy-the-dip post-subscription session (Phase 1 / 2b / 3b design segments)

**Date:** 2026-07-04. **Status: FINAL — owner approved all three asks 2026-07-04 (validation pass, full-window replication, publication). Results published in commit c20735f; this memo is the running record behind the filed review.**

Norgate Platinum active 2026-07-04 (6-month term to 2027-01-04). NDU full-depth archive sync verified before any run.

## 0. Runbook steps 0-2 (data integrity)

- Smoke test: AAPL 9,192 bars 1990-01-02 → 2026-07-02; delisted DB 21,046 symbols (trial held only within-window deaths); 40-symbol delisted sample shows first bars distributed 1990-2021 with zero clustering at 2024+ (no partial-sync signature). SPX membership genuinely PIT (MSFT first member-day 1994-06-07, its true join date). NDX membership floor 1993-10-01 — explains the source's 1994 backtest start; covers our design segment.
- Depth gate demonstrated: weekly engine hard-failed on the warm trial cache ("Cache depth mismatch... re-run with --refresh-cache", exit 1). No bypass, no manual cache deletion.
- Universes rebuilt by full membership scan (35,467 candidates each, ~16 min each): SPX Current & Past 542 → **1,299**; NDX 125 → **479**. Both **set-identical** to Norgate's own watchlists (which now work post-subscription — trial watchlist quirk, open issue 6, is resolved). Two independent construction paths agreeing symbol-for-symbol.

## 1. Phase 1 — anchor replication: PASS, with a convention discovery

Official run (Wilder RSI(5)<20, close>SMA200, 5-bar positional exits, $1k/trade, costless, PIT membership, TOTALRETURN series, fetch 1998→, eval 2000-01-01 → 2024-09-19):

| Metric | Published | Replicated | Verdict |
|---|---|---|---|
| Trades | ~25,000 | **25,603** | +2.4% ✓ |
| Winners | 56.81% | **57.04%** | +0.23 pts ✓ |
| Avg win vs loss | win > loss | +3.19% / −2.93% | ✓ |

- **Convention discovery:** entering on every signal bar ("per_signal") gives 52,129 trades / 57.22% on the same window — ~2.09x the anchor with near-identical win rate. One-open-position-per-symbol ("no_reentry", new engine default) reproduces the anchor. The source's "overlapping trades allowed" means portfolio-level concurrency, not same-symbol pyramiding. RSI dip episodes persist ~2 days on average, hence the doubling.
- Resolves open issue 7: the trial window's "2x trade rate" was this convention, not the 2025 regime. Entries/year 2000-2023 mean 1,027 vs anchor-implied ~1,012; minimum 2008 (319 — SMA200 filter), maximum 2021 (1,583).
- Resolves open issue 1 in practice: Wilder smoothing replicates the anchors; the Cutler/SMA variant test is unnecessary for acceptance.
- Full window to 2026-07-01: 27,596 trades, 56.90% winners, PF 1.43, 30 delisting exits realised, 0 symbol failures, 1,029/1,299 symbols traded (91 symbols dead before the 1998 fetch start — correctly present in the universe, absent from the window).
- Files: `data/baseline_anchor_*.{csv,json}`, `data/baseline_noreentry_full_*.{csv,json}`, plus the per-signal exploratory run `data/baseline_full_*.{csv,json}` (pre-flag artefact; params JSON lacks `entry_overlap`).

## 2. Conventions fixed / deviations logged this session

1. **Baseline entry overlap** (above): engine default is now `no_reentry`; `--entry-overlap per_signal` preserves the stacked variant. The Phase 0 trial status entry (2,302 trades) was per_signal; noted, not re-stated.
2. **Price-filter basis (Phase 2b/3b engines):** the registered "price > $5" and dollar-volume screens now read the **unadjusted (actual traded) series** by default. Back-adjusted prices shrink early history for split-heavy compounders (AAPL's TOTALRETURN close in 2000 ≈ $0.11; NVDA far smaller) — an adjusted-basis screen would systematically exclude the era's best names, a reverse-survivorship distortion. Indicator maths stays on the adjusted series (RSI/SMA/ATR are scale-free). `--price-basis adjusted` is retained and run once as a sensitivity. This is an implementation clarification bringing the code into line with the registered rule's plain meaning; logged as a deviation-class change because the 2a/3a engines (mechanics-validated on the trial window, where the two bases coincide) behaved otherwise.
3. **Phase 3b calendar/benchmark: `$NDX`** (1985→) instead of `$NDXTR` (starts 1999-03) — a TR calendar would silently amputate 1994-1999 from the design segment. Benchmark CAGR/MaxDD therefore reference the price index; stated wherever quoted.
4. **T-bill symbol for the cash alternate: `%IRX`** (Norgate Economic DB, 1960→; `$IRX` does not exist in Norgate). ACT/252 accrual approximation, sensitivity-grade.
5. **Phase 3b SPX transplant window is 2000-2017** (not 1994-2017): the SPX cache is fetched from 1998 per Phase 1 conventions; stated beside the result.
6. **NDX membership floor 1993-10-01** (Norgate's constituent history start): design-segment start 1994-01 is fully covered; nothing before it is claimable.

## 3. Phase 2b design segment (2000-01 → 2017-12) — results

18 runs (17 battery + combination), all clean, 0 symbol failures, 0 dropped orders. Universe 1,208 loaded of 1,299 (91 names dead before the 1998 fetch start). Benchmark note: summary benchmark is the $SPX price index (5.18% CAGR, −56.8% MaxDD on the segment); S&P 500 total return over the segment is roughly 7.3% p.a.

| run | tr/yr | win% | avgW% | avgL% | PF | CAGR% | Sharpe | MaxDD% | usage% |
|---|---|---|---|---|---|---|---|---|---|
| **primary (v1)** | 20.9 | 56.5 | 14.7 | −10.3 | 2.04 | 7.6 | 0.79 | −29.3 | 72.5 |
| dip below_high | 21.8 | 60.0 | 14.8 | −10.4 | 2.14 | 10.3 | 1.02 | −17.8 | 76.4 |
| regime breadth | 20.9 | 60.1 | 14.6 | −10.5 | 2.14 | 9.4 | 0.97 | −13.1 | 75.8 |
| **combo (below_high + breadth)** | 21.0 | 62.3 | 14.8 | −10.4 | 2.34 | 10.9 | 1.10 | −15.9 | 77.7 |
| dip lower_closes | 19.1 | 57.3 | 14.2 | −10.3 | 1.98 | 7.0 | 0.75 | −15.1 | 76.7 |
| rank high_natr | 40.8 | 46.9 | 14.8 | −10.3 | 1.23 | 5.1 | 0.43 | −26.1 | 65.9 |
| rsi20 / rsi30 | 19.5 / 21.6 | 58.3 / 55.5 | — | — | 2.15 / 1.93 | 7.9 / 7.5 | 0.88 / 0.78 | −24.7 / −24.9 | — |
| target10 / target20 | 31.1 / 16.9 | 68.0 / 54.6 | 9.8 / 19.5 | — | 2.18 / 2.61 | 10.3 / 9.8 | 1.11 / 0.99 | −19.8 / −25.9 | — |
| timestop26 | 26.6 | 59.2 | 11.9 | −9.5 | 1.98 | 8.2 | 0.85 | −29.3 | 71.4 |
| cash tbill | 20.9 | 56.5 | — | — | 2.06 | 8.1 | 0.84 | −28.8 | 72.5 |
| regime-off-exit | 30.3 | 49.4 | 10.5 | −6.5 | 1.68 | 5.5 | 0.64 | −25.4 | 59.3 |
| cost 3 / 7 / 14 bps | 20.9 | 56.5 | — | — | 2.07/2.04/1.98 | 7.8/7.6/7.3 | 0.81/0.79/0.76 | ≈−29 | — |
| entry next_open | 20.5 | 59.0 | 14.6 | −10.3 | 2.40 | 8.8 | 0.90 | −28.4 | 72.9 |
| monitor weekly_close | 16.9 | 62.1 | 17.2 | −13.4 | 2.37 | 9.3 | 0.86 | −23.3 | 76.0 |
| basis adjusted | 21.0 | 57.4 | 14.7 | −10.4 | 2.13 | 8.2 | 0.85 | −28.6 | 72.4 |

Readings:

1. **The primary's entire −29.3% MaxDD is the 2000-02 bear** (slice: −8.5% return, 104 trades at 38.5% winners — the 40-week cap-weighted SMA gate whipsawed and kept admitting entries). 2008 was handled (1 trade, −4.5%).
2. **Two registered alternates fix that episode via different channels and beat the primary on every headline metric at the same trade rate:** below_high (2000-02: +16.3%, −15.3% DD — buys measured pullbacks, not capitulation) and the breadth gate (2000-02: +15.0%, −11.2% DD; 2008: zero entries — breadth dies before the cap-weighted index breaks its SMA).
3. **Their combination is additive**: Sharpe 1.10, MaxDD −15.9%, PF 2.34, 62.3% winners, 21 trades/yr; 2000-02 +26.3% at −12.1% DD; 2008 zero entries. Its profile sits on top of the published live-model statistics (62.12% win, PF 2.31, −18.1% MaxDD, 11.07% ROR) — noted as encouraging, and explicitly NOT evidence: the validation pass decides.
4. **Plateaus:** RSI 20/25/30 flat (0.88/0.79/0.78) — 25 acceptable. Target 10/15/20 **V-shaped** (1.11/0.79/0.99): no flat plateau exists on this dial; target10 additionally shifts the model's character away from the published family (68% win, 9.8% avg win, 31 tr/yr). Per the pre-registered flat-plateau rule, not selected; recorded as a validation-era watch item.
5. **Ranking direction resolved (open issue 4, weekly context):** high-NATR ranking is decisively worse (Sharpe 0.43, 46.9% win) — the live model's low-volatility preference is right in a portfolio-with-stops context; the research note's high-ATR finding does not transfer from per-trade daily statistics to weekly portfolio selection.
6. **Honesty checks behave as pre-registered:** weekly-close monitoring flatters (Sharpe 0.86 vs 0.79, MaxDD −23.3 vs −29.3 — the predicted bias direction; daily monitoring stays the convention). Next-open entry is slightly BETTER than same-close (0.90 vs 0.79) — the optimistic close-entry convention is not carrying the result. Cost sensitivity mild (3→14 bps costs ~0.05 Sharpe). Regime-off forced exits destroy value (0.64) — the entries-only gate design validated. T-bill cash worth ~+0.5 CAGR, mechanical.
7. **Price-filter basis (deviation 2) is immaterial for this configuration** (378 vs 375 trades; Sharpe 0.85 vs 0.79 — adjusted marginally better here): S&P large caps rarely sit near $5 unadjusted. The correction stands on principle and matters more for the NDX/transplant universes.

**Shortlist recommendation (≤2, per protocol): (A) dip_below_high alone; (B) the below_high + breadth combination.** With the primary, the validation pass {primary, A, B} yields clean attribution: primary→A isolates the trigger, A→B isolates the gate. Both components are registered alternates; the combination is a composition of registered alternates, selected on the design segment only.

## 4. Phase 3b design segment (1994-01 → 2017-12) — results

Primary (their defaults, our registered fill conventions, 7 bps/side, unadjusted basis):
CAGR 10.60%, Sharpe 1.073, MaxDD −13.19%, usage 7.74%, 2,269 trades (94.6/yr), 68.49% win, PF 1.78, AvgWin +3.77% / AvgLoss −4.71%, winners 1.6 bars vs losers 3.2; exits: target 1,971 / target_gap 220 / price_action 73 / time 4 / delist 1; 11,002 orders expired unfilled; 0 symbol failures. Benchmark $NDX same segment: 12.65% CAGR, −82.9% MaxDD.

Notes for the deferred full-window anchor comparison (19.17% p.a. / −22.55% / ~13.9% usage, 1994→2025): design-segment CAGR trails the full-window anchor materially — their 2018-2025 validation era likely carries a large share of the compounding; usage runs at roughly half their full-window average. Neither is adjudicable without the validation segment; both are flagged, not explained. Supporting the era story: the strategy's slices show +103% through 2000-02 (−11.9% DD, 457 trades, 68.3% win) and +13.9% through calendar 2008 — the no-stop-loss dip harvester monetises panic vol, and the design segment simply contains less of it after 2009.

Plateau/sensitivity battery (all 1994-01 → 2017-12, $NDX calendar, 7 bps unless stated):

| run | tr/yr | win% | PF | CAGR% | Sharpe | MaxDD% | usage% |
|---|---|---|---|---|---|---|---|
| **primary (their defaults)** | 94.6 | 68.5 | 1.78 | 10.6 | 1.07 | −13.2 | 7.7 |
| drop −2% / −4% | 131.0 / 62.7 | 66.9 / 68.6 | 1.59 / 2.00 | 10.7 / 9.1 | 1.01 / 1.00 | −13.8 / −12.2 | 11.1 / 5.1 |
| entry 0.5 / 1.2 ×ATR | 193.5 / 49.9 | 62.9 / 70.8 | 1.33 / 1.99 | 11.1 / 7.9 | 0.81 / 1.08 | **−30.7** / −6.5 | 16.4 / 4.1 |
| target 0.3 / 0.8 ×ATR | 96.9 / 89.7 | 66.5 / 69.6 | 1.76 / 1.82 | 9.0 / 13.2 | 1.08 / 1.05 | −13.6 / −19.1 | 5.7 / 11.4 |
| max positions 5 / 20 | 63.0 / 115.4 | 66.7 / 68.8 | 1.62 / 1.82 | 6.0 / 13.7 | 0.89 / 1.13 | −11.0 / −14.5 | 5.4 / 9.3 |
| NATR filter off | 103.4 | 68.5 | 1.77 | 10.8 | 1.09 | −13.2 | 8.4 |
| dollar-vol screen $5m | 93.9 | 68.2 | 1.76 | 10.2 | 1.03 | −14.5 | 7.7 |
| fill strict_touch | 94.7 | 68.5 | 1.78 | 10.6 | 1.07 | −13.2 | 7.7 |
| fill at_limit | 94.7 | 67.2 | 1.53 | 8.2 | 0.84 | −13.5 | 7.7 |
| target touch strict (gt) | 94.7 | 68.5 | 1.78 | 10.6 | 1.07 | −13.2 | 7.7 |
| cost 3 bps | 94.7 | 69.2 | 1.86 | 11.5 | 1.15 | −12.8 | 7.7 |
| cost 14 bps | 94.7 | 67.0 | 1.64 | 9.2 | 0.94 | −13.8 | 7.7 |
| SPX transplant (2000-2017) | 125.4 | 67.3 | 1.82 | 14.2 | 1.39 | −17.7 | 11.3 |

Readings:

1. **Every dial sits on a flat or defensibly-shaped plateau around the source's defaults.** Drop −3% flat; target 0.5 flat; NATR filter and the liquidity screen nearly redundant; strict-touch and strict-target sensitivities literally indistinguishable (fills are not knife-edge).
2. **Entry depth is the one cliff, and the default is on the right side of it:** 0.5×ATR fills too easily (catches continuing declines; −30.7% MaxDD, Sharpe 0.81), 0.9 and 1.2 are equivalent on Sharpe with 1.2 halving activity. The published 0.9 is validated, not fragile.
3. **More slots help** (Sharpe 1.13 at 20 positions, usage still only 9.3%) — relevant to the capital-stacking thesis, not a deviation candidate for replication.
4. **Fill-price honesty:** pricing gap-through fills at the limit instead of the open costs ~2.4 CAGR points (8.2 vs 10.6). A real resting limit order does fill at the better open price, so min(open, limit) remains the stated convention — but a visible share of the edge lives in gap-down fills; flagged for the live-execution discussion.
5. Costs: 3→14 bps spans Sharpe 1.15→0.94 and CAGR 11.5→9.2 — a steeper cost gradient than the weekly variant (94 short trades/yr vs 21 long ones), but robust across the plausible range for NDX-liquidity names.
6. **The edge survives the universe transplant (registered alternate 7) and then some:** on the S&P 500 PIT universe, 2000-2017 (window differs — SPX data fetched from 1998 per Phase 1 conventions; stated), CAGR 14.2%, Sharpe 1.39, MaxDD −17.7%, usage 11.3%, 125 trades/yr at 67.3% winners. More names supply more independent dip events with the same fill discipline. Strengthens the mechanism claim and the multi-strategy stacking case; the NDX configuration remains the replication target.

## 5. Recommendations / sign-off requests — APPROVED by owner 2026-07-04 (all three asks); execution and verdicts in §7

**Ask 1 — Phase 2b validation pass (single execution, 2018-01 → present).** Approve the shortlist {primary, dip_below_high, below_high + breadth combo}. Per protocol: run once, no iteration on the results, decision gates as pre-registered (validation Sharpe ≥ 0.7; MaxDD no worse than −25%; PF ≥ 1.5; 15-25 trades/yr; holds of months). The validation runs will also produce the 2020 and 2022 regime slices and the remaining robustness rows on the validation window.

**Ask 2 — Phase 3b full-window replication run (1994-01 → present).** The acceptance gate (CAGR ±3 pts of 19.17%, MaxDD ±5 pts of −22.55%, usage ±4 pts of ~13.9%) is defined on the full window, which includes the validation years — so it awaits this approval. Configuration: their defaults exactly, our stated fill conventions, $NDX calendar, 7 bps, with their 2024-01 live boundary reported as a sub-slice. Design-segment evidence says the configuration is stable (flat plateaus); the open question is whether 2018-2025 closes the CAGR and usage gaps.

**Ask 3 — publication scope.** Recommend: after Asks 1-2 complete and results are reviewed, publish to the dashboard (a) Phase 1 anchor-replication summary, (b) the 2b/3b primary configurations' full-history records with the validation boundary marked, (c) derived aggregates only (trade lists, equity curves, summary JSON) per the licence. The MECHANICS-ONLY banner comes down only at that point. Alternates and plateau tables can go into the filed review rather than the public page.

**Not recommended for validation:** target10 (design-segment spike on a V-shaped dial; changes the model's character), any monitoring/fill convention softer than the registered ones.

**Post-approval mechanics** (ready to execute on your word): validation runs (~30 min), README status + open-issues update (issues 1, 4, 6, 7 close; convention discovery and deviations logged), STUDIES_LEDGER row, `research-review` filing (running memo + technical record), dashboard rebuild via `scripts/pipeline.py` only after publication approval.

## 7. Validation and replication execution (owner approval 2026-07-04, all three asks)

### 7.1 Phase 1 filing compliance — adjustment-basis sensitivity: PASS

Capital-only adjustment, anchor window: 24,639 trades / 56.62% winners / PF 1.44 vs TOTALRETURN 25,603 / 57.04% / 1.45. The published anchors (~25,000 / 56.81%) sit between the two bases. The replication does not depend on the undisclosed adjustment basis. **Open issue 2 closed.**

### 7.2 Phase 2b validation pass (2018-01 → 2026-07, executed once): GATES FAIL

| config | CAGR% | Sharpe | MaxDD% | PF | win% | tr/yr | verdict vs gates (Sharpe ≥ 0.7, MaxDD ≥ −25, PF ≥ 1.5, 15-25 tr/yr) |
|---|---|---|---|---|---|---|---|
| primary (v1) | 5.41 | 0.548 | −17.2 | 1.42 | 50.8 | 22.3 | **FAIL** (Sharpe, PF) |
| below_high | 4.87 | 0.479 | −23.4 | 1.30 | 48.4 | 25.1 | **FAIL** (Sharpe, PF; tr/yr at band edge) |
| below_high + breadth combo | 5.06 | 0.498 | −20.6 | 1.32 | 49.0 | 23.6 | **FAIL** (Sharpe, PF) |

**The design-segment ranking inverted out-of-sample — the unmodified primary validated best of the three.** Textbook selection overfitting caught by the two-segment protocol. Benchmark $SPX price index 7.43% CAGR on the segment (total return ≈ 10%+). Exit geometry held (AvgWin ~14.8 / AvgLoss ~−10.4; targets and stops in the designed ratio); what changed out-of-sample is the hit rate (50.8% / 48.4% vs 56.5% / 60.0% in design). The below_high alternate's design-segment edge — concentrated in repairing 2000-02 — did not transfer.

**Pre-registered decision: the weekly variant is NOT taken forward on these results.** No iteration on the validation segment. Any successor idea requires a fresh pre-registration (new design work, not re-tuning). Honest headline: our reconstruction of the vendor's weekly concept, under our pre-registered rules, does not reproduce the live-era quality their published statistics claim; either their undisclosed rules differ materially (their WinLen 121 bars and AvgWin 16.1% vs our ~95 / 14.8 point at a different exit structure) or their era statistics embed information we cannot replicate from the disclosures.

### 7.3 Phase 3b full-window replication (1994-01 → 2026-07): ANCHOR GATE FAIL — investigation per registered order

Full window: CAGR 9.99% / Sharpe 1.05 / MaxDD −13.19% / usage 7.33% / 2,892 trades / 68.4% win / PF 1.85 / 0 failures.
On the source's window (1994 → 2025-01): **CAGR 9.84% vs 19.17% (FAIL ±3); usage 7.32% vs ~13.9% (FAIL ±4); MaxDD −13.19% vs −22.55% (outside ±5 in the favourable direction)**. Their live boundary sub-slice (2024-01→): CAGR 12.76%, MaxDD −6.07%.

Signature — half the return at half the exposure with lower drawdown, per-trade statistics in family — indicates a participation difference, not a signal difference. Registered investigation order says fill model first: the prime suspect is our pre-registered interpretation convention 3 (orders placed only for free slots). A form-based backtester most plausibly places an order for EVERY signal and lets capacity bind at fill time; in volatility clusters (where this model earns), slot-rationing at placement forfeits exactly the fills that drive their usage and return. Implemented as `--order-placement all_signals` (capacity enforced at fill, NATR priority, cash-capped), tested (63 passing). Design segment: 17.7% p.a. / usage 10.0% / Sharpe 1.21 / MaxDD −15.7% with the per-trade profile intact (69.5% winners) — every axis moves toward the anchors. **Full window, source's anchor window (1994 → 2025-01): CAGR 15.37% / usage 9.27% / MaxDD −15.68%** — the placement convention explains ~60% of the CAGR gap and half the usage gap; the gate is still narrowly missed (−3.8 CAGR pts vs ±3; −4.6 usage pts vs ±4; MaxDD better throughout). Residual attributed (not resolvable from disclosures) to the source's fixed-capital, non-compounding form — simple annualisation on fixed $10k reads above compound CAGR — and the undisclosed cost model (7 vs 3 bps ≈ 1 CAGR point). Verdict: anchors not replicated within tolerances; dominant driver identified and quantified; the strategy's character replicates cleanly, and on our conservative engine its merits stand (Sharpe 1.14, −15.7% MaxDD, 9.3% usage). Full record appended to PHASE3_DESIGN.md.

## 8. Session audit trail

- Depth gate: warm-cache hard-fail reproduced before any refresh.
- All refreshes via `--refresh-cache`; no manual cache deletion.
- 62 tests green (43 pre-existing + 19 added: guard wiring, eval-end, sim bounds, basis, alternates, fill models, monitoring, no-reentry).
- Validation segments were touched only after explicit owner approval, and only by the pre-registered configurations: exactly three Phase 2b validation runs (executed once, no iteration) and the Phase 3b full-window runs (registered conventions, then the logged all_signals investigation variant per the registered miss order).
- 63 tests green at final commit. Two commits pushed: 736a732 (engine controls, no result figures — pre-approval) and c20735f (results, records, dashboard — post-approval).
- Published data artefacts are derived aggregates only (summaries, trade lists, equity curves); the licensed raw cache remains gitignored. The dashboard's rebased $SPXTR benchmark overlay follows the owner's shipped 2026-07-03 precedent.

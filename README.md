# buy-the-dip

Stock-level dip-buying on the S&P 500 with a survivorship-bias-free, point-in-time universe. Reconstruction and extension of the CrackingMarkets "Buy the Dip" strategy family (daily research baseline + weekly live model). **Personal research artefact** — not investment advice. **Live dashboard**: [phuazz.github.io/buy-the-dip](https://phuazz.github.io/buy-the-dip/) (full-history record since 2026-07-04; the Phase 2b validation verdict — gates not met — is stated on-page).

## Source material

Three CrackingMarkets documents (PDFs filed in `OneDrive\Main`, captured 2026-07-03):

1. **"Buy the dip"** (Trading Strategies, 2024-09-19) — discloses a complete baseline rule set and two signal-strength findings.
2. **"Buy the dip (weekly)"** (Live Trading Models, 2024-09-17) — the live weekly model traded since 2018; discloses shape, portfolio construction, and full performance statistics, but not exact entry/exit rules.
3. **"Survivorship Bias in Trading"** (Trading Glossary, 2024-01-02) — the data-integrity rationale; their NDX Momentum comparison shows a survivorship-biased variant overstating net profit by ~2.5x ($663,714 vs $265,820).

The authors use Norgate Data with historical index constituents and delisted securities. This project does the same (see Data layer).

## Strategy family

### Phase 0/1 baseline — disclosed in full (daily)

| Rule | Value |
|---|---|
| Universe | S&P 500 members, **point-in-time** (historical constituents) |
| Trend filter | Close > 200-day simple moving average |
| Dip trigger | RSI(5) < 20 *(RSI smoothing variant undisclosed; we assume Wilder — flagged as an open issue)* |
| Entry | Close of the signal bar |
| Exit | Close 5 trading bars later |
| Sizing | $1,000 per trade, overlapping trades allowed *(established in Phase 1: portfolio-level concurrency with ONE open position per symbol — per-signal same-symbol stacking roughly doubles the trade count and does not match the anchors)* |
| Costs | None in the published baseline |

**Published validation anchors (2000 → 2024-09):** ~25,000 trades ("nearly 25,000"), 56.81% winners, average win greater than average loss. The engine must reproduce these numbers before any variant is trusted. **Replicated 2026-07-04**: 25,603 trades / 57.04% winners / avg win +3.19% vs avg loss −2.93% under the one-position-per-symbol convention; insensitive to the adjustment basis (capital-only: 24,639 / 56.62% — the anchors sit between the two bases).

Two published signal-strength findings to reuse in variant design:

- Dip depth (lower RSI) does **not** materially improve average profit per trade.
- Higher short-term volatility (5-day ATR / price) **does** — the higher the normalised ATR at entry, the higher the average profit per trade.

### Phase 2 target — weekly live model (shape disclosed, rules not)

- Weekly timeframe; trades only when the overall market is in "positive growth" (contextual/regime filter — exact definition undisclosed).
- Buys S&P 500 stocks in an uptrend experiencing a correction on the weekly chart.
- Up to 10 positions, 10% allocation each, **favouring lower-volatility stocks**.
- 10% stop-loss per position; exits via profit targets.
- Statistics (their site, "Last update 07-01-2026", IB commissions included, continuous backtest since 2000): ROR 11.07% p.a., MaxDD −18.10%, 499 trades, 62.12% winners, AvgWin 16.08%, AvgLoss 10.23%, expectancy 6.12% per trade (headline text says 6.43% — source inconsistency, flagged), profit factor 2.31, Sharpe 1.07, average capital usage 80.95%. WinLen 121.23 / LossLen 86.33 (their "periods" unit; the period count implies daily bars, so roughly 121 trading days for the average winner).
- Note the tension with the daily research note: the live model *favours* low volatility while the research note shows higher normalised ATR raises average profit. Both ranking directions are in the variant design space and will be tested.

These weekly statistics are **calibration anchors, not replication targets** — the exact rules are proprietary, so we design our own rules "along these lines" and compare the profile (trade count ≈ 19/year, win rate ~60%, hold ~2–6 months, MaxDD < −20%).

## Data layer

**Provider: Norgate Data** (as the source articles use). Verified 2026-07-03 from norgatedata.com:

- **Free trial**: 3 weeks, US Stocks at Platinum level, fully functional NDU, but only ~2 years of history. One trial per market.
- **Platinum** (US$346.50 / 6 months, US$630.00 / 12 months): history + delisted securities back to 1990, historical index constituents. This is the minimum tier for this project — Silver/Gold have **no delisted stocks and no historical constituents**.
- **Diamond** (US$787.50 / 12 months): as Platinum but back to 1950 — not needed (backtest window starts 2000).
- Python access: `pip install norgatedata` (installed, v1.0.74). The package proxies the **Norgate Data Updater (NDU)** Windows application, which must be running locally. No API keys; no cloud calls from our code.
- **Licence discipline: raw price/constituent data is never committed.** `data/cache/` is gitignored. Only derived aggregates (trade lists, summaries, dashboard JSON) may be committed.

**Trial plan**: validate plumbing + engine on the 2-year trial window (Phase 0), then subscribe to Platinum to run the full 2000→ replication (Phase 1). The 2-year trial result is a plumbing check, not a strategy verdict.

`scripts/providers.py` abstracts the provider. `YFinanceProvider` exists for engine development only — it is survivorship-biased and its output must never be quoted as a result.

## Three ways this backtest could be silently wrong

Stated before code, per house rules, with the implemented defence:

1. **Universe look-ahead / survivorship** — using today's members historically, or ignoring delisted names. *Defence*: point-in-time membership gate on the signal day from Norgate `index_constituent_timeseries`; universe drawn from the "Current & Past" watchlist; delisted series end naturally (padding NONE) and open trades exit at the final print, realising delisting losses.
2. **Corporate-action and adjustment distortion** — RSI/SMA computed on a differently-adjusted series than the one traded; dividend ex-dates masquerading as dips; splits creating phantom signals. *Defence*: one adjusted series (total-return by default) used for both signals and fills; adjustment setting is a named parameter reported in every output; sensitivity run on capital-only adjustment before results are filed.
3. **Exit-alignment and fill fiction** — calendar-day arithmetic shifting exits across weekends/holidays/halts; and close-to-close fills that assume the signal is knowable at the traded close. *Defence*: exits are positional on each symbol's own bar index (t+5 bars, month/year boundaries tested); the same-close entry convention is retained deliberately to match the published baseline and is flagged as optimistic for live execution (a live implementation needs pre-close signal estimation or next-open entry — Phase 2 tests next-open sensitivity).

(Fourth, for the portfolio phase: costless results. The baseline is costless only to match the anchor; every portfolio-level result includes commissions + slippage.)

## Repo layout

```
buy-the-dip/
├── README.md                     This file — single source of truth
├── CLAUDE.md                     Project-specific working rules
├── requirements.txt
├── scripts/
│   ├── providers.py              NorgateProvider (results-grade) / YFinanceProvider (plumbing only)
│   ├── indicators.py             Wilder RSI, SMA, ATR — pure functions, tested
│   ├── norgate_smoke_test.py     Run after installing the Norgate trial + NDU
│   └── backtest_baseline.py      Phase 0/1 published-baseline replication engine
├── tests/                        Indicator correctness + date-boundary + delisting-exit tests
├── data/                         Outputs; data/cache/ (gitignored) holds licensed raw pulls
└── reviews/                      Filed study documents (ledger-linked)
```

## Run order

```
python -m pip install -r requirements.txt
# after Norgate trial + NDU installed and running:
python scripts/norgate_smoke_test.py
python scripts/backtest_baseline.py --provider norgate            # trial: auto-detects ~2y window
# If watchlists return zero members on your NDU install (known quirk):
python scripts/build_universe_fallback.py
python scripts/backtest_baseline.py --provider norgate --symbols-file data/cache/sp500_current_past_symbols.txt
pytest tests/
# Daily limit variant (Nasdaq 100):
python scripts/build_universe_fallback.py --index-name "Nasdaq 100" --out data/cache/ndx100_current_past_symbols.txt
python scripts/backtest_daily_limit.py --provider norgate
# Dashboard — rebuild after any backtest run:
python scripts/pipeline.py          # injects data/dashboard.json into template.html -> docs/index.html
npx serve docs                      # or: npx serve .  and open /template.html (fetch fallback for dev)
```

## Post-subscription runbook (day one of Platinum) — EXECUTED 2026-07-04, all steps clean (see Status)

The trial tier is a **rolling two-year window for every symbol**, and its delisted
database contains only within-window deaths — so day one of Platinum requires a
full data rebuild, in this order:

1. Let NDU re-sync completely (US Equities + Delisted grow to full 1990→ depth; allow up to an hour or two).
2. `python scripts/norgate_smoke_test.py` — the AAPL window should now start decades back, not 2024.
3. Rebuild BOTH universes (full-database membership scans take materially longer than the trial's ~6 minutes):
   `python scripts/build_universe_fallback.py` (S&P 500 — expect roughly 1,200+ names, was 542) and
   `python scripts/build_universe_fallback.py --index-name "Nasdaq 100" --out data/cache/ndx100_current_past_symbols.txt` (expect several hundred, was 125). Both counts are expectations, not verified figures.
4. **Phase 1**: `python scripts/backtest_baseline.py --provider norgate --symbols-file data/cache/sp500_current_past_symbols.txt --refresh-cache` → compare against ~25,000 trades / 56.81% winners.
5. **Phase 2b data pass**: `python scripts/backtest_weekly.py --provider norgate --refresh-cache`, then evaluation strictly per `PHASE2_DESIGN.md` (design segment first).
6. **Phase 3b replication**: `python scripts/backtest_daily_limit.py --provider norgate --refresh-cache` → compare against 19.17% p.a. / −22.55% MaxDD / ~13.9% usage.
7. `python scripts/pipeline.py`, commit, push — the dashboard picks up refreshed data (full-history panels to be added at that point).

Every engine now hard-fails on a stale trial-depth cache (`assert_cache_depth` in
`scripts/providers.py`): if you see "Cache depth mismatch", rebuild the universes
and add `--refresh-cache` — that error existing is the point.

## Roadmap

- **Phase 0 (trial window)** — DONE 2026-07-03. Plumbing and engine validation on the Norgate trial window.
- **Phase 1 (full history)** — **DONE 2026-07-04, gate PASSED.** 25,603 trades / 57.04% winners on the anchor window vs ~25,000 / 56.81% published; convention and adjustment-basis sensitivities in Status.
- **Phase 2 (weekly portfolio variant, S&P 500)** — 2a DONE 2026-07-03. **2b DONE 2026-07-04: validation gates NOT MET** (primary Sharpe 0.55 / PF 1.42 on 2018→; both shortlisted alternates degraded further out-of-sample). Pre-registered decision honoured: variant not taken forward; any successor idea requires a fresh pre-registration.
- **Phase 3 (daily limit variant, Nasdaq 100)** — 3a DONE 2026-07-03. **3b design segment DONE 2026-07-04** (plateau-stable around the source defaults; S&P 500 transplant strengthens the mechanism). **Full-window replication vs anchors FAILED on CAGR and capital usage** (9.84% vs 19.17% p.a.; 7.3% vs ~13.9%; MaxDD better at −13.2% vs −22.55%) — per-trade statistics in family; participation-convention investigation per the registered miss order in Status/open issues.
- **Phase 4 (robustness reviews)** — cost, fill-model, monitoring-convention and plateau batteries DONE on the design segments (2026-07-04, filed review); remaining walk-forward and validation-era regime work only proceeds if a variant is revived under a new pre-registration.
- **Phase 5 (dashboard / multi-strategy)** — mechanics view shipped 2026-07-03; **full-history record with gate verdicts shipped 2026-07-04** (single weekly panel; daily-variant panel and validation-boundary marker are queued template work); multi-strategy JSON contract shared with breadth-thrust-etf; the stacking study is moot unless a variant is revived.

## Integration with breadth-thrust-etf

Kept as a **separate repo** (different universe, data vendor, cadence), with three planned touch-points:

1. **Common signal contract** — this project will publish the same shape of derived JSON (`as_of`, regime state, holdings, equity curve) so a future multi-strategy page can consume both repos via fetch, mirroring the PCC fetch-based model.
2. **Shared regime input** — the weekly model's "positive growth" filter and breadth-thrust's CSP1 breadth overlay are the same idea. Once Norgate is live, S&P 500 breadth can be computed from Norgate PIT constituents and serve both projects.
3. **Data-layer upgrade path for breadth-thrust-etf** — Norgate would remove its two standing data risks (iShares endpoint blocking; yfinance's missing delisted names). Flagged as a follow-up, not in scope here.

## Status

- **2026-07-03** — Project initialised. Spec extracted from the three source PDFs; Norgate trial terms and pricing verified; provider abstraction, indicators, Phase 0/1 engine and tests written.
- **2026-07-03 (evening)** — Norgate US Stocks trial activated (window 2024-07-03 → 2026-07-02; NDU 4.2.2.65). Known quirk on this install: every watchlist resolves with zero members (HTTP 200, Record-Count 0) despite activation, forced update and restart — worked around with `scripts/build_universe_fallback.py`, which reconstructs "S&P 500 Current & Past" from point-in-time membership scans (542 names on the trial window; re-run after subscribing). Phase 0 baseline ran clean end-to-end: 2,302 trades (2025-05-12 → 2026-07-01; first entry consistent with the 210-bar warm-up), 54.6% winners, avg win +3.19% vs avg loss −3.15%, profit factor 1.22, 29 delisting/series-end exits realised, 0 symbol failures. **Plumbing gate PASSED; performance judgement deferred to Phase 1 (full history) per project discipline. Platinum subscribe/decline decision due by trial end, 2026-07-24.**
- **2026-07-03 (late)** — **Phase 2a complete.** Weekly variant **pre-registered before full-history data exists** (`PHASE2_DESIGN.md`: v1 rules, registered alternates, 2000-2017 design / 2018→ validation protocol mirroring the vendor's live boundary, decision gates). Portfolio engine built (`scripts/backtest_weekly.py`: weekly decisions, daily gap-aware stop/target monitoring with stop-first convention, low-volatility ranking, regime gate, next-open sensitivity mode) with 12 mechanics tests — 23 passing in total. Mechanics validation on the trial universe exercised every exit path cleanly (29 trades: 22 target / 6 stop / 1 gap-stop; 10/10 slots; 0 failures — MECHANICS ONLY, no evidential weight). Discovery: Norgate ships **precomputed S&P 500 breadth series** (`#SPX%MA200`, advance/decline, new highs/lows) — registered as a regime-gate alternate and flagged as a data-layer upgrade for breadth-thrust-etf. Next actions: Platinum decision by 2026-07-24 → Phase 1 anchor replication, then Phase 2b design-segment evaluation per protocol.
- **2026-07-03 (Phase 3a)** — **Daily limit variant (Nasdaq 100) pre-registered and mechanically validated**, same discipline as Phase 2a. Source: CrackingMarkets "Buying Short-Term Dips in Stocks [backtester]" (2025-01-27) — fully disclosed rules, so Phase 3b is a *replication* with stated fill conventions (`PHASE3_DESIGN.md`: one-day limit orders at close − 0.9×ATR(5), fill = min(open, limit) when touched; trailing +0.5×ATR(5) target from the day after entry; close-above-previous-high; 10-day time stop; **no stop-loss**; high-NATR ranking — the opposite direction to Phase 2, as published). Engine `scripts/backtest_daily_limit.py` + 15 mechanics tests (38 passing repo-wide). NDX PIT universe: 125 current-and-past names on the trial window (universe builder now index-parameterised; membership caches are index-specific by directory). Mechanics run clean: 93 trades, all four exit paths exercised, 578 orders expired unfilled — the limit discipline behind the published ~13.9% capital usage — 0 failures. MECHANICS ONLY. Replication anchors for 3b: 19.17% p.a. / −22.55% MaxDD / ~13.9% usage (1994→2025).
- **2026-07-03 (phase gate)** — Post-subscription entry gate built: `assert_cache_depth` guard in both portfolio engines (+ `--refresh-cache` flags) hard-fails any full-history run against a warm trial-depth cache — the silent-wrong-data landmine a subscription upgrade would otherwise create; 5 guard tests (43 passing repo-wide); post-subscription runbook added above. Recommendation upgraded: **subscribe to Platinum now rather than by 2026-07-24** — the trial has proven everything a 2-year window can prove, and a second vault workstream is now blocked on the same purchase.
- **2026-07-04 (Platinum day one — runbook + Phase 1)** — Subscription active (6-month term to 2027-01-04). Post-subscription runbook executed in order: full-depth sync verified by breadth checks before anything ran (21,046 delisted symbols; a 40-name delisted sample shows first bars 1990-2021 with zero clustering at 2024+; MSFT's first S&P member-day reads 1994-06-07, its true join date); the depth gate demonstrated its hard-fail on the warm trial cache before any refresh; both universes rebuilt at full depth (SPX 542 → 1,299; NDX 125 → 479) and verified **set-identical** to Norgate's own watchlists, which now work (issue 6 resolved). **Phase 1 anchor replication PASSED**: 25,603 trades / 57.04% winners on 2000 → 2024-09 vs ~25,000 / 56.81% published, entries averaging 1,027/year (2008 minimum 319; 2021 maximum 1,583), 0 symbol failures. Convention discovery: the anchor requires ONE open position per symbol — per-signal stacking gives 52,129 trades at 57.22% — so "overlapping trades allowed" is portfolio-level concurrency (issues 1 and 7 resolved; `no_reentry` is now the engine default). Adjustment-basis sensitivity: capital-only gives 24,639 / 56.62%, the anchors sitting between the bases (issue 2 resolved). Full window to 2026-07: 27,596 trades / 56.90%.
- **2026-07-04 (Phase 2b — design and validation, verdict NEGATIVE)** — Design-segment battery (2000-2017, 18 runs incl. the registered alternates, sensitivities and a below_high+breadth combination): primary Sharpe 0.79 / MaxDD −29.3% (entirely the 2000-02 bear), best alternates below_high (Sharpe 1.02) and breadth gate (0.97), combo Sharpe 1.10 / MaxDD −15.9% / PF 2.34 — profile on top of the published family. RSI plateau flat; target plateau V-shaped (spike declined per the flat-plateau rule); high-NATR ranking decisively worse (issue 4 resolved — low-volatility preference is right in the weekly portfolio context); monitoring/fill honesty checks moved in the pre-registered directions. **Single validation pass (2018-01 → 2026-07, executed once): ALL THREE configurations failed the gates** — primary Sharpe 0.548 / PF 1.42, below_high 0.479 / 1.30, combo 0.498 / 1.32 (gates: ≥ 0.7 / ≥ 1.5) — and the design-segment ranking inverted out-of-sample. Pre-registered decision honoured: **the weekly variant is not taken forward**; no iteration on the validation segment; any successor requires a fresh pre-registration. The chain-linked continuous primary record (design + validation, fresh capital at the boundary) is the published dashboard record: 6.89% p.a. / Sharpe 0.71 / MaxDD −29.3% / 564 trades over 26.4 years.
- **2026-07-04 (Phase 3b — replication and investigation)** — Design segment (1994-2017, $NDX calendar since $NDXTR starts 1999-03): primary 10.6% p.a. / Sharpe 1.07 / MaxDD −13.2% / usage 7.7% / 68.5% winners, all plateaus flat or defensible around the source defaults; entry depth is the one cliff and 0.9×ATR sits on the right side of it; gap-through fills carry ~2.4 CAGR points (at-limit pricing sensitivity); S&P 500 transplant (2000-2017) strengthens the mechanism at 14.2% / Sharpe 1.39 / usage 11.3%. **Full-window replication vs anchors FAILED the acceptance gate** on their window (CAGR 9.84% vs 19.17%; usage 7.3% vs ~13.9%; MaxDD −13.2% vs −22.55%, better) with per-trade statistics in family — a participation-shaped miss. Investigation per the registered order (fill model first) identified pre-registered interpretation convention 3 (orders placed only for free slots) as the driver: an `all_signals` placement variant (order every signal, capacity binds at fill, NATR priority) moves the design segment to 17.7% p.a. / usage 10.0% / Sharpe 1.21 with the per-trade profile intact, and the anchor window to 15.37% / 9.27% / −15.68% — roughly 60% of the CAGR gap explained; the narrow residual is attributed to the source's non-compounding fixed-capital form and undisclosed costs (verdict recorded in `PHASE3_DESIGN.md`, issue 8). Price-filter basis for both portfolio engines fixed to the unadjusted (actual traded) series — back-adjusted screens would exclude early-history compounders (AAPL's 2000 total-return close ≈ $0.11); sensitivity shows the effect is small for S&P large caps.
- **2026-07-03 (dashboard)** — Mechanics-view dashboard shipped: `template.html` (19.6KB) + `scripts/pipeline.py` → `docs/index.html` (46.9KB), styled per `C:\dev\design.md` (PCC DNA verbatim). Amber MECHANICS-ONLY banner wired to the live window length; equity curve vs rebased $SPXTR, capital usage, trade-return bars, full trade log with exit-reason chips, open-position chips, Phase 0 and published-family reference cards (clearly labelled as the source's own statistics), roadmap with gate states. Verified in local preview: zero console errors, all charts mounted, tokens applied. **GitHub Pages publication deliberately deferred** until the public/private remote decision (open issue 5) — the dashboard runs locally via `npx serve docs`.

## Open issues

1. ~~RSI smoothing variant in the source articles is undisclosed (assumed Wilder).~~ **Resolved 2026-07-04**: Wilder smoothing replicates the anchors (57.04% vs 56.81% published); no Cutler test needed.
2. ~~Adjustment basis of the published backtest is undisclosed (assumed total-return).~~ **Resolved 2026-07-04**: capital-only sensitivity run — anchors sit between the two bases; the replication is basis-insensitive.
3. ~~Weekly regime filter and dip trigger must be designed, not copied.~~ **Done 2a/2b; outcome negative 2026-07-04**: the pre-registered design and its shortlisted alternates failed the validation gates (see Status); variant not taken forward.
4. ~~Low-volatility ranking (live model) vs high-ATR edge (research note) — resolve empirically in Phase 2.~~ **Resolved 2026-07-04**: in the weekly portfolio-with-stops context, low-volatility ranking is right; high-NATR ranking scores Sharpe 0.43 vs 0.79 on the design segment. The high-ATR edge remains real at per-trade level in the daily limit variant (Phase 3), where the structure suits it.
5. ~~GitHub remote not yet created — decide public vs private.~~ **Resolved 2026-07-03 by owner decision: PUBLIC** at [github.com/phuazz/buy-the-dip](https://github.com/phuazz/buy-the-dip), dashboard on GitHub Pages. Boundary maintained: licensed raw data stays out of git (`data/cache/` ignored); committed artefacts are derived analytics only (trade lists, equity curves, summaries). The baseline rules published here come from CrackingMarkets' free public article; the weekly variant rules are this project's own pre-registered design.
6. ~~NDU watchlist endpoint returns zero members for every watchlist on this install.~~ **Resolved 2026-07-04**: watchlists work post-subscription (a trial-tier artefact); both rebuilt scan universes verified set-identical to the watchlists.
7. ~~Trial-window trade rate ran ~2x the anchor's average.~~ **Resolved 2026-07-04**: an entry-overlap convention artefact, not a regime effect — one-position-per-symbol gives 1,027 entries/year on average vs the anchor-implied ~1,012.
8. Phase 3b anchor gate: the pre-registered free-slot order-placement convention under-participates vs the source's backtester (CAGR 9.84% vs 19.17% on their window). The `all_signals` placement variant closes most of the gap — anchor window CAGR 15.37% / usage 9.27% / MaxDD −15.68% — but the gate is still narrowly missed (−3.8 CAGR points vs ±3); the residual is attributed to the source's fixed-capital, non-compounding form (simple annualisation reads above compound CAGR) and its undisclosed cost model. Verdict in `PHASE3_DESIGN.md`: character replicates cleanly; headline figures do not, for identified and quantified reasons. Lesson recorded: when replicating a form-based backtester, order placement policy is part of the fill model, not a free implementation detail.

*Last updated: 2026-07-04*

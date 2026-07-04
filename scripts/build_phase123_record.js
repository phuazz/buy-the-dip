// Build the 2026-07-04 phase 1/2b/3b technical record.
// Run: node scripts/build_phase123_record.js
// Content distilled from RESEARCH_MEMO.md; every number traces to the
// committed summary JSONs under data/ (commit c20735f).
const { buildReport } = require('C:/Users/phuaz/.claude/skills/research-review/assets/report_builder.js');

const W = { half: [4513, 4513], metric: [2606, 1605, 1605, 1605, 1605], dec: [2206, 2410, 4410] };

const spec = {
  meta: {
    title: 'Buy the Dip — full-history evaluation record',
    subtitle: 'Phase 1 anchor replication · Phase 2b design and validation · Phase 3b replication',
    dateISO: '2026-07-04',
    weekday: 'Saturday',
    headerLeft: 'buy-the-dip — Personal research',
    headerRight: '2026-07-04',
    assetsDir: 'C:/dev/buy-the-dip/reviews/assets',
  },
  metaTable: [
    ['Project / context', 'buy-the-dip (Personal). CrackingMarkets strategy-family reconstruction on Norgate full-depth data (Platinum active 2026-07-04, term to 2027-01-04).'],
    ['Review scope', 'Post-subscription runbook steps 0-3; Phase 1 anchor replication; Phase 2b design battery and single validation pass; Phase 3b design battery, full-window replication and anchor-miss investigation.'],
    ['Evaluation windows', 'Phase 1: 2000-01 to 2024-09 (anchor) and to 2026-07 (record). Phase 2b: design 2000-2017, validation 2018 to 2026-07, executed once. Phase 3b: design 1994-2017, source window 1994 to 2025-01, record to 2026-07.'],
    ['Data basis', 'Norgate point-in-time index constituency with delisted securities (SPX universe 1,299 names, NDX 479; both set-identical to vendor watchlists). TOTALRETURN series for signals and fills; unadjusted series for absolute price screens.'],
    ['Method basis', 'Pre-registered designs PHASE2_DESIGN.md / PHASE3_DESIGN.md (frozen 2026-07-03, before full-history data existed); positional exits; costs 7 bps per side in the portfolio engines; baseline costless to match the published anchor.'],
    ['Repository commits', '736a732 (engine controls, pre-approval) · c20735f (results, records, dashboard).'],
    ['Running memo', 'RESEARCH_MEMO.md (project root).'],
    ['Outcome', 'Phase 1 PASS. Phase 2b validation gates NOT MET — weekly variant not taken forward. Phase 3b anchors not replicated within tolerances; dominant driver identified and quantified; character replicates.'],
  ],
  sections: [
    { type: 'h1', text: '1. Executive summary' },
    { type: 'numbers', items: [
      'Phase 1 (published daily baseline) replicates: 25,603 trades and 57.04% winners on 2000-01 to 2024-09 against the published ~25,000 and 56.81%, average win +3.19% versus average loss −2.93%, zero symbol failures. The anchor requires one open position per symbol; entering on every signal bar gives 52,129 trades at 57.22%, so the source’s "overlapping trades allowed" is portfolio-level concurrency, not same-symbol pyramiding.',
      'The replication is insensitive to the undisclosed adjustment basis: capital-only adjustment gives 24,639 trades and 56.62% winners — the published anchors sit between the two bases.',
      'Phase 2b validation (2018-01 to 2026-07, executed once, no iteration): every configuration fails the pre-registered gates — primary Sharpe 0.548 and profit factor 1.42, below-high trigger 0.479 / 1.30, below-high plus breadth 0.498 / 1.32 (gates: at least 0.7 and 1.5). The design-segment ranking inverted out of sample; the weekly variant is not taken forward.',
      'Phase 3b design segment (1994-2017) is plateau-stable around the source defaults (primary 10.6% p.a., Sharpe 1.07, maximum drawdown −13.2%, usage 7.7%); the S&P 500 transplant strengthens the mechanism (14.2% p.a., Sharpe 1.39, usage 11.3%).',
      'Phase 3b full-window replication fails the acceptance gate under the pre-registered order-placement convention (CAGR 9.84% versus 19.17%; usage 7.32% versus ~13.9% on the source window). The registered investigation identifies the free-slot placement convention as the dominant driver: an all-signals placement variant reaches 15.37% CAGR and 9.27% usage — roughly 60% of the CAGR gap — with the per-trade profile intact. The residual is attributed to the source’s non-compounding fixed-capital form and undisclosed costs.',
      'Forty-five backtest executions this session; zero configurations taken forward; one engine convention (baseline no-reentry) adopted on anchor-match evidence rather than performance.',
    ]},

    { type: 'h1', text: '2. Verified data layer and engine map' },
    { type: 'p', text: 'Runbook steps 0-2 preceded every result. The NDU archive was verified complete by breadth checks, not a single-symbol probe: 14,421 current plus 21,046 delisted symbols; a 40-name delisted sample shows first bars distributed 1990-2021 with none clustered at 2024 or later; MSFT’s first S&P 500 member-day reads 1994-06-07, its true join date; Nasdaq 100 constituency begins 1993-10-01, which both covers the Phase 3 design segment and explains the source’s 1994 start.' },
    { type: 'bullets', items: [
      'Depth gate: the weekly engine hard-failed on the warm trial-depth cache before any refresh ("Cache depth mismatch", exit 1); the same guard is now wired into the baseline engine via a pre-sweep probe.',
      'Universes: full membership scans over 35,467 candidates rebuilt both lists (SPX 542 to 1,299; NDX 125 to 479), each set-identical to the vendor watchlist — two independent construction paths agreeing symbol for symbol. The trial watchlist quirk resolved itself post-subscription.',
      'Calendar conventions: $NDX (1985 onward) is the Phase 3 calendar and benchmark because $NDXTR only begins 1999-03; %IRX (1960 onward) backs the T-bill cash alternate.',
      'Absolute price screens ($5 minimum, dollar-volume) read the unadjusted traded series; back-adjusted screens would exclude early-history compounders (AAPL’s 2000 total-return close is about $0.11). Sensitivity shows the effect is small for S&P large caps (378 versus 375 trades).',
    ]},

    { type: 'h1', text: '3. Findings' },
    { type: 'h2', text: 'F1 — the published baseline replicates, and the convention matters more than the indicator' },
    { type: 'p', text: 'Wilder RSI(5) under 20 with close above the 200-day average, five-bar positional exits, point-in-time membership: the win rate lands within a quarter point of the published figure under either entry convention, but the trade count only matches under one open position per symbol. Dip episodes persist for several days, so per-signal stacking roughly doubles the count without changing per-trade statistics. The trial window’s apparent two-times trade rate was this convention, not the 2025 regime.' },
    { type: 'table',
      headers: ['Configuration (2000-01 to 2024-09)', 'Trades', 'Win %', 'Avg win %', 'Avg loss %'],
      rows: [
        ['Published anchor', '~25,000', '56.81', 'win > loss', '—'],
        ['No re-entry (adopted default)', '25,603', '57.04', '+3.19', '−2.93'],
        ['Per-signal stacking', '52,129', '57.22', '+3.16', '−2.90'],
        ['No re-entry, capital-only adjustment', '24,639', '56.62', '+3.20', '−2.90'],
      ],
      widths: W.metric, numericFrom: 1 },

    { type: 'h2', text: 'F2 — Phase 2b design segment: two alternates repaired 2000-02 and led the shortlist' },
    { type: 'p', text: 'The v1 primary’s entire −29.3% maximum drawdown sits in the 2000-02 bear (104 trades at 38.5% winners; the capitalisation-weighted 40-week gate whipsawed). The below-high dip trigger and the breadth gate each repaired that episode through a distinct mechanism and beat the primary on every headline metric at the same trade rate; their combination reached Sharpe 1.10, drawdown −15.9% and profit factor 2.34 on the design segment — a profile sitting on top of the published live-model statistics. The registered honesty checks moved in the pre-registered directions (weekly-close monitoring flatters; next-open entry is slightly better than same-close; costs move little). High-NATR ranking is decisively worse in this portfolio-with-stops context (Sharpe 0.43), resolving the ranking-direction question in favour of the live model’s low-volatility preference.' },
    { type: 'h2', text: 'F3 — Phase 2b validation: the ranking inverted and every gate failed' },
    { type: 'p', text: 'The single validation pass ran exactly three configurations. All three failed the Sharpe and profit-factor gates while passing drawdown and trade-rate; hit rates fell from 56-62% in design to 48-51%. The unmodified primary validated best — the design-segment selection added negative value out of sample, which is precisely the failure mode the two-segment protocol exists to catch. Per the pre-registration there is no iteration: the weekly variant is not taken forward, and any successor requires a fresh pre-registration.' },
    { type: 'chart', file: 'design_vs_validation.png',
      caption: 'Sharpe by segment for the three validated configurations. The green region is the validation pass zone (at least 0.7). The steepest design-segment improvements collapse hardest out of sample; the ranking inverts.' },
    { type: 'chart', file: 'weekly_chained_equity.png',
      caption: 'The published dashboard record: design and validation segments of the v1 primary chain-linked with fresh capital at the 2018 boundary. The chained curve’s own Sharpe (0.707) is incidental; the gate applies to the validation segment alone (0.548).' },

    { type: 'h2', text: 'F4 — Phase 3b design segment: the source defaults are stable, not fitted' },
    { type: 'p', text: 'Every registered dial sits on a flat or defensibly-shaped plateau around the published defaults: dip depth flat across −2/−3/−4%; target multiple flat; the volatility filter and the liquidity screen nearly redundant; strict-touch fill and strict-target sensitivities indistinguishable from the defaults. Entry depth is the one cliff — 0.5 x ATR fills too easily and takes −30.7% drawdown — and the published 0.9 sits on the safe side. Pricing gap-through fills at the limit rather than the open costs about 2.4 CAGR points, so a visible share of the edge lives in gap-down fills; a real resting order does receive the better open price, so the default convention stands. The strategy earned +103% through 2000-02 at −11.9% drawdown — it monetises panic volatility, as the source claims.' },
    { type: 'h2', text: 'F5 — Phase 3b anchors: not replicated within tolerances; the driver is order placement' },
    { type: 'p', text: 'Under the pre-registered free-slot placement convention the source window returns half the anchor CAGR at half the usage with materially lower drawdown and an in-family per-trade profile — a participation signature, not a signal difference. The registered investigation order (fill model first) identified the convention: placing orders only for free slots forfeits fills in exactly the volatility clusters the model monetises. The all-signals variant closes most of the gap; the residual (−3.8 CAGR points against a ±3 gate; −4.6 usage points against ±4) is attributed to the source’s fixed-capital, non-compounding form — simple annualisation on fixed capital reads above compound CAGR for a profitable strategy — and its undisclosed cost model. Character replicates cleanly: 68-69% winners, profit factor 1.8-1.9, one-to-two-day winners, drawdown well inside the published figure throughout.' },
    { type: 'chart', file: 'dl_participation_gap.png',
      caption: 'CAGR and average capital usage on the source window (1994 to 2025-01) under the two placement conventions, against the published anchors. The green bands are the pre-registered acceptance tolerances (±3 CAGR points, ±4 usage points).' },

    { type: 'h1', text: '4. Decisions', pageBreakBefore: true },
    { type: 'table',
      headers: ['Component', 'Decision', 'Basis'],
      rows: [
        ['Baseline entry convention', 'ADOPT no-reentry default', 'Anchor trade count matches only under one open position per symbol (F1); per-signal retained behind a flag.'],
        ['Weekly variant (all configurations)', 'REJECT — not taken forward', 'Validation gates failed for primary and both shortlisted alternates; ranking inverted out of sample (F3). Successor requires a fresh pre-registration.'],
        ['Weekly validation segment', 'CLOSED', 'Touched once by exactly three pre-registered configurations; no iteration.'],
        ['Daily limit variant replication', 'RECORD as not-replicated-within-tolerances', 'Dominant driver identified and quantified (F5); residual attributed to undisclosed engine and metric conventions; character replicates.'],
        ['Order placement conventions', 'KEEP BOTH, documented', 'Free-slots is the conservative deployable reading; all-signals is the faithful reading of the source backtester.'],
        ['Price-screen basis', 'ADOPT unadjusted series', 'Back-adjusted screens exclude early-history compounders; logged as an implementation clarification of the registered rule.'],
        ['Publication', 'PUBLISHED with verdicts on-page', 'Dashboard carries the chained record and the gates-not-met banner; derived aggregates only, licensed raw data excluded (commit c20735f).'],
      ],
      widths: W.dec },

    { type: 'h1', text: '5. Trial register' },
    { type: 'p', text: 'Forty-five backtest executions across approximately forty distinct configurations: Phase 1 conventions and sensitivities (4); Phase 2b design battery including the combination (18); Phase 2b validation, executed once (3); Phase 3b design battery including the transplant and the all-signals investigation (18); Phase 3b full-window replication under both placement conventions (2). Zero configurations were selected for deployment, so no deflated-Sharpe haircut is charged against a deployed claim; the register exists to charge any future revival of these families for this search.' },
    { type: 'chart', file: 'scope_funnel.png',
      caption: 'Executions per family. Red bars touch validation-era data and were run exactly once each under owner approval; blue bars are design-segment or anchor-window work.' },

    { type: 'h1', text: '6. Artefact register' },
    { type: 'bullets', items: [
      'Engines and controls: scripts/backtest_baseline.py, scripts/backtest_weekly.py, scripts/backtest_daily_limit.py, scripts/providers.py (63 tests passing).',
      'Run records (derived aggregates, committed): data/baseline_anchor_*, data/baseline_noreentry_full_summary.json, data/baseline_anchor_capital_summary.json, data/weekly_design_*_summary.json, data/weekly_valid_*, data/daily_limit_full_*, data/daily_limit_full_allsignals_*, data/dl_design_*_summary.json, plus headline trade and equity CSVs.',
      'Dashboard: template.html and docs/index.html (chained record, verdict banner), data/dashboard.json via scripts/pipeline.py.',
      'Design documents with appended verdict records: PHASE2_DESIGN.md (validation record), PHASE3_DESIGN.md (replication record). README status entries 2026-07-04; open issues 1/2/3/4/6/7 closed, issue 8 opened and answered.',
      'Charts: scripts/record_charts.py writes reviews/assets/*.png from committed data.',
      'Running memo: RESEARCH_MEMO.md. Commits: 736a732, c20735f.',
    ]},

    { type: 'h1', text: '7. Next phase' },
    { type: 'bullets', items: [
      'Weekly family: dormant. Reopening requires a fresh pre-registration that inherits this trial register; the validation segment stays closed to iteration.',
      'Daily limit family: the replication record is complete. Any deployment question would start from the free-slots (conservative) record at small size and would need its own pre-registration; the stacking study with the weekly variant is moot.',
      'Dashboard: a daily-variant panel and a visual validation-boundary marker are queued as mechanical template work for an Opus-fast session per the project session-model guidance.',
      'Norgate: renewal or right-sizing decision due December 2026 (shared with em-rotation-lab).',
    ]},
  ],
  signoff: [
    ['Prepared by', 'Claude (Fable 5), buy-the-dip research session 2026-07-04'],
    ['Reviewed and approved by', 'Zhenghao Phua — validation and publication approved in-session 2026-07-04; record sign-off pending'],
    ['Date', '2026-07-04 (Saturday)'],
    ['Next review', 'Event-driven: any revival pre-registration, or the December 2026 Norgate renewal decision'],
  ],
  disclaimer: 'Personal research artefact. Not investment advice. All statistics are backtested results on survivorship-bias-free point-in-time data with the stated cost and fill conventions; published-source figures are quoted for comparison only and remain the source’s own claims.',
};

buildReport(spec, 'C:/dev/buy-the-dip/reviews/2026-07-04_phase1-2b-3b_full-history.docx')
  .then(r => console.log('wrote', r.outPath, r.bytes));

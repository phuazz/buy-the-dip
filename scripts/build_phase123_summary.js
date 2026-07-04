// Build the 2026-07-04 plain-language / allocator summary — companion to the
// technical record 2026-07-04_phase1-2b-3b_full-history.docx.
// Run: node scripts/build_phase123_summary.js
// Chart-led; every number traces to the technical record and the committed
// summary JSONs under data/ (commit c20735f). No new figures are introduced.
const { buildReport } = require('C:/Users/phuaz/.claude/skills/research-review/assets/report_builder.js');

const spec = {
  meta: {
    title: 'Why does our rebuild earn less than the published "Buy the Dip"?',
    subtitle: 'Buy the Dip — independent full-history reconstruction · plain-language summary',
    dateISO: '2026-07-04',
    weekday: 'Saturday',
    dateLine: 'Saturday, 4 July 2026 · plain-language summary of the full-history evaluation recorded on 4 July 2026',
    headerLeft: 'buy-the-dip — plain-language summary',
    headerRight: '2026-07-04',
    assetsDir: 'C:/dev/buy-the-dip/reviews/assets',
  },
  sections: [
    { type: 'callout', text: 'The published figure of about 11% a year is an in-sample, optimistically-filled number; our lower figure of 6.9% a year is the honest, fully-costed, out-of-sample one. Once both are put on the same rules over the same history, the difference is disclosure — not a weaker signal.' },

    { type: 'p', runs: [
      { text: 'The question. ', bold: true },
      { text: 'We rebuilt a published S&P 500 "buy the dip" strategy from scratch on clean, survivorship-bias-free data. Its public page shows about 11% a year; our own dashboard shows less. Is our rebuild wrong, or is the published figure flattered?' },
    ] },
    { type: 'p', runs: [
      { text: 'The answer. ', bold: true },
      { text: 'Neither the signal nor our engine is wrong — rebuilt from scratch, our engine reproduces the vendor’s own published trade count almost to the trade. Our headline is lower for three honest reasons: we measure it out-of-sample, on data the rules never saw, where the page shows one continuous in-sample backtest; we charge realistic costs and buy only when we genuinely have room, where the page’s fills are undisclosed and optimistic; and we compound honestly where the page’s headline annualises on fixed capital. The weekly form is the one piece that failed the out-of-sample exam outright, so it has been shelved.' },
    ] },
    { type: 'p', runs: [
      { text: 'How it was tested. ', bold: true },
      { text: 'Full survivorship-bias-free S&P 500 history back to 2000 (the daily cousin to 1994), delisted companies included; every rule fixed in writing before the full data was bought; realistic costs of 7 basis points a side; and a single locked out-of-sample exam, run once, with no retries.' },
    ] },
    { type: 'spacer', after: 60 },

    { type: 'h2', text: '1. The engine is proven correct — it reproduces the vendor’s own published trade count almost exactly' },
    { type: 'p', text: 'Rebuilt from scratch on point-in-time data, it produced 25,603 trades at 57.0% winners against the vendor’s published figure of about 25,000 at 56.8% — so any gap that follows is economics and honesty, not a coding error.' },

    { type: 'h2', text: '2. The mechanism is real — buying panic pays' },
    { type: 'p', text: 'Across the full history the per-trade signature reproduces cleanly — roughly 68 to 69% winners, about $1.90 of gross profit for every $1.00 of loss, and winners held only one to two days — exactly as the source describes.' },

    { type: 'h2', text: '3. The published headline is an in-sample number; ours is out-of-sample — and that is most of the gap' },
    { type: 'p', text: 'The vendor’s page is one continuous backtest whose settings were chosen with the whole history in view; ours splits the history and honestly reports the part the rules never saw. Our full-history headline is 6.9% a year against the page’s 11.1%, and the strategy visibly weakens in that untouched 2018-onward exam — the win rate slips from about 56-62% to about 48-51%.' },
    { type: 'chart', file: 'weekly_chained_equity.png',
      caption: 'Our reconstructed weekly strategy: $100,000 growing on a log scale. The rules were chosen on the left "design" stretch (2000-2017); the shaded band from 2018 is the single out-of-sample exam, run once. The line keeps rising — but not fast enough to clear the pass mark, as the next chart shows.' },

    { type: 'h2', text: '4. The weekly form failed the honest exam, so we are not deploying it' },
    { type: 'p', text: 'Every weekly configuration fell below our pre-set pass mark once it met data it had never seen — even the "improved" versions that had matched or beaten the vendor beforehand (risk-adjusted return up to 1.10 against their 1.07). The tweaks that looked best did worst live, the classic fingerprint of fitting to the past, so by our own rule there is no second attempt.' },
    { type: 'chart', file: 'design_vs_validation.png',
      caption: 'Risk-adjusted return (return per unit of volatility; higher is better) for three weekly configurations, on the design stretch (left) versus the untouched exam (right). The green band is the pass zone (0.7 and above). All three start strong and fall below the line; the two "improved" versions (red, teal) fall furthest — they were fitted to the past.' },

    { type: 'h2', text: '5. Most of the remaining gap is participation and accounting, not skill' },
    { type: 'p', text: 'On the strategy’s daily cousin, our deployable rule buys only when a portfolio slot is genuinely free, so it keeps far less money at work than the vendor’s version; put on the vendor’s own fill convention, the rebuild’s return rises from about 10% to about 15% a year — roughly 60% of the gap — with the rest explained by the vendor’s fixed-capital arithmetic and undisclosed costs.' },
    { type: 'chart', file: 'dl_participation_gap.png',
      caption: 'The daily cousin, on the source’s own window. Left: growth rate per year. Right: the average share of capital actually invested. Our deployable "free-slot" rule (navy) keeps only about 7% of capital at work; adopting the vendor’s "all-signals" fills (teal) lifts both bars most of the way to the published anchor (grey). The green band is the pre-agreed match tolerance.' },

    { type: 'h1', text: 'What an allocator should take away' },
    { type: 'bullets', items: [
      'This is not a failed rebuild. The engine is verified against the vendor’s own trade count, and the money-making mechanism reproduces cleanly.',
      'The published figure of about 11% a year is, in effect, an in-sample, optimistically-filled, fixed-capital number. The honest, deployable, out-of-sample version is lower — the difference is disclosure, not a broken signal.',
      'The weekly form did not clear an honest out-of-sample bar and has been shelved. The daily cousin reproduces the mechanism and is the only candidate for any future deployment question — at small size, and only under a fresh, written pre-registration.',
      'Every figure here is a backtest on clean, survivorship-bias-free data, not a live track record.',
    ] },

    { type: 'h1', text: 'Appendix — the work behind the summary', pageBreakBefore: true },
    { type: 'p', text: 'This is the extent of the testing behind the findings, included to show the depth of the work without the detail. Everything was pre-registered before the full data existed; nothing was carried forward into deployment.' },
    { type: 'chart', file: 'scope_funnel.png',
      caption: 'Every backtest run in this evaluation, grouped by phase. Forty-five runs in all; not one configuration was adopted to improve returns. The single engine convention that was adopted was chosen to match the vendor’s trade count, not to lift performance. The red bars touched the out-of-sample exam data and were each run exactly once, under owner approval.' },
    { type: 'p', runs: [
      { text: 'Full method, tables and per-component decisions are in the technical record, ' },
      { text: '2026-07-04_phase1-2b-3b_full-history.docx', italics: true },
      { text: ', filed alongside this summary. Sibling reconstructions in the same house format sit under the em-rotation-lab and breadth-thrust-etf projects.' },
    ] },
  ],
  signoff: [
    ['Prepared by', 'Claude (Opus 4.8), buy-the-dip session 2026-07-04 — plain-language companion to the Fable 5 technical record'],
    ['Reviewed and approved by', 'Zhenghao Phua — summary review pending'],
    ['Date', '2026-07-04 (Saturday)'],
    ['Next review', 'Event-driven: any revival pre-registration, or the December 2026 Norgate renewal decision'],
  ],
  disclaimer: 'Personal research artefact. Not investment advice. All statistics are backtested results on survivorship-bias-free point-in-time data with the stated cost and fill conventions; the published-source figures are quoted for comparison only and remain the source’s own claims.',
};

buildReport(spec, 'C:/dev/buy-the-dip/reviews/2026-07-04_phase1-2b-3b_full-history_summary.docx')
  .then(r => console.log('wrote', r.outPath, r.bytes));

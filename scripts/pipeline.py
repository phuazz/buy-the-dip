"""Dashboard pipeline: assemble data/dashboard.json and inject it into
template.html -> docs/index.html (house architecture, style per C:\\dev\\design.md).

Inputs (already produced by the backtest scripts):
    data/weekly_summary.json, data/weekly_equity.csv, data/weekly_trades.csv
    data/baseline_summary.json

Optional: a rebased $SPXTR benchmark overlay is fetched via norgatedata when
NDU is running; the dashboard renders without it otherwise.

The published-family block quotes the CrackingMarkets weekly model statistics
verbatim as REFERENCE ONLY (their full-history numbers, not ours).
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MARKER_RE = re.compile(
    r'(<script id="dashboard-data" type="application/json">)(.*?)(</script>)', re.S)

# Quoted from the "Buy the dip (weekly)" source PDF (their stats page, "Last
# update 07-01-2026", US date format; continuous backtest since 2000 with IB
# commissions). Reference family for shape comparison — not our results.
PUBLISHED_FAMILY = {
    "ror_pct_pa": 11.07, "max_dd_pct": -18.10, "n_trades": 499,
    "win_rate_pct": 62.12, "avg_win_pct": 16.08, "avg_loss_pct": -10.23,
    "expectancy_pct": 6.12, "profit_factor": 2.31, "sharpe": 1.07,
    "avg_usage_pct": 80.95, "win_len_bars": 121.23, "loss_len_bars": 86.33,
    "source": "CrackingMarkets 'Buy the dip (weekly)' stats page, captured 2026-07-03",
}


def _benchmark(eq_dates: pd.DatetimeIndex, base_value: float):
    try:
        import norgatedata
        df = norgatedata.price_timeseries(
            "$SPXTR", padding_setting=norgatedata.PaddingType.NONE,
            timeseriesformat="pandas-dataframe")
        s = df["Close"].reindex(eq_dates).ffill()
        if s.isna().all():
            return None
        first = float(s.dropna().iloc[0])
        return [None if pd.isna(v) else round(float(v) / first * base_value, 2)
                for v in s]
    except Exception as exc:  # NDU not running, symbol missing, etc.
        print(f"Benchmark overlay skipped: {exc}")
        return None


def build_payload() -> dict:
    eq = pd.read_csv(ROOT / "data" / "weekly_equity.csv", parse_dates=["date"])
    trades = pd.read_csv(ROOT / "data" / "weekly_trades.csv")
    weekly = json.loads((ROOT / "data" / "weekly_summary.json").read_text(encoding="utf-8"))
    baseline = json.loads((ROOT / "data" / "baseline_summary.json").read_text(encoding="utf-8"))
    dates = pd.DatetimeIndex(eq["date"])
    payload = {
        "as_of": dates[-1].date().isoformat(),
        "built": date.today().isoformat(),   # date library, not manual arithmetic
        "weekly": weekly,
        "baseline": baseline,
        "published_family": PUBLISHED_FAMILY,
        "equity": {
            "dates": [d.date().isoformat() for d in dates],
            "equity": [round(float(v), 2) for v in eq["equity"]],
            "invested_pct": [round(100.0 * float(v), 2) for v in eq["invested_frac"]],
            "benchmark": _benchmark(dates, float(eq["equity"].iloc[0])),
        },
        "trades": trades.to_dict(orient="records"),
    }
    return payload


def main() -> int:
    payload = build_payload()
    text = json.dumps(payload, separators=(",", ":"), allow_nan=False)
    if "</script" in text.lower():
        raise ValueError("payload would break the inline script tag")
    (ROOT / "data" / "dashboard.json").write_text(text, encoding="utf-8")

    tpl = (ROOT / "template.html").read_text(encoding="utf-8")
    if not MARKER_RE.search(tpl):
        raise ValueError("dashboard-data marker not found in template.html")
    out = MARKER_RE.sub(lambda m: m.group(1) + text + m.group(3), tpl, count=1)
    docs = ROOT / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "index.html").write_text(out, encoding="utf-8")

    # Static companion page: plain-language findings + its chart exhibits
    # (source findings.html at the repo root; charts from reviews/assets).
    shutil.copy2(ROOT / "findings.html", docs / "findings.html")
    assets = docs / "assets"
    assets.mkdir(exist_ok=True)
    copied = 0
    for png in sorted((ROOT / "reviews" / "assets").glob("*.png")):
        shutil.copy2(png, assets / png.name)
        copied += 1
    print(f"docs/findings.html + {copied} chart assets copied")

    print(f"template.html : {len(tpl.encode('utf-8')):,} bytes")
    print(f"docs/index.html: {len(out.encode('utf-8')):,} bytes")
    print(f"data/dashboard.json: {len(text.encode('utf-8')):,} bytes")
    print(f"as_of {payload['as_of']}, {len(payload['trades'])} trades, "
          f"benchmark={'yes' if payload['equity']['benchmark'] else 'no'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

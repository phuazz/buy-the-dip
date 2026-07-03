"""Fallback universe builder: "S&P 500 Current & Past" without watchlists.

NDU installs have been observed to answer watchlist queries with zero members
(HTTP 200, Record-Count: 0) while every other endpoint works. This script
reconstructs the same universe from first principles: enumerate US Equities +
US Equities Delisted and keep every symbol whose point-in-time S&P 500
membership series contains at least one member-day in the available window.

Output: data/cache/sp500_current_past_symbols.txt (one symbol per line),
consumed by scripts/backtest_baseline.py --symbols-file.

Note: on the 2-year trial window this yields roughly current members plus
window churn (~540-570 names). On full Platinum history it converges to the
complete Current & Past list. Re-run after subscribing.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import norgatedata

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = "data/cache/sp500_current_past_symbols.txt"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--index-name", default="S&P 500",
                    help="Norgate index name for constituency checks (e.g. 'Nasdaq 100')")
    ap.add_argument("--out", default=DEFAULT_OUT,
                    help="Output path (repo-relative) for the symbol list")
    args = ap.parse_args()
    out = ROOT / args.out

    if not norgatedata.status():
        print("FAIL: NDU is not running.")
        return 1
    syms = list(norgatedata.database_symbols("US Equities"))
    syms += list(norgatedata.database_symbols("US Equities Delisted"))
    print(f"{len(syms)} candidate symbols (US Equities + US Equities Delisted) "
          f"vs index {args.index_name!r}")
    members = []
    t0 = time.time()
    for k, s in enumerate(syms, 1):
        try:
            df = norgatedata.index_constituent_timeseries(
                s, args.index_name, timeseriesformat="pandas-dataframe"
            )
            if df is not None and len(df) and int(df[df.columns[0]].sum()) > 0:
                members.append(s)
        except Exception:
            pass  # non-equity instruments and oddities: never members
        if k % 1000 == 0:
            print(f"  {k}/{len(syms)} scanned, {len(members)} members, {time.time() - t0:.0f}s elapsed")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(sorted(members)) + "\n", encoding="utf-8")
    print(f"DONE: {len(members)} members in {time.time() - t0:.0f}s -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Charts for the 2026-07-04 phase 1/2b/3b technical record.

Reads only committed derived aggregates under data/ and writes the record
exhibits to reviews/assets/. Reproducible: python scripts/record_charts.py
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reviews" / "assets"
NAVY, RED, TEAL, GREY = "#1e3a8a", "#dc2626", "#0891b2", "#9ca3af"
GREEN_FILL = "#dcfce7"

plt.rcParams.update({
    "font.family": "sans-serif", "font.size": 11, "axes.edgecolor": "#d1d5db",
    "axes.grid": True, "grid.color": "#e5e7eb", "grid.linewidth": 0.6,
    "figure.facecolor": "white", "axes.facecolor": "white",
})


def _summary(name: str) -> dict:
    return json.loads((ROOT / "data" / f"{name}_summary.json").read_text(encoding="utf-8"))


def chained_equity():
    eq = pd.read_csv(ROOT / "data" / "weekly_equity.csv", index_col=0, parse_dates=True)
    fig, ax = plt.subplots(figsize=(9.5, 4.2))
    ax.plot(eq.index, eq["equity"], color=NAVY, lw=1.4)
    ax.set_yscale("log")
    boundary = pd.Timestamp("2018-01-02")
    ax.axvspan(boundary, eq.index[-1], color="#f3f4f6", zorder=0)
    ax.axvline(boundary, color=GREY, ls="--", lw=1.2)
    ax.text(0.30, 0.90, "design segment 2000-2017\n(rule selection happened here)",
            transform=ax.transAxes, ha="center", va="top", fontsize=10)
    ax.text(0.845, 0.22, "validation 2018→\nexecuted once — gates not met",
            transform=ax.transAxes, ha="center", va="top", fontsize=10, color=RED)
    ax.set_title("Weekly v1 primary — chained record (fresh capital at the 2018 boundary)")
    ax.set_ylabel("portfolio value (log scale, US$)")
    fig.tight_layout()
    fig.savefig(OUT / "weekly_chained_equity.png", dpi=150)
    plt.close(fig)


def design_vs_validation():
    rows = [
        ("v1 primary", NAVY, "weekly_design_primary", "weekly_valid_primary"),
        ("below-high trigger", RED, "weekly_design_dip_belowhigh", "weekly_valid_belowhigh"),
        ("below-high + breadth", TEAL, "weekly_design_combo", "weekly_valid_combo"),
    ]
    fig, ax = plt.subplots(figsize=(7.2, 4.4))
    ax.axhspan(0.7, 1.35, color=GREEN_FILL, zorder=0)
    ax.text(1.02, 0.72, "validation gate: Sharpe ≥ 0.7", fontsize=9, color="#166534")
    for label, colour, d_name, v_name in rows:
        d, v = _summary(d_name)["sharpe"], _summary(v_name)["sharpe"]
        ax.plot([0, 1], [d, v], color=colour, marker="o", lw=1.6, label=label)
        ax.annotate(f"{d:.2f}", (0, d), textcoords="offset points", xytext=(-30, -3),
                    color=colour, fontsize=10)
        ax.annotate(f"{v:.2f}", (1, v), textcoords="offset points", xytext=(10, -3),
                    color=colour, fontsize=10)
    ax.set_xlim(-0.35, 1.45)
    ax.set_ylim(0.3, 1.35)
    ax.set_xticks([0, 1], ["design segment\n2000-2017", "validation segment\n2018→"])
    ax.set_ylabel("Sharpe ratio")
    ax.set_title("The design-segment ranking inverted out of sample")
    ax.legend(loc="lower left", frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(OUT / "design_vs_validation.png", dpi=150)
    plt.close(fig)


def participation_gap():
    # Anchor-window numbers computed in the memo from the full-window equity
    # records; anchors from PHASE3_DESIGN.md.
    cagr = {"free-slot placement\n(pre-registered)": 9.84,
            "all-signals placement\n(investigation)": 15.37,
            "published anchor": 19.17}
    usage = {"free-slot placement\n(pre-registered)": 7.32,
             "all-signals placement\n(investigation)": 9.27,
             "published anchor": 13.9}
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 4.0))
    for ax, series, gate, title in (
        (axes[0], cagr, 3.0, "CAGR on the source window (1994 → 2025-01), %"),
        (axes[1], usage, 4.0, "Average capital usage, %"),
    ):
        labels = list(series)
        vals = [series[k] for k in labels]
        colours = [NAVY, TEAL, GREY]
        bars = ax.bar(labels, vals, color=colours, width=0.62)
        anchor = vals[-1]
        ax.axhspan(anchor - gate, anchor + gate, color=GREEN_FILL, zorder=0)
        for bar, v in zip(bars, vals):
            ax.annotate(f"{v:.1f}", (bar.get_x() + bar.get_width() / 2, v),
                        ha="center", va="bottom", fontsize=10)
        ax.set_title(title, fontsize=10.5)
        ax.tick_params(axis="x", labelsize=8.5)
    fig.suptitle("Order-placement convention explains most of the anchor gap; "
                 "the green band is the acceptance tolerance", fontsize=11)
    fig.tight_layout()
    fig.savefig(OUT / "dl_participation_gap.png", dpi=150)
    plt.close(fig)


def scope_graphic():
    fams = [
        ("Phase 1 conventions & sensitivities", 4, NAVY),
        ("Phase 2b design battery", 18, NAVY),
        ("Phase 2b validation (executed once)", 3, RED),
        ("Phase 3b design battery", 18, NAVY),
        ("Phase 3b full-window replication", 2, RED),
    ]
    fig, ax = plt.subplots(figsize=(9.0, 3.4))
    names = [f[0] for f in fams][::-1]
    counts = [f[1] for f in fams][::-1]
    colours = [f[2] for f in fams][::-1]
    bars = ax.barh(names, counts, color=colours, height=0.55)
    for bar, c in zip(bars, counts):
        ax.annotate(str(c), (c + 0.3, bar.get_y() + bar.get_height() / 2),
                    va="center", fontsize=10)
    ax.set_xlim(0, 21)
    ax.set_title("45 backtest executions → 0 configurations taken forward\n"
                 "→ 1 engine convention adopted on anchor evidence", fontsize=11)
    fig.tight_layout()
    fig.savefig(OUT / "scope_funnel.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    chained_equity()
    design_vs_validation()
    participation_gap()
    scope_graphic()
    print(f"Wrote 4 charts to {OUT}")

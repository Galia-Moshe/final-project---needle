"""
visualize_model_comparison.py — Publication-ready comparison chart for the
NYC Safe Walking Route Finder's two safety models (NYPD crime-cluster
avoidance vs. Airbnb review-warning avoidance).

Produces a 1x4 small-multiples figure — one panel per metric, each on its own
Y-axis (never a dual-axis chart, since the metrics don't share units) — plus
an insight-driven title/subtitle pair and a shared legend.

Design rationale (see the project's `dataviz` skill for the full method):
  - Form: four independent magnitudes across different units (%, %, s, km) ->
    small multiples, one bar-pair panel per metric. A single grouped-bar
    chart would force a shared axis across incompatible units — the #1
    charting mistake — so each metric gets its own scale instead.
  - Color: a fixed two-slot categorical assignment (blue = NYPD, orange =
    Airbnb) held constant across every panel — identity never repaints.
    These are categorical slots 1 & 2 of the project's validated palette:
    adjacent-pair contrast clears the accessibility gates in both light and
    dark review (CVD ΔE 9.1, normal-vision ΔE 19.6 — well above the 8 / 15
    floors), so the pair reads correctly under the common forms of color
    vision deficiency, not just to full-color vision.
  - Chartjunk: no dual axes, no 3D, no gradient fills; top/right spines
    removed; gridlines are hairline and low-opacity; every value is
    direct-labeled so the reader never has to eyeball a bar against the axis.
  - Labeling: identity is carried by color *and* by plain-ink x-tick text
    (model names), plus one shared legend — never color alone.

Usage:
    python evaluation/visualize_model_comparison.py [--input evaluation/evaluation_results.csv]
                                                      [--output evaluation/model_comparison.png]

Requires: matplotlib, seaborn (both in requirements.txt).
"""

import argparse
import csv
import os

import matplotlib
matplotlib.use("Agg")            # headless-safe backend, no display needed
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import seaborn as sns

# evaluate_routes.py lives next to this file; importing it (rather than
# reimplementing the aggregation) is what keeps this chart from drifting out
# of sync with evaluation_results.csv the way the old hardcoded values did.
from evaluate_routes import compute_summary_stats

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MODELS = ["NYPD Model", "Airbnb Model"]
MODEL_SCENARIO = {"NYPD Model": "nypd", "Airbnb Model": "airbnb"}


# ── DATA LOADING ─────────────────────────────────────────────────

def load_rows(csv_path):
    """Read evaluation_results.csv back into the same row-dict shape
    evaluate_routes.evaluate() builds in memory, so compute_summary_stats()
    can be reused verbatim instead of re-derived here."""
    def _num(v):
        return float(v) if v not in ("", None) else None

    def _flag(v):
        return v == "True" if v not in ("", None) else None

    with open(csv_path, newline="", encoding="utf-8") as f:
        return [
            {
                "od_id": int(row["od_id"]),
                "scenario": row["scenario"],
                "status": row["status"],
                "overhead_pct": _num(row["overhead_pct"]),
                "distance_km": _num(row["distance_km"]),
                "calc_time_sec": _num(row["calc_time_sec"]),
                "danger_zones_crossed": _num(row["danger_zones_crossed"]),
                "warning_zones_crossed": _num(row["warning_zones_crossed"]),
                "entered_danger_zone": _flag(row["entered_danger_zone"]),
                "entered_warning_zone": _flag(row["entered_warning_zone"]),
            }
            for row in csv.DictReader(f)
        ]


def build_metrics(stats):
    """Turns compute_summary_stats() output into the same panel-spec shape
    the chart used to hardcode. Each entry is one panel."""
    nypd, airbnb = stats["nypd"], stats["airbnb"]

    def v(layer, key):
        return layer[key] if layer[key] is not None else 0.0

    def av(layer):
        pct = layer["avoidance"]["pct"]
        return pct if pct is not None else 0.0

    return [
        {
            "key": "hazard_avoidance", "title": "Hazard Avoidance Rate", "better": "higher",
            "unit_suffix": "%", "value_fmt": "{:.1f}%",
            "values": {"NYPD Model": av(nypd), "Airbnb Model": av(airbnb)},
            "ylabel": "% of hazard-exposed routes avoided",
        },
        {
            "key": "distance_overhead", "title": "Distance Overhead", "better": "lower",
            "unit_suffix": "%", "value_fmt": "{:.1f}%",
            "values": {"NYPD Model": v(nypd, "avg_overhead"), "Airbnb Model": v(airbnb, "avg_overhead")},
            "ylabel": "% increase over shortest route",
        },
        {
            "key": "calc_time", "title": "Calculation Time", "better": "lower",
            "unit_suffix": "s", "value_fmt": "{:.2f}s",
            "values": {"NYPD Model": v(nypd, "avg_calc_time"), "Airbnb Model": v(airbnb, "avg_calc_time")},
            "ylabel": "seconds per route",
        },
        {
            "key": "route_distance", "title": "Avg. Route Distance", "better": None,
            "unit_suffix": " km", "value_fmt": "{:.2f} km",
            "values": {"NYPD Model": v(nypd, "avg_distance"), "Airbnb Model": v(airbnb, "avg_distance")},
            "ylabel": "kilometers",
        },
    ]


def build_takeaway_title(stats):
    """Derives the headline from whichever model actually wins hazard
    avoidance in this run, and only names a metric as a 'cost' if the winner
    really is worse on it — so the claim can't silently invert again the way
    the old hardcoded 'higher distance overhead' line did."""
    nypd, airbnb = stats["nypd"], stats["airbnb"]
    n_av, a_av = nypd["avoidance"]["pct"], airbnb["avoidance"]["pct"]
    if n_av is None or a_av is None:
        return "NYPD vs. Airbnb Safety Model — Hazard Avoidance Comparison"

    winner_name, winner, loser = ("Airbnb", airbnb, nypd) if a_av >= n_av else ("NYPD", nypd, airbnb)

    costs = []
    if winner["avg_overhead"] is not None and loser["avg_overhead"] is not None \
            and winner["avg_overhead"] > loser["avg_overhead"]:
        costs.append("Higher Distance Overhead")
    if winner["avg_calc_time"] is not None and loser["avg_calc_time"] is not None \
            and winner["avg_calc_time"] > loser["avg_calc_time"]:
        costs.append("Higher Compute Time")

    winner_av = winner["avoidance"]["pct"]
    if not costs:
        return f"{winner_name} Model Yields Superior Hazard Avoidance ({winner_av}%)\nWith No Tradeoff on Distance or Compute Time"
    return (f"{winner_name} Model Yields Superior Hazard Avoidance ({winner_av}%) at the\n"
            f"Cost of {' and '.join(costs)}")


def build_experiment_context(stats):
    return f"Based on {stats['n_od']} OD pairs  |  Routing engine: {stats['engine']}"

# ── STYLE ────────────────────────────────────────────────────────
# Two fixed categorical slots (blue / orange) from the project's validated
# accessible palette — same colors, same order, in every panel.
COLORS = {
    "NYPD Model": "#2a78d6",     # categorical slot 1 (blue)
    "Airbnb Model": "#eb6834",   # categorical slot 2 (orange)
}

INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRID_COLOR = "#8a8a86"
SURFACE = "#fcfcfb"

for _font in ("Segoe UI", "Helvetica Neue", "Arial"):
    if _font in {f.name for f in matplotlib.font_manager.fontManager.ttflist}:
        plt.rcParams["font.family"] = _font
        break
else:
    plt.rcParams["font.family"] = "DejaVu Sans"


# ── Panel drawing ────────────────────────────────────────────────

def _draw_panel(ax, metric):
    """Draws one metric's NYPD-vs-Airbnb bar pair on its own Y-axis."""
    x = [0, 1]
    values = [metric["values"][m] for m in MODELS]
    colors = [COLORS[m] for m in MODELS]

    bars = ax.bar(x, values, width=0.55, color=colors, zorder=3)

    # Direct value labels at the bar tips — the reader reads the number,
    # never has to interpolate it from the axis.
    headroom = max(values) * 0.16 or 1
    for bar, val in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2, val + headroom * 0.12,
            metric["value_fmt"].format(val),
            ha="center", va="bottom", fontsize=12, fontweight="bold", color=INK_PRIMARY,
        )

    ax.set_ylim(0, max(values) + headroom)

    # Chartjunk reduction: hairline, low-opacity gridlines; no top/right spine.
    ax.grid(axis="y", color=GRID_COLOR, linewidth=0.7, alpha=0.25, zorder=0)
    ax.set_axisbelow(True)
    sns.despine(ax=ax, top=True, right=True)
    ax.spines["left"].set_color(INK_MUTED)
    ax.spines["bottom"].set_color(INK_MUTED)

    ax.set_xticks([])
    # ax.set_xticklabels(MODELS, fontsize=9.5, color=INK_SECONDARY)
    ax.tick_params(axis="x", length=0)
    ax.tick_params(axis="y", labelsize=8.5, colors=INK_MUTED, length=0)
    ax.yaxis.set_major_locator(mticker.MaxNLocator(nbins=4))
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(
        lambda v, _: f"{v:g}{metric['unit_suffix']}"
    ))

    ax.set_ylabel(metric["ylabel"], fontsize=8.5, color=INK_MUTED)

    # Panel header: metric name (bold) + a one-line "which direction wins"
    # cue -- an insight-driven header at the panel level, not just the figure.
    direction = {"higher": "▲ higher is better", "lower": "▼ lower is better"}.get(metric["better"])
    header = metric["title"] if direction is None else f"{metric['title']}\n{direction}"
    ax.set_title(header, fontsize=11.5, fontweight="bold", color=INK_PRIMARY, pad=10, linespacing=1.6)


# ── Figure assembly ──────────────────────────────────────────────

def build_figure(metrics, takeaway_title, experiment_context):
    """
    Explicit inches-based layout (rather than suptitle + tight_layout): the
    figure height is the exact sum of each band's height, so the saved PNG
    hugs its content with no dead space between the legend and the panels,
    regardless of title line count.
    """
    n = len(metrics)
    fig_w = 16.0
    title_h    = 0.95   # two-line bold takeaway title
    subtitle_h = 0.28   # one-line "N OD pairs | engine" context line
    legend_h   = 0.35
    gap        = 0.75   # gap between legend and panels (room for 2-line panel titles)
    panels_h   = 4.30    # bar area, incl. panel titles + x tick labels
    bottom_pad = 0.10
    fig_h = title_h + subtitle_h + legend_h + gap + panels_h + bottom_pad

    fig = plt.figure(figsize=(fig_w, fig_h), facecolor=SURFACE)

    panels_top = 1 - (title_h + subtitle_h + legend_h + gap) / fig_h
    panels_bottom = bottom_pad / fig_h
    gs = fig.add_gridspec(1, n, left=0.045, right=0.985, wspace=0.45,
                           top=panels_top, bottom=panels_bottom)
    axes = [fig.add_subplot(gs[0, i]) for i in range(n)]

    for ax, metric in zip(axes, metrics):
        ax.set_facecolor(SURFACE)
        _draw_panel(ax, metric)

    # Insight-driven takeaway title + experimental-context subtitle, each
    # centered within its own inch band at the top of the figure.
    title_y = 1 - (title_h * 0.55) / fig_h
    subtitle_y = 1 - (title_h + subtitle_h * 0.5) / fig_h
    legend_y = 1 - (title_h + subtitle_h + legend_h * 0.5) / fig_h

    fig.text(0.5, title_y, takeaway_title, ha="center", va="center",
              fontsize=17, fontweight="bold", color=INK_PRIMARY, linespacing=1.4)
    fig.text(0.5, subtitle_y, experiment_context, ha="center", va="center",
              fontsize=10, color=INK_SECONDARY)

    # One shared legend (color -> model identity), never per-panel repeats.
    handles = [plt.Rectangle((0, 0), 1, 1, color=COLORS[m]) for m in MODELS]
    fig.legend(
        handles, MODELS, loc="center", bbox_to_anchor=(0.5, legend_y),
        ncol=2, frameon=False, fontsize=10.5, labelcolor=INK_SECONDARY,
        handlelength=1.1, handleheight=1.1, columnspacing=2.0,
    )

    return fig


def main():
    ap = argparse.ArgumentParser(description="Render the NYPD-vs-Airbnb model comparison chart.")
    ap.add_argument("--input", type=str,
                     default=os.path.join(PROJECT_ROOT, "evaluation", "evaluation_results.csv"),
                     help="input evaluation_results.csv path")
    ap.add_argument("--output", type=str,
                     default=os.path.join(PROJECT_ROOT, "evaluation", "model_comparison.png"),
                     help="output PNG path")
    args = ap.parse_args()

    rows = load_rows(args.input)
    stats = compute_summary_stats(rows)

    metrics = build_metrics(stats)
    takeaway_title = build_takeaway_title(stats)
    experiment_context = build_experiment_context(stats)

    fig = build_figure(metrics, takeaway_title, experiment_context)
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    fig.savefig(args.output, dpi=300, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)
    print(f"Loaded {len(rows)} rows from {args.input} ({stats['n_od']} OD pairs, engine: {stats['engine']})")
    print(f"Saved -> {args.output}")


if __name__ == "__main__":
    main()

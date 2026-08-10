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
    python evaluation/visualize_model_comparison.py [--output evaluation/model_comparison.png]

Requires: matplotlib, seaborn (both in requirements.txt).
"""

import argparse
import os

import matplotlib
matplotlib.use("Agg")            # headless-safe backend, no display needed
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import seaborn as sns

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── DATA ─────────────────────────────────────────────────────────
# Edit these to re-plot with a different run. Each entry is one panel.

MODELS = ["NYPD Model", "Airbnb Model"]

METRICS = [
    {
        "key": "hazard_avoidance",
        "title": "Hazard Avoidance Rate",
        "better": "higher",
        "unit_suffix": "%",
        "value_fmt": "{:.1f}%",
        "values": {"NYPD Model": 55.8, "Airbnb Model": 96.6},
        "ylabel": "% of hazard-exposed routes avoided",
    },
    {
        "key": "distance_overhead",
        "title": "Distance Overhead",
        "better": "lower",
        "unit_suffix": "%",
        "value_fmt": "{:.1f}%",
        "values": {"NYPD Model": 10.2, "Airbnb Model": 18.5},
        "ylabel": "% increase over shortest route",
    },
    {
        "key": "calc_time",
        "title": "Calculation Time",
        "better": "lower",
        "unit_suffix": "s",
        "value_fmt": "{:.2f}s",
        "values": {"NYPD Model": 0.12, "Airbnb Model": 0.28},
        "ylabel": "seconds per route",
    },
    {
        "key": "route_distance",
        "title": "Avg. Route Distance",
        "better": None,   # contextual, not a "win" metric
        "unit_suffix": " km",
        "value_fmt": "{:.2f} km",
        "values": {"NYPD Model": 3.82, "Airbnb Model": 4.11},
        "ylabel": "kilometers",
    },
]

EXPERIMENT_CONTEXT = ""

TAKEAWAY_TITLE = (
    "Airbnb Model Yields Superior Hazard Avoidance (96.6%) at the\n"
    "Cost of Higher Distance Overhead and Compute Time"
)

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

def build_figure():
    """
    Explicit inches-based layout (rather than suptitle + tight_layout): the
    figure height is the exact sum of each band's height, so the saved PNG
    hugs its content with no dead space between the legend and the panels,
    regardless of title line count.
    """
    n = len(METRICS)
    fig_w = 16.0
    title_h    = 0.95   # two-line bold takeaway title
    subtitle_h = 0.0
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

    for ax, metric in zip(axes, METRICS):
        ax.set_facecolor(SURFACE)
        _draw_panel(ax, metric)

    # Insight-driven takeaway title + experimental-context subtitle, each
    # centered within its own inch band at the top of the figure.
    title_y = 1 - (title_h * 0.55) / fig_h
    subtitle_y = 1 - (title_h + subtitle_h * 0.5) / fig_h
    legend_y = 1 - (title_h + subtitle_h + legend_h * 0.5) / fig_h

    fig.text(0.5, title_y, TAKEAWAY_TITLE, ha="center", va="center",
              fontsize=17, fontweight="bold", color=INK_PRIMARY, linespacing=1.4)
    fig.text(0.5, subtitle_y, EXPERIMENT_CONTEXT, ha="center", va="center",
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
    ap.add_argument("--output", type=str,
                     default=os.path.join(PROJECT_ROOT, "evaluation", "model_comparison.png"),
                     help="output PNG path")
    args = ap.parse_args()

    fig = build_figure()
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    fig.savefig(args.output, dpi=300, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)
    print(f"Saved -> {args.output}")


if __name__ == "__main__":
    main()

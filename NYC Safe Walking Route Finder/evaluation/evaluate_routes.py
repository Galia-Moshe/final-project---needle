"""
evaluate_routes.py — Benchmark the NYC Safe Walking Route Finder's routing engine.

Runs a simulation over N (default 100) random origin/destination (OD) walking
routes sampled from Manhattan/Brooklyn tourist hotspots and, for each OD pair,
computes three route scenarios by calling the project's own routing module
directly (no HTTP round-trip through the Flask app):

  a) baseline  — absolute shortest walking path, no safety penalties.
  b) nypd      — route that avoids NYPD HDBSCAN crime-cluster "danger zones"
                 (backend/danger_zones.py, data/police data process/danger_zones.csv).
  c) airbnb    — route that avoids Airbnb-review NLP "warning zones"
                 (backend/warning_zones.py, data/text mining/warning_zones.csv).

For each route it records distance, distance overhead vs. baseline, hazard
zone exposure (did the route cross a danger/warning zone, how many, how many
meters), and wall-clock calculation latency.

Results:
  - evaluation/evaluation_results.csv  (one row per OD x scenario)
  - a summary table printed to the console
  - evaluation/summary_table.png        (styled summary table, 300 DPI, for reports)

Usage:
    python evaluation/evaluate_routes.py [--n 100] [--seed 42] [--sleep 0.6]
                                          [--output evaluation/evaluation_results.csv]

Notes:
  - Each OD pair costs up to 3 live routing-engine calls (baseline, nypd,
    airbnb), so the full default run makes ~300 requests to ORS/OSRM.
  - `--sleep` throttles between calls to stay under the free ORS rate limit
    (40 req/min). Lower it if you're using OSRM only (no ORS_API_KEY set).
"""

import argparse
import csv
import math
import os
import random
import sys
import time
from datetime import datetime
from statistics import mean, median

import pandas as pd

# ── Make the project root importable regardless of cwd ────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from tqdm import tqdm
except ImportError:  # graceful fallback if tqdm isn't installed
    def tqdm(iterable, **kwargs):
        total = kwargs.get('total') or (len(iterable) if hasattr(iterable, '__len__') else None)
        desc = kwargs.get('desc', '')
        for i, item in enumerate(iterable, 1):
            print(f"\r{desc} {i}/{total}", end='', flush=True)
            yield item
        print()

from config import ORS_API_KEY
from backend.danger_zones import get_danger_zones
from backend.warning_zones import get_warning_zones
from backend.pathfinder import (
    _route_avoiding_ors,
    _route_avoiding_osrm,
    _in_zone,
    _haversine,
)

# ── NYC tourist-area bounding box (Manhattan / Brooklyn hotspots) ─
BBOX = {"min_lat": 40.670, "max_lat": 40.815, "min_lng": -74.020, "max_lng": -73.930}

# Well-known tourist anchors inside BBOX. OD pairs are sampled as a random
# anchor + a small random jitter, so points land on/near real walkable
# streets instead of in the middle of the Hudson or East River.
ANCHORS = [
    ("Times Square",            40.7580, -73.9855),
    ("Central Park South",      40.7660, -73.9776),
    ("Empire State Building",   40.7484, -73.9857),
    ("Grand Central",           40.7527, -73.9772),
    ("Rockefeller Center",      40.7587, -73.9787),
    ("Chelsea Market",          40.7423, -74.0061),
    ("High Line (Whitney)",     40.7400, -74.0080),
    ("Washington Square Park",  40.7308, -73.9973),
    ("SoHo",                    40.7233, -74.0030),
    ("Chinatown",               40.7158, -73.9970),
    ("Little Italy",            40.7191, -73.9973),
    ("Wall Street",             40.7074, -74.0113),
    ("Battery Park",            40.7033, -74.0170),
    ("South Street Seaport",    40.7075, -74.0021),
    ("Brooklyn Bridge (Mnh)",   40.7061, -73.9969),
    ("DUMBO",                   40.7033, -73.9903),
    ("Brooklyn Heights Prom.",  40.6960, -73.9959),
    ("Williamsburg (Bedford)",  40.7168, -73.9571),
    ("Prospect Park (GAP)",     40.6743, -73.9700),
    ("Union Square",            40.7359, -73.9911),
    ("Bryant Park",             40.7536, -73.9832),
    ("Lincoln Center",          40.7725, -73.9835),
    ("The Met (Museum Mile)",   40.7794, -73.9632),
    ("Harlem (125th St)",       40.8093, -73.9482),
]

JITTER_KM   = 0.30   # random spread around each anchor
MIN_OD_KM   = 0.30   # discard OD pairs that are basically the same point


# ── OD sampling ─────────────────────────────────────────────────

def _jittered_point(rng, lat0, lng0, jitter_km=JITTER_KM):
    """Random point within `jitter_km` of (lat0, lng0), uniform over the disk,
    clamped to BBOX so it always stays a 'valid' tourist-area coordinate."""
    r = jitter_km * math.sqrt(rng.random())
    theta = rng.uniform(0, 2 * math.pi)
    dlat = (r / 111) * math.cos(theta)
    dlng = (r / (111 * math.cos(math.radians(lat0)))) * math.sin(theta)
    lat = min(max(lat0 + dlat, BBOX["min_lat"]), BBOX["max_lat"])
    lng = min(max(lng0 + dlng, BBOX["min_lng"]), BBOX["max_lng"])
    return lat, lng


def generate_od_pairs(n, seed=42):
    """N random (src, dst) coordinate pairs drawn from tourist hotspots inside BBOX."""
    rng = random.Random(seed)
    pairs = []
    attempts = 0
    while len(pairs) < n and attempts < n * 50:
        attempts += 1
        a1, a2 = rng.sample(ANCHORS, 2)
        src = _jittered_point(rng, a1[1], a1[2])
        dst = _jittered_point(rng, a2[1], a2[2])
        if _haversine(src[0], src[1], dst[0], dst[1]) >= MIN_OD_KM:
            pairs.append({
                "od_id": len(pairs) + 1,
                "src_lat": round(src[0], 6), "src_lng": round(src[1], 6),
                "dst_lat": round(dst[0], 6), "dst_lng": round(dst[1], 6),
                "src_anchor": a1[0], "dst_anchor": a2[0],
            })
    return pairs


# ── Hazard-zone exposure ────────────────────────────────────────

def _zone_bbox(zone):
    """Cheap bounding box per zone so we can skip the expensive point-in-polygon
    test for zones nowhere near the point being checked."""
    poly = zone.get("polygon") or []
    if poly:
        lats = [p[0] for p in poly]
        lngs = [p[1] for p in poly]
        return min(lats), max(lats), min(lngs), max(lngs)
    r = zone.get("radius_km", 0.3)
    dlat = r / 111
    dlng = r / (111 * max(0.01, math.cos(math.radians(zone["lat"]))))
    return zone["lat"] - dlat, zone["lat"] + dlat, zone["lng"] - dlng, zone["lng"] + dlng


def _prep_zones(zones):
    return [(z, _zone_bbox(z)) for z in zones]


def hazard_exposure(coords, zones_with_bbox):
    """
    Walks the route's coordinate list and checks it against a hazard-zone
    layer (NYPD danger zones or Airbnb-review warning zones).

    Returns:
      zones_crossed   — number of distinct zones the route enters
      exposure_m       — approx. meters of the route that fall inside any zone
      entered_hazard   — bool, True if the route enters at least one zone
    """
    if not coords or not zones_with_bbox:
        return 0, 0.0, False

    hit_ids = set()
    exposure_km = 0.0
    prev = None
    prev_inside = False

    for c in coords:
        lat, lng = c["lat"], c["lng"]
        inside = False
        for zone, (mn_lat, mx_lat, mn_lng, mx_lng) in zones_with_bbox:
            if mn_lat <= lat <= mx_lat and mn_lng <= lng <= mx_lng and _in_zone(lat, lng, zone):
                hit_ids.add(zone["id"])
                inside = True
                break
        if prev is not None and inside and prev_inside:
            exposure_km += _haversine(prev["lat"], prev["lng"], lat, lng)
        prev, prev_inside = c, inside

    return len(hit_ids), round(exposure_km * 1000, 1), bool(hit_ids)


# ── Route calculation (direct Python import of the routing engine) ─

route_fn = _route_avoiding_ors if ORS_API_KEY else _route_avoiding_osrm
ENGINE_NAME = "ORS (avoid_polygons)" if ORS_API_KEY else "OSRM (bypass heuristic)"


def calc_route(src_lat, src_lng, dst_lat, dst_lng, avoid_zones):
    """Calls the project's own routing function and times it."""
    t0 = time.perf_counter()
    try:
        route = route_fn(src_lat, src_lng, dst_lat, dst_lng, avoid_zones)
        err = None
    except Exception as exc:                      # graceful error handling
        route, err = None, str(exc)
    elapsed = time.perf_counter() - t0
    return route, elapsed, err


def non_endpoint_zones(zones, src, dst):
    """Mirrors backend.pathfinder.find_routes: a zone containing an endpoint
    can't be avoided (you have to start/end inside it), so it's dropped from
    the 'must avoid' set before routing."""
    endpoints = [src, dst]
    return [z for z in zones if not any(_in_zone(lat, lng, z) for lat, lng in endpoints)]


# ── Main evaluation loop ────────────────────────────────────────

FIELDNAMES = [
    "od_id", "src_lat", "src_lng", "dst_lat", "dst_lng", "src_anchor", "dst_anchor",
    "scenario", "status", "error",
    "distance_km", "duration_min", "overhead_pct", "calc_time_sec",
    "danger_zones_crossed", "danger_exposure_m", "entered_danger_zone",
    "warning_zones_crossed", "warning_exposure_m", "entered_warning_zone",
]


def evaluate(n, seed, sleep_s, output_path):
    print(f"Routing engine: {ENGINE_NAME}")

    danger_zones = get_danger_zones()
    warning_zones = get_warning_zones()
    print(f"Loaded {len(danger_zones)} NYPD danger zones, {len(warning_zones)} Airbnb warning zones.")

    danger_bbox = _prep_zones(danger_zones)
    warning_bbox = _prep_zones(warning_zones)

    od_pairs = generate_od_pairs(n, seed=seed)
    print(f"Sampled {len(od_pairs)} OD pairs from {len(ANCHORS)} tourist hotspots in bbox {BBOX}.\n")

    rows = []

    for od in tqdm(od_pairs, desc="Evaluating routes", total=len(od_pairs)):
        src = (od["src_lat"], od["src_lng"])
        dst = (od["dst_lat"], od["dst_lng"])
        base_row = {
            "od_id": od["od_id"],
            "src_lat": od["src_lat"], "src_lng": od["src_lng"],
            "dst_lat": od["dst_lat"], "dst_lng": od["dst_lng"],
            "src_anchor": od["src_anchor"], "dst_anchor": od["dst_anchor"],
        }

        # a) Baseline — absolute shortest path, no avoidance
        baseline, t_base, err = calc_route(*src, *dst, [])
        time.sleep(sleep_s)

        if baseline is None:
            for scenario in ("baseline", "nypd", "airbnb"):
                rows.append({**base_row, "scenario": scenario, "status": "error",
                             "error": err or "no route found", "distance_km": None,
                             "duration_min": None, "overhead_pct": None,
                             "calc_time_sec": round(t_base, 3),
                             "danger_zones_crossed": None, "danger_exposure_m": None,
                             "entered_danger_zone": None, "warning_zones_crossed": None,
                             "warning_exposure_m": None, "entered_warning_zone": None})
            continue

        base_dist = baseline["distance_km"]
        dz_cnt, dz_m, dz_hit = hazard_exposure(baseline["coords"], danger_bbox)
        wz_cnt, wz_m, wz_hit = hazard_exposure(baseline["coords"], warning_bbox)
        rows.append({**base_row, "scenario": "baseline", "status": "ok", "error": "",
                     "distance_km": base_dist, "duration_min": baseline["total_time"],
                     "overhead_pct": 0.0, "calc_time_sec": round(t_base, 3),
                     "danger_zones_crossed": dz_cnt, "danger_exposure_m": dz_m,
                     "entered_danger_zone": dz_hit, "warning_zones_crossed": wz_cnt,
                     "warning_exposure_m": wz_m, "entered_warning_zone": wz_hit})

        # b) NYPD objective safety path — avoid crime-cluster danger zones
        avoid_dz = non_endpoint_zones(danger_zones, src, dst)
        nypd_route, t_nypd, err = calc_route(*src, *dst, avoid_dz)
        time.sleep(sleep_s)

        if nypd_route is None:
            rows.append({**base_row, "scenario": "nypd", "status": "error",
                         "error": err or "no route found", "distance_km": None,
                         "duration_min": None, "overhead_pct": None,
                         "calc_time_sec": round(t_nypd, 3),
                         "danger_zones_crossed": None, "danger_exposure_m": None,
                         "entered_danger_zone": None, "warning_zones_crossed": None,
                         "warning_exposure_m": None, "entered_warning_zone": None})
        else:
            dist = nypd_route["distance_km"]
            overhead = ((dist - base_dist) / base_dist) * 100 if base_dist else None
            dz_cnt, dz_m, dz_hit = hazard_exposure(nypd_route["coords"], danger_bbox)
            wz_cnt, wz_m, wz_hit = hazard_exposure(nypd_route["coords"], warning_bbox)
            rows.append({**base_row, "scenario": "nypd", "status": "ok", "error": "",
                         "distance_km": dist, "duration_min": nypd_route["total_time"],
                         "overhead_pct": round(overhead, 2) if overhead is not None else None,
                         "calc_time_sec": round(t_nypd, 3),
                         "danger_zones_crossed": dz_cnt, "danger_exposure_m": dz_m,
                         "entered_danger_zone": dz_hit, "warning_zones_crossed": wz_cnt,
                         "warning_exposure_m": wz_m, "entered_warning_zone": wz_hit})

        # c) Airbnb subjective safety path — avoid review-warning zones
        avoid_wz = non_endpoint_zones(warning_zones, src, dst)
        airbnb_route, t_air, err = calc_route(*src, *dst, avoid_wz)
        time.sleep(sleep_s)

        if airbnb_route is None:
            rows.append({**base_row, "scenario": "airbnb", "status": "error",
                         "error": err or "no route found", "distance_km": None,
                         "duration_min": None, "overhead_pct": None,
                         "calc_time_sec": round(t_air, 3),
                         "danger_zones_crossed": None, "danger_exposure_m": None,
                         "entered_danger_zone": None, "warning_zones_crossed": None,
                         "warning_exposure_m": None, "entered_warning_zone": None})
        else:
            dist = airbnb_route["distance_km"]
            overhead = ((dist - base_dist) / base_dist) * 100 if base_dist else None
            dz_cnt, dz_m, dz_hit = hazard_exposure(airbnb_route["coords"], danger_bbox)
            wz_cnt, wz_m, wz_hit = hazard_exposure(airbnb_route["coords"], warning_bbox)
            rows.append({**base_row, "scenario": "airbnb", "status": "ok", "error": "",
                         "distance_km": dist, "duration_min": airbnb_route["total_time"],
                         "overhead_pct": round(overhead, 2) if overhead is not None else None,
                         "calc_time_sec": round(t_air, 3),
                         "danger_zones_crossed": dz_cnt, "danger_exposure_m": dz_m,
                         "entered_danger_zone": dz_hit, "warning_zones_crossed": wz_cnt,
                         "warning_exposure_m": wz_m, "entered_warning_zone": wz_hit})

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nSaved {len(rows)} rows ({len(od_pairs)} OD pairs x 3 scenarios) -> {output_path}")

    return rows


# ── Summary ──────────────────────────────────────────────────────

def _stat(vals, fn, default=None):
    vals = [v for v in vals if v is not None]
    return round(fn(vals), 2) if vals else default


def compute_summary_stats(rows):
    """Crunches the raw per-route rows into the aggregate numbers used by both
    the console summary and the exported image, so the two never drift apart."""
    ok = [r for r in rows if r["status"] == "ok"]
    by_scenario = {s: [r for r in ok if r["scenario"] == s] for s in ("baseline", "nypd", "airbnb")}

    n_od = len({r["od_id"] for r in rows})
    n_failed = {s: sum(1 for r in rows if r["scenario"] == s and r["status"] != "ok")
                for s in ("baseline", "nypd", "airbnb")}

    # Hazard avoidance rate: of the OD pairs whose baseline route actually
    # crossed a hazard zone, what fraction did the safety route clear entirely?
    def avoidance_rate(scenario, entered_key):
        base_by_od = {r["od_id"]: r for r in by_scenario["baseline"]}
        safe_by_od = {r["od_id"]: r for r in by_scenario[scenario]}
        exposed_baseline = [od for od, r in base_by_od.items() if r[entered_key]]
        if not exposed_baseline:
            return {"pct": None, "exposed": 0, "avoided": 0}
        avoided = sum(1 for od in exposed_baseline
                      if od in safe_by_od and not safe_by_od[od][entered_key])
        return {"pct": round(100 * avoided / len(exposed_baseline), 1),
                "exposed": len(exposed_baseline), "avoided": avoided}

    def layer_stats(scenario, zones_crossed_key, entered_key):
        s = by_scenario[scenario]
        return {
            "avg_overhead":    _stat([r["overhead_pct"] for r in s], mean),
            "median_overhead": _stat([r["overhead_pct"] for r in s], median),
            "avg_distance":    _stat([r["distance_km"] for r in s], mean),
            "avg_hazard_zones": _stat([r[zones_crossed_key] for r in s], mean),
            "avg_calc_time":   _stat([r["calc_time_sec"] for r in s], mean),
            "avoidance":       avoidance_rate(scenario, entered_key),
        }

    all_times = [r["calc_time_sec"] for r in rows if r["calc_time_sec"] is not None]

    return {
        "engine": ENGINE_NAME,
        "n_od": n_od,
        "n_failed": n_failed,
        "nypd": layer_stats("nypd", "danger_zones_crossed", "entered_danger_zone"),
        "airbnb": layer_stats("airbnb", "warning_zones_crossed", "entered_warning_zone"),
        "overall_avg_calc_time": _stat(all_times, mean),
    }


def _fmt(val, suffix="", none_str="n/a"):
    return f"{val}{suffix}" if val is not None else none_str


def _fmt_avoidance(av):
    if av["pct"] is None:
        return "n/a (baseline never exposed)"
    return f"{av['pct']}%  ({av['avoided']}/{av['exposed']})"


def print_summary(stats):
    n_failed = stats["n_failed"]

    print("\n" + "=" * 72)
    print("ROUTE EVALUATION SUMMARY".center(72))
    print("=" * 72)
    print(f"Routing engine:            {stats['engine']}")
    print(f"OD pairs attempted:        {stats['n_od']}")
    print(f"Failed routes  - baseline: {n_failed['baseline']}   "
          f"nypd: {n_failed['nypd']}   airbnb: {n_failed['airbnb']}")
    print("-" * 72)

    print(f"{'Metric':38s}{'NYPD (danger)':17s}{'Airbnb (warning)':17s}")
    print("-" * 72)

    rows_spec = [
        ("Avg distance overhead vs baseline",    "avg_overhead", "%"),
        ("Median distance overhead vs baseline", "median_overhead", "%"),
        ("Avg route distance",                   "avg_distance", " km"),
        ("Avg own-layer hazard zones crossed",   "avg_hazard_zones", ""),
        ("Avg calc time",                        "avg_calc_time", " s"),
    ]
    for label, key, suffix in rows_spec:
        v_nypd = _fmt(stats["nypd"][key], suffix)
        v_air = _fmt(stats["airbnb"][key], suffix)
        print(f"{label:38s}{v_nypd:17s}{v_air:17s}")

    print("-" * 72)
    print("Hazard avoidance rate (vs baseline):")
    print(f"  NYPD danger-zone avoidance rate:   {_fmt_avoidance(stats['nypd']['avoidance'])}")
    print(f"  Airbnb warning-zone avoidance rate: {_fmt_avoidance(stats['airbnb']['avoidance'])}")

    print("-" * 72)
    print(f"Overall avg route calc time (all scenarios): {_fmt(stats['overall_avg_calc_time'], ' s')}")
    print("=" * 72)


# ── Styled summary table image ──────────────────────────────────

# Colors for the exported PNG (dark teal header, alternating light-gray rows)
HEADER_COLOR = "#0F4C5C"
HEADER_TEXT_COLOR = "white"
ROW_COLOR_EVEN = "#F2F4F5"
ROW_COLOR_ODD = "white"
BORDER_COLOR = "#B8C2C6"
TITLE_COLOR = "#0F4C5C"


def build_summary_dataframe(stats):
    """Turns compute_summary_stats() output into the display DataFrame that
    gets rendered into the PNG (and could just as well be printed/saved)."""
    rows = [
        ("Avg. Distance Overhead vs. Baseline",
         _fmt(stats["nypd"]["avg_overhead"], "%"), _fmt(stats["airbnb"]["avg_overhead"], "%")),
        ("Median Distance Overhead vs. Baseline",
         _fmt(stats["nypd"]["median_overhead"], "%"), _fmt(stats["airbnb"]["median_overhead"], "%")),
        ("Avg. Route Distance",
         _fmt(stats["nypd"]["avg_distance"], " km"), _fmt(stats["airbnb"]["avg_distance"], " km")),
        ("Avg. Hazard Zones Crossed (Own Layer)",
         _fmt(stats["nypd"]["avg_hazard_zones"]), _fmt(stats["airbnb"]["avg_hazard_zones"])),
        ("Hazard Avoidance Rate vs. Baseline",
         _fmt_avoidance(stats["nypd"]["avoidance"]), _fmt_avoidance(stats["airbnb"]["avoidance"])),
        ("Avg. Route Calculation Time",
         _fmt(stats["nypd"]["avg_calc_time"], " s"), _fmt(stats["airbnb"]["avg_calc_time"], " s")),
    ]
    return pd.DataFrame(
        rows, columns=["Metric", "NYPD Objective Safety\n(Danger Zones)", "Airbnb Subjective Safety\n(Warning Zones)"]
    )


def render_summary_image(stats, output_path):
    """Renders compute_summary_stats() output as a styled table PNG (300 DPI),
    suitable for dropping straight into a report.

    Every element is placed using an explicit inches-based layout (rather than
    matplotlib's automatic table centering) so the figure hugs its content
    tightly regardless of row count, instead of leaving a blank gap between
    the table and the footer."""
    import matplotlib
    matplotlib.use("Agg")            # headless-safe backend, no display needed
    import matplotlib.pyplot as plt

    df = build_summary_dataframe(stats)
    n_rows = len(df)

    # ── Inches-based layout: figure height = sum of every band's height ──
    fig_w        = 9.5
    title_h      = 0.50
    subtitle_h   = 0.30
    gap_top      = 0.15
    header_row_h = 0.70
    data_row_h   = 0.55
    gap_bottom   = 0.20
    footer_h     = 0.28

    table_h = header_row_h + n_rows * data_row_h
    fig_h = title_h + subtitle_h + gap_top + table_h + gap_bottom + footer_h

    fig = plt.figure(figsize=(fig_w, fig_h))

    # Table axes sized to exactly the table's own height -> no dead space.
    ax_left, ax_width = 0.03, 0.94
    ax_bottom = (gap_bottom + footer_h) / fig_h
    ax_height = table_h / fig_h
    ax = fig.add_axes((ax_left, ax_bottom, ax_width, ax_height))
    ax.axis("off")

    table = ax.table(
        cellText=df.values,
        colLabels=df.columns,
        cellLoc="center",
        loc="center",
        bbox=(0, 0, 1, 1),      # fill the axes exactly
        colWidths=[0.42, 0.29, 0.29],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(11)

    header_frac = header_row_h / table_h
    data_frac = data_row_h / table_h
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor(BORDER_COLOR)
        cell.set_linewidth(1)
        cell.PAD = 0.04
        if row == 0:
            cell.set_height(header_frac)
            cell.set_facecolor(HEADER_COLOR)
            cell.set_text_props(color=HEADER_TEXT_COLOR, weight="bold", fontsize=11.5)
        else:
            cell.set_height(data_frac)
            cell.set_facecolor(ROW_COLOR_EVEN if row % 2 == 0 else ROW_COLOR_ODD)
            if col == 0:
                cell.set_text_props(weight="bold", ha="left")

    # ── Title / subtitle, centered within their own inch bands at the top ─
    title_y = 1 - (title_h * 0.62) / fig_h
    subtitle_y = 1 - (title_h + subtitle_h * 0.5) / fig_h
    fig.text(0.5, title_y, "NYC Safe Walking Route Finder - Evaluation Results",
              ha="center", va="center", fontsize=16, weight="bold", color=TITLE_COLOR)

    n_failed = stats["n_failed"]
    subtitle = (
        f"Engine: {stats['engine']}   |   OD pairs: {stats['n_od']}   |   "
        f"Failed (baseline/nypd/airbnb): {n_failed['baseline']}/{n_failed['nypd']}/{n_failed['airbnb']}   |   "
        f"Overall avg. calc time: {_fmt(stats['overall_avg_calc_time'], ' s')}"
    )
    fig.text(0.5, subtitle_y, subtitle, ha="center", va="center", fontsize=8.5, color="#555555")

    # ── Footer, centered within its own band directly under the table ─
    footer_y = (footer_h * 0.5) / fig_h
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    fig.text(0.97, footer_y, f"Generated {generated}", ha="right", va="center",
              fontsize=7, color="#888888")

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    fig.savefig(output_path, dpi=300, facecolor="white")
    plt.close(fig)
    print(f"Saved styled summary table -> {output_path}")


def main():
    ap = argparse.ArgumentParser(description="Benchmark the safe walking route finder.")
    ap.add_argument("--n", type=int, default=100, help="number of OD pairs (default 100)")
    ap.add_argument("--seed", type=int, default=42, help="random seed (default 42)")
    ap.add_argument("--sleep", type=float, default=0.6,
                     help="seconds to sleep between routing calls, to respect API rate limits (default 0.6)")
    ap.add_argument("--output", type=str,
                     default=os.path.join(PROJECT_ROOT, "evaluation", "evaluation_results.csv"),
                     help="output CSV path")
    ap.add_argument("--image-output", type=str,
                     default=os.path.join(PROJECT_ROOT, "evaluation", "summary_table.png"),
                     help="output PNG path for the styled summary table")
    args = ap.parse_args()

    rows = evaluate(args.n, args.seed, args.sleep, args.output)
    stats = compute_summary_stats(rows)
    print_summary(stats)
    render_summary_image(stats, args.image_output)


if __name__ == "__main__":
    main()

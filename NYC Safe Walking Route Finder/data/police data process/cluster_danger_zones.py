"""
Cluster NYPD crime hotspots into danger zones using HDBSCAN, then build the
outer boundary (convex hull) polygon of each cluster with a spatial buffer.

Input : Pre-aggregated CSV with columns latitude,longitude,crime_count
        (e.g. filtered_hotspots_nypd.csv). Each row is a hotspot point and
        crime_count is the number of crimes it represents.
Output:
  • danger_zones.csv     — app-ready format (id,name,lat,lng,radius_km,polygon)
                            read directly by backend/danger_zones.py
  • danger_zones.geojson — standard GeoJSON FeatureCollection of the same hulls

Requires: pip install pandas scikit-learn scipy shapely

Note: neither scikit-learn's HDBSCAN nor the standalone `hdbscan` package
supports a `sample_weight` argument in `fit()`. Weighting is instead
approximated by replicating each row crime_count times before fitting, so
HDBSCAN sees the true point density (see cluster_points).
"""

import csv
import json
import os
import uuid

import numpy as np
import pandas as pd
from scipy.spatial import ConvexHull
from scipy.spatial import QhullError
from sklearn.cluster import HDBSCAN
from shapely.geometry import Polygon

# ── Config — tune these ─────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_CSV      = os.path.join(SCRIPT_DIR, 'filtered_hotspots_nypd.csv')
OUTPUT_CSV     = os.path.join(SCRIPT_DIR, 'danger_zones.csv')
OUTPUT_GEOJSON = os.path.join(SCRIPT_DIR, 'danger_zones.geojson')

MIN_CLUSTER_SIZE = 8   # HDBSCAN: smallest grouping considered a cluster
MIN_SAMPLES      = 5    # HDBSCAN: conservativeness of noise classification
TOP_N_DENSEST    = 90   # keep only the N densest clusters (points per km^2)
BUFFER_METERS    = 1    # How much to inflate the polygons outwards (in meters)

MAX_REPLICAS     = 5    # cap on per-row duplication when weighting clusters


def load_data(path):
    """Load the crime hotspot dataset and drop rows with missing coordinates."""
    df = pd.read_csv(path)
    df = df.dropna(subset=['latitude', 'longitude']).reset_index(drop=True)
    return df


def cluster_points(df):
    """
    Run HDBSCAN on latitude/longitude, weighting each hotspot by replicating
    its row before fitting — HDBSCAN has no sample_weight support, so this is
    how it sees busier hotspots as denser instead of treating every hotspot
    as equal. Longitude is scaled by cos(mean latitude) so a degree of
    longitude and a degree of latitude represent comparable distances at
    NYC's latitude.

    Replica counts are crime_count normalized to [1, MAX_REPLICAS] rather
    than the raw crime_count: every crime_count in this dataset already
    exceeds MIN_CLUSTER_SIZE, so replicating by the raw value would let any
    single hotspot's self-duplicates alone form a "cluster", regardless of
    real neighbors — collapsing every row into its own degenerate cluster.
    Capping keeps the weighting signal while requiring genuine neighbors to
    reach MIN_CLUSTER_SIZE.

    Returns one label per row of the original (un-replicated) df. Points
    labeled -1 are noise and are not part of any cluster.
    """
    mean_lat_rad = np.radians(df['latitude'].mean())

    weights = df['crime_count'].to_numpy()
    w_min, w_max = weights.min(), weights.max()
    scaled = (weights - w_min) / (w_max - w_min) if w_max > w_min else np.zeros_like(weights, dtype=float)
    repeats = np.clip(np.round(1 + (MAX_REPLICAS - 1) * scaled), 1, MAX_REPLICAS).astype(int)

    expanded = df.loc[df.index.repeat(repeats)]
    expanded_coords = np.column_stack([
        expanded['latitude'].to_numpy(),
        expanded['longitude'].to_numpy() * np.cos(mean_lat_rad),
    ])

    clusterer = HDBSCAN(min_cluster_size=MIN_CLUSTER_SIZE, min_samples=MIN_SAMPLES)
    clusterer.fit(expanded_coords)

    # Map labels back onto the original rows. Duplicates of the same row are
    # at identical coordinates and in practice always land in one cluster,
    # but take the majority label per row (first label on a tie) in case any
    # duplicate set is split across clusters.
    expanded_labels = pd.Series(clusterer.labels_, index=expanded.index)
    majority_label = expanded_labels.groupby(level=0).agg(lambda s: s.mode().iloc[0])
    return majority_label.reindex(df.index).to_numpy()


def _haversine_km(lat1, lng1, lat2, lng2):
    """Vectorized haversine distance (km) from one point to an array of points."""
    R = 6371.0088
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dlat = np.radians(lat2 - lat1)
    dlng = np.radians(lng2 - lng1)
    a = np.sin(dlat / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlng / 2) ** 2
    return R * 2 * np.arcsin(np.sqrt(a))


def _polygon_area_km2(hull_pts, center_lat):
    """
    Approximate area (km^2) of a lat/lon polygon: project to local km-scale
    x/y then apply the shoelace formula.
    """
    km_per_deg_lat = 111.32
    km_per_deg_lng = 111.32 * np.cos(np.radians(center_lat))
    x = hull_pts[:, 1] * km_per_deg_lng
    y = hull_pts[:, 0] * km_per_deg_lat
    return 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def build_cluster_polygons(df, labels):
    """
    Group points by cluster id, compute convex hull, and apply an outward
    spatial buffer to create realistic, block-sized danger zones.
    """
    grouped = df.assign(cluster=labels).groupby('cluster')
    zones = []

    # 1 degree of latitude is ~111,320 meters
    buffer_deg = BUFFER_METERS / 111320.0

    for cluster_id, group in grouped:
        if cluster_id == -1:
            continue   # HDBSCAN noise — not a real cluster, skip

        pts = group[['latitude', 'longitude']].to_numpy()
        if len(pts) < 3:
            continue

        try:
            hull = ConvexHull(pts, qhull_options='Qt')
        except QhullError:
            continue   # degenerate cluster — skip

        hull_pts = pts[hull.vertices]   # ordered boundary ring, [lat, lon] pairs
        c_lat, c_lng = pts[:, 0].mean(), pts[:, 1].mean()

        # Weighted density: sum of crime_count inside the cluster / area
        area_km2 = max(_polygon_area_km2(hull_pts, c_lat), 1e-6)
        density = group['crime_count'].sum() / area_km2

        # ── תוספת הניפוח הגיאומטרי (Buffering) ──────────────────────────
        # נועלים את עיוות קווי האורך של ניו יורק לצורך הניפוח הסימטרי
        cos_lat = np.cos(np.radians(c_lat))
        projected_pts = [(lon * cos_lat, lat) for lat, lon in hull_pts]

        # יצירת פוליגון וניפוחו כלפי חוץ
        poly = Polygon(projected_pts)
        buffered_poly = poly.buffer(buffer_deg)

        # החזרת נקודות הפוליגון המנופח חזרה לפורמט הגיאוגרפי המקורי
        # [:-1] מסיר את הנקודה הסוגרת הכפולה ש-shapely מייצר אוטומטית במעגל
        buffered_pts = [[y, x / cos_lat] for x, y in buffered_poly.exterior.coords][:-1]
        buffered_hull_arr = np.array(buffered_pts)

        # עדכון רדיוס החסימה לפי הצורה המנופחת החדשה
        radius_km = float(_haversine_km(c_lat, c_lng, buffered_hull_arr[:, 0], buffered_hull_arr[:, 1]).max())

        zones.append({
            'id':          str(uuid.uuid4()),
            'name':        f'Crime Cluster {cluster_id}',
            'lat':         round(float(c_lat), 6),
            'lng':         round(float(c_lng), 6),
            'radius_km':   round(radius_km, 3),
            'polygon':     [[round(float(la), 6), round(float(lo), 6)] for la, lo in buffered_pts],
            'point_count': int(len(pts)),
            'density':     float(density),
        })

    return zones


def keep_densest(zones, top_n=TOP_N_DENSEST):
    """Keep only the top_n clusters ranked by points-per-km^2 density."""
    return sorted(zones, key=lambda z: -z['density'])[:top_n]


def save_app_csv(zones, path):
    """App-ready format, consumed directly by backend/danger_zones.py."""
    with open(path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(
            f, fieldnames=['id', 'name', 'lat', 'lng', 'radius_km', 'polygon'],
            extrasaction='ignore',
        )
        writer.writeheader()
        for z in zones:
            writer.writerow({**z, 'polygon': json.dumps(z['polygon'])})


def save_geojson(zones, path):
    """Standard GeoJSON FeatureCollection (coordinates in lon, lat order)."""
    features = []
    for z in zones:
        ring = [[lng, lat] for lat, lng in z['polygon']]
        ring.append(ring[0])   # GeoJSON polygon rings must be closed
        features.append({
            'type': 'Feature',
            'properties': {
                'name':        z['name'],
                'radius_km':   z['radius_km'],
                'point_count': z['point_count'],
                'density':     round(z['density'], 1),
            },
            'geometry': {'type': 'Polygon', 'coordinates': [ring]},
        })
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'type': 'FeatureCollection', 'features': features}, f)


def main():
    df = load_data(INPUT_CSV)
    print(f'Loaded {len(df)} points with valid coordinates from {INPUT_CSV}')

    labels = cluster_points(df)
    n_clusters = len(set(labels) - {-1})
    n_noise = int((labels == -1).sum())
    zones = build_cluster_polygons(df, labels)
    print(f'Found {n_clusters} clusters ({n_noise} noise points), '
          f'built {len(zones)} buffered hull polygons')

    zones = keep_densest(zones, TOP_N_DENSEST)
    densities = [round(z['density']) for z in zones]
    print(f'Kept the {len(zones)} densest clusters '
          f'(density range: {min(densities)}-{max(densities)} pts/km^2)')

    save_app_csv(zones, OUTPUT_CSV)
    print(f'Saved app-ready zones to {OUTPUT_CSV}')

    save_geojson(zones, OUTPUT_GEOJSON)
    print(f'Saved GeoJSON to {OUTPUT_GEOJSON}')


if __name__ == '__main__':
    main()
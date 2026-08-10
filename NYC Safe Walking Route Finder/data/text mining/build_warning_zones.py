"""
Build "Warning Zones" from discrete review-flagged coordinates using a
buffer-and-dissolve approach: each coordinate gets a circular buffer, and
overlapping buffers are dissolved into single, amorphous polygons. Unlike
NYPD crime clustering, these are individual property reviews, not a density
surface, so there's no HDBSCAN step here — just geometry.

Input : CSV with columns latitude,longitude
        (e.g. high_risk_safety_coordinates.csv) — each row is a location
        that received a negative safety/security review.
Output:
  • warning_zones.csv     — app-ready format (id,name,lat,lng,radius_km,polygon)
                            read directly by backend/danger_zones.py
  • warning_zones.geojson — standard GeoJSON FeatureCollection of the same
                            polygons

Requires: pip install pandas numpy shapely
"""

import csv
import json
import os
import uuid

import numpy as np
import pandas as pd
import shapely
from shapely.ops import unary_union

# ── Config — tune these ─────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_CSV      = os.path.join(SCRIPT_DIR, 'high_risk_safety_coordinates.csv')
OUTPUT_CSV     = os.path.join(SCRIPT_DIR, 'warning_zones.csv')
OUTPUT_GEOJSON = os.path.join(SCRIPT_DIR, 'warning_zones.geojson')

BUFFER_METERS = 50   # radius of each point's circular buffer, before dissolve


def load_data(path):
    """Load review-flagged coordinates and drop rows with missing values."""
    df = pd.read_csv(path)
    return df.dropna(subset=['latitude', 'longitude']).reset_index(drop=True)


def _haversine_km(lat1, lng1, lat2, lng2):
    """Vectorized haversine distance (km) from one point to an array of points."""
    R = 6371.0088
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dlat = np.radians(lat2 - lat1)
    dlng = np.radians(lng2 - lng1)
    a = np.sin(dlat / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlng / 2) ** 2
    return R * 2 * np.arcsin(np.sqrt(a))


def build_warning_zones(df):
    """
    Buffer each coordinate by BUFFER_METERS and dissolve overlapping buffers
    into unified polygons. Longitude is scaled by cos(mean latitude) before
    buffering so a BUFFER_METERS buffer is a true circle at NYC's latitude
    (rather than an ellipse), then un-scaled back to geographic coordinates
    for the output. Points whose buffers don't overlap anything stay as
    standalone circular polygons.
    """
    lat = df['latitude'].to_numpy()
    lon = df['longitude'].to_numpy()
    cos_lat = np.cos(np.radians(lat.mean()))
    buffer_deg = BUFFER_METERS / 111320.0   # 1 degree of latitude is ~111,320 m

    points = shapely.points(lon * cos_lat, lat)
    buffers = shapely.buffer(points, buffer_deg)
    dissolved = unary_union(buffers)
    geoms = list(dissolved.geoms) if hasattr(dissolved, 'geoms') else [dissolved]

    zones = []
    for i, geom in enumerate(geoms, 1):
        exterior = np.array(geom.exterior.coords)[:-1]   # drop closing duplicate
        poly_latlon = np.column_stack([exterior[:, 1], exterior[:, 0] / cos_lat])

        centroid = geom.centroid
        c_lat, c_lng = float(centroid.y), float(centroid.x / cos_lat)
        radius_km = float(_haversine_km(c_lat, c_lng, poly_latlon[:, 0], poly_latlon[:, 1]).max())
        point_count = int(shapely.contains(geom, points).sum())

        zones.append({
            'id':          str(uuid.uuid4()),
            'name':        f'Review Warning Zone {i}',
            'lat':         round(c_lat, 6),
            'lng':         round(c_lng, 6),
            'radius_km':   round(radius_km, 3),
            'polygon':     [[round(float(la), 6), round(float(lo), 6)] for la, lo in poly_latlon],
            'point_count': point_count,
        })

    return zones


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
            },
            'geometry': {'type': 'Polygon', 'coordinates': [ring]},
        })
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'type': 'FeatureCollection', 'features': features}, f)


def main():
    df = load_data(INPUT_CSV)
    print(f'Loaded {len(df)} points with valid coordinates from {INPUT_CSV}')

    zones = build_warning_zones(df)
    print(f'Dissolved {len(df)} buffered points ({BUFFER_METERS}m each) '
          f'into {len(zones)} warning zones')

    save_app_csv(zones, OUTPUT_CSV)
    print(f'Saved app-ready zones to {OUTPUT_CSV}')

    save_geojson(zones, OUTPUT_GEOJSON)
    print(f'Saved GeoJSON to {OUTPUT_GEOJSON}')


if __name__ == '__main__':
    main()

import csv
import json
import math
import uuid
from collections import defaultdict
from config import DANGER_ZONES_FILE


# ── Flexible column lookup (case-insensitive) ─────────────────────

def _col(row, *keys):
    for k in keys:
        val = row.get(k, '').strip()
        if val:
            return val
    # case-insensitive fallback
    row_lower = {k2.lower(): v for k2, v in row.items()}
    for k in keys:
        val = row_lower.get(k.lower(), '').strip()
        if val:
            return val
    return None


# ── Haversine (km) ────────────────────────────────────────────────

def _haversine(lat1, lng1, lat2, lng2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlng / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


# ── CSV format detection ──────────────────────────────────────────

def _is_internal(fieldnames):
    """True if the CSV was written by _save() (our internal format)."""
    required = {'id', 'name', 'lat', 'lng', 'radius_km'}
    return required.issubset({f.lower() for f in (fieldnames or [])})


# ── Public API ────────────────────────────────────────────────────

def get_danger_zones():
    """
    Read danger zones from danger_zones.csv.

    Accepts two formats automatically:
      • Internal  (id, name, lat, lng, radius_km) — written by this module
      • External  (e.g. Point_ID, Latitude, Longitude, Area_Name) —
        groups rows by area name, computes one centroid zone per group.
    """
    try:
        with open(DANGER_ZONES_FILE, 'r', encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            if not rows:
                return []

            if _is_internal(reader.fieldnames):
                return _parse_internal(rows)
            else:
                return _parse_external(rows)

    except FileNotFoundError:
        return []


def _parse_internal(rows):
    zones = []
    for row in rows:
        try:
            poly_str = row.get('polygon', '[]') or '[]'
            try:
                polygon = json.loads(poly_str)
            except json.JSONDecodeError:
                polygon = []
            zones.append({
                'id':        row['id'],
                'name':      row['name'],
                'lat':       float(row['lat']),
                'lng':       float(row['lng']),
                'radius_km': float(row['radius_km']),
                'polygon':   polygon,
            })
        except (KeyError, ValueError):
            continue
    return zones


def _sort_polygon(points, c_lat, c_lng):
    """Sort boundary points by polar angle around centroid → valid simple polygon."""
    return sorted(points, key=lambda p: math.atan2(p[0] - c_lat, p[1] - c_lng))


def _parse_external(rows):
    """
    Group coordinate points into zones, then one zone per group.
    Centroid = average of all points; radius = max distance from centroid.

    Grouping key, in priority order:
      • area name (e.g. Area_Name)   → boundary polygon from the raw points
      • DBSCAN 'cluster' id          → circle zone (centroid + radius);
                                       noise points (cluster == -1) are dropped
      • neither present              → each row is its own zone
    """
    named_groups    = defaultdict(list)
    cluster_groups  = defaultdict(list)
    use_clusters    = False

    for i, row in enumerate(rows, 1):
        lat = _col(row, 'lat', 'latitude', 'Latitude')
        lng = _col(row, 'lng', 'lon', 'longitude', 'Longitude')
        if lat is None or lng is None:
            continue
        try:
            point = (float(lat), float(lng))
        except ValueError:
            continue

        name = _col(row, 'name', 'Name', 'Area_Name', 'area_name')
        if name:
            named_groups[name].append(point)
            continue

        cluster = _col(row, 'cluster', 'Cluster')
        if cluster is not None:
            use_clusters = True
            if cluster == '-1':
                continue   # DBSCAN noise/outlier — not a real hotspot
            cluster_groups[cluster].append(point)
        else:
            named_groups[f'Zone {i}'].append(point)

    zones = []
    for name, points in named_groups.items():
        zones.append(_make_polygon_zone(name, points))
    for cluster_id, points in cluster_groups.items():
        zones.append(_make_circle_zone(f'Crime Cluster {cluster_id}', points))
    return zones


def _centroid_and_radius(points):
    c_lat = sum(p[0] for p in points) / len(points)
    c_lng = sum(p[1] for p in points) / len(points)
    radius = (
        max(_haversine(c_lat, c_lng, p[0], p[1]) for p in points)
        if len(points) > 1 else 0.3
    )
    return c_lat, c_lng, radius


def _make_polygon_zone(name, points):
    """Boundary polygon built from the raw points (used for named/drawn areas)."""
    c_lat, c_lng, radius = _centroid_and_radius(points)
    ordered = _sort_polygon(points, c_lat, c_lng)
    return {
        'id':        str(uuid.uuid4()),
        'name':      name,
        'lat':       round(c_lat, 6),
        'lng':       round(c_lng, 6),
        'radius_km': round(max(0.1, radius), 2),
        'polygon':   ordered,
    }


def _make_circle_zone(name, points):
    """Circle zone (centroid + radius) — cheap to check, used for crime clusters."""
    c_lat, c_lng, radius = _centroid_and_radius(points)
    return {
        'id':        str(uuid.uuid4()),
        'name':      name,
        'lat':       round(c_lat, 6),
        'lng':       round(c_lng, 6),
        'radius_km': round(max(0.1, radius), 2),
        'polygon':   [],
    }



import csv
import io
import json
import math
import uuid
from collections import defaultdict
from config import DANGER_ZONES_FILE

# Columns written by _save() — our internal storage format
FIELDNAMES = ['id', 'name', 'lat', 'lng', 'radius_km', 'polygon']


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
    Group coordinate points by area name → one zone per unique name.
    Centroid = average of all points; radius = max distance from centroid.
    """
    groups = defaultdict(list)
    for i, row in enumerate(rows, 1):
        lat = _col(row, 'lat', 'latitude', 'Latitude')
        lng = _col(row, 'lng', 'lon', 'longitude', 'Longitude')
        name = _col(row, 'name', 'Name', 'Area_Name', 'area_name') or f'Zone {i}'
        if lat is None or lng is None:
            continue
        try:
            groups[name].append((float(lat), float(lng)))
        except ValueError:
            continue

    zones = []
    for name, points in groups.items():
        c_lat = sum(p[0] for p in points) / len(points)
        c_lng = sum(p[1] for p in points) / len(points)
        radius = (
            max(_haversine(c_lat, c_lng, p[0], p[1]) for p in points)
            if len(points) > 1 else 0.3
        )
        # Sort into a valid polygon ring (angular order around centroid)
        ordered = _sort_polygon(points, c_lat, c_lng)
        zones.append({
            'id':        str(uuid.uuid4()),
            'name':      name,
            'lat':       round(c_lat, 6),
            'lng':       round(c_lng, 6),
            'radius_km': round(max(0.1, radius), 2),
            'polygon':   ordered,
        })
    return zones


def _save(zones):
    """Write zones in our internal format (with polygon column as JSON string)."""
    with open(DANGER_ZONES_FILE, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for zone in zones:
            writer.writerow({
                'id':        zone['id'],
                'name':      zone['name'],
                'lat':       zone['lat'],
                'lng':       zone['lng'],
                'radius_km': zone['radius_km'],
                'polygon':   json.dumps(zone.get('polygon') or []),
            })


def add_danger_zone(data):
    zones = get_danger_zones()
    zone = {
        'id':        str(uuid.uuid4()),
        'name':      data.get('name', 'Danger Zone'),
        'lat':       float(data['lat']),
        'lng':       float(data['lng']),
        'radius_km': float(data.get('radius_km', 0.5)),
        'polygon':   [],   # manually added zones are circles, not polygons
    }
    zones.append(zone)
    _save(zones)
    return zone


def remove_danger_zone(zone_id):
    zones = get_danger_zones()
    new_zones = [z for z in zones if z['id'] != zone_id]
    if len(new_zones) == len(zones):
        return False
    _save(new_zones)
    return True


def import_from_csv(file_obj):
    """
    Load danger zones from an uploaded CSV file and replace all existing zones.
    Accepts any column naming; groups multiple coordinate rows by area name.
    """
    reader = csv.DictReader(io.TextIOWrapper(file_obj, encoding='utf-8-sig'))
    rows = list(reader)

    if _is_internal(reader.fieldnames):
        zones = _parse_internal(rows)
        # Re-assign fresh IDs so uploaded file is treated as new data
        for z in zones:
            z['id'] = str(uuid.uuid4())
    else:
        zones = _parse_external(rows)

    _save(zones)
    return zones

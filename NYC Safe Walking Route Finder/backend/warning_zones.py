import csv
from config import WARNING_ZONES_FILE
from .danger_zones import _parse_internal


def get_warning_zones():
    """
    Read review-based warning zones from warning_zones.csv (produced by
    data/text mining/build_warning_zones.py — buffer-and-dissolve polygons
    around hotel/apartment locations with negative safety reviews).
    Columns: id,name,lat,lng,radius_km,polygon.
    """
    try:
        with open(WARNING_ZONES_FILE, 'r', encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            return _parse_internal(rows) if rows else []
    except FileNotFoundError:
        return []

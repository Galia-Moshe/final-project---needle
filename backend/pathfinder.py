"""
Walking-only router.

Primary:  OpenRouteService (ORS) foot-walking with native avoid_polygons.
          Gives the true shortest path around danger zones.
Fallback: OSRM public server + waypoint heuristic (used when ORS key not set).
"""

import math
import requests
from .danger_zones import get_danger_zones
from config import ORS_API_KEY

ORS_URL     = "https://api.openrouteservice.org/v2/directions/foot-walking/geojson"
OSRM_BASE   = "http://router.project-osrm.org/route/v1/foot"
HEADERS     = {"User-Agent": "NYC-Transit-Recommender/1.0"}
BYPASS_MARGIN = 0.003   # degrees ~330 m, used by the OSRM fallback only


# ── Shared geometry helpers ───────────────────────────────────────

def _haversine(lat1, lng1, lat2, lng2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlng / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def _point_in_polygon(lat, lng, poly):
    """Ray-casting. poly = [[lat, lng], ...]"""
    n, inside, j = len(poly), False, len(poly) - 1
    for i in range(n):
        lat_i, lng_i = poly[i][0], poly[i][1]
        lat_j, lng_j = poly[j][0], poly[j][1]
        if ((lng_i > lng) != (lng_j > lng)) and \
           (lat < (lat_j - lat_i) * (lng - lng_i) / (lng_j - lng_i) + lat_i):
            inside = not inside
        j = i
    return inside


def _in_zone(lat, lng, zone):
    poly = zone.get('polygon', [])
    if len(poly) >= 3:
        return _point_in_polygon(lat, lng, poly)
    return _haversine(lat, lng, zone['lat'], zone['lng']) <= zone.get('radius_km', 0.5)


def _blocking_zones(coords, zones):
    blocking = []
    for zone in zones:
        if any(_in_zone(c['lat'], c['lng'], zone) for c in coords):
            blocking.append(zone)
    return blocking


def _circle_poly(lat, lng, radius_km, n=24):
    """Approximate a circle zone as a polygon ring."""
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        dlat = radius_km / 111 * math.cos(a)
        dlng = radius_km / (111 * math.cos(math.radians(lat))) * math.sin(a)
        pts.append([lat + dlat, lng + dlng])
    return pts


# ── ORS routing (primary) ─────────────────────────────────────────

def _ors(src_lat, src_lng, dst_lat, dst_lng, avoid_polys=None):
    """
    Call ORS foot-walking. avoid_polys = list of [[lat,lng],...] polygon rings.
    Returns route dict or None.
    """
    body = {"coordinates": [[src_lng, src_lat], [dst_lng, dst_lat]]}

    if avoid_polys:
        rings = []
        for poly in avoid_polys:
            ring = [[p[1], p[0]] for p in poly]   # lat,lng → lng,lat for GeoJSON
            if ring[0] != ring[-1]:
                ring.append(ring[0])               # close the ring
            rings.append([ring])
        body["options"] = {
            "avoid_polygons": {"type": "MultiPolygon", "coordinates": rings}
        }

    hdrs = {
        **HEADERS,
        "Authorization": ORS_API_KEY,
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/geo+json",
    }

    try:
        resp = requests.post(ORS_URL, json=body, headers=hdrs, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return None

    features = data.get("features", [])
    if not features:
        return None

    feat    = features[0]
    coords  = feat.get("geometry", {}).get("coordinates", [])
    props   = feat.get("properties", {})
    summary = props.get("summary", {})

    steps = []
    for seg in props.get("segments", []):
        for s in seg.get("steps", []):
            instr = s.get("instruction", "")
            if instr:
                steps.append({
                    "instruction":  instr,
                    "distance_m":   round(s.get("distance", 0)),
                    "duration_min": round(s.get("duration", 0) / 60, 1),
                })

    return {
        "total_time":  round(summary.get("duration", 0) / 60, 1),
        "distance_km": round(summary.get("distance", 0) / 1000, 2),
        "coords":      [{"lat": c[1], "lng": c[0]} for c in coords],
        "steps":       steps,
    }


def _find_routes_ors(src_lat, src_lng, dst_lat, dst_lng, zones):
    # Direct (potentially unsafe) route
    direct = _ors(src_lat, src_lng, dst_lat, dst_lng)
    if direct is None:
        return None

    blocking = _blocking_zones(direct["coords"], zones)
    if not blocking:
        direct["is_safe"] = True
        return {"safe_route": direct, "unsafe_route": None}

    direct["is_safe"] = False

    # Build the avoid list: polygon zones use their actual boundary;
    # circle zones are approximated as 24-gon polygons.
    avoid = []
    for z in zones:
        poly = z.get("polygon", [])
        avoid.append(poly if len(poly) >= 3 else _circle_poly(z["lat"], z["lng"], z["radius_km"]))

    safe = _ors(src_lat, src_lng, dst_lat, dst_lng, avoid)
    if safe:
        safe["is_safe"] = not bool(_blocking_zones(safe["coords"], zones))
        if not safe["is_safe"]:
            safe = None   # ORS still went through a zone (shouldn't happen)

    return {"safe_route": safe, "unsafe_route": direct}


# ── OSRM fallback (used when ORS key not configured) ─────────────

def _bearing_to_dir(bearing):
    dirs = ["north", "northeast", "east", "southeast",
            "south", "southwest", "west", "northwest"]
    return dirs[int((bearing + 22.5) / 45) % 8]


def _build_instruction(m_type, modifier, name, bearing_after):
    on = f" on {name}" if name else ""
    if m_type == "depart":
        return f"Head {_bearing_to_dir(bearing_after)}{on}"
    if m_type == "arrive":
        return "Arrive at your destination"
    mod_map = {
        "left": "Turn left", "right": "Turn right",
        "sharp left": "Turn sharp left", "sharp right": "Turn sharp right",
        "slight left": "Keep left", "slight right": "Keep right",
        "straight": "Continue straight", "uturn": "Make a U-turn",
    }
    if m_type in ("turn", "end of road"):
        return f"{mod_map.get(modifier, 'Continue')}{on}"
    if m_type == "fork":
        return f"{'Keep left' if 'left' in modifier else 'Keep right'}{on}"
    if m_type in ("new name", "continue", "notification", "merge"):
        return f"Continue{on}" if name else None
    if m_type in ("roundabout", "rotary"):
        return f"Enter roundabout{on}"
    return None


def _osrm(waypoints):
    """OSRM foot route. waypoints = [(lat, lng), ...]"""
    coord_str = ";".join(f"{lng},{lat}" for lat, lng in waypoints)
    try:
        resp = requests.get(
            f"{OSRM_BASE}/{coord_str}",
            params={"overview": "full", "geometries": "geojson", "steps": "true"},
            headers=HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return None

    if data.get("code") != "Ok" or not data.get("routes"):
        return None

    r         = data["routes"][0]
    coords_raw = r["geometry"]["coordinates"]
    legs      = r.get("legs", [])
    steps     = []

    for leg_idx, leg in enumerate(legs):
        is_last = leg_idx == len(legs) - 1
        for step in leg.get("steps", []):
            maneuver = step.get("maneuver", {})
            m_type   = maneuver.get("type", "")
            if m_type == "arrive" and not is_last:
                continue
            if m_type == "depart" and leg_idx > 0:
                continue
            instr = _build_instruction(
                m_type, maneuver.get("modifier", ""),
                step.get("name", ""), maneuver.get("bearing_after", 0),
            )
            if instr:
                steps.append({
                    "instruction":  instr,
                    "distance_m":   round(step.get("distance", 0)),
                    "duration_min": round(step.get("duration", 0) / 60, 1),
                })

    return {
        "total_time":  round(r["duration"] / 60, 1),
        "distance_km": round(r["distance"] / 1000, 2),
        "coords":      [{"lat": c[1], "lng": c[0]} for c in coords_raw],
        "steps":       steps,
    }


def _osrm_bypass_candidates(zone):
    poly = zone.get("polygon", [])
    if poly:
        lats = [p[0] for p in poly]; lngs = [p[1] for p in poly]
    else:
        dlat = zone["radius_km"] / 111
        dlng = dlat / max(0.01, math.cos(math.radians(zone["lat"])))
        lats = [zone["lat"] - dlat, zone["lat"] + dlat]
        lngs = [zone["lng"] - dlng, zone["lng"] + dlng]
    n = max(lats) + BYPASS_MARGIN; s = min(lats) - BYPASS_MARGIN
    e = max(lngs) + BYPASS_MARGIN; w = min(lngs) - BYPASS_MARGIN
    c_lat = (n + s) / 2;           c_lng = (e + w) / 2
    return [(n,c_lng),(s,c_lng),(c_lat,e),(c_lat,w),(n,w),(n,e),(s,w),(s,e)]


def _find_routes_osrm(src_lat, src_lng, dst_lat, dst_lng, zones):
    shortest = _osrm([(src_lat, src_lng), (dst_lat, dst_lng)])
    if shortest is None:
        return None

    blocking = _blocking_zones(shortest["coords"], zones)
    if not blocking:
        shortest["is_safe"] = True
        return {"safe_route": shortest, "unsafe_route": None}

    shortest["is_safe"] = False
    best = None
    for zone in blocking:
        for wp in _osrm_bypass_candidates(zone):
            c = _osrm([(src_lat, src_lng), wp, (dst_lat, dst_lng)])
            if c and not _blocking_zones(c["coords"], zones):
                c["is_safe"] = True
                if best is None or c["total_time"] < best["total_time"]:
                    best = c

    return {"safe_route": best, "unsafe_route": shortest}


# ── Public entry point ────────────────────────────────────────────

def find_routes(src_lat, src_lng, dst_lat, dst_lng):
    """
    Returns {'safe_route': ..., 'unsafe_route': ...} or None on network failure.
    Uses ORS (accurate) when key is configured, OSRM heuristic otherwise.
    """
    zones = get_danger_zones()
    if ORS_API_KEY:
        return _find_routes_ors(src_lat, src_lng, dst_lat, dst_lng, zones)
    return _find_routes_osrm(src_lat, src_lng, dst_lat, dst_lng, zones)

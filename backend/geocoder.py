import requests

NOMINATIM = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "NYC-Transit-Recommender/1.0"}
NYC_BBOX = "-74.26,40.49,-73.70,40.92"


def geocode_autocomplete(query, limit=6):
    """Return address suggestions for a partial query, restricted to NYC."""
    params = {
        "q": f"{query}, New York City",
        "format": "json",
        "limit": limit,
        "viewbox": NYC_BBOX,
        "bounded": 1,
        "countrycodes": "us",
    }
    try:
        resp = requests.get(NOMINATIM, params=params, headers=HEADERS, timeout=8)
        resp.raise_for_status()
        results = resp.json()
    except Exception:
        return []

    suggestions = []
    for r in results:
        # Shorten "Empire State Building, 350, 5th Avenue, …, United States" → first 3 parts
        parts = r["display_name"].split(", ")
        label = ", ".join(parts[:3])
        suggestions.append({"label": label, "full": r["display_name"]})
    return suggestions


def geocode(address):
    """Return {lat, lng, display_name} for an address, or None if not found."""
    params = {
        "q": f"{address}, New York City, NY",
        "format": "json",
        "limit": 1,
    }
    resp = requests.get(NOMINATIM, params=params, headers=HEADERS, timeout=10)
    resp.raise_for_status()
    results = resp.json()
    if not results:
        return None
    r = results[0]
    return {"lat": float(r["lat"]), "lng": float(r["lon"]), "display_name": r["display_name"]}



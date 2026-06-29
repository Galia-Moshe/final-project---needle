import json
import uuid
from config import DANGER_ZONES_FILE


def get_danger_zones():
    try:
        with open(DANGER_ZONES_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save(zones):
    with open(DANGER_ZONES_FILE, 'w') as f:
        json.dump(zones, f, indent=2)


def add_danger_zone(data):
    zones = get_danger_zones()
    zone = {
        'id': str(uuid.uuid4()),
        'name': data.get('name', 'Danger Zone'),
        'lat': float(data['lat']),
        'lng': float(data['lng']),
        'radius_km': float(data.get('radius_km', 0.5)),
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

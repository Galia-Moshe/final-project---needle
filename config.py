import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
NYC_STOPS_FILE = os.path.join(DATA_DIR, 'nyc_stops.json')
DANGER_ZONES_FILE = os.path.join(DATA_DIR, 'danger_zones.json')

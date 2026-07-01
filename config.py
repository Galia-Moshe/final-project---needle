import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
DANGER_ZONES_FILE = os.path.join(DATA_DIR, 'danger_zones.csv')

# Get a free key at: openrouteservice.org/dev/#/signup → Dashboard → Request a Token
ORS_API_KEY = os.environ.get('ORS_API_KEY', '')

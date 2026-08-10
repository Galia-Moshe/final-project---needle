import os

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'))

DATA_DIR = os.path.join(BASE_DIR, 'data')
DANGER_ZONES_FILE = os.path.join(DATA_DIR, 'police data process', 'danger_zones.csv')
REVIEW_RISK_POINTS_FILE = os.path.join(DATA_DIR, 'text mining', 'high_risk_safety_coordinates.csv')
WARNING_ZONES_FILE = os.path.join(DATA_DIR, 'text mining', 'warning_zones.csv')

# Get a free key at: openrouteservice.org/dev/#/signup → Dashboard → Request a Token
ORS_API_KEY = os.environ.get('ORS_API_KEY', '')


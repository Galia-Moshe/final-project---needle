import csv
from config import REVIEW_RISK_POINTS_FILE


def get_review_risk_points():
    """
    Read hotel locations whose reviews mention tourist safety concerns
    (produced by text-mining review data). CSV columns: longitude, latitude.
    """
    try:
        with open(REVIEW_RISK_POINTS_FILE, 'r', encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            points = []
            for row in reader:
                try:
                    points.append({
                        'lat': float(row['latitude']),
                        'lng': float(row['longitude']),
                    })
                except (KeyError, ValueError):
                    continue
            return points
    except FileNotFoundError:
        return []

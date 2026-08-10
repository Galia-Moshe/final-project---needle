from flask import Blueprint, render_template, request, jsonify
from .pathfinder import find_routes
from .danger_zones import get_danger_zones
from .geocoder import geocode, geocode_autocomplete
from .review_risk_points import get_review_risk_points
from .warning_zones import get_warning_zones

api_bp = Blueprint('api', __name__)


@api_bp.route('/')
def index():
    return render_template('index.html')


@api_bp.route('/api/autocomplete')
def autocomplete():
    q = request.args.get('q', '').strip()
    if len(q) < 3:
        return jsonify([])
    return jsonify(geocode_autocomplete(q))



def _point_from_request(data, prefix, addr_key):
    """Resolve a {lat, lng, display_name} point from either raw coordinates
    (map click picking) or a free-text address (form search)."""
    lat, lng = data.get(f'{prefix}_lat'), data.get(f'{prefix}_lng')
    if lat is not None and lng is not None:
        lat, lng = float(lat), float(lng)
        return {'lat': lat, 'lng': lng, 'display_name': f'Pinned ({lat:.5f}, {lng:.5f})'}, None

    addr = (data.get(addr_key) or '').strip()
    if not addr:
        return None, 'Please provide both a start and end address.'
    geo = geocode(addr)
    if not geo:
        return None, f'Could not find "{addr}". Try being more specific.'
    return geo, None


@api_bp.route('/api/routes', methods=['POST'])
def routes():
    data = request.get_json()
    case = data.get('case') if data.get('case') in ('nypd', 'reviews') else 'nypd'

    src_geo, err = _point_from_request(data, 'source', 'source_address')
    if err:
        return jsonify({'error': err}), 400

    dst_geo, err = _point_from_request(data, 'dest', 'destination_address')
    if err:
        return jsonify({'error': err}), 400

    result = find_routes(src_geo['lat'], src_geo['lng'], dst_geo['lat'], dst_geo['lng'], case=case)
    if result is None:
        return jsonify({'error': 'No walking route found between these locations.'}), 503

    if result['green_route'] is None and result['red_route'] is None:
        return jsonify({'error': 'No walking route found between these locations.'}), 404

    result['source_address'] = src_geo['display_name']
    result['source_geo']     = src_geo
    result['dest_address']   = dst_geo['display_name']
    result['dest_geo']       = dst_geo

    return jsonify(result)


@api_bp.route('/api/review-risk-points', methods=['GET'])
def review_risk_points_list():
    return jsonify(get_review_risk_points())


@api_bp.route('/api/danger-zones', methods=['GET'])
def danger_zones_list():
    return jsonify(get_danger_zones())


@api_bp.route('/api/warning-zones', methods=['GET'])
def warning_zones_list():
    return jsonify(get_warning_zones())

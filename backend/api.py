from flask import Blueprint, render_template, request, jsonify
from .pathfinder import find_routes
from .danger_zones import get_danger_zones, add_danger_zone, remove_danger_zone, import_from_csv
from .geocoder import geocode, geocode_autocomplete

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



@api_bp.route('/api/routes', methods=['POST'])
def routes():
    data = request.get_json()
    src_addr = (data.get('source_address') or '').strip()
    dst_addr = (data.get('destination_address') or '').strip()

    if not src_addr or not dst_addr:
        return jsonify({'error': 'Please provide both a start and end address.'}), 400

    src_geo = geocode(src_addr)
    if not src_geo:
        return jsonify({'error': f'Could not find "{src_addr}". Try being more specific.'}), 400

    dst_geo = geocode(dst_addr)
    if not dst_geo:
        return jsonify({'error': f'Could not find "{dst_addr}". Try being more specific.'}), 400

    result = find_routes(src_geo['lat'], src_geo['lng'], dst_geo['lat'], dst_geo['lng'])
    if result is None:
        return jsonify({'error': 'Walking route service is unavailable. Try again later.'}), 503

    if result['safe_route'] is None and result['unsafe_route'] is None:
        return jsonify({'error': 'No walking route found between these locations.'}), 404

    result['source_address'] = src_addr
    result['source_geo']     = src_geo
    result['dest_address']   = dst_addr
    result['dest_geo']       = dst_geo

    return jsonify(result)


@api_bp.route('/api/danger-zones', methods=['GET'])
def danger_zones_list():
    return jsonify(get_danger_zones())


@api_bp.route('/api/danger-zones', methods=['POST'])
def danger_zones_add():
    zone = add_danger_zone(request.get_json())
    return jsonify(zone), 201


@api_bp.route('/api/danger-zones/import', methods=['POST'])
def danger_zones_import():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    f = request.files['file']
    if not f.filename.lower().endswith('.csv'):
        return jsonify({'error': 'File must be a .csv'}), 400
    try:
        zones = import_from_csv(f)
    except Exception as e:
        return jsonify({'error': f'Could not parse CSV: {e}'}), 400
    return jsonify({'imported': len(zones), 'zones': zones}), 200


@api_bp.route('/api/danger-zones/<zone_id>', methods=['DELETE'])
def danger_zones_delete(zone_id):
    if remove_danger_zone(zone_id):
        return jsonify({'message': 'Removed'}), 200
    return jsonify({'error': 'Zone not found'}), 404

from flask import Blueprint, render_template, request, jsonify
from .transit import get_stops_list
from .pathfinder import find_route
from .danger_zones import get_danger_zones, add_danger_zone, remove_danger_zone

api_bp = Blueprint('api', __name__)


@api_bp.route('/')
def index():
    return render_template('index.html', stops=get_stops_list())


@api_bp.route('/api/stops')
def stops():
    return jsonify(get_stops_list())


@api_bp.route('/api/routes', methods=['POST'])
def routes():
    data = request.get_json()
    source = data.get('source')
    destination = data.get('destination')

    if not source or not destination:
        return jsonify({'error': 'Source and destination required'}), 400
    if source == destination:
        return jsonify({'error': 'Source and destination must be different'}), 400

    result = find_route(source, destination)
    if result is None:
        return jsonify({'error': 'No safe route found between these stops'}), 404

    return jsonify(result)


@api_bp.route('/api/danger-zones', methods=['GET'])
def danger_zones_list():
    return jsonify(get_danger_zones())


@api_bp.route('/api/danger-zones', methods=['POST'])
def danger_zones_add():
    zone = add_danger_zone(request.get_json())
    return jsonify(zone), 201


@api_bp.route('/api/danger-zones/<zone_id>', methods=['DELETE'])
def danger_zones_delete(zone_id):
    if remove_danger_zone(zone_id):
        return jsonify({'message': 'Removed'}), 200
    return jsonify({'error': 'Zone not found'}), 404

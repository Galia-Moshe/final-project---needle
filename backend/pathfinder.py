import heapq
import math
from .transit import get_graph
from .danger_zones import get_danger_zones


def _haversine_km(lat1, lng1, lat2, lng2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def _in_danger_zone(stop, zones):
    for z in zones:
        if _haversine_km(stop['lat'], stop['lng'], z['lat'], z['lng']) <= z['radius_km']:
            return True
    return False


def find_route(source_id, dest_id):
    graph = get_graph()
    zones = get_danger_zones()
    stops_by_id = graph['stops_by_id']
    adj = graph['adj']

    if source_id not in stops_by_id or dest_id not in stops_by_id:
        return None

    # Always allow source and dest even if inside a danger zone
    safe = {
        s['id'] for s in graph['stops']
        if not _in_danger_zone(s, zones) or s['id'] in (source_id, dest_id)
    }

    dist = {sid: float('inf') for sid in stops_by_id}
    dist[source_id] = 0
    prev = {}
    pq = [(0, source_id)]

    while pq:
        d, node = heapq.heappop(pq)
        if d > dist[node]:
            continue
        if node == dest_id:
            break
        for neighbor, line, time in adj.get(node, []):
            if neighbor not in safe:
                continue
            nd = d + time
            if nd < dist[neighbor]:
                dist[neighbor] = nd
                prev[neighbor] = (node, line)
                heapq.heappush(pq, (nd, neighbor))

    if dist[dest_id] == float('inf'):
        return None

    # Reconstruct raw path
    raw = []
    cur = dest_id
    while cur != source_id:
        node, line = prev[cur]
        raw.append({'stop': stops_by_id[cur], 'from_stop': stops_by_id[node], 'line': line})
        cur = node
    raw.reverse()

    # Merge consecutive segments on the same line into a single instruction
    steps = []
    if raw:
        seg_line = raw[0]['line']
        seg_from = raw[0]['from_stop']
        seg_to = raw[0]['stop']
        for seg in raw[1:]:
            if seg['line'] == seg_line:
                seg_to = seg['stop']
            else:
                steps.append({'line': seg_line, 'from': seg_from, 'to': seg_to})
                seg_line = seg['line']
                seg_from = seg['from_stop']
                seg_to = seg['stop']
        steps.append({'line': seg_line, 'from': seg_from, 'to': seg_to})

    # Full coordinate list for drawing the polyline
    coords = [stops_by_id[source_id]] + [s['stop'] for s in raw]

    return {
        'total_time': dist[dest_id],
        'steps': steps,
        'coords': [{'lat': s['lat'], 'lng': s['lng'], 'name': s['name']} for s in coords],
        'source': stops_by_id[source_id],
        'destination': stops_by_id[dest_id],
    }

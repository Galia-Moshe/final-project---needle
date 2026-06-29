import json
from collections import defaultdict
from config import NYC_STOPS_FILE

_graph = None


def _load_graph():
    global _graph
    if _graph is not None:
        return _graph

    with open(NYC_STOPS_FILE, 'r') as f:
        data = json.load(f)

    stops_by_id = {s['id']: s for s in data['stops']}
    adj = defaultdict(list)

    for conn in data['connections']:
        a, b = conn['from'], conn['to']
        line, time = conn['line'], conn['time']
        adj[a].append((b, line, time))
        adj[b].append((a, line, time))

    _graph = {
        'stops': data['stops'],
        'stops_by_id': stops_by_id,
        'adj': dict(adj),
    }
    return _graph


def get_graph():
    return _load_graph()


def get_stops_list():
    return _load_graph()['stops']

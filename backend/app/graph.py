import json
from collections import defaultdict
from pathlib import Path

from app.models import Edge, GraphData

# (neighbor_id, line_id, distance, travel_time)
Adjacency = dict[str, list[tuple[str, str, float, float]]]


def load_graph_data(path: Path) -> GraphData:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return GraphData.model_validate(raw)


def station_ids(data: GraphData) -> set[str]:
    return {s.id for s in data.stations}


def build_adjacency(edges: list[Edge]) -> Adjacency:
    adj: dict[str, list[tuple[str, str, float, float]]] = defaultdict(list)
    for e in edges:
        tup = (e.line_id, e.distance, e.travel_time)
        adj[e.from_station_id].append((e.to_station_id, *tup))
        adj[e.to_station_id].append((e.from_station_id, *tup))
    return dict(adj)

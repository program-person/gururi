import heapq

from app.graph import Adjacency
from app.models import OptimizeBy


def _edge_weight(distance: float, travel_time: float, by: OptimizeBy) -> float:
    return distance if by == OptimizeBy.distance else travel_time


def shortest_route(
    adj: Adjacency,
    start: str,
    end: str,
    by: OptimizeBy,
) -> tuple[list[tuple[str, str]], float, float] | None:
    """Return (path as (station_id, line_id_arrival) pairs, total_distance, total_time).

    The first segment uses an empty line_id (origin). Unreachable targets return None.
    """
    if start == end:
        return [(start, "")], 0.0, 0.0

    best: dict[str, float] = {start: 0.0}
    # predecessor: station -> (previous_station, line_id, edge_distance, edge_travel_time)
    prev: dict[str, tuple[str, str, float, float]] = {}

    heap: list[tuple[float, str]] = [(0.0, start)]
    seen: set[str] = set()

    while heap:
        dist_u, u = heapq.heappop(heap)
        if u in seen:
            continue
        seen.add(u)
        if u == end:
            break
        if dist_u > best.get(u, float("inf")):
            continue

        for v, line_id, edge_dist, edge_time in adj.get(u, []):
            w = _edge_weight(edge_dist, edge_time, by)
            cand = dist_u + w
            if cand < best.get(v, float("inf")):
                best[v] = cand
                prev[v] = (u, line_id, edge_dist, edge_time)
                heapq.heappush(heap, (cand, v))

    if end not in prev:
        return None

    # Reconstruct stations and edges from end to start
    stations_rev: list[str] = [end]
    edges_rev: list[tuple[str, float, float]] = []  # line_id, dist, time
    cur = end
    while cur != start:
        p = prev.get(cur)
        if p is None:
            return None
        u, line_id, edge_dist, edge_time = p
        edges_rev.append((line_id, edge_dist, edge_time))
        cur = u
        stations_rev.append(cur)

    stations_rev.reverse()
    edges_rev.reverse()

    total_distance = sum(d for _, d, _ in edges_rev)
    total_time = sum(t for _, _, t in edges_rev)

    path: list[tuple[str, str]] = [(stations_rev[0], "")]
    for i, (line_id, _, _) in enumerate(edges_rev):
        path.append((stations_rev[i + 1], line_id))

    return path, total_distance, total_time

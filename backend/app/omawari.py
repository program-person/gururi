"""大回り乗車ルート探索エンジン。

ランダム化DFSで同一駅を通らない長いルートを複数探索する。
"""

import heapq
import random
from dataclasses import dataclass, field

from app.fare import calc_direct_fare, km_to_fare
from app.graph import Adjacency
from app.models import FareEntry, OmawariRoute, PathSegment


@dataclass
class _Route:
    stations: list[str] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)
    total_distance: float = 0.0
    total_time: float = 0.0

    @property
    def station_count(self) -> int:
        return len(self.stations)

    def score(self) -> float:
        return self.station_count * 10.0 + self.total_distance

    def copy(self) -> "_Route":
        return _Route(
            stations=list(self.stations),
            lines=list(self.lines),
            total_distance=self.total_distance,
            total_time=self.total_time,
        )


def _nearest_km(adj: Adjacency, start: str) -> dict[str, float]:
    """Dijkstra でキロ程の最短距離マップを返す。"""
    dist: dict[str, float] = {start: 0.0}
    heap: list[tuple[float, str]] = [(0.0, start)]
    while heap:
        d, u = heapq.heappop(heap)
        if d > dist.get(u, float("inf")):
            continue
        for v, _lid, edge_dist, _t in adj.get(u, []):
            nd = d + edge_dist
            if nd < dist.get(v, float("inf")):
                dist[v] = nd
                heapq.heappush(heap, (nd, v))
    return dist


def _stations_within_km(adj: Adjacency, start: str, max_km: float) -> set[str]:
    return {sid for sid, d in _nearest_km(adj, start).items() if d <= max_km}


def _max_km_for_fare(max_fare: int, table: list[FareEntry]) -> float:
    for entry in reversed(table):
        if entry.fare_ic <= max_fare:
            return float(entry.to_km)
    return float(table[0].to_km)


def _dfs_random(
    adj: Adjacency,
    current: str,
    visited: set[str],
    route: _Route,
    max_stations: int,
    max_time: float,
    rng: random.Random,
    eligible_ends: set[str] | None,
    collected: list[_Route] | None,
) -> _Route:
    """ランダム化DFS。

    eligible_ends が指定されている場合、そこに到達するたびにルートを収集する。
    collected が None の場合は従来の「最良ルートを返す」モード。
    """
    # by-fare モード: 現在地が eligible_ends にあればスナップショット保存
    if eligible_ends is not None and collected is not None:
        if current in eligible_ends and route.station_count >= 3:
            collected.append(route.copy())

    best = route.copy()

    if route.station_count >= max_stations or route.total_time >= max_time:
        return best

    neighbors = list(adj.get(current, []))
    rng.shuffle(neighbors)

    for neighbor_id, line_id, dist, t in neighbors:
        if neighbor_id in visited:
            continue
        if route.total_time + t > max_time:
            continue

        visited.add(neighbor_id)
        route.stations.append(neighbor_id)
        route.lines.append(line_id)
        route.total_distance += dist
        route.total_time += t

        candidate = _dfs_random(
            adj, neighbor_id, visited, route,
            max_stations, max_time, rng, eligible_ends, collected
        )
        if eligible_ends is None and candidate.score() > best.score():
            best = candidate

        route.stations.pop()
        route.lines.pop()
        route.total_distance -= dist
        route.total_time -= t
        visited.remove(neighbor_id)

    return best


def _build_output(
    routes: list[_Route],
    adj: Adjacency,
    start: str,
    fare_table: list[FareEntry],
    num_results: int,
) -> list[OmawariRoute]:
    seen: set[tuple[str, ...]] = set()
    deduped: list[_Route] = []
    for r in sorted(routes, key=lambda x: x.score(), reverse=True):
        sig = tuple(r.stations)
        if sig not in seen:
            seen.add(sig)
            deduped.append(r)
        if len(deduped) >= num_results:
            break

    output: list[OmawariRoute] = []
    for r in deduped:
        path = [
            PathSegment(station_id=sid, line_id=lid)
            for sid, lid in zip(r.stations, r.lines)
        ]
        end = r.stations[-1]
        direct_km, fare_ic, _ = calc_direct_fare(adj, start, end, fare_table)
        output.append(
            OmawariRoute(
                path=path,
                total_distance=round(r.total_distance, 1),
                total_time=round(r.total_time, 1),
                station_count=r.station_count,
                direct_km=round(direct_km, 1),
                fare_ic=fare_ic,
            )
        )
    return output


def find_omawari_routes(
    adj: Adjacency,
    start: str,
    fare_table: list[FareEntry],
    max_stations: int = 40,
    max_time_min: float = 480.0,
    num_results: int = 5,
    num_trials: int = 300,
    seed: int | None = None,
) -> list[OmawariRoute]:
    """大回りルートを複数探索して返す。"""
    rng = random.Random(seed)
    results: list[_Route] = []

    for _ in range(num_trials):
        init = _Route(stations=[start], lines=[""])
        visited = {start}
        best = _dfs_random(
            adj, start, visited, init, max_stations, max_time_min, rng,
            eligible_ends=None, collected=None,
        )
        if best.station_count >= 3:
            results.append(best)

    return _build_output(results, adj, start, fare_table, num_results)


def find_omawari_by_fare(
    adj: Adjacency,
    start: str,
    fare_table: list[FareEntry],
    max_fare: int,
    max_time_min: float = 480.0,
    num_results: int = 5,
    num_trials: int = 400,
    seed: int | None = None,
) -> list[OmawariRoute]:
    """指定運賃以内に収まる大回りルートを探索して返す。

    eligible_ends（start から max_km 以内の駅）に到達したときに
    スナップショットを保存することで確実に候補を収集する。
    """
    rng = random.Random(seed)
    max_km = _max_km_for_fare(max_fare, fare_table)
    eligible_ends = _stations_within_km(adj, start, max_km)
    eligible_ends.discard(start)  # 出発駅そのものは除外

    collected: list[_Route] = []

    for _ in range(num_trials):
        init = _Route(stations=[start], lines=[""])
        visited = {start}
        _dfs_random(
            adj, start, visited, init, 50, max_time_min, rng,
            eligible_ends=eligible_ends, collected=collected,
        )

    # fare_ic が max_fare 以内のものだけを返す
    valid = [r for r in collected if r.station_count >= 3]
    # 事前に計算した eligible_ends に含まれる駅で終わっているので、
    # 実際の fare_ic 確認は _build_output 内で行う
    filtered_output = [
        r for r in _build_output(valid, adj, start, fare_table, num_results * 3)
        if r.fare_ic <= max_fare
    ]
    return filtered_output[:num_results]

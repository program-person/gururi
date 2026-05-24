"""大回り乗車ルート探索エンジン。

スコア三軸: 路線多様性(主)・走行距離(副)・駅数(補助)
探索戦略:
  自由探索    → 貪欲DFS(最良1本) + 重み付きランダムウォーク(多様性)
  終着駅指定  → ノイズ付きDFS + eligible_ends スナップショット収集
  運賃指定    → ランダムウォーク + eligible_ends スナップショット収集
"""

import heapq
import random
from dataclasses import dataclass, field

from app.fare import calc_direct_fare
from app.graph import Adjacency
from app.models import FareEntry, OmawariRoute, PathSegment


@dataclass
class _Route:
    stations: list[str] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)
    # バックトラック時に正確に管理するため set ではなく使用回数カウント
    line_counts: dict[str, int] = field(default_factory=dict)
    total_distance: float = 0.0
    total_time: float = 0.0

    @property
    def station_count(self) -> int:
        return len(self.stations)

    def score(self) -> float:
        """三軸スコア。

        路線多様性を最優先にすることで、同じエリアをぐるぐる回るだけの
        ルートではなく、広域を縦横断する大回りらしいルートを高く評価する。
        """
        return (
            len(self.line_counts) * 10.0   # 路線種別数: 大回りの醍醐味
            + self.total_distance * 0.5    # 走行距離: 大回りの本質
            + self.station_count * 2.0     # 駅数: タイブレーク補助
        )

    def copy(self) -> "_Route":
        return _Route(
            stations=list(self.stations),
            lines=list(self.lines),
            line_counts=dict(self.line_counts),
            total_distance=self.total_distance,
            total_time=self.total_time,
        )


# --------------------------------------------------------------------------- #
# グラフユーティリティ
# --------------------------------------------------------------------------- #

def _nearest_km(adj: Adjacency, start: str) -> dict[str, float]:
    """Dijkstra でキロ程最短距離マップを返す。"""
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


def _compute_graph_stats(adj: Adjacency) -> tuple[float, float, int]:
    """(平均辺距離, 最大辺距離, グラフ内総路線数) を返す。"""
    dists: list[float] = []
    lines: set[str] = set()
    for neighbors in adj.values():
        for _, lid, dist, _ in neighbors:
            dists.append(dist)
            if lid:
                lines.add(lid)
    if not dists:
        return 0.0, 0.0, 0
    return sum(dists) / len(dists), max(dists), len(lines)


def _max_km_for_fare(max_fare: int, table: list[FareEntry]) -> float:
    for entry in reversed(table):
        if entry.fare_ic <= max_fare:
            return float(entry.to_km)
    return float(table[0].to_km)


def _shortest_avoiding(
    adj: Adjacency,
    start: str,
    end: str,
    blocked: set[str],
) -> tuple[list[str], list[str], float, float] | None:
    """blocked にある駅を通らずに start→end の最短経路（時間ベース）を返す。

    戻り値: (stations, lines, total_distance, total_time)
      stations[0]==start, stations[-1]==end
      lines[0]="" (起点)、lines[i] は stations[i-1]→stations[i] のエッジの路線ID
    到達不能の場合は None を返す。
    """
    if start == end:
        return [start], [""], 0.0, 0.0

    best: dict[str, float] = {start: 0.0}
    prev: dict[str, tuple[str, str, float, float]] = {}
    heap: list[tuple[float, str]] = [(0.0, start)]
    seen: set[str] = set()

    while heap:
        d, u = heapq.heappop(heap)
        if u in seen:
            continue
        seen.add(u)
        if u == end:
            break
        for v, line_id, edge_dist, edge_time in adj.get(u, []):
            if v in blocked and v != end:
                continue
            cand = d + edge_time
            if cand < best.get(v, float("inf")):
                best[v] = cand
                prev[v] = (u, line_id, edge_dist, edge_time)
                heapq.heappush(heap, (cand, v))

    if end not in prev:
        return None

    stations_rev: list[str] = [end]
    edges_rev: list[tuple[str, float, float]] = []
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

    lines: list[str] = [""]
    for line_id, _, _ in edges_rev:
        lines.append(line_id)

    return stations_rev, lines, total_distance, total_time


# --------------------------------------------------------------------------- #
# 隣接駅の重み計算
# --------------------------------------------------------------------------- #

def _neighbor_weight(
    n_id: str,
    lid: str,
    dist: float,
    adj: Adjacency,
    visited: set[str],
    line_counts: dict[str, int],
) -> float:
    """乗算型重みで隣接駅の「有望度」を計算する。

    加算型ではなく乗算型にすることで各要素が相互に増幅し合い、
    明確に優れた選択肢を強調しつつ適度なランダム性を保持する。

    - 新路線係数(3x): スコア関数の路線項と整合した誘導
    - 辺距離係数: 長い辺ほど走行距離スコアへの貢献が大きい
    - 残余次数係数: 未訪問隣接が多い駅 = 行き詰まりにくい
    """
    remaining_deg = sum(1 for v, _, _, _ in adj.get(n_id, []) if v not in visited)
    new_line_mult = 3.0 if (lid and lid not in line_counts) else 1.0
    return new_line_mult * (1.0 + dist * 0.2) * (1.0 + remaining_deg * 0.3)


# --------------------------------------------------------------------------- #
# ランダムウォーク（多様性確保の主力）
# --------------------------------------------------------------------------- #

def _random_walk(
    adj: Adjacency,
    start: str,
    max_stations: int,
    max_time: float,
    rng: random.Random,
    eligible_ends: set[str] | None = None,
    collected: list["_Route"] | None = None,
    end_distances: dict[str, float] | None = None,
    min_detour_distance: float = 0.0,
) -> "_Route":
    """重み付きランダムウォーク（バックトラックなし）。

    バックトラック付きDFSと異なり、異なるシードで呼ぶたびに
    本質的に異なる経路を生成するため多様性に優れる。

    eligible_ends が指定された場合、通過のたびにスナップショットを収集する。
    end_distances が指定された場合、終着駅までの距離で重みをバイアスし、
    前半は遠ざかる方向・後半は近づく方向を優先する。
    min_detour_distance を満たさないスナップショットは収集しない。
    """
    route = _Route(stations=[start], lines=[""])
    visited: set[str] = {start}
    current = start

    while route.station_count < max_stations and route.total_time < max_time:
        # 通過時スナップショット収集（by-fare / end 指定モード）
        if eligible_ends is not None and collected is not None:
            if (current in eligible_ends and route.station_count >= 3
                    and route.total_distance >= min_detour_distance):
                collected.append(route.copy())

        candidates = [
            (n_id, lid, dist, t)
            for n_id, lid, dist, t in adj.get(current, [])
            if n_id not in visited and route.total_time + t <= max_time
        ]
        if not candidates:
            break

        weights = [
            _neighbor_weight(n_id, lid, dist, adj, visited, route.line_counts)
            for n_id, lid, dist, _t in candidates
        ]

        # 終着駅からの距離によるバイアス（DFS の detour_bonus と整合）
        if end_distances is not None:
            progress = route.station_count / max_stations
            biased: list[float] = []
            for w, (n_id, _lid, _d, _t) in zip(weights, candidates):
                d_end = end_distances.get(n_id)
                if d_end is None:
                    biased.append(w)
                    continue
                if progress < 0.6:
                    # 前半: 終着駅から遠い駅を優先
                    biased.append(w * (1.0 + d_end * 0.1))
                else:
                    # 後半: 終着駅に近い駅を優先（近いほど大きく）
                    biased.append(w * (1.0 + 10.0 / (1.0 + d_end * 0.5)))
            weights = biased

        n_id, lid, dist, t = rng.choices(candidates, weights=weights, k=1)[0]

        visited.add(n_id)
        route.stations.append(n_id)
        route.lines.append(lid)
        if lid:
            route.line_counts[lid] = route.line_counts.get(lid, 0) + 1
        route.total_distance += dist
        route.total_time += t
        current = n_id

    # ウォーク終了時も eligible_ends チェック
    if eligible_ends is not None and collected is not None:
        if (current in eligible_ends and route.station_count >= 3
                and route.total_distance >= min_detour_distance):
            collected.append(route.copy())

    return route


# --------------------------------------------------------------------------- #
# 貪欲/ノイズDFS（品質重視・終着駅指定）
# --------------------------------------------------------------------------- #

def _dfs(
    adj: Adjacency,
    current: str,
    visited: set[str],
    route: "_Route",
    max_stations: int,
    max_time: float,
    avg_dist: float,
    total_lines: int,
    best_score: list[float],
    eligible_ends: set[str] | None,
    collected: list["_Route"] | None,
    rng: random.Random | None = None,
    noise_scale: float = 0.0,
    end_distances: dict[str, float] | None = None,
    min_detour_distance: float = 0.0,
) -> "_Route":
    """スコア誘導DFS。

    noise_scale=0  → 純粋な貪欲探索（最良1本の初期解生成用）
    noise_scale>0  → ノイズ付き確率的探索（終着駅指定の多様性確保用）

    eligible_ends が指定された場合は通過のたびにスナップショットを収集する。
    """
    if eligible_ends is not None and collected is not None:
        if current in eligible_ends and route.station_count >= 3 \
                and route.total_distance >= min_detour_distance:
            collected.append(route.copy())

    best = route.copy()

    if route.station_count >= max_stations or route.total_time >= max_time:
        return best

    # 楽観的上限による枝刈り（自由探索モードのみ）
    if eligible_ends is None:
        remaining = max_stations - route.station_count
        # 残り探索で追加できる路線数の上限（グラフ総路線 - 現在使用路線）
        additional_lines = min(total_lines - len(route.line_counts), remaining)
        upper = (
            route.score()
            + additional_lines * 10.0            # 路線追加ボーナス上限
            + remaining * (2.0 + avg_dist * 0.5) # 駅数+距離の楽観値
        )
        if upper <= best_score[0]:
            return best

    candidates = [
        (n_id, lid, dist, t)
        for n_id, lid, dist, t in adj.get(current, [])
        if n_id not in visited and route.total_time + t <= max_time
    ]
    if not candidates:
        return best

    def promise(item: tuple[str, str, float, float]) -> float:
        n_id, lid, dist, _ = item
        remaining_deg = sum(1 for v, _, _, _ in adj.get(n_id, []) if v not in visited)
        new_line = 10.0 if (lid and lid not in route.line_counts) else 0.0
        noise = (rng.gauss(0, noise_scale) if (rng and noise_scale > 0) else 0.0)
        if end_distances is not None and n_id in end_distances:
            progress = route.station_count / max_stations
            sign = 1.0 if progress < 0.6 else -1.0
            detour_bonus = sign * end_distances[n_id] * 3.0
        else:
            detour_bonus = 0.0
        return new_line + dist * 0.5 + remaining_deg * avg_dist * 0.15 + noise + detour_bonus

    candidates.sort(key=promise, reverse=True)

    for n_id, lid, dist, t in candidates:
        visited.add(n_id)
        route.stations.append(n_id)
        route.lines.append(lid)
        if lid:
            route.line_counts[lid] = route.line_counts.get(lid, 0) + 1
        route.total_distance += dist
        route.total_time += t

        candidate = _dfs(
            adj, n_id, visited, route,
            max_stations, max_time, avg_dist, total_lines, best_score,
            eligible_ends, collected, rng, noise_scale,
            end_distances, min_detour_distance,
        )
        if eligible_ends is None and candidate.score() > best.score():
            best = candidate
            if best.score() > best_score[0]:
                best_score[0] = best.score()

        route.stations.pop()
        route.lines.pop()
        if lid:
            route.line_counts[lid] -= 1
            if route.line_counts[lid] == 0:
                del route.line_counts[lid]
        route.total_distance -= dist
        route.total_time -= t
        visited.remove(n_id)

    return best


# --------------------------------------------------------------------------- #
# 出力構築
# --------------------------------------------------------------------------- #

def _build_output(
    routes: list["_Route"],
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


# --------------------------------------------------------------------------- #
# ウェイポイント方式（決定論的な経由地指定ルート）
# --------------------------------------------------------------------------- #

# (出発駅名, 到着駅名) → [経由地名のリスト, ...]
# 各経由地リストは start → waypoints[0] → ... → end の順を意味する。
# 駅名は graph データの stations[].name と一致する必要がある。
WAYPOINT_ROUTES: dict[tuple[str, str], list[list[str]]] = {
    ("大阪", "天王寺"): [
        ["京都", "近江今津", "近江塩津", "米原", "草津", "柘植"],
    ],
    ("天王寺", "大阪"): [
        ["王寺", "奈良", "柘植", "草津", "米原", "近江塩津", "近江今津", "京都"],
    ],
}


def find_routes_via_waypoints(
    adj: Adjacency,
    start: str,
    end: str,
    waypoints: list[str],
    fare_table: list[FareEntry],
) -> OmawariRoute | None:
    """start → waypoints[0] → waypoints[1] → ... → end の順にDijkstraで
    各区間をつなぎ、1本のルートを返す。

    経由地間でvisitedを引き継いで同じ駅を通らないようにする。
    つなげない区間があればNoneを返す。
    """
    chain = [start] + waypoints + [end]

    full_stations: list[str] = [start]
    full_lines: list[str] = [""]
    visited: set[str] = {start}
    total_distance = 0.0
    total_time = 0.0

    for i in range(len(chain) - 1):
        seg_from = chain[i]
        seg_to = chain[i + 1]
        # 現区間の出発駅は通れる、それ以外の訪問済み駅は避ける
        blocked = visited - {seg_from}
        result = _shortest_avoiding(adj, seg_from, seg_to, blocked)
        if result is None:
            return None
        seg_stations, seg_lines, seg_dist, seg_time = result
        # seg_stations[0] は前区間の終点と一致するため skip
        for j in range(1, len(seg_stations)):
            full_stations.append(seg_stations[j])
            full_lines.append(seg_lines[j])
            visited.add(seg_stations[j])
        total_distance += seg_dist
        total_time += seg_time

    path = [
        PathSegment(station_id=sid, line_id=lid)
        for sid, lid in zip(full_stations, full_lines)
    ]
    direct_km, fare_ic, _ = calc_direct_fare(adj, start, end, fare_table)
    return OmawariRoute(
        path=path,
        total_distance=round(total_distance, 1),
        total_time=round(total_time, 1),
        station_count=len(full_stations),
        direct_km=round(direct_km, 1),
        fare_ic=fare_ic,
    )


# --------------------------------------------------------------------------- #
# 公開API
# --------------------------------------------------------------------------- #

def find_omawari_routes(
    adj: Adjacency,
    start: str,
    fare_table: list[FareEntry],
    end: str | None = None,
    max_stations: int = 120,
    max_time_min: float = 480.0,
    num_results: int = 5,
    num_trials: int = 600,
    seed: int | None = None,
    name_to_id: dict[str, str] | None = None,
) -> list[OmawariRoute]:
    """大回りルートを複数探索して返す。

    end を指定した場合はその駅に到達するルートだけを収集する。
    name_to_id が指定されており、WAYPOINT_ROUTES に該当する定義があれば、
    そのウェイポイント経由ルートを結果の先頭に追加する。
    """
    rng = random.Random(seed)
    avg_dist, _max_dist, total_lines = _compute_graph_stats(adj)

    if end is not None:
        # WAYPOINT_ROUTES から該当する経由地リストを取得して決定論的ルートを構築
        waypoint_results: list[OmawariRoute] = []
        if name_to_id is not None:
            id_to_name = {v: k for k, v in name_to_id.items()}
            start_name = id_to_name.get(start)
            end_name = id_to_name.get(end)
            if start_name and end_name:
                key = (start_name, end_name)
                for waypoint_names in WAYPOINT_ROUTES.get(key, []):
                    waypoint_ids: list[str] = []
                    ok = True
                    for n in waypoint_names:
                        wid = name_to_id.get(n)
                        if wid is None:
                            ok = False
                            break
                        waypoint_ids.append(wid)
                    if not ok:
                        continue
                    wp_route = find_routes_via_waypoints(
                        adj, start, end, waypoint_ids, fare_table
                    )
                    if wp_route is not None:
                        waypoint_results.append(wp_route)

        # 終着駅指定モード: ノイズ付きDFS で eligible_ends に到達するたびに収集
        eligible_ends = {end}
        collected: list[_Route] = []
        best_score = [0.0]
        noise_scale = avg_dist * 2.0  # sigma ≈ 6km で十分な多様性
        start_distances = _nearest_km(adj, start)
        direct_dist = start_distances.get(end, 0.0)
        min_detour_distance = direct_dist * 2.5
        end_distances = _nearest_km(adj, end)
        # DFS による品質重視の探索
        for _ in range(num_trials):
            init = _Route(stations=[start], lines=[""])
            _dfs(
                adj, start, {start}, init, max_stations, max_time_min,
                avg_dist, total_lines, best_score,
                eligible_ends, collected, rng, noise_scale,
                end_distances, min_detour_distance,
            )
        # Random walk による多様性確保の探索（end_distances でバイアス）
        for _ in range(num_trials):
            _random_walk(
                adj, start, max_stations, max_time_min, rng,
                eligible_ends, collected,
                end_distances, min_detour_distance,
            )
        valid = [r for r in collected if r.station_count >= 3]
        dfs_results = _build_output(valid, adj, start, fare_table, num_results)
        return waypoint_results + dfs_results

    # 自由探索モード
    results: list[_Route] = []

    # Phase 1 — 貪欲DFS で最良ルートを1本確保（スコア上限の基準値を引き上げる）
    global_best: list[float] = [0.0]
    seed_init = _Route(stations=[start], lines=[""])
    seed_route = _dfs(
        adj, start, {start}, seed_init, max_stations, max_time_min,
        avg_dist, total_lines, global_best,
        None, None,  # 自由探索, 収集なし
    )
    if seed_route.station_count >= 3:
        results.append(seed_route)
        global_best[0] = seed_route.score()

    # Phase 2 — ランダムウォークで多様な経路を大量生成
    # DFS は同じグラフ構造に収束しやすいが、ランダムウォークは
    # 各ステップで確率的に分岐するため本質的に異なるルートを生成できる
    for _ in range(num_trials):
        walk = _random_walk(adj, start, max_stations, max_time_min, rng)
        if walk.station_count >= 3:
            results.append(walk)

    return _build_output(results, adj, start, fare_table, num_results)


def find_omawari_by_fare(
    adj: Adjacency,
    start: str,
    fare_table: list[FareEntry],
    max_fare: int,
    max_time_min: float = 480.0,
    num_results: int = 5,
    num_trials: int = 600,
    seed: int | None = None,
) -> list[OmawariRoute]:
    """指定運賃以内に収まる大回りルートを探索して返す。

    ランダムウォークの通過時スナップショット収集を使う。
    eligible_ends（出発駅から max_km 以内の駅）を通過するたびに記録するため、
    1回のウォークで複数の有効ルートを収集できる。
    """
    rng = random.Random(seed)
    max_km = _max_km_for_fare(max_fare, fare_table)
    eligible_ends = _stations_within_km(adj, start, max_km)
    eligible_ends.discard(start)

    collected: list[_Route] = []
    for _ in range(num_trials):
        _random_walk(adj, start, 60, max_time_min, rng, eligible_ends, collected)

    valid = [r for r in collected if r.station_count >= 3]
    filtered_output = [
        r for r in _build_output(valid, adj, start, fare_table, num_results * 3)
        if r.fare_ic <= max_fare
    ]
    return filtered_output[:num_results]

"""大回り乗車ルート探索エンジン。

スコア三軸: 路線多様性(主)・走行距離(副)・駅数(補助)
探索戦略:
  自由探索    → 貪欲DFS(最良1本) + 重み付きランダムウォーク(多様性)
  終着駅指定  → FSAランダムウォーク（DEPART/EXPLORE/RETURN の 3 状態）
  運賃指定    → ランダムウォーク + eligible_ends スナップショット収集
"""

import heapq
import random
from dataclasses import dataclass, field
from enum import Enum, auto


class Phase(Enum):
    DEPART = "depart"
    EXPLORE = "explore"
    RETURN = "return"


GOLDEN_LOOP: list[str] = [
    "waka", "takat", "nara", "kubd", "hant", "kizu",
    "kamo", "tsuge", "kusa", "maib", "enis", "kyot",
    "ssin", "shgy", "kyob", "amaz", "osak", "nkuj", "tenn",
]

LOOP_LINES: list[str] = [
    "T",  # 和歌山 → 高田（和歌山線）
    "U",  # 高田 → 奈良（桜井線 = 万葉まほろば線）
    "Q",  # 奈良 → 久宝寺（大和路線）
    "F",  # 久宝寺 → 放出（おおさか東線）
    "H",  # 放出 → 木津（学研都市線）
    "Q",  # 木津 → 加茂（大和路線）
    "V",  # 加茂 → 柘植（関西本線）
    "C",  # 柘植 → 草津（草津線）
    "A",  # 草津 → 米原（琵琶湖線 = JR京都線・琵琶湖線）
    "A",  # 米原 → 近江塩津（北陸本線）
    "B",  # 近江塩津 → 京都（湖西線）
    "A",  # 京都 → 新大阪（JR京都線 = JR京都線・琵琶湖線）
    "F",  # 新大阪 → 鴫野（おおさか東線）
    "H",  # 鴫野 → 京橋（学研都市線）
    "H",  # 京橋 → 尼崎（JR東西線）
    "A",  # 尼崎 → 大阪（JR神戸線）
    # 大阪環状線は大阪〜天王寺が東西2ルートに分かれる。京橋（東回り）は
    # 学研都市線側で使うため、西九条を明示的な経由地に置いて西回りに固定する。
    "O",  # 大阪 → 西九条（大阪環状線・西回り）
    "O",  # 西九条 → 天王寺（大阪環状線・西回り）
    "R",  # 天王寺 → 和歌山（阪和線）
]

KOBE_LOOP: list[str] = ["amaz", "tani", "kkok"]
KOBE_LINES: list[str] = ["G", "I", "A"]

SHORTCUTS: list[dict] = [
    {
        "from": "kyot",    # 京都
        "to": "kizu",      # 木津
        "line": "D",       # 奈良線
        "skips": ["enis", "maib", "kusa", "tsuge", "kamo"],
    },
]

# 終着駅指定時、直通距離のこの倍数を下回るゴールデンループ候補は
# 「ループを回らず素通りした縮退ルート」とみなして捨てる
MIN_DETOUR_RATIO: float = 3.0

# 結果に占めるゴールデンループの上限割合。定型ループだけで埋まらないよう、
# 残り枠は探索（FSA）由来のルートに割り当てる
GOLDEN_RESULT_RATIO: float = 1 / 3


from app.fare import calc_direct_fare
from app.graph import Adjacency
from app.models import FareTable, OmawariRoute, PathSegment


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


def _max_km_for_fare(max_fare: int, start: str, table: FareTable) -> float:
    """指定運賃以内で到達できる最大キロ程を概算する。

    出発駅が電車特定区間内であればdenshaku表、そうでなければtrunk表を使う
    （経路の途中で区間をまたぐケースは近似しない）。
    """
    bands = table.denshaku if start in table.denshaku_station_ids else table.trunk
    for band in reversed(bands):
        if band.fare <= max_fare:
            return float(band.to_km)
    return float(bands[0].to_km)


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
# FSA 状態定義
# --------------------------------------------------------------------------- #

class _WalkState(Enum):
    DEPART = auto()   # 出発フェーズ: 目的地から離れる
    EXPLORE = auto()  # 探索フェーズ: 新路線を開拓、慣性で直進
    RETURN = auto()   # 帰還フェーズ: 目的地に近づく


# --------------------------------------------------------------------------- #
# FSA 用重み計算（状態切り替え版）
# --------------------------------------------------------------------------- #

def _neighbor_weight_fsa(
    n_id: str,
    lid: str,
    dist: float,
    adj: Adjacency,
    visited: set[str],
    line_counts: dict[str, int],
    state: _WalkState,
    last_line: str,
    end_distances: dict[str, float] | None,
) -> float:
    """FSA の各状態に応じた加算型重みを返す。"""
    remaining_deg = sum(1 for v, _, _, _ in adj.get(n_id, []) if v not in visited)
    new_line_mult = 3.0 if (lid and lid not in line_counts) else 1.0

    if state == _WalkState.DEPART:
        d_end = end_distances.get(n_id, 0.0) if end_distances is not None else 0.0
        return d_end * 2.0 + new_line_mult * 3.0 + remaining_deg * 0.3

    if state == _WalkState.EXPLORE:
        same_line = 5.0 if lid == last_line else 1.0  # 1次マルコフ連鎖（慣性）
        return new_line_mult * 3.0 * same_line + dist * 0.5 + remaining_deg * 0.3

    # RETURN
    d_end = end_distances.get(n_id, 0.0) if end_distances is not None else 0.0
    closeness = 1.0 / (1.0 + d_end)
    return closeness * 10.0 + remaining_deg * 0.5


# --------------------------------------------------------------------------- #
# マルチアトラクター チェイン生成
# --------------------------------------------------------------------------- #

def _build_attractor_chain(
    adj: Adjacency,
    start: str,
    end: str,
    rng: random.Random,
    num_attractors: int = 3,
    dist_cache: dict[str, dict[str, float]] | None = None,
) -> list[str]:
    """出発駅から貪欲法で互いに遠いアトラクター列を生成する。

    最後のアトラクターは目的地に帰りやすいよう、
    目的地からの距離でペナルティをかける。
    dist_cache は呼び出し元が渡した辞書をインプレースに更新する（再利用）。
    """
    if dist_cache is None:
        dist_cache = {}

    if start not in dist_cache:
        dist_cache[start] = _nearest_km(adj, start)

    start_dists = dist_cache[start]

    median = sorted(start_dists.values())[len(start_dists) // 2]
    candidates = [
        s for s, d in start_dists.items()
        if d > median and s != start and s != end
    ]
    if not candidates:
        return []

    chain: list[str] = []
    current_ref = start

    for i in range(num_attractors):
        if not candidates:
            break
        if current_ref not in dist_cache:
            dist_cache[current_ref] = _nearest_km(adj, current_ref)

        ref_dists = dist_cache[current_ref]

        end_dists: dict[str, float] | None = None
        if i == num_attractors - 1:
            if end not in dist_cache:
                dist_cache[end] = _nearest_km(adj, end)
            end_dists = dist_cache[end]

        def attractor_score(s: str, _ref: dict = ref_dists, _end: dict | None = end_dists) -> float:
            far_score = _ref.get(s, 0.0)
            if _end is not None:
                return far_score - _end.get(s, 999.0) * 0.3
            return far_score

        top_candidates = sorted(candidates, key=attractor_score, reverse=True)[:10]
        chosen = rng.choice(top_candidates)

        chain.append(chosen)
        candidates = [c for c in candidates if c != chosen]
        current_ref = chosen

    return chain


# --------------------------------------------------------------------------- #
# ランダムウォーク（多様性確保の主力）
# --------------------------------------------------------------------------- #

def _random_walk_legacy(
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


def _random_walk_fsa(
    adj: Adjacency,
    start: str,
    end: str,
    end_distances: dict[str, float],
    attractor_chain: list[str],
    attractor_dist_cache: dict[str, dict[str, float]],
    max_stations: int,
    max_time: float,
    rng: random.Random,
) -> "_Route | None":
    """マルチアトラクター FSAランダムウォーク。

    attractor_chain のアトラクターを順番に巡回してから目的地に帰還する。
    DEPART→(EXPLORE×N アトラクター切り替え)→RETURN の3状態。
    """
    route = _Route(stations=[start], lines=[""])
    visited: set[str] = {start}
    current = start
    phase = Phase.DEPART
    attractor_idx = 0

    def current_attractor_dists() -> dict[str, float]:
        if attractor_idx < len(attractor_chain):
            return attractor_dist_cache[attractor_chain[attractor_idx]]
        return end_distances

    min_loop = 10 if start == end else 3

    def close_home() -> "_Route | None":
        """行き詰まったウォークを、未訪問駅のみの最短路で目的地まで接いで完結させる。

        再訪禁止のため行き止まり路線（末端駅）に入ると通常のウォークでは
        帰還できない。時間・駅数予算内に収まる場合のみ接続する。
        """
        result = _shortest_avoiding(adj, current, end, visited - {end})
        if result is None:
            return None
        seg_stations, seg_lines, seg_dist, seg_time = result
        if route.total_time + seg_time > max_time:
            return None
        if route.station_count + len(seg_stations) - 1 > max_stations:
            return None
        for j in range(1, len(seg_stations)):
            route.stations.append(seg_stations[j])
            route.lines.append(seg_lines[j])
            if seg_lines[j]:
                route.line_counts[seg_lines[j]] = route.line_counts.get(seg_lines[j], 0) + 1
        route.total_distance += seg_dist
        route.total_time += seg_time
        if route.stations[-1] == end and route.station_count >= min_loop:
            return route
        return None
    while route.station_count < max_stations and route.total_time < max_time:
        if current == end and route.station_count >= min_loop:
            return route

        # --- 状態遷移 ---
        if phase == Phase.DEPART:
            if attractor_chain and attractor_idx < len(attractor_chain):
                dist_to_attr = current_attractor_dists().get(current, 999.0)
                if dist_to_attr < 20.0 or route.station_count >= 10:
                    phase = Phase.EXPLORE

        elif phase == Phase.EXPLORE:
            if attractor_idx < len(attractor_chain):
                dist_to_attr = current_attractor_dists().get(current, 999.0)
                if dist_to_attr < 15.0:
                    attractor_idx += 1
                    if attractor_idx >= len(attractor_chain):
                        phase = Phase.RETURN
            else:
                phase = Phase.RETURN

        # --- 候補駅を取得 ---
        # RETURN かつ十分な駅数を通過済みの場合のみ、目的地（= 出発駅）への帰還を許可
        candidates = [
            (n_id, lid, dist, t)
            for n_id, lid, dist, t in adj.get(current, [])
            if (
                n_id not in visited
                or (n_id == end and phase == Phase.RETURN
                    and route.station_count >= min_loop)
            )
            and route.total_time + t <= max_time
        ]
        if not candidates:
            return close_home()

        last_line = route.lines[-1] if route.lines else ""
        weights = []
        for n_id, lid, dist, t in candidates:
            remaining_deg = sum(1 for v, _, _, _ in adj.get(n_id, []) if v not in visited)
            new_line_bonus = 3.0 if (lid and lid not in route.line_counts) else 1.0

            if phase == Phase.DEPART:
                attract_dist = current_attractor_dists().get(n_id, 999.0)
                attract_score = 1.0 / (1.0 + attract_dist) * 50.0
                w = attract_score + new_line_bonus * 3.0 + remaining_deg * 0.5
            elif phase == Phase.EXPLORE:
                momentum = 5.0 if (lid and lid == last_line) else 1.0
                attract_dist = current_attractor_dists().get(n_id, 999.0)
                direction_bonus = 1.0 / (1.0 + attract_dist) * 10.0
                w = (new_line_bonus * 3.0 * momentum
                     + direction_bonus
                     + dist * 0.5
                     + remaining_deg * 0.3)
            else:  # RETURN
                n_dist = end_distances.get(n_id, 0.0)
                # 残り予算を計算（時間・駅数のうち小さい方）
                time_ratio = (max_time - route.total_time) / max_time if max_time > 0 else 0
                station_ratio = (max_stations - route.station_count) / max_stations if max_stations > 0 else 0
                budget_ratio = min(time_ratio, station_ratio)

                if budget_ratio > 0.3:
                    # のんびりRETURN: 寄り道しながら帰る
                    closeness = 1.0 / (1.0 + n_dist) * 5.0
                    momentum = 5.0 if (lid and lid == last_line) else 1.0
                    w = closeness + new_line_bonus * 3.0 * momentum + remaining_deg * 0.3
                else:
                    # 急ぎRETURN: 確実に帰着する
                    closeness = 1.0 / (1.0 + n_dist) * 15.0
                    w = closeness + remaining_deg * 0.5

            weights.append(max(w, 0.01))

        n_id, lid, dist, t = rng.choices(candidates, weights=weights, k=1)[0]

        visited.add(n_id)
        route.stations.append(n_id)
        route.lines.append(lid)
        if lid:
            route.line_counts[lid] = route.line_counts.get(lid, 0) + 1
        route.total_distance += dist
        route.total_time += t
        current = n_id

    # 予算（時間・駅数）切れでループを抜けた場合も帰還を試みる
    if current == end and route.station_count >= min_loop:
        return route
    return close_home()


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
    fare_table: FareTable,
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
# ゴールデンループ方式
# --------------------------------------------------------------------------- #

def _trim_last_station(r: "_Route", adj: Adjacency) -> "_Route":
    """末尾の駅（= 出発駅に戻る最後の1駅）を除去する。

    大回りのルールでは同駅発着不可のため、ループルートの最終駅を
    1つ手前で打ち切るときに使う。
    """
    if len(r.stations) < 2:
        return r

    last_st = r.stations[-1]
    prev_st = r.stations[-2]
    last_line = r.lines[-1]

    edge_dist = 0.0
    edge_time = 0.0
    for v, lid, edist, etime in adj.get(prev_st, []):
        if v == last_st and lid == last_line:
            edge_dist = edist
            edge_time = etime
            break

    new_line_counts = dict(r.line_counts)
    if last_line and last_line in new_line_counts:
        new_line_counts[last_line] -= 1
        if new_line_counts[last_line] == 0:
            del new_line_counts[last_line]

    return _Route(
        stations=r.stations[:-1],
        lines=r.lines[:-1],
        line_counts=new_line_counts,
        total_distance=r.total_distance - edge_dist,
        total_time=r.total_time - edge_time,
    )


def _nearest_in_set(adj: Adjacency, station: str, candidates: set[str]) -> str | None:
    """station から最も近い candidates の駅をDijkstラで探す。

    ジャンクション駅ではなく「展開後のループ上の全駅」を候補にするため、
    ループの途中駅から出発した場合はその駅自身が選ばれる。
    """
    if station in candidates:
        return station

    dist_map = _nearest_km(adj, station)
    reachable = [(sid, d) for sid, d in dist_map.items() if sid in candidates]
    if not reachable:
        return None
    return min(reachable, key=lambda x: x[1])[0]


def _apply_shortcut(
    loop_junctions: list[str], loop_lines: list[str], shortcut: dict
) -> tuple[list[str], list[str]] | None:
    """短絡路線を使うようジャンクション列を縮約する。

    shortcut["skips"] のジャンクションを列から取り除き、残った
    from ↔ to の隣接辺を短絡路線に差し替える。
    """
    skips = set(shortcut["skips"])
    junctions: list[str] = []
    lines: list[str] = []
    for junction, line in zip(loop_junctions, loop_lines):
        if junction in skips:
            continue
        junctions.append(junction)
        lines.append(line)

    endpoints = {shortcut["from"], shortcut["to"]}
    num = len(junctions)
    for i in range(num):
        if {junctions[i], junctions[(i + 1) % num]} == endpoints:
            lines[i] = shortcut["line"]
            return junctions, lines
    return None


def _expand_full_cycle(
    adj: Adjacency,
    loop_junctions: list[str],
    loop_lines: list[str],
    reverse: bool,
    shortcut: dict | None = None,
) -> tuple[list[str], list[str]] | None:
    """ジャンクション列を駅レベルに展開した「閉路」を返す。

    戻り値: (cycle_stations, edge_lines)
      cycle_stations は N 駅（先頭駅の重複は含まない）
      edge_lines[i] は cycle_stations[i] → cycle_stations[(i + 1) % N] の路線ID

    出発駅に依存しないため、呼び出し側は結果を回転させるだけで
    任意の駅始発のループを得られる。展開に失敗（駅の重複・辺の欠落）した
    場合は None。
    """
    if shortcut is not None:
        reduced = _apply_shortcut(loop_junctions, loop_lines, shortcut)
        if reduced is None:
            return None
        loop_junctions, loop_lines = reduced

    stations: list[str] = [loop_junctions[0]]
    edge_lines: list[str] = []
    visited: set[str] = {loop_junctions[0]}

    num_junctions = len(loop_junctions)
    start_idx = 0
    cur_idx = start_idx

    while True:
        from_st = loop_junctions[cur_idx]

        if reverse:
            next_idx = (cur_idx - 1) % num_junctions
            line = loop_lines[next_idx]
        else:
            next_idx = (cur_idx + 1) % num_junctions
            line = loop_lines[cur_idx]
        to_st = loop_junctions[next_idx]
        cur_idx = next_idx

        # 閉路の最後の1区間は先頭駅に戻るため、先頭駅だけはブロックを外す
        closing = to_st == stations[0]
        blocked = visited - {to_st} if closing else visited

        segment = _expand_junction_path(adj, from_st, to_st, line, blocked)
        for st, lid in segment[1:]:
            if st in visited and not (closing and st == stations[0]):
                return None
            if closing and st == stations[0]:
                edge_lines.append(lid)
                break
            stations.append(st)
            edge_lines.append(lid)
            visited.add(st)

        if cur_idx == start_idx:
            break

    if len(edge_lines) != len(stations):
        return None
    return stations, edge_lines


def _materialize_route(
    adj: Adjacency, stations: list[str], lines: list[str]
) -> _Route | None:
    """駅列＋路線列から距離・時間を実グラフで積算して _Route を作る。

    指定された路線の辺が存在しない箇所が1つでもあれば None（＝不正な経路）。
    """
    total_distance = 0.0
    total_time = 0.0
    line_counts: dict[str, int] = {}

    for i in range(1, len(stations)):
        line_id = lines[i]
        for v, lid, edge_dist, edge_time in adj.get(stations[i - 1], []):
            if v == stations[i] and lid == line_id:
                total_distance += edge_dist
                total_time += edge_time
                break
        else:
            return None
        if line_id:
            line_counts[line_id] = line_counts.get(line_id, 0) + 1

    return _Route(
        stations=stations,
        lines=lines,
        line_counts=line_counts,
        total_distance=total_distance,
        total_time=total_time,
    )


def _build_loop_route(
    adj: Adjacency,
    start: str,
    end: str,
    cycle_stations: list[str],
    edge_lines: list[str],
) -> _Route | None:
    """展開済み閉路を start 始発になるよう回転させ、end で打ち切ってルート化する。

    start がループ上の駅（ジャンクションに限らない中間駅を含む）なら
    そのまま回転するだけでよい。ループ外の駅なら最寄りのループ駅まで
    アプローチ区間を敷いてから回転させる。
    """
    cycle_set = set(cycle_stations)
    entry = _nearest_in_set(adj, start, cycle_set)
    if entry is None:
        return None

    stations: list[str] = []
    lines: list[str] = []

    if entry != start:
        # アプローチはループ上の他の駅を踏まない経路でなければ重複訪問になる
        approach = _shortest_avoiding(adj, start, entry, cycle_set - {entry})
        if approach is None:
            return None
        stations = list(approach[0])
        lines = list(approach[1])
    else:
        stations = [start]
        lines = [""]

    num_stations = len(cycle_stations)
    entry_idx = cycle_stations.index(entry)
    for i in range(num_stations):
        idx = (entry_idx + i) % num_stations
        stations.append(cycle_stations[(idx + 1) % num_stations])
        lines.append(edge_lines[idx])

    # 打ち切り位置: end がループ上ならその駅、そうでなければ end に最も近いループ駅
    exit_station = end if end in cycle_set else _nearest_in_set(adj, end, cycle_set)
    if exit_station is None:
        return None
    approach_len = len(stations) - num_stations
    try:
        cut = stations.index(exit_station, approach_len)
    except ValueError:
        return None
    stations = stations[: cut + 1]
    lines = lines[: cut + 1]

    # 同一駅の再訪は禁止。ただし「出発駅に戻って閉じる」末尾だけは許す
    # （呼び出し元が _trim_last_station で1駅手前に切り詰めるため）
    body = stations[:-1]
    if len(body) != len(set(body)):
        return None
    if stations[-1] != stations[0] and stations[-1] in body:
        return None

    route = _materialize_route(adj, stations, lines)
    if route is None:
        return None

    if exit_station != end:
        escape = _shortest_avoiding(adj, exit_station, end, set(stations) - {end})
        if escape is None:
            return None
        esc_stations, esc_lines, esc_dist, esc_time = escape
        for j in range(1, len(esc_stations)):
            if esc_stations[j] in route.stations:
                return None
            route.stations.append(esc_stations[j])
            route.lines.append(esc_lines[j])
            if esc_lines[j]:
                route.line_counts[esc_lines[j]] = route.line_counts.get(esc_lines[j], 0) + 1
        route.total_distance += esc_dist
        route.total_time += esc_time

    return route


def _expand_junction_path(
    adj: Adjacency, from_st: str, to_st: str, line: str, blocked: set[str]
) -> list[tuple[str, str]]:
    """2つのジャンクション駅間の全駅を、指定路線の辺のみを使ってDijkstraで展開する。"""
    if from_st == to_st:
        return [(from_st, "")]

    best = {from_st: 0.0}
    prev = {}
    heap = [(0.0, from_st)]
    seen = set()
    
    while heap:
        d, u = heapq.heappop(heap)
        if u in seen:
            continue
        seen.add(u)
        if u == to_st:
            break
        for v, lid, edge_dist, edge_time in adj.get(u, []):
            if lid != line:
                continue
            if v in blocked and v != to_st:
                continue
            cand = d + edge_dist
            if cand < best.get(v, float("inf")):
                best[v] = cand
                prev[v] = (u, lid)
                heapq.heappush(heap, (cand, v))
                
    if to_st not in prev:
        result = _shortest_avoiding(adj, from_st, to_st, blocked)
        if result is None:
            return [(from_st, "")]
        stations, lines, _, _ = result
        return list(zip(stations, lines))
        
    path = []
    cur = to_st
    while cur != from_st:
        u, lid = prev[cur]
        path.append((cur, lid))
        cur = u
    path.append((from_st, ""))
    path.reverse()
    return path


def find_golden_loop_routes(
    adj: Adjacency,
    start: str,
    fare_table: FareTable,
    end: str | None = None,
    max_time_min: float = 480.0,
    num_results: int = 5,
) -> list[OmawariRoute]:
    effective_time = max_time_min
    # 自由探索モード（同駅発着）は末尾の出発駅を除去する
    trim_last = end is None or end == start
    if end is None:
        end = start

    # ループを回らずに end へ抜けてしまう縮退ルートを弾くための下限距離
    direct_km, _, _ = calc_direct_fare(adj, start, end, fare_table)
    min_detour_km = direct_km * MIN_DETOUR_RATIO

    routes: list[_Route] = []

    loops = [
        {
            "junctions": GOLDEN_LOOP,
            "lines": LOOP_LINES,
            "shortcuts": SHORTCUTS,
        },
        {
            "junctions": KOBE_LOOP,
            "lines": KOBE_LINES,
            "shortcuts": [],
        },
    ]

    for loop_info in loops:
        loop_junctions = loop_info["junctions"]
        loop_lines = loop_info["lines"]
        loop_shortcuts = loop_info["shortcuts"]

        for reverse in (False, True):
            for shortcut in [None, *loop_shortcuts]:
                cycle = _expand_full_cycle(
                    adj, loop_junctions, loop_lines, reverse, shortcut
                )
                if cycle is None:
                    continue
                route = _build_loop_route(adj, start, end, cycle[0], cycle[1])
                if route is None or route.total_time > effective_time:
                    continue
                if route.total_distance < min_detour_km:
                    continue
                routes.append(route)

    # 自由探索モードでは末尾の出発駅（ループの閉じ駅）を除去する
    if trim_last:
        routes = [
            _trim_last_station(r, adj) if r.stations and r.stations[-1] == start else r
            for r in routes
        ]

    return _build_output(routes, adj, start, fare_table, num_results)


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
    fare_table: FareTable,
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

def _merge_result_layers(
    waypoint_routes: list[OmawariRoute],
    golden_routes: list[OmawariRoute],
    fsa_routes: list[OmawariRoute],
    num_results: int,
) -> list[OmawariRoute]:
    """レイヤー別の候補を合成し、パス（駅ID列）で重複排除して返す。

    ゴールデンループは駅によらずほぼ同じ定型ルートになるため、そのまま
    先頭に積むと結果が「一番大きいループ」とその変種だけで埋まってしまう。
    枠を GOLDEN_RESULT_RATIO までに制限し、残りは探索由来のルートに回す。
    枠が余った場合（探索側が不足）に限り、あふれたループで埋め直す。
    """
    golden_quota = max(1, int(num_results * GOLDEN_RESULT_RATIO))

    seen: set[tuple[str, ...]] = set()
    deduped: list[OmawariRoute] = []

    def add(routes: list[OmawariRoute]) -> None:
        for route in routes:
            if len(deduped) >= num_results:
                return
            sig = tuple(seg.station_id for seg in route.path)
            if sig in seen:
                continue
            seen.add(sig)
            deduped.append(route)

    add(waypoint_routes)
    add(golden_routes[:golden_quota])
    add(fsa_routes)
    add(golden_routes[golden_quota:])
    return deduped


def find_omawari_routes(
    adj: Adjacency,
    start: str,
    fare_table: FareTable,
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
    effective_time = max_time_min

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
                    if wp_route is not None and wp_route.total_time <= effective_time:
                        waypoint_results.append(wp_route)

        # ゴールデンループ方式によるルート生成
        golden_routes = find_golden_loop_routes(
            adj, start, fare_table, end, max_time_min, num_results
        )

        # 終着駅指定モード: マルチアトラクター FSAランダムウォークを num_trials 回実行
        end_distances = _nearest_km(adj, end)
        # 試行間でDijkstra結果を共有するグローバルキャッシュ
        global_dist_cache: dict[str, dict[str, float]] = {end: end_distances}
        collected: list[_Route] = []
        for _ in range(num_trials):
            chain = _build_attractor_chain(
                adj, start, end, rng,
                num_attractors=rng.randint(2, 4),
                dist_cache=global_dist_cache,
            )
            # チェイン内の未キャッシュ駅を補完（_build_attractor_chain で大半は計算済み）
            for attr in chain:
                if attr not in global_dist_cache:
                    global_dist_cache[attr] = _nearest_km(adj, attr)
            result = _random_walk_fsa(
                adj, start, end, end_distances,
                chain, global_dist_cache,
                max_stations, effective_time, rng,
            )
            if result is not None and result.station_count >= 3:
                collected.append(result)

        # 乗車時間上限でフィルタリング（0.0は制限なし）
        time_filtered = [r for r in collected if r.total_time <= effective_time]
        final = time_filtered if time_filtered else collected
        fsa_routes = _build_output(final, adj, start, fare_table, num_results)

        return _merge_result_layers(
            waypoint_results, golden_routes, fsa_routes, num_results
        )

    # 自由探索モード → 出発駅に戻るループとして FSA を使う
    else:
        # ゴールデンループ方式によるルート生成
        golden_routes = find_golden_loop_routes(
            adj, start, fare_table, None, max_time_min, num_results
        )

        loop_end = start
        end_distances = _nearest_km(adj, loop_end)
        global_dist_cache: dict[str, dict[str, float]] = {loop_end: end_distances}
        collected: list[_Route] = []

        for _ in range(num_trials):
            chain = _build_attractor_chain(
                adj, start, loop_end, rng,
                num_attractors=rng.randint(2, 4),
                dist_cache=global_dist_cache,
            )
            for attr in chain:
                if attr not in global_dist_cache:
                    global_dist_cache[attr] = _nearest_km(adj, attr)
            result = _random_walk_fsa(
                adj, start, loop_end, end_distances,
                chain, global_dist_cache,
                max_stations, effective_time, rng,
            )
            if result is not None and result.station_count >= 3:
                collected.append(result)

        # 乗車時間上限でフィルタリング（0.0は制限なし）
        time_filtered = [r for r in collected if r.total_time <= effective_time]
        final = time_filtered if time_filtered else collected
        # 同駅発着不可のため、出発駅に戻るループの末尾をトリム
        final = [
            _trim_last_station(r, adj) if r.stations and r.stations[-1] == start else r
            for r in final
        ]
        fsa_routes = _build_output(final, adj, start, fare_table, num_results)

        return _merge_result_layers([], golden_routes, fsa_routes, num_results)


def find_omawari_by_fare(
    adj: Adjacency,
    start: str,
    fare_table: FareTable,
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
    effective_time = max_time_min
    max_km = _max_km_for_fare(max_fare, start, fare_table)
    eligible_ends = _stations_within_km(adj, start, max_km)
    eligible_ends.discard(start)

    collected: list[_Route] = []
    for _ in range(num_trials):
        _random_walk_legacy(adj, start, 60, effective_time, rng, eligible_ends, collected)

    valid = [r for r in collected if r.station_count >= 3]
    filtered_output = [
        r for r in _build_output(valid, adj, start, fare_table, num_results * 3)
        if r.fare_ic <= max_fare
    ]
    return filtered_output[:num_results]

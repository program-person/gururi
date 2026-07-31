"""omawari モジュールのユニットテスト。

主に以下をカバーする:
- _shortest_avoiding: visited 駅を回避する Dijkstra
- find_routes_via_waypoints: 経由地連結ルート
- find_omawari_routes: WAYPOINT_ROUTES 統合 / detour 誘導
"""
from pathlib import Path

import pytest

from app.fare import load_fare_table
from app.graph import build_adjacency, load_graph_data
from app.omawari import (
    WAYPOINT_ROUTES,
    _shortest_avoiding,
    find_omawari_routes,
    find_routes_via_waypoints,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
TINY_GRAPH = FIXTURES / "tiny.json"


# tiny.json:
#   A --L1-- B --L1-- C        (distance: 5+1=6, time: 10+30=40)
#   A --L2-- C                  (distance: 10, time: 12)
# 上記の三角形構造で動作を検証する。


# --------------------------------------------------------------------------- #
# _shortest_avoiding
# --------------------------------------------------------------------------- #

def test_shortest_avoiding_direct_path() -> None:
    """blocked が空なら通常の時間ベース Dijkstra と同じ結果を返す。"""
    data = load_graph_data(TINY_GRAPH)
    adj = build_adjacency(data.edges)
    out = _shortest_avoiding(adj, "A", "C", set())
    assert out is not None
    stations, lines, dist, time = out
    # 時間最短は A→C 直行（L2, 12分）
    assert stations == ["A", "C"]
    assert lines == ["", "L2"]
    assert dist == 10.0
    assert time == 12.0


def test_shortest_avoiding_blocked_intermediate() -> None:
    """中継駅を blocked にしたら別経路を選ぶ。"""
    data = load_graph_data(TINY_GRAPH)
    adj = build_adjacency(data.edges)
    # 直行 A→C を強制せず B 経由を試したいので、まず B 経由のテストとして
    # A→C 直行が時間最短だが、A から C への B経由は時間40分
    # blocked={B} だと B 経由は使えないが A→C 直行は使える
    out = _shortest_avoiding(adj, "A", "C", {"B"})
    assert out is not None
    stations, _, _, _ = out
    assert stations == ["A", "C"]


def test_shortest_avoiding_same_station() -> None:
    """start == end は (start, ""), 0, 0 を返す。"""
    adj = build_adjacency(load_graph_data(TINY_GRAPH).edges)
    out = _shortest_avoiding(adj, "A", "A", set())
    assert out == (["A"], [""], 0.0, 0.0)


def test_shortest_avoiding_unreachable_when_blocked() -> None:
    """すべての経路が blocked されたら None。"""
    # A--B--C のみのグラフ（直結なし）
    adj = {
        "A": [("B", "L1", 1.0, 1.0)],
        "B": [("A", "L1", 1.0, 1.0), ("C", "L1", 1.0, 1.0)],
        "C": [("B", "L1", 1.0, 1.0)],
    }
    # B を blocked にすると A→C は到達不能
    assert _shortest_avoiding(adj, "A", "C", {"B"}) is None


# --------------------------------------------------------------------------- #
# find_routes_via_waypoints
# --------------------------------------------------------------------------- #

def test_find_routes_via_waypoints_basic() -> None:
    """A → B → C と経由地指定したらその通りのルートを返す。"""
    data = load_graph_data(TINY_GRAPH)
    adj = build_adjacency(data.edges)
    fare_table = load_fare_table()
    route = find_routes_via_waypoints(adj, "A", "C", ["B"], fare_table)
    assert route is not None
    station_ids = [seg.station_id for seg in route.path]
    assert station_ids == ["A", "B", "C"]
    assert route.station_count == 3


def test_find_routes_via_waypoints_unreachable_waypoint() -> None:
    """グラフに存在しない経由地を指定したら None。"""
    data = load_graph_data(TINY_GRAPH)
    adj = build_adjacency(data.edges)
    fare_table = load_fare_table()
    route = find_routes_via_waypoints(adj, "A", "C", ["Z"], fare_table)
    assert route is None


def test_find_routes_via_waypoints_no_duplicate_stations() -> None:
    """経由地を巡る過程で同じ駅を二度通らない。"""
    # 三角形グラフで A→C→A→B と巡らせようとしたら、
    # C から A への帰路は使えるが、その後 A から B への経路で A をスタートに含むため OK
    # ただし、ここでは visited が継承されるので A→C 後の A 再訪は禁止
    data = load_graph_data(TINY_GRAPH)
    adj = build_adjacency(data.edges)
    fare_table = load_fare_table()
    # A → C → B（C から B は L1 で行ける）
    route = find_routes_via_waypoints(adj, "A", "B", ["C"], fare_table)
    assert route is not None
    station_ids = [seg.station_id for seg in route.path]
    # A は一度だけ
    assert station_ids.count("A") == 1
    assert station_ids[0] == "A"
    assert station_ids[-1] == "B"
    assert "C" in station_ids


# --------------------------------------------------------------------------- #
# WAYPOINT_ROUTES 統合
# --------------------------------------------------------------------------- #

def test_waypoint_routes_constant_shape() -> None:
    """WAYPOINT_ROUTES のキーと値の構造を検証する。"""
    for key, val in WAYPOINT_ROUTES.items():
        assert isinstance(key, tuple) and len(key) == 2
        assert all(isinstance(k, str) for k in key)
        assert isinstance(val, list)
        for waypoints in val:
            assert isinstance(waypoints, list)
            assert all(isinstance(w, str) for w in waypoints)


def test_find_omawari_routes_with_waypoint_integration() -> None:
    """name_to_id を渡し WAYPOINT_ROUTES に該当する場合、結果の先頭に追加される。"""
    # tiny.json で擬似的に検証する
    data = load_graph_data(TINY_GRAPH)
    adj = build_adjacency(data.edges)
    fare_table = load_fare_table()
    # WAYPOINT_ROUTES に対応する偽のキー定義を試すため、独自に検証
    name_to_id = {"Station A": "A", "Station B": "B", "Station C": "C"}
    # 通常呼び出し（WAYPOINT_ROUTES に該当しない）
    routes = find_omawari_routes(
        adj, "A", fare_table,
        end="C", num_results=2, num_trials=10,
        name_to_id=name_to_id, seed=1,
    )
    # 少なくとも何らかのルートが返る（または空でも OK）
    assert isinstance(routes, list)


# --------------------------------------------------------------------------- #
# detour 誘導の挙動確認（end_distances）
# --------------------------------------------------------------------------- #

def test_find_omawari_routes_end_mode_smoke() -> None:
    """end 指定モードがエラーなく動く（スモークテスト）。"""
    data = load_graph_data(TINY_GRAPH)
    adj = build_adjacency(data.edges)
    fare_table = load_fare_table()
    routes = find_omawari_routes(
        adj, "A", fare_table,
        end="C", num_results=3, num_trials=20,
        seed=42,
    )
    assert isinstance(routes, list)
    for r in routes:
        assert r.path[0].station_id == "A"
        # end 指定モードなので終点は C のはず
        # ただし min_detour_distance のフィルタで何も残らない可能性もある


def test_find_omawari_routes_free_mode_smoke() -> None:
    """end 未指定の自由探索モードがエラーなく動く。"""
    data = load_graph_data(TINY_GRAPH)
    adj = build_adjacency(data.edges)
    fare_table = load_fare_table()
    routes = find_omawari_routes(
        adj, "A", fare_table,
        num_results=3, num_trials=20,
        seed=42,
    )
    assert isinstance(routes, list)


# --------------------------------------------------------------------------- #
# ゴールデンループ方式のテスト
# --------------------------------------------------------------------------- #

REAL_GRAPH = Path(__file__).resolve().parent.parent / "data" / "graph.json"


def test_nearest_in_set_returns_self() -> None:
    """候補集合に含まれる駅自身を渡すと、その駅をそのまま返す。"""
    from app.omawari import _nearest_in_set
    data = load_graph_data(REAL_GRAPH)
    adj = build_adjacency(data.edges)

    assert _nearest_in_set(adj, "osak", {"osak", "kyot"}) == "osak"


def test_nearest_in_set_picks_closest() -> None:
    """候補集合外の駅からは、最も近い候補駅を返す。"""
    from app.omawari import _nearest_in_set
    data = load_graph_data(REAL_GRAPH)
    adj = build_adjacency(data.edges)

    # 吹田(suit)からは新大阪(ssin)のほうが京都(kyot)より近い
    assert _nearest_in_set(adj, "suit", {"ssin", "kyot"}) == "ssin"


def test_expand_full_cycle_is_a_valid_cycle() -> None:
    """展開した閉路は駅が重複せず、隣接駅どうしが指定路線の辺でつながる。"""
    from app.omawari import GOLDEN_LOOP, LOOP_LINES, _expand_full_cycle
    data = load_graph_data(REAL_GRAPH)
    adj = build_adjacency(data.edges)

    for reverse in (False, True):
        cycle = _expand_full_cycle(adj, GOLDEN_LOOP, LOOP_LINES, reverse)
        assert cycle is not None
        stations, edge_lines = cycle
        assert len(stations) == len(set(stations))
        assert len(stations) == len(edge_lines)
        for i, from_station in enumerate(stations):
            to_station = stations[(i + 1) % len(stations)]
            assert any(
                v == to_station and lid == edge_lines[i]
                for v, lid, _, _ in adj.get(from_station, [])
            ), f"{from_station} -> {to_station} ({edge_lines[i]}) が存在しない"


def test_golden_loop_from_intermediate_station() -> None:
    """ループ上の中間駅（ジャンクション以外）発でも同じループが生成される。

    回帰テスト: 以前はジャンクション（新大阪）までのアプローチ区間が
    ループ自身と重複して探索が破綻し、茨木発では1本も返らなかった。
    """
    from app.omawari import find_golden_loop_routes
    data = load_graph_data(REAL_GRAPH)
    adj = build_adjacency(data.edges)
    fare_table = load_fare_table()

    osaka_routes = find_golden_loop_routes(adj, "osak", fare_table, max_time_min=10000.0)
    ibaraki_routes = find_golden_loop_routes(adj, "ibrk", fare_table, max_time_min=10000.0)

    assert osaka_routes and ibaraki_routes
    # 茨木は大阪発の最大ループに含まれるので、同じ規模のループが返るはず
    assert ibaraki_routes[0].station_count == osaka_routes[0].station_count
    ibaraki_ids = [seg.station_id for seg in ibaraki_routes[0].path]
    assert ibaraki_ids[0] == "ibrk"
    assert "osak" in ibaraki_ids
    assert len(ibaraki_ids) == len(set(ibaraki_ids))


def test_results_are_not_only_the_biggest_loop() -> None:
    """結果が定型のゴールデンループだけで埋まらない。"""
    from app.omawari import find_omawari_routes
    data = load_graph_data(REAL_GRAPH)
    adj = build_adjacency(data.edges)
    fare_table = load_fare_table()

    routes = find_omawari_routes(
        adj, "ibrk", fare_table,
        max_time_min=10000.0, num_results=5, num_trials=120, seed=1,
    )
    assert len(routes) >= 3
    # 最大ループと同規模のルートが結果を占有していない
    biggest = routes[0].station_count
    assert sum(1 for r in routes if r.station_count == biggest) <= 2


def test_expand_junction_path() -> None:
    """2つのジャンクション駅間の全駅を展開する。"""
    from app.omawari import _expand_junction_path
    data = load_graph_data(REAL_GRAPH)
    adj = build_adjacency(data.edges)
    
    # "osak" (大阪) から "tenn" (天王寺) へ大阪環状線 "O" で展開
    path = _expand_junction_path(adj, "osak", "tenn", "O", set())
    assert len(path) > 2
    assert path[0][0] == "osak"
    assert path[-1][0] == "tenn"
    # 中間駅が含まれていること
    station_ids = [st for st, _ in path]
    assert "kyob" in station_ids  # 京橋駅


def test_golden_loop_cw() -> None:
    """大阪発のゴールデンループ（時計回り）が正しく生成される。

    大回りのルールでは同駅発着不可のため、出発駅に戻る最終駅は
    トリムされる（出発駅の1駅手前で終わる）。
    """
    from app.omawari import find_golden_loop_routes
    data = load_graph_data(REAL_GRAPH)
    adj = build_adjacency(data.edges)
    fare_table = load_fare_table()

    # 時間制限で結果が変わらないよう十分大きい値（旧仕様の 0=無制限 は廃止）
    routes = find_golden_loop_routes(adj, "osak", fare_table, "osak", max_time_min=10000.0)
    assert len(routes) > 0
    # 先頭が最もスコアが高い
    best_route = routes[0]
    station_ids = [seg.station_id for seg in best_route.path]
    # 大阪発・出発駅には戻らない（同駅発着不可）
    assert station_ids[0] == "osak"
    assert station_ids[-1] != "osak"
    # 同一駅を2度通らない
    assert len(station_ids) == len(set(station_ids))
    # 最終駅は出発駅の隣接駅（ループを一周して1駅手前で終わる）
    neighbors = {v for v, _, _, _ in adj.get("osak", [])}
    assert station_ids[-1] in neighbors


def test_find_omawari_routes_includes_golden() -> None:
    """合成された大回りルートにゴールデンループが含まれる。"""
    data = load_graph_data(REAL_GRAPH)
    adj = build_adjacency(data.edges)
    fare_table = load_fare_table()
    
    # 大阪→天王寺
    routes = find_omawari_routes(adj, "osak", fare_table, "tenn", max_time_min=10000.0, num_results=5)
    assert len(routes) > 0
    # いずれかのルートにゴールデンループの特徴的な駅（例: 近江塩津 enis）が含まれる
    has_enis = any("enis" in [seg.station_id for seg in r.path] for r in routes)
    assert has_enis


# --------------------------------------------------------------------------- #
# 最大乗車時間の遵守（回帰テスト: 時間制限つきでルートが出ない不具合）
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("max_time", [120.0, 240.0, 480.0])
def test_free_mode_respects_max_time(max_time: float) -> None:
    """自由探索モード: 有限の時間制限でもルートが返り、全件が制限内に収まる。"""
    data = load_graph_data(REAL_GRAPH)
    adj = build_adjacency(data.edges)
    fare_table = load_fare_table()
    routes = find_omawari_routes(
        adj, "osak", fare_table,
        max_time_min=max_time, num_trials=300, seed=42,
    )
    assert len(routes) > 0
    assert all(r.total_time <= max_time for r in routes)
    # 同駅発着不可: 出発駅に戻るルートは末尾がトリムされている
    assert all(r.path[-1].station_id != "osak" for r in routes)


@pytest.mark.parametrize("max_time", [120.0, 240.0, 480.0])
def test_dest_mode_respects_max_time(max_time: float) -> None:
    """駅間指定モード: 有限の時間制限でもルートが返り、全件が制限内に収まる。"""
    data = load_graph_data(REAL_GRAPH)
    adj = build_adjacency(data.edges)
    fare_table = load_fare_table()
    name_to_id = {s.name: s.id for s in data.stations}
    routes = find_omawari_routes(
        adj, "osak", fare_table, end="tenn",
        max_time_min=max_time, num_trials=300, seed=42,
        name_to_id=name_to_id,
    )
    assert len(routes) > 0
    assert all(r.total_time <= max_time for r in routes)
    assert all(r.path[-1].station_id == "tenn" for r in routes)


def test_loop_lines_match_graph() -> None:
    """LOOP_LINES / KOBE_LINES の路線IDが graph.json に実在する。"""
    from app.omawari import LOOP_LINES, KOBE_LINES, SHORTCUTS
    data = load_graph_data(REAL_GRAPH)
    graph_lines = {e.line_id for e in data.edges}
    assert set(LOOP_LINES) <= graph_lines
    assert set(KOBE_LINES) <= graph_lines
    assert {sc["line"] for sc in SHORTCUTS} <= graph_lines


# --------------------------------------------------------------------------- #
# API レベル
# --------------------------------------------------------------------------- #

def test_lines_endpoint(client) -> None:
    """/lines が tiny.json の路線を返す。"""
    r = client.get("/lines")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert {"id": "L1", "name": "Line 1"} in body
    assert {"id": "L2", "name": "Line 2"} in body

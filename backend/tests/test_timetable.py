from pathlib import Path

from app.graph import build_adjacency, load_graph_data
from app.models import PathSegment
from app.timetable import (
    Leg,
    build_timetable,
    split_legs,
    _fmt,
    _next_after,
    _parse_hhmm,
    _pick_direct,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
TINY_GRAPH = FIXTURES / "tiny.json"


def _path(*pairs: tuple[str, str]) -> list[PathSegment]:
    return [PathSegment(station_id=s, line_id=l) for s, l in pairs]


def test_split_legs_single_line() -> None:
    path = _path(("A", ""), ("B", "X"), ("C", "X"))
    legs = split_legs(path)
    assert legs == [Leg("X", ("A", "B", "C"))]


def test_split_legs_with_transfer() -> None:
    path = _path(("A", ""), ("B", "X"), ("C", "X"), ("D", "Y"), ("E", "Y"))
    legs = split_legs(path)
    assert legs == [Leg("X", ("A", "B", "C")), Leg("Y", ("C", "D", "E"))]
    # 乗換駅 C は両レッグに含まれる
    assert legs[0].station_ids[-1] == legs[1].station_ids[0]


def test_split_legs_empty_and_single() -> None:
    assert split_legs([]) == []
    assert split_legs(_path(("A", ""))) == []


def test_hhmm_roundtrip() -> None:
    assert _parse_hhmm("10:05") == 10 * 3600 + 300
    assert _fmt(10 * 3600 + 300) == "10:05"
    assert _fmt(25 * 3600) == "01:00"  # 日跨ぎは mod 24h


def test_pick_direct_prefers_zero_transfer() -> None:
    data = {
        "journeys": [
            {"transferCount": 1, "legs": []},
            {
                "transferCount": 0,
                "legs": [
                    {
                        "kind": "transit",
                        "departureSecs": 36000,
                        "arrivalSecs": 37200,
                        "trainType": "普通",
                        "headsign": "普通 天王寺",
                    }
                ],
            },
        ]
    }
    picked = _pick_direct(data)
    assert picked == (36000, 37200, "普通", "普通 天王寺")


def test_pick_direct_none_when_all_transfers() -> None:
    assert _pick_direct({"journeys": [{"transferCount": 2, "legs": []}]}) is None


def test_build_timetable_estimate_fallback(monkeypatch) -> None:
    """transit API 不通時は運転間隔ベースの推定にフォールバックする"""
    import app.timetable as tt

    monkeypatch.setattr(tt.transit, "plan", lambda *a, **k: None)
    data = load_graph_data(TINY_GRAPH)
    adj = build_adjacency(data.edges)

    # tiny.json: A-B-C（路線X相当のlineIdを使う）
    path = _path(("A", ""), ("B", "L1"), ("C", "L1"))
    res = build_timetable(path, "10:00", adj, {})

    assert res.has_estimate is True
    assert len(res.legs) == 1
    leg = res.legs[0]
    assert leg.source == "estimate"
    assert leg.from_station_id == "A"
    assert leg.to_station_id == "C"
    # 待ち = 未定義路線のデフォルト間隔 20 / 2 = 10分（初乗りなので乗換歩行なし）
    assert leg.wait_min == 10.0
    # 乗車 = tiny.json の travelTime 合計（A-B, B-C）
    assert leg.ride_min > 0
    assert res.arrival_time > res.depart_time


def test_build_timetable_uses_timetable_source(monkeypatch) -> None:
    """マッピングがあり API が応答すれば実ダイヤを使う"""
    import app.timetable as tt

    def fake_plan(from_id: str, to_id: str, hhmm: str):
        return {
            "journeys": [
                {
                    "transferCount": 0,
                    "legs": [
                        {
                            "kind": "transit",
                            "departureSecs": _parse_hhmm("10:07"),
                            "arrivalSecs": _parse_hhmm("10:30"),
                            "trainType": "普通",
                            "headsign": "普通 C行",
                        }
                    ],
                }
            ]
        }

    monkeypatch.setattr(tt.transit, "plan", fake_plan)
    data = load_graph_data(TINY_GRAPH)
    adj = build_adjacency(data.edges)

    path = _path(("A", ""), ("B", "L1"), ("C", "L1"))
    tmap = {"L1": {"A": "feed:A", "C": "feed:C"}}
    res = build_timetable(path, "10:00", adj, tmap)

    assert res.has_estimate is False
    leg = res.legs[0]
    assert leg.source == "timetable"
    assert leg.departure == "10:07"
    assert leg.arrival == "10:30"
    assert leg.wait_min == 7.0
    assert leg.ride_min == 23.0
    assert res.arrival_time == "10:30"
    assert res.total_min == 30.0


def test_next_after_same_day_and_rollover() -> None:
    ten = _parse_hhmm("10:00")
    assert _next_after(_parse_hhmm("10:48"), ten) == _parse_hhmm("10:48")
    # 入力が現在カーソルより前なら翌日の同時刻と解釈する
    assert _next_after(_parse_hhmm("09:00"), ten) == _parse_hhmm("09:00") + 86400
    # ちょうど同時刻はその日のまま（>= で判定）
    assert _next_after(ten, ten) == ten
    # カーソル自体が翌日に入っていても基準日が追従する
    assert _next_after(_parse_hhmm("00:15"), _parse_hhmm("23:50")) == _parse_hhmm("00:15") + 86400


def test_build_timetable_arrival_override_shifts_following_legs(monkeypatch) -> None:
    """推定区間の着時刻を上書きすると、後続レッグがその時刻を起点に組み直される。"""
    import app.timetable as tt

    monkeypatch.setattr(tt.transit, "plan", lambda *a, **k: None)
    data = load_graph_data(TINY_GRAPH)
    adj = build_adjacency(data.edges)

    # A -L2- C -L1- B の2レッグ。1本目（A→C）の着時刻を上書きする
    path = _path(("A", ""), ("C", "L2"), ("B", "L1"))
    base = build_timetable(path, "10:00", adj, {})
    res = build_timetable(path, "10:00", adj, {}, arrival_overrides={"C": "11:30"})

    assert res.legs[0].overridden is True
    assert res.legs[0].arrival == "11:30"
    # 乗車時間は元のまま保たれ、発時刻が着から逆算される
    assert res.legs[0].ride_min == base.legs[0].ride_min
    # 2本目は上書き後の 11:30 を起点に組み直される
    assert res.legs[1].overridden is False
    assert res.legs[1].departure > "11:30"
    assert res.arrival_time > base.arrival_time


def test_build_timetable_override_clears_estimate_flag(monkeypatch) -> None:
    """全推定レッグを上書きすれば hasEstimate は下りる（＝「目安」警告が消える）"""
    import app.timetable as tt

    monkeypatch.setattr(tt.transit, "plan", lambda *a, **k: None)
    data = load_graph_data(TINY_GRAPH)
    adj = build_adjacency(data.edges)

    path = _path(("A", ""), ("B", "L1"), ("C", "L1"))
    assert build_timetable(path, "10:00", adj, {}).has_estimate is True
    res = build_timetable(path, "10:00", adj, {}, arrival_overrides={"C": "10:40"})
    assert res.has_estimate is False
    assert res.legs[0].source == "estimate"  # 出所そのものは推定のまま


def test_build_timetable_override_clamps_departure_to_cursor(monkeypatch) -> None:
    """推定より早い着時刻を入れても、前の駅に着く前の発時刻は作らない。"""
    import app.timetable as tt

    monkeypatch.setattr(tt.transit, "plan", lambda *a, **k: None)
    data = load_graph_data(TINY_GRAPH)
    adj = build_adjacency(data.edges)

    # A→B→C は推定で 10:10発 10:50着。着時刻に 10:20 を入れると乗車40分は入らない
    path = _path(("A", ""), ("B", "L1"), ("C", "L1"))
    res = build_timetable(path, "10:00", adj, {}, arrival_overrides={"C": "10:20"})
    leg = res.legs[0]
    assert leg.arrival == "10:20"
    assert leg.departure >= "10:00"  # 出発時刻より前には遡らない
    assert leg.wait_min >= 0
    assert leg.ride_min >= 0


def test_build_timetable_override_crossing_midnight(monkeypatch) -> None:
    """23時台発 → 0時台着の上書きは翌日扱いになり、総所要がマイナスにならない。"""
    import app.timetable as tt

    monkeypatch.setattr(tt.transit, "plan", lambda *a, **k: None)
    data = load_graph_data(TINY_GRAPH)
    adj = build_adjacency(data.edges)

    path = _path(("A", ""), ("B", "L1"), ("C", "L1"))
    res = build_timetable(path, "23:50", adj, {}, arrival_overrides={"C": "00:15"})
    assert res.arrival_time == "00:15"
    assert res.total_min == 25.0

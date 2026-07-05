from pathlib import Path

from app.graph import build_adjacency, load_graph_data
from app.models import PathSegment
from app.timetable import (
    Leg,
    build_timetable,
    split_legs,
    _fmt,
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

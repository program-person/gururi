"""監査対応で追加した入力バリデーションのテスト。

- POST /timetable: path の実在ルート検証・長さ上限（外部APIへの踏み台化防止）
- GET /omawari 系: maxTimeMin=0（旧・無制限センチネル）の拒否
"""
import pytest
from fastapi.testclient import TestClient

import app.timetable as tt


@pytest.fixture(autouse=True)
def no_transit_api(monkeypatch: pytest.MonkeyPatch) -> None:
    """テストから実 transit API を呼ばない（常に推定フォールバック）"""
    monkeypatch.setattr(tt.transit, "plan", lambda *a, **k: None)


def _timetable_body(path: list[tuple[str, str]]) -> dict:
    return {
        "path": [{"stationId": s, "lineId": l} for s, l in path],
        "departTime": "10:00",
    }


def test_timetable_valid_path_ok(client: TestClient) -> None:
    r = client.post("/timetable", json=_timetable_body([("A", ""), ("B", "L1"), ("C", "L1")]))
    assert r.status_code == 200
    assert r.json()["legs"][0]["source"] == "estimate"


def test_timetable_rejects_non_adjacent_pair(client: TestClient) -> None:
    # A-C 直結エッジは L2 のみ。L1 と偽った path は不正ルートとして拒否
    r = client.post("/timetable", json=_timetable_body([("A", ""), ("C", "L1")]))
    assert r.status_code == 400
    assert "not a valid route" in r.json()["detail"]


def test_timetable_rejects_unknown_line(client: TestClient) -> None:
    r = client.post("/timetable", json=_timetable_body([("A", ""), ("B", "NOPE")]))
    assert r.status_code == 400


def test_timetable_rejects_unknown_station(client: TestClient) -> None:
    r = client.post("/timetable", json=_timetable_body([("A", ""), ("Z", "L1")]))
    assert r.status_code == 404


def test_timetable_rejects_too_long_path(client: TestClient) -> None:
    # 201要素（A-B を往復し続ける形式的な path）。長さ上限で先に弾かれる
    pairs: list[tuple[str, str]] = [("A", "")]
    for i in range(200):
        pairs.append(("B" if i % 2 == 0 else "A", "L1"))
    r = client.post("/timetable", json=_timetable_body(pairs))
    assert r.status_code == 400
    assert "too long" in r.json()["detail"]


def test_timetable_rejects_short_path(client: TestClient) -> None:
    r = client.post("/timetable", json=_timetable_body([("A", "")]))
    assert r.status_code == 400


def test_omawari_rejects_max_time_zero(client: TestClient) -> None:
    r = client.get("/omawari", params={"startStationId": "A", "maxTimeMin": 0})
    assert r.status_code == 422


def test_omawari_by_fare_rejects_max_time_zero(client: TestClient) -> None:
    r = client.get(
        "/omawari/by-fare",
        params={"startStationId": "A", "maxFare": 200, "maxTimeMin": 0},
    )
    assert r.status_code == 422

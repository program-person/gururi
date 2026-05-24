from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.config as app_config
from app.main import app
from app.routing import shortest_route
from app.graph import build_adjacency, load_graph_data
from app.models import OptimizeBy

FIXTURES = Path(__file__).resolve().parent / "fixtures"
TINY_GRAPH = FIXTURES / "tiny.json"


def test_dijkstra_by_distance() -> None:
    data = load_graph_data(TINY_GRAPH)
    adj = build_adjacency(data.edges)
    out = shortest_route(adj, "A", "C", OptimizeBy.distance)
    assert out is not None
    path, td, tt = out
    assert td == 6.0
    assert tt == 40.0
    assert [p[0] for p in path] == ["A", "B", "C"]


def test_dijkstra_by_time() -> None:
    data = load_graph_data(TINY_GRAPH)
    adj = build_adjacency(data.edges)
    out = shortest_route(adj, "A", "C", OptimizeBy.time)
    assert out is not None
    path, td, tt = out
    assert td == 10.0
    assert tt == 12.0
    assert [p[0] for p in path] == ["A", "C"]


def test_same_station() -> None:
    data = load_graph_data(TINY_GRAPH)
    adj = build_adjacency(data.edges)
    out = shortest_route(adj, "B", "B", OptimizeBy.distance)
    assert out == ([("B", "")], 0.0, 0.0)


def test_unreachable() -> None:
    adj = {"X": [("Y", "L", 1.0, 1.0)], "Y": [("X", "L", 1.0, 1.0)]}
    assert shortest_route(adj, "X", "A", OptimizeBy.distance) is None


def test_get_route_api(client: TestClient) -> None:
    r = client.get("/route", params={"startStationId": "A", "endStationId": "C", "by": "distance"})
    assert r.status_code == 200
    body = r.json()
    assert body["totalDistance"] == 6.0
    assert body["totalTime"] == 40.0
    assert [p["stationId"] for p in body["path"]] == ["A", "B", "C"]
    assert body["path"][0]["lineId"] == ""


def test_get_route_unknown_station(client: TestClient) -> None:
    r = client.get("/route", params={"startStationId": "Z", "endStationId": "A"})
    assert r.status_code == 404


def test_health(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_config.settings, "data_path", TINY_GRAPH)
    with TestClient(app) as client:
        body = client.get("/health").json()
        assert body["status"] == "ok"
        assert "version" in body

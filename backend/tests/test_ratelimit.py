"""レート制限（app/ratelimit.py + main.py ミドルウェア）のテスト。"""
import pytest
from fastapi.testclient import TestClient

import app.config as app_config
import app.main as app_main
from app.ratelimit import SlidingWindowRateLimiter


# ------------------------------------------------------------------
# SlidingWindowRateLimiter 単体
# ------------------------------------------------------------------

def test_allows_up_to_max_then_blocks() -> None:
    limiter = SlidingWindowRateLimiter()
    for _ in range(3):
        assert limiter.allow("ip1", 3, 60.0, now=100.0) is True
    assert limiter.allow("ip1", 3, 60.0, now=100.0) is False


def test_window_expiry_allows_again() -> None:
    limiter = SlidingWindowRateLimiter()
    for _ in range(3):
        assert limiter.allow("ip1", 3, 60.0, now=100.0) is True
    assert limiter.allow("ip1", 3, 60.0, now=159.0) is False
    # 60秒経過でウィンドウから外れる
    assert limiter.allow("ip1", 3, 60.0, now=161.0) is True


def test_keys_are_independent() -> None:
    limiter = SlidingWindowRateLimiter()
    assert limiter.allow("ip1", 1, 60.0, now=100.0) is True
    assert limiter.allow("ip1", 1, 60.0, now=100.0) is False
    assert limiter.allow("ip2", 1, 60.0, now=100.0) is True


def test_reset_clears_state() -> None:
    limiter = SlidingWindowRateLimiter()
    assert limiter.allow("ip1", 1, 60.0, now=100.0) is True
    limiter.reset()
    assert limiter.allow("ip1", 1, 60.0, now=100.0) is True


# ------------------------------------------------------------------
# ミドルウェア結合（TestClient 経由）
# ------------------------------------------------------------------

def test_omawari_returns_429_over_limit(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app_config.settings, "rate_limit_max_requests", 2)
    params = {"startStationId": "A", "numResults": 1, "maxStations": 5}
    assert client.get("/omawari", params=params).status_code == 200
    assert client.get("/omawari", params=params).status_code == 200
    r = client.get("/omawari", params=params)
    assert r.status_code == 429
    assert "detail" in r.json()


def test_non_limited_endpoint_unaffected(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app_config.settings, "rate_limit_max_requests", 1)
    for _ in range(5):
        assert client.get("/health").status_code == 200


def test_rate_limit_can_be_disabled(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app_config.settings, "rate_limit_enabled", False)
    monkeypatch.setattr(app_config.settings, "rate_limit_max_requests", 1)
    params = {"startStationId": "A", "numResults": 1, "maxStations": 5}
    for _ in range(3):
        assert client.get("/omawari", params=params).status_code == 200


def test_x_forwarded_for_first_hop_is_key(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app_config.settings, "rate_limit_max_requests", 1)
    params = {"startStationId": "A", "numResults": 1, "maxStations": 5}
    h1 = {"X-Forwarded-For": "203.0.113.1, 10.0.0.1"}
    h2 = {"X-Forwarded-For": "203.0.113.2, 10.0.0.1"}
    assert client.get("/omawari", params=params, headers=h1).status_code == 200
    assert client.get("/omawari", params=params, headers=h1).status_code == 429
    # 別クライアントIPは独立してカウントされる
    assert client.get("/omawari", params=params, headers=h2).status_code == 200

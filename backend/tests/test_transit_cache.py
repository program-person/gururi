"""transit.py キャッシュの上限（無限成長防止）のテスト。"""
import pytest

from app import transit


class _FakeResponse:
    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return {"journeys": []}


@pytest.fixture(autouse=True)
def clean_cache(monkeypatch: pytest.MonkeyPatch):
    transit._cache.clear()
    monkeypatch.setattr(transit.httpx, "get", lambda *a, **k: _FakeResponse())
    yield
    transit._cache.clear()


def test_cache_size_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(transit, "MAX_CACHE_ENTRIES", 4)
    for i in range(20):
        assert transit.plan(f"from{i}", "to", "10:00") is not None
    assert len(transit._cache) <= 4


def test_prune_drops_expired_first(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(transit, "MAX_CACHE_ENTRIES", 4)
    base = 1000.0
    clock = {"now": base}
    monkeypatch.setattr(transit.time, "monotonic", lambda: clock["now"])

    for i in range(3):
        transit.plan(f"old{i}", "to", "10:00")
    # TTL を超えて時間を進めた後の新規追加で、期限切れが先に落ちる
    clock["now"] = base + transit.CACHE_TTL_SECS + 1
    transit.plan("new0", "to", "10:00")
    transit.plan("new1", "to", "10:00")
    keys = {k[0] for k in transit._cache}
    assert "new0" in keys and "new1" in keys
    assert not any(k.startswith("old") for k in keys)


def test_cache_hit_within_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def counting_get(*a, **k):
        calls["n"] += 1
        return _FakeResponse()

    monkeypatch.setattr(transit.httpx, "get", counting_get)
    transit.plan("x", "y", "10:00")
    transit.plan("x", "y", "10:00")
    assert calls["n"] == 1

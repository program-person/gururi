"""transit.ls8h.com API クライアント（実ダイヤ照会）。

個人運営の非公式APIのため、失敗時は None を返して呼び出し側が
推定値にフォールバックできるようにする。レスポンスは短時間キャッシュする。
"""
from __future__ import annotations

import time
from typing import Any

import httpx

BASE_URL = "https://api.transit.ls8h.com/api/v1"
HEADERS = {"User-Agent": "omawari-app (personal project)"}
TIMEOUT_SECS = 10.0
CACHE_TTL_SECS = 300.0
# キャッシュの無限成長防止。超過時は期限切れ→古い順に削除する
MAX_CACHE_ENTRIES = 512

_cache: dict[tuple[str, str, str], tuple[float, dict[str, Any]]] = {}


def _prune_cache(now: float) -> None:
    expired = [k for k, (ts, _) in _cache.items() if now - ts >= CACHE_TTL_SECS]
    for k in expired:
        del _cache[k]
    overflow = len(_cache) - (MAX_CACHE_ENTRIES - 1)
    if overflow > 0:
        oldest = sorted(_cache, key=lambda k: _cache[k][0])[:overflow]
        for k in oldest:
            del _cache[k]


def plan(from_id: str, to_id: str, time_hhmm: str) -> dict[str, Any] | None:
    """経路検索。ネットワーク障害・異常レスポンス時は None。"""
    key = (from_id, to_id, time_hhmm)
    now = time.monotonic()
    cached = _cache.get(key)
    if cached and now - cached[0] < CACHE_TTL_SECS:
        return cached[1]
    try:
        r = httpx.get(
            f"{BASE_URL}/plan",
            params={"from": from_id, "to": to_id, "time": time_hhmm},
            headers=HEADERS,
            timeout=TIMEOUT_SECS,
        )
        r.raise_for_status()
        data = r.json()
    except Exception:
        return None
    if not isinstance(data, dict) or "journeys" not in data:
        return None
    if len(_cache) >= MAX_CACHE_ENTRIES:
        _prune_cache(now)
    _cache[key] = (now, data)
    return data

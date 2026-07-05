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

_cache: dict[tuple[str, str, str], tuple[float, dict[str, Any]]] = {}


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
    _cache[key] = (now, data)
    return data

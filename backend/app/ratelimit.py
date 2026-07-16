"""IP単位のスライディングウィンドウ・レート制限。

外部依存を増やさないための自作実装。状態はプロセス内メモリに持つため
単一インスタンス構成（Railway）を前提とする。水平スケールする場合は
Redis 等の共有ストアを使う実装（slowapi など）に置き換えること。
"""
from __future__ import annotations

import threading
import time
from collections import deque

# 追跡するクライアントキー数の上限（メモリの無限成長防止）
MAX_TRACKED_KEYS = 10_000


class SlidingWindowRateLimiter:
    """キーごとに直近 window_secs 秒間のリクエスト時刻を保持して判定する。

    max_requests / window_secs を呼び出し時に受け取るのは、設定
    （pydantic-settings）の値をテストで差し替えやすくするため。
    """

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(
        self,
        key: str,
        max_requests: int,
        window_secs: float,
        now: float | None = None,
    ) -> bool:
        if now is None:
            now = time.monotonic()
        cutoff = now - window_secs
        with self._lock:
            hits = self._hits.get(key)
            if hits is None:
                if len(self._hits) >= MAX_TRACKED_KEYS:
                    self._evict_stale(cutoff)
                hits = deque()
                self._hits[key] = hits
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= max_requests:
                return False
            hits.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()

    def _evict_stale(self, cutoff: float) -> None:
        # ウィンドウ外のヒットしか持たないキーを落とす（ロック取得済みで呼ぶ）
        for key in list(self._hits):
            hits = self._hits[key]
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if not hits:
                del self._hits[key]

"""AI 응답 캐싱 + 요청 제한 service (mock 단계).

이 단계에서는 실제 Redis 를 사용하지 않고 in-memory dict 로 구현한다.
- 서버 재시작 시 캐시는 모두 사라진다.
- 멀티 워커 환경에서는 워커별로 캐시가 분리된다 (실 Redis 도입 시 해소).
- check_rate_limit 은 mock 단계에서 항상 True 를 반환한다.
"""

import hashlib
import json
import time
from typing import Any

from app.core.config import settings

__all__ = ["CacheService"]


class CacheService:
    """in-memory 캐시 + rate-limit (mock) service."""

    def __init__(self) -> None:
        # value, expires_at(epoch seconds | None)
        self._store: dict[str, tuple[Any, float | None]] = {}

    # ------------------------------------------------------------------
    # cache
    # ------------------------------------------------------------------
    def get_cache(self, key: str) -> Any | None:
        item = self._store.get(key)
        if item is None:
            return None
        value, expires_at = item
        if expires_at is not None and expires_at < time.time():
            self._store.pop(key, None)
            return None
        return value

    def set_cache(self, key: str, value: Any, ttl: int | None = None) -> None:
        effective_ttl = ttl if ttl is not None else settings.CACHE_TTL_SECONDS
        if effective_ttl is None or effective_ttl <= 0:
            expires_at: float | None = None
        else:
            expires_at = time.time() + float(effective_ttl)
        self._store[key] = (value, expires_at)

    def delete_cache(self, key: str) -> None:
        self._store.pop(key, None)

    def build_cache_key(self, prefix: str, payload: dict) -> str:
        """prefix + payload 의 결정적 해시로 캐시 키를 만든다.

        동일 payload → 동일 키 (sort_keys 로 dict 순서 영향 제거).
        """
        normalized = json.dumps(
            payload or {},
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        )
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
        return f"{prefix}:{digest}"

    # ------------------------------------------------------------------
    # rate limit (mock)
    # ------------------------------------------------------------------
    def check_rate_limit(self, user_id: str | None, client_ip: str) -> bool:
        # mock 단계: 항상 허용. 실제 슬라이딩 윈도우 카운팅은 Redis 도입 후 구현.
        return True

    def get_remaining_requests(self, key: str) -> int:
        # mock 단계: 실제 사용량 추적 미구현 → 분당 한도를 그대로 반환.
        return settings.RATE_LIMIT_PER_MINUTE

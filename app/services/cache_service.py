"""Cache service with graceful Redis fallback.

원칙:
- REDIS_URL 미설정/연결 실패/직렬화 실패 시에도 호출자는 예외를 받지 않는다.
- in-memory fallback은 테스트와 로컬 개발을 위한 보조 경로다.
- 기존 get_cache/set_cache/build_cache_key API는 하위 호환을 위해 유지한다.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any

from app.core.config import settings

__all__ = ["CacheService"]

logger = logging.getLogger(__name__)


class CacheService:
    """Redis 우선 + in-memory fallback 캐시 서비스."""

    _GLOBAL_STORE: dict[str, tuple[Any, float | None]] = {}

    def __init__(self) -> None:
        self._store = CacheService._GLOBAL_STORE
        self._redis = None
        self._redis_ready = False
        self._init_redis_client()

    # ------------------------------------------------------------------
    # redis
    # ------------------------------------------------------------------
    def _init_redis_client(self) -> None:
        if not settings.REDIS_URL:
            return
        try:
            import redis

            self._redis = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
            self._redis.ping()
            self._redis_ready = True
            logger.info("cache redis connected")
        except Exception as exc:  # pragma: no cover - depends on runtime infra
            self._redis = None
            self._redis_ready = False
            logger.warning("cache redis unavailable errorType=%s", type(exc).__name__)

    def is_available(self) -> bool:
        return bool(self._redis_ready and self._redis is not None)

    # ------------------------------------------------------------------
    # generic key helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_payload(payload: dict | list | Any) -> str:
        return json.dumps(
            payload or {},
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        )

    @staticmethod
    def _short_hash(value: str, length: int = 16) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]

    def build_cache_key(self, prefix: str, payload: dict) -> str:
        normalized = self._normalize_payload(payload)
        digest = self._short_hash(normalized, 16)
        return f"{prefix}:{digest}"

    def build_hashed_key(self, prefix: str, payload: dict | list | Any) -> str:
        normalized = self._normalize_payload(payload)
        digest = self._short_hash(normalized, 32)
        return f"{prefix}:{digest}"

    # ------------------------------------------------------------------
    # in-memory fallback
    # ------------------------------------------------------------------
    def _mem_get(self, key: str) -> Any | None:
        item = self._store.get(key)
        if item is None:
            return None
        value, expires_at = item
        if expires_at is not None and expires_at < time.time():
            self._store.pop(key, None)
            return None
        return value

    def _mem_set(self, key: str, value: Any, ttl_seconds: int | None) -> None:
        if ttl_seconds is None or ttl_seconds <= 0:
            expires_at: float | None = None
        else:
            expires_at = time.time() + float(ttl_seconds)
        self._store[key] = (value, expires_at)

    # ------------------------------------------------------------------
    # json interface (new)
    # ------------------------------------------------------------------
    def get_json(self, key: str) -> dict | list | None:
        if self.is_available():
            try:
                raw = self._redis.get(key)
                if not raw:
                    return None
                loaded = json.loads(raw)
                if isinstance(loaded, (dict, list)):
                    return loaded
                return None
            except Exception as exc:  # pragma: no cover - infra-dependent
                logger.warning("cache redis get_json failed errorType=%s", type(exc).__name__)
                return None

        mem = self._mem_get(key)
        if isinstance(mem, (dict, list)):
            return mem
        return None

    def set_json(self, key: str, value: Any, ttl_seconds: int) -> bool:
        if not isinstance(value, (dict, list)):
            return False

        if self.is_available():
            try:
                raw = json.dumps(value, ensure_ascii=False, default=str)
                if ttl_seconds > 0:
                    self._redis.setex(key, ttl_seconds, raw)
                else:
                    self._redis.set(key, raw)
                return True
            except Exception as exc:  # pragma: no cover - infra-dependent
                logger.warning("cache redis set_json failed errorType=%s", type(exc).__name__)
                return False

        self._mem_set(key, value, ttl_seconds)
        return True

    # ------------------------------------------------------------------
    # legacy cache interface (compatible)
    # ------------------------------------------------------------------
    def get_cache(self, key: str) -> Any | None:
        return self._mem_get(key)

    def set_cache(self, key: str, value: Any, ttl: int | None = None) -> None:
        effective_ttl = ttl if ttl is not None else settings.CACHE_TTL_SECONDS
        self._mem_set(key, value, effective_ttl)

    def delete_cache(self, key: str) -> None:
        self._store.pop(key, None)

    # ------------------------------------------------------------------
    # rate limit (mock)
    # ------------------------------------------------------------------
    def check_rate_limit(self, user_id: str | None, client_ip: str) -> bool:
        return True

    def get_remaining_requests(self, key: str) -> int:
        return settings.RATE_LIMIT_PER_MINUTE

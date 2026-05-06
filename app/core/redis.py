"""Redis 연결 구조 (mock 단계).

이 단계에서는 redis 패키지를 사용하지 않는다.
- REDIS_URL 미설정 → None 반환.
- REDIS_URL 설정 → 추후 단계에서 실제 redis client 를 반환하도록 확장.
  현재는 redis 패키지 미설치이므로 None 을 반환해 서버가 안전하게 기동되도록 한다.

호출자(service) 는 항상 반환값이 None 일 수 있음을 가정하고
캐시 미사용 분기를 함께 구현해야 한다.
"""

from typing import Any

from app.core.config import settings

__all__ = ["get_redis_client"]


def get_redis_client() -> Any | None:
    if not settings.REDIS_URL:
        return None

    # TODO: 실제 redis-py 패키지 추가 후 아래 코드 활성화.
    # import redis
    # return redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    return None

"""환경변수 기반 설정.

이 단계에서는 설정 구조만 정의한다.
실제 Redis / Qdrant / vLLM 연결은 추후 단계에서 추가한다.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    APP_ENV: str = "local"
    API_PREFIX: str = "/ai"

    REDIS_URL: str | None = None
    QDRANT_URL: str | None = None
    VLLM_BASE_URL: str | None = None

    LLM_PROVIDER: str = "vllm"
    LLM_MODEL_NAME: str = "Qwen2.5-Coder-7B-Instruct"
    VLLM_MODEL: str | None = None
    VLLM_MODEL_NAME: str = "Qwen2.5-Coder-7B-Instruct"
    LLM_TEMPERATURE: float = 0.3
    LLM_MAX_TOKENS: int = 4096
    LLM_TIMEOUT_SECONDS: int = 60

    CACHE_TTL_SECONDS: int = 3600
    RATE_LIMIT_PER_MINUTE: int = 30


settings = Settings()

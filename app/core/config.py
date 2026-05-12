"""환경변수 기반 설정."""

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

    # Qdrant (Compose 서비스명 기본; 로컬 단독은 host.docker.internal 등으로 덮어쓰기)
    QDRANT_URL: str = "http://qdrant:6333"
    QDRANT_COLLECTION: str = "cobip_knowledge"

    # Embedding (Retriever 연동 전 단계)
    EMBEDDING_MODEL: str = "BAAI/bge-m3"

    LLM_PROVIDER: str = "ollama"
    OLLAMA_BASE_URL: str = "http://host.docker.internal:11434/v1"
    OLLAMA_MODEL: str = "qwen2.5-coder:1.5b"
    LLM_TEMPERATURE: float = 0.3
    LLM_MAX_TOKENS: int = 4096
    LLM_TIMEOUT_SECONDS: int = 60

    CACHE_TTL_SECONDS: int = 3600
    RATE_LIMIT_PER_MINUTE: int = 30

    # RAG: Retriever 연동 전 토글·파라미터
    RAG_ENABLED: bool = False
    RAG_TOP_K: int = 3


settings = Settings()

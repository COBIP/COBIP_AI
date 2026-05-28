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
    FEATURE_TEMPLATE_LLM_TIMEOUT_SECONDS: int = 120

    CACHE_TTL_SECONDS: int = 3600
    RATE_LIMIT_PER_MINUTE: int = 30

    # RAG: Retriever 연동 전 토글·파라미터
    RAG_ENABLED: bool = False
    RAG_TOP_K: int = 3

    # Agentic RAG 15차: 기능템플릿 전용 RAG 검색·프롬프트 방어 파라미터
    FEATURE_TEMPLATE_RAG_TOP_K: int = 3
    FEATURE_TEMPLATE_RAG_CONTENT_MAX_CHARS: int = 1000

    # Agentic RAG 16차: warm-up 및 Redis 캐시 제어
    EMBEDDING_WARMUP_ENABLED: bool = False
    EMBEDDING_WARMUP_TEXT: str = "Spring Boot 로그인 기능템플릿 RAG warm up"
    RAG_RETRIEVAL_CACHE_ENABLED: bool = False
    RAG_RETRIEVAL_CACHE_TTL_SECONDS: int = 3600
    FEATURE_TEMPLATE_CACHE_ENABLED: bool = False
    FEATURE_TEMPLATE_CACHE_TTL_SECONDS: int = 3600

    # Agent /ai/chat: 룰 기본, 선택적 LLM intent 보조
    AGENT_LLM_INTENT_ENABLED: bool = False
    AGENT_LLM_INTENT_REFINE_GENERAL: bool = False


settings = Settings()

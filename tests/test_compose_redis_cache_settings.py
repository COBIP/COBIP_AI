"""20차: 운영 compose Redis cache / skeleton env 정적 검증 (PyYAML 불필요)."""

from pathlib import Path

import pytest

from app.core.config import Settings

_REPO_ROOT = Path(__file__).resolve().parents[1]
_RAG_COMPOSE = _REPO_ROOT / "docker-compose.rag.yml"
_DEPLOY_COMPOSE = _REPO_ROOT / "docker-compose.deploy.yml"
_ENV_EXAMPLE = _REPO_ROOT / ".env.example"

_REQUIRED_RAG_COMPOSE_SNIPPETS = (
    "REDIS_URL: redis://redis:6379/0",
    "RAG_RETRIEVAL_CACHE_ENABLED: \"true\"",
    "RAG_RETRIEVAL_CACHE_TTL_SECONDS: \"3600\"",
    "FEATURE_TEMPLATE_CACHE_ENABLED: \"true\"",
    "FEATURE_TEMPLATE_CACHE_TTL_SECONDS: \"3600\"",
    "FEATURE_TEMPLATE_ULTRA_FAST_SKELETON_ENABLED: \"true\"",
    "FEATURE_TEMPLATE_FAST_SKELETON_ENABLED: \"true\"",
    "FEATURE_TEMPLATE_SKELETON_MAX_TOKENS: \"800\"",
    "FEATURE_TEMPLATE_SKELETON_RAG_TOP_K: \"2\"",
    "FEATURE_TEMPLATE_SKELETON_RAG_CONTENT_MAX_CHARS: \"300\"",
    "RAG_ENABLED: \"true\"",
)


def test_docker_compose_rag_file_exists() -> None:
    assert _RAG_COMPOSE.is_file()


@pytest.mark.parametrize("snippet", _REQUIRED_RAG_COMPOSE_SNIPPETS)
def test_docker_compose_rag_contains_cache_and_skeleton_env(snippet: str) -> None:
    text = _RAG_COMPOSE.read_text(encoding="utf-8")
    assert snippet in text


def test_docker_compose_deploy_has_redis_service() -> None:
    text = _DEPLOY_COMPOSE.read_text(encoding="utf-8")
    assert "redis:" in text
    assert "image: redis:7-alpine" in text


def test_env_example_documents_skeleton_and_cache_defaults() -> None:
    text = _ENV_EXAMPLE.read_text(encoding="utf-8")
    assert "FEATURE_TEMPLATE_SKELETON_MAX_TOKENS=800" in text
    assert "FEATURE_TEMPLATE_SKELETON_RAG_CONTENT_MAX_CHARS=300" in text
    assert "RAG_RETRIEVAL_CACHE_ENABLED=false" in text
    assert "docker-compose.rag.yml" in text


def test_config_defaults_match_compose_skeleton_tuning() -> None:
    s = Settings(_env_file=None)
    assert s.FEATURE_TEMPLATE_SKELETON_MAX_TOKENS == 800
    assert s.FEATURE_TEMPLATE_SKELETON_RAG_CONTENT_MAX_CHARS == 300
    assert s.FEATURE_TEMPLATE_SKELETON_RAG_TOP_K == 2
    assert s.FEATURE_TEMPLATE_ULTRA_FAST_SKELETON_ENABLED is True
    assert s.FEATURE_TEMPLATE_FAST_SKELETON_ENABLED is True

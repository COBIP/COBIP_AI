"""Agentic RAG 16차: timing/cache/warm-up 검증."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, settings
from app.main import app
from app.schemas.feature_template import (
    FeatureTemplateData,
    FeatureTemplateGenerateRequest,
    FeatureTemplateGenerateResult,
    FlowSchema,
    OverviewSchema,
)
from app.schemas.rag import RetrievedReference
from app.services.agent_orchestrator import AgentOrchestrator
from app.services.cache_service import CacheService
from app.services.feature_template_generator import FeatureTemplateGenerator
from app.services.rag_service import (
    build_feature_template_rag_cache_key,
    retrieve_feature_template_rag_references,
)


def _minimal_template(feature_name: str = "로그인") -> FeatureTemplateData:
    return FeatureTemplateData(
        overview=OverviewSchema(
            featureName=feature_name,
            purpose="p",
            useCases=[],
            resultDescription="r",
            techStack=[],
            learningGoals=[],
        ),
        requirements=[],
        flow=FlowSchema(steps=[], layers=[]),
        apiSpec=[],
        codeFiles=[],
        basicQuestions=[],
        missions=[],
        interviewQuestions=[],
        nextRecommendations=[],
    )


def _clear_cache() -> None:
    CacheService._GLOBAL_STORE.clear()


class _FakeRetriever:
    def __init__(self, hits: list[RetrievedReference] | None = None) -> None:
        self.hits = hits or []
        self.calls = 0

    def retrieve(self, query: str, top_k: int | None = None) -> list[RetrievedReference]:
        self.calls += 1
        return list(self.hits)


def test_settings_defaults_for_rag16() -> None:
    s = Settings(_env_file=None)
    assert s.EMBEDDING_WARMUP_ENABLED is False
    assert s.EMBEDDING_WARMUP_TEXT
    assert s.RAG_RETRIEVAL_CACHE_ENABLED is False
    assert s.RAG_RETRIEVAL_CACHE_TTL_SECONDS == 3600
    assert s.FEATURE_TEMPLATE_CACHE_ENABLED is False
    assert s.FEATURE_TEMPLATE_CACHE_TTL_SECONDS == 3600


def test_cache_service_graceful_fallback_without_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_cache()
    monkeypatch.setattr(settings, "REDIS_URL", "redis://127.0.0.1:65535/0")
    cache = CacheService()
    assert cache.is_available() is False
    assert cache.get_json("missing") is None
    ok = cache.set_json("k", {"a": 1}, 10)
    assert ok is True
    assert cache.get_json("k") == {"a": 1}


def test_rag_retrieval_cache_hit_skips_retriever(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_cache()
    monkeypatch.setattr(settings, "RAG_RETRIEVAL_CACHE_ENABLED", True)
    cache = CacheService()
    key = build_feature_template_rag_cache_key(query="로그인", top_k=3)
    cache.set_json(
        key,
        {
            "status": "success",
            "references": [{"title": "cached", "source": "qdrant", "content": "cached body"}],
            "retrieved_count": 1,
        },
        60,
    )
    fake = _FakeRetriever()
    out = retrieve_feature_template_rag_references(
        query="로그인",
        top_k=3,
        enabled=True,
        retriever=fake,
        cache_service=cache,
    )
    assert out.cache_hit is True
    assert out.cache_key == key
    assert fake.calls == 0
    assert out.status == "success"
    assert len(out.references) == 1


def test_rag_retrieval_cache_miss_stores_result(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_cache()
    monkeypatch.setattr(settings, "RAG_RETRIEVAL_CACHE_ENABLED", True)
    cache = CacheService()
    fake = _FakeRetriever(
        [
            RetrievedReference(
                id="1",
                title="doc",
                content="body",
                score=0.9,
                sourceType="document",
                metadata={},
            )
        ]
    )
    out = retrieve_feature_template_rag_references(
        query="로그인",
        top_k=3,
        enabled=True,
        retriever=fake,
        cache_service=cache,
    )
    assert out.cache_hit is False
    assert fake.calls == 1
    assert out.cache_key is not None
    cached = cache.get_json(out.cache_key)
    assert isinstance(cached, dict)
    assert cached.get("status") == "success"


def test_feature_template_cache_hit_skips_generator(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_cache()
    monkeypatch.setattr(settings, "FEATURE_TEMPLATE_CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "RAG_ENABLED", False)

    req = FeatureTemplateGenerateRequest(
        language="java",
        framework="spring-boot",
        featureName="로그인",
        level="beginner",
        includeCode=False,
        includeMissions=False,
        includeInterview=False,
    )
    key = AgentOrchestrator._build_feature_template_cache_key(
        feature_request=req,
        rag_references=[],
    )
    CacheService().set_json(
        key,
        {
            "template": _minimal_template("로그인").model_dump(),
            "source": "ollama",
            "appliedReferences": [],
            "generationMode": "skeleton",
            "skeletonFirst": True,
            "deferredSections": ["codeFiles", "missions", "interviewQuestions"],
        },
        60,
    )

    def should_not_run(self, request):
        raise AssertionError("generate should be skipped by cache hit")

    monkeypatch.setattr(FeatureTemplateGenerator, "generate", should_not_run)

    client = TestClient(app)
    resp = client.post(
        "/ai/agentic-rag/run",
        json={
            "message": "로그인 기능템플릿 생성",
            "featureTemplate": req.model_dump(),
        },
    )
    assert resp.status_code == 200
    tr = resp.json()["data"]["trace"]
    assert tr["featureTemplateCacheHit"] is True
    assert tr["featureTemplateCacheKey"] == key
    assert tr["featureTemplateGenerationMs"] == 0


def test_feature_template_cache_miss_stores_non_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_cache()
    monkeypatch.setattr(settings, "FEATURE_TEMPLATE_CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "RAG_ENABLED", False)

    def fake_generate(self, request):
        return FeatureTemplateGenerateResult(
            template=_minimal_template(request.featureName),
            source="ollama",
            appliedReferences=[],
            generationMode="skeleton",
            skeletonFirst=True,
            deferredSections=["codeFiles", "missions", "interviewQuestions"],
        )

    monkeypatch.setattr(FeatureTemplateGenerator, "generate", fake_generate)

    client = TestClient(app)
    payload = {
        "message": "로그인 기능템플릿 생성",
        "featureTemplate": {
            "language": "java",
            "framework": "spring-boot",
            "featureName": "로그인",
            "level": "beginner",
            "includeCode": False,
            "includeMissions": False,
            "includeInterview": False,
        },
    }
    resp = client.post("/ai/agentic-rag/run", json=payload)
    assert resp.status_code == 200
    tr = resp.json()["data"]["trace"]
    key = tr["featureTemplateCacheKey"]
    assert tr["featureTemplateCacheHit"] is False
    assert key
    cached = CacheService().get_json(key)
    assert isinstance(cached, dict)
    assert cached.get("source") == "ollama"


def test_fallback_result_not_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_cache()
    monkeypatch.setattr(settings, "FEATURE_TEMPLATE_CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "RAG_ENABLED", False)

    call_count = {"n": 0}

    def fake_generate(self, request):
        call_count["n"] += 1
        return FeatureTemplateGenerateResult(
            template=_minimal_template(request.featureName),
            source="fallback",
            appliedReferences=[],
            generationMode="fallback",
            skeletonFirst=True,
            deferredSections=["codeFiles", "missions", "interviewQuestions"],
        )

    monkeypatch.setattr(FeatureTemplateGenerator, "generate", fake_generate)
    client = TestClient(app)
    payload = {
        "message": "로그인 기능템플릿 생성",
        "featureTemplate": {
            "language": "java",
            "featureName": "로그인",
            "level": "beginner",
            "includeCode": False,
            "includeMissions": False,
            "includeInterview": False,
        },
    }
    _ = client.post("/ai/agentic-rag/run", json=payload)
    _ = client.post("/ai/agentic-rag/run", json=payload)
    assert call_count["n"] == 2


def test_trace_contains_rag16_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_cache()
    monkeypatch.setattr(settings, "RAG_ENABLED", False)
    monkeypatch.setattr(settings, "FEATURE_TEMPLATE_CACHE_ENABLED", True)

    def fake_generate(self, request):
        return FeatureTemplateGenerateResult(
            template=_minimal_template(request.featureName),
            source="ollama",
            appliedReferences=[],
            generationMode="skeleton",
            skeletonFirst=True,
            deferredSections=["codeFiles", "missions", "interviewQuestions"],
        )

    monkeypatch.setattr(FeatureTemplateGenerator, "generate", fake_generate)
    client = TestClient(app)
    resp = client.post(
        "/ai/agentic-rag/run",
        json={
            "message": "로그인 기능템플릿 생성",
            "featureTemplate": {
                "language": "java",
                "featureName": "로그인",
                "level": "beginner",
                "includeCode": False,
                "includeMissions": False,
                "includeInterview": False,
            },
        },
    )
    tr = resp.json()["data"]["trace"]
    for key in (
        "embeddingMs",
        "qdrantSearchMs",
        "referenceBuildMs",
        "ragCacheHit",
        "ragCacheKey",
        "featureTemplateCacheHit",
        "featureTemplateCacheKey",
    ):
        assert key in tr


def test_embedding_warmup_enabled_attempts_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"n": 0}

    def fake_warmup(self, text: str | None = None) -> bool:
        calls["n"] += 1
        return True

    monkeypatch.setattr(settings, "EMBEDDING_WARMUP_ENABLED", True)
    monkeypatch.setattr(settings, "RAG_ENABLED", True)
    monkeypatch.setattr("app.services.embedding_service.EmbeddingService.warm_up", fake_warmup)

    with TestClient(app):
        pass
    assert calls["n"] >= 1


def test_embedding_warmup_disabled_skips_call(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def fake_warmup(self, text: str | None = None) -> bool:
        calls["n"] += 1
        return True

    monkeypatch.setattr(settings, "EMBEDDING_WARMUP_ENABLED", False)
    monkeypatch.setattr(settings, "RAG_ENABLED", True)
    monkeypatch.setattr("app.services.embedding_service.EmbeddingService.warm_up", fake_warmup)

    with TestClient(app):
        pass
    assert calls["n"] == 0

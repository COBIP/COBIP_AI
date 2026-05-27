"""Agentic RAG 15차: RAG 관측성·시연 안정성 테스트."""

from __future__ import annotations

import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.schemas.feature_template import (
    FeatureTemplateData,
    FeatureTemplateGenerateResult,
    FlowSchema,
    OverviewSchema,
)
from app.schemas.rag import RetrievedReference
from app.services.feature_template_generator import FeatureTemplateGenerator
from app.services.prompt_builder import build_applied_references_payload
from app.services.rag_service import (
    _hit_to_reference,
    effective_feature_template_rag_top_k,
    feature_template_rag_content_max_chars,
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


class _FakeRetrieverRecording:
    def __init__(self, hits: list[RetrievedReference] | None = None, *, delay_ms: int = 0) -> None:
        self._hits = hits or []
        self.delay_ms = delay_ms
        self.calls: list[tuple[str, int | None]] = []

    def retrieve(self, query: str, top_k: int | None = None) -> list[RetrievedReference]:
        self.calls.append((query, top_k))
        if self.delay_ms:
            time.sleep(self.delay_ms / 1000.0)
        return list(self._hits)


def _patch_retrieval(monkeypatch: pytest.MonkeyPatch, retriever: Any) -> None:
    from app.services import rag_service

    original = rag_service.retrieve_feature_template_rag_references

    def _patched(**kwargs: Any):
        kwargs.pop("enabled", None)
        kwargs.pop("retriever", None)
        return original(enabled=True, retriever=retriever, **kwargs)

    monkeypatch.setattr(rag_service, "retrieve_feature_template_rag_references", _patched)


def test_effective_feature_template_rag_top_k_uses_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "FEATURE_TEMPLATE_RAG_TOP_K", 2)
    assert effective_feature_template_rag_top_k() == 2
    assert effective_feature_template_rag_top_k(top_k=5) == 5
    monkeypatch.setattr(settings, "FEATURE_TEMPLATE_RAG_TOP_K", 99)
    assert effective_feature_template_rag_top_k() == 10


def test_content_truncation_respects_max_chars_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "FEATURE_TEMPLATE_RAG_CONTENT_MAX_CHARS", 80)
    assert feature_template_rag_content_max_chars() == 80
    long_body = "가" * 200
    ref = _hit_to_reference(
        {
            "content": long_body,
            "title": "긴 문서",
            "score": 0.8,
            "metadata": {"docType": "guide", "section": "apiSpec", "path": "seed/x"},
        }
    )
    assert ref is not None
    assert len(ref["content"]) <= 80
    assert ref["metadata"]["contentTruncated"] is True
    assert ref["metadata"]["originalContentLength"] == 200


def test_retrieve_passes_feature_template_top_k_to_retriever(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "FEATURE_TEMPLATE_RAG_TOP_K", 2)
    retriever = _FakeRetrieverRecording(
        [
            RetrievedReference(
                id="1",
                title="A",
                content="본문 A",
                score=0.9,
                sourceType="document",
                metadata={},
            )
        ]
    )
    out = retrieve_feature_template_rag_references(
        query="Spring Boot 로그인",
        enabled=True,
        retriever=retriever,
    )
    assert out.status == "success"
    assert retriever.calls == [("Spring Boot 로그인", 2)]


def test_applied_references_include_section_doc_type_path(
) -> None:
    selected = [
        {
            "title": "로그인 API",
            "source": "qdrant",
            "score": 0.91,
            "content": "POST /api/auth/login 으로 JWT를 발급한다.",
            "metadata": {
                "docType": "feature_template_reference",
                "section": "apiSpec",
                "path": "seed/spring-boot-login/api-spec",
            },
        }
    ]
    applied = build_applied_references_payload(selected)
    assert len(applied) == 1
    item = applied[0]
    assert item["title"] == "로그인 API"
    assert item["source"] == "qdrant"
    assert item["score"] == 0.91
    assert item["section"] == "apiSpec"
    assert item["docType"] == "feature_template_reference"
    assert item["path"] == "seed/spring-boot-login/api-spec"
    assert item["usedInPrompt"] is True
    assert len(item["contentPreview"]) <= 200


def test_trace_includes_split_timing_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    retriever = _FakeRetrieverRecording(
        [
            RetrievedReference(
                id="1",
                title="JWT 가이드",
                content="JWT accessToken은 Bearer 헤더로 전달된다.",
                score=0.85,
                sourceType="document",
                metadata={"section": "apiSpec", "docType": "guide", "path": "seed/jwt"},
            )
        ],
        delay_ms=30,
    )
    _patch_retrieval(monkeypatch, retriever)

    def fake_generate(self, request):
        time.sleep(0.05)
        return FeatureTemplateGenerateResult(
            template=_minimal_template(request.featureName),
            source="ollama",
            appliedReferences=[
                {
                    "title": "JWT 가이드",
                    "source": "qdrant",
                    "score": 0.85,
                    "section": "apiSpec",
                    "docType": "guide",
                    "path": "seed/jwt",
                    "contentPreview": "JWT accessToken",
                    "usedInPrompt": True,
                }
            ],
            generationMode="skeleton",
            skeletonFirst=True,
            deferredSections=["codeFiles", "missions", "interviewQuestions"],
        )

    monkeypatch.setattr(FeatureTemplateGenerator, "generate", fake_generate)

    client = TestClient(app)
    resp = client.post(
        "/ai/agentic-rag/run",
        json={
            "message": "Spring Boot 로그인 기능템플릿 만들어줘",
            "featureTemplate": {
                "language": "Java",
                "framework": "Spring Boot",
                "featureName": "로그인",
                "level": "beginner",
                "includeCode": False,
                "includeMissions": False,
                "includeInterview": False,
            },
        },
    )
    assert resp.status_code == 200
    tr = resp.json()["data"]["trace"]
    assert tr["ragRetrievalMs"] is not None
    assert tr["featureTemplateGenerationMs"] is not None
    assert tr["totalLatencyMs"] is not None
    assert tr["latencyMs"] == tr["totalLatencyMs"]
    assert tr["ragRetrievalMs"] >= 0
    assert tr["featureTemplateGenerationMs"] >= 40
    assert tr["totalLatencyMs"] >= tr["featureTemplateGenerationMs"]
    assert tr["ragRetrievalStatus"] == "success"
    assert tr["ragRetrievedCount"] == 1
    assert tr["ragInjectedCount"] == 1
    assert tr["appliedReferenceCount"] == 1
    assert tr["generationMode"] == "skeleton"
    assert tr["skeletonFirst"] is True
    assert tr["deferredSections"] == ["codeFiles", "missions", "interviewQuestions"]


def test_rag_failure_still_completes_with_timing(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FailingRetriever:
        def retrieve(self, query: str, top_k: int | None = None) -> list[RetrievedReference]:
            raise RuntimeError("qdrant down")

    _patch_retrieval(monkeypatch, _FailingRetriever())

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
            "message": "로그인 기능템플릿",
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
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    tr = body["data"]["trace"]
    assert tr["ragRetrievalStatus"] == "failed"
    assert tr["ragRetrievalMs"] is not None
    assert tr["featureTemplateGenerationMs"] is not None
    assert tr["totalLatencyMs"] is not None
    assert body["data"]["result"]["generationMode"] == "skeleton"


def test_manual_and_qdrant_merge_still_works(monkeypatch: pytest.MonkeyPatch) -> None:
    retriever = _FakeRetrieverRecording(
        [
            RetrievedReference(
                id="auto",
                title="JWT 가이드",
                content="JWT accessToken을 발급한다.",
                score=0.7,
                sourceType="document",
                metadata={"section": "apiSpec", "docType": "guide", "path": "seed/jwt"},
            )
        ]
    )
    _patch_retrieval(monkeypatch, retriever)

    def fake_generate(self, request):
        refs = (request.referenceContext or {}).get("ragReferences") or []
        return FeatureTemplateGenerateResult(
            template=_minimal_template(request.featureName),
            source="ollama",
            appliedReferences=[
                {"title": r.get("title"), "source": r.get("source"), "usedInPrompt": True}
                for r in refs
            ],
        )

    monkeypatch.setattr(FeatureTemplateGenerator, "generate", fake_generate)

    client = TestClient(app)
    resp = client.post(
        "/ai/agentic-rag/run",
        json={
            "message": "로그인 기능템플릿",
            "featureTemplate": {
                "language": "java",
                "featureName": "로그인",
                "level": "beginner",
                "referenceContext": {
                    "ragReferences": [
                        {
                            "title": "수동 요구사항",
                            "source": "manual",
                            "content": "로그인은 이메일과 비밀번호를 입력받는다.",
                        }
                    ]
                },
            },
        },
    )
    tr = resp.json()["data"]["trace"]
    assert tr["ragSource"] == "manual+qdrant"
    assert tr["ragInjectedCount"] == 2
    assert tr["ragRetrievalMs"] is not None

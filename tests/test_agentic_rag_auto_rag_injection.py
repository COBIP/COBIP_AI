"""Agentic RAG 13차: feature_template_generate 자동 Qdrant retrieval 주입."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.feature_template import (
    FeatureTemplateData,
    FeatureTemplateGenerateResult,
    FlowSchema,
    OverviewSchema,
)
from app.schemas.rag import RetrievedReference
from app.services.feature_template_generator import FeatureTemplateGenerator


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


class _FakeRetrieverOk:
    def __init__(self, hits: list[RetrievedReference]) -> None:
        self._hits = hits
        self.calls: list[tuple[str, int | None]] = []

    def retrieve(self, query: str, top_k: int | None = None) -> list[RetrievedReference]:
        self.calls.append((query, top_k))
        return list(self._hits)


class _FakeRetrieverEmpty:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int | None]] = []

    def retrieve(self, query: str, top_k: int | None = None) -> list[RetrievedReference]:
        self.calls.append((query, top_k))
        return []


class _FakeRetrieverFailing:
    def retrieve(self, query: str, top_k: int | None = None) -> list[RetrievedReference]:
        raise RuntimeError("qdrant unreachable")


def _capturing_generator() -> dict[str, Any]:
    captured: dict[str, Any] = {}

    def fake_generate(self, request):
        captured["referenceContext"] = (
            dict(request.referenceContext) if request.referenceContext else None
        )
        return FeatureTemplateGenerateResult(
            template=_minimal_template(request.featureName),
            source="ollama",
            appliedReferences=[
                {
                    "title": r.get("title"),
                    "source": r.get("source"),
                    "contentPreview": (r.get("content") or "")[:120],
                    "usedInPrompt": True,
                }
                for r in (
                    (request.referenceContext or {}).get("ragReferences") or []
                )
            ],
        )

    captured["fake_generate"] = fake_generate
    return captured


def _patch_retrieval(monkeypatch: pytest.MonkeyPatch, retriever, *, enabled: bool = True):
    import app.services.agent_orchestrator as ao
    from app.services import rag_service

    real_fn = rag_service.retrieve_feature_template_rag_references

    def _wrapped(*, query: str, top_k=None, enabled=None, retriever_=None):  # type: ignore[no-redef]
        return real_fn(query=query, top_k=top_k, enabled=True, retriever=retriever)

    # 단순화를 위해 enabled를 강제로 True로 두고 retriever를 fake로 주입한다.
    def _patched(**kwargs: Any):
        kwargs.pop("enabled", None)
        kwargs.pop("retriever", None)
        return real_fn(enabled=enabled, retriever=retriever, **kwargs)

    monkeypatch.setattr(
        ao,
        "retrieve_feature_template_rag_references",
        None,
        raising=False,
    )
    # orchestrator는 함수를 lazy import하므로 모듈 수준에서 패치
    monkeypatch.setattr(
        rag_service,
        "retrieve_feature_template_rag_references",
        _patched,
    )


def _post_agentic(client: TestClient, **flags: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
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
    }
    ft = payload["featureTemplate"]
    ft.update(flags.pop("featureTemplate", {}))
    payload.update(flags)
    resp = client.post("/ai/agentic-rag/run", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_auto_qdrant_injection_when_no_manual_reference(monkeypatch: pytest.MonkeyPatch) -> None:
    cap = _capturing_generator()
    monkeypatch.setattr(FeatureTemplateGenerator, "generate", cap["fake_generate"])
    retriever = _FakeRetrieverOk(
        [
            RetrievedReference(
                id="doc-1",
                title="Spring Security 로그인 가이드",
                content="POST /api/auth/login 으로 사용자 인증을 수행하고 BCrypt로 비밀번호를 검증한다.",
                score=0.91,
                sourceType="document",
                metadata={"docType": "guide", "section": "auth"},
            )
        ]
    )
    _patch_retrieval(monkeypatch, retriever)

    client = TestClient(app)
    body = _post_agentic(client)

    tr = body["data"]["trace"]
    result = body["data"]["result"]
    assert tr["ragRetrievalAttempted"] is True
    assert tr["ragRetrievalStatus"] == "success"
    assert tr["ragRetrievedCount"] == 1
    assert tr["ragInjectedCount"] == 1
    assert tr["ragSource"] == "qdrant"
    assert tr["ragQuery"]
    assert "Spring Boot" in tr["ragQuery"]
    assert "로그인" in tr["ragQuery"]
    assert tr["ragFailureReason"] is None
    assert tr["ragRetrievalSkippedReason"] is None
    assert tr["ragContextAvailable"] is True
    assert tr["ragReferenceCount"] == 1

    ctx = cap["referenceContext"]
    assert ctx is not None
    auto_refs = ctx.get("ragReferences") or []
    assert len(auto_refs) == 1
    assert auto_refs[0]["source"] == "qdrant"
    assert "POST /api/auth/login" in auto_refs[0]["content"]
    applied = result["appliedReferences"]
    assert len(applied) == 1
    assert applied[0]["usedInPrompt"] is True


def test_manual_reference_is_preserved_and_merged_with_auto(monkeypatch: pytest.MonkeyPatch) -> None:
    cap = _capturing_generator()
    monkeypatch.setattr(FeatureTemplateGenerator, "generate", cap["fake_generate"])
    retriever = _FakeRetrieverOk(
        [
            RetrievedReference(
                id="doc-2",
                title="JWT 가이드",
                content="JWT accessToken은 Authorization Bearer 헤더로 전달된다.",
                score=0.82,
                sourceType="document",
                metadata={},
            )
        ]
    )
    _patch_retrieval(monkeypatch, retriever)

    client = TestClient(app)
    body = _post_agentic(
        TestClient(app),
        featureTemplate={
            "referenceContext": {
                "ragReferences": [
                    {
                        "title": "로그인 요구사항",
                        "source": "manual",
                        "content": "로그인은 이메일과 비밀번호를 입력받고 JWT를 발급한다.",
                    }
                ]
            }
        },
    )
    tr = body["data"]["trace"]
    assert tr["ragRetrievalStatus"] == "success"
    assert tr["ragRetrievedCount"] == 1
    assert tr["ragInjectedCount"] == 2
    assert tr["ragSource"] == "manual+qdrant"
    assert tr["ragReferenceCount"] == 2
    assert tr["appliedReferenceCount"] == 2

    ctx = cap["referenceContext"]
    refs = ctx["ragReferences"]
    sources = [r.get("source") for r in refs]
    # 수동 reference가 먼저, 자동 reference가 뒤
    assert sources[0] == "manual"
    assert sources[1] == "qdrant"


def test_dedupe_removes_duplicate_between_manual_and_auto(monkeypatch: pytest.MonkeyPatch) -> None:
    cap = _capturing_generator()
    monkeypatch.setattr(FeatureTemplateGenerator, "generate", cap["fake_generate"])
    duplicate_content = "로그인은 이메일과 비밀번호를 입력받고 JWT를 발급한다."
    retriever = _FakeRetrieverOk(
        [
            RetrievedReference(
                id="dup",
                title="로그인 요구사항",
                content=duplicate_content,
                score=0.7,
                sourceType=None,
                metadata={},
            )
        ]
    )
    _patch_retrieval(monkeypatch, retriever)

    body = _post_agentic(
        TestClient(app),
        featureTemplate={
            "referenceContext": {
                "ragReferences": [
                    {
                        "title": "로그인 요구사항",
                        "source": "manual",
                        "content": duplicate_content,
                    }
                ]
            }
        },
    )
    tr = body["data"]["trace"]
    assert tr["ragInjectedCount"] == 1
    refs = cap["referenceContext"]["ragReferences"]
    assert len(refs) == 1
    assert refs[0]["source"] == "manual"


def test_qdrant_failure_keeps_manual_reference_and_marks_trace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cap = _capturing_generator()
    monkeypatch.setattr(FeatureTemplateGenerator, "generate", cap["fake_generate"])
    _patch_retrieval(monkeypatch, _FakeRetrieverFailing())

    body = _post_agentic(
        TestClient(app),
        featureTemplate={
            "referenceContext": {
                "ragReferences": [
                    {
                        "title": "로그인 요구사항",
                        "source": "manual",
                        "content": "로그인은 이메일과 비밀번호를 입력받고 JWT를 발급한다.",
                    }
                ]
            }
        },
    )
    tr = body["data"]["trace"]
    assert tr["ragRetrievalAttempted"] is True
    assert tr["ragRetrievalStatus"] == "failed"
    assert tr["ragFailureReason"] and "retrieve_failed" in tr["ragFailureReason"]
    assert tr["ragRetrievedCount"] == 0
    assert tr["ragInjectedCount"] == 1
    assert tr["ragSource"] == "manual"
    assert tr["ragReferenceCount"] == 1
    refs = cap["referenceContext"]["ragReferences"]
    assert len(refs) == 1
    assert refs[0]["source"] == "manual"


def test_qdrant_empty_result_falls_back_to_manual_only(monkeypatch: pytest.MonkeyPatch) -> None:
    cap = _capturing_generator()
    monkeypatch.setattr(FeatureTemplateGenerator, "generate", cap["fake_generate"])
    _patch_retrieval(monkeypatch, _FakeRetrieverEmpty())

    body = _post_agentic(
        TestClient(app),
        featureTemplate={
            "referenceContext": {
                "ragReferences": [
                    {
                        "title": "로그인 요구사항",
                        "source": "manual",
                        "content": "로그인은 이메일과 비밀번호를 입력받고 JWT를 발급한다.",
                    }
                ]
            }
        },
    )
    tr = body["data"]["trace"]
    assert tr["ragRetrievalAttempted"] is True
    assert tr["ragRetrievalStatus"] == "empty"
    assert tr["ragRetrievedCount"] == 0
    assert tr["ragInjectedCount"] == 1
    assert tr["ragSource"] == "manual"
    assert tr["ragReferenceCount"] == 1


def test_qdrant_empty_with_no_manual_still_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    cap = _capturing_generator()
    monkeypatch.setattr(FeatureTemplateGenerator, "generate", cap["fake_generate"])
    _patch_retrieval(monkeypatch, _FakeRetrieverEmpty())

    body = _post_agentic(TestClient(app))
    tr = body["data"]["trace"]
    assert tr["ragRetrievalAttempted"] is True
    assert tr["ragRetrievalStatus"] == "empty"
    assert tr["ragInjectedCount"] == 0
    assert tr["ragSource"] == "none"
    assert tr["ragContextAvailable"] is False
    assert tr["generationMode"] in {"quality_llm_full", "skeleton", "fallback"}
    assert tr["skeletonFirst"] is False
    assert tr["deferredSections"] == ["codeFiles", "missions", "interviewQuestions"]


def test_rag_disabled_marks_skipped_and_keeps_manual(monkeypatch: pytest.MonkeyPatch) -> None:
    cap = _capturing_generator()
    monkeypatch.setattr(FeatureTemplateGenerator, "generate", cap["fake_generate"])
    # enabled=False 시 retriever는 호출되지 않아야 함
    retriever = _FakeRetrieverOk([])
    _patch_retrieval(monkeypatch, retriever, enabled=False)

    body = _post_agentic(
        TestClient(app),
        featureTemplate={
            "referenceContext": {
                "ragReferences": [
                    {
                        "title": "로그인 요구사항",
                        "source": "manual",
                        "content": "로그인은 이메일과 비밀번호를 입력받고 JWT를 발급한다.",
                    }
                ]
            }
        },
    )
    tr = body["data"]["trace"]
    assert tr["ragRetrievalAttempted"] is False
    assert tr["ragRetrievalStatus"] == "skipped"
    assert tr["ragRetrievalSkippedReason"] == "rag_disabled"
    assert tr["ragSource"] == "manual"
    assert tr["ragInjectedCount"] == 1
    assert retriever.calls == []


def test_retrieval_query_uses_feature_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    cap = _capturing_generator()
    monkeypatch.setattr(FeatureTemplateGenerator, "generate", cap["fake_generate"])
    retriever = _FakeRetrieverOk(
        [
            RetrievedReference(
                id="x",
                title="가이드",
                content="요구사항 문서",
                score=0.5,
                sourceType=None,
                metadata={},
            )
        ]
    )
    _patch_retrieval(monkeypatch, retriever)

    body = _post_agentic(TestClient(app))
    tr = body["data"]["trace"]
    query = tr["ragQuery"]
    assert "Spring Boot" in query
    assert "로그인" in query
    assert "Java" in query
    assert "beginner" in query
    assert "기능템플릿" in query
    assert "요구사항" in query
    assert retriever.calls  # 한 번은 호출됨

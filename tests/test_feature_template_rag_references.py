"""기능템플릿 generate 경로 Qdrant RAG reference 주입 검증."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.core.config import settings
from app.models.enums import DifficultyLevel
from app.schemas.feature_template import FeatureTemplateGenerateRequest
from app.schemas.rag import RetrievedReference
from app.services.feature_template_generator import FeatureTemplateGenerator
from app.services.prompt_builder import build_feature_template_prompt_with_applied_rags
from app.services import rag_service
from scripts.seed_qdrant_feature_template_docs import (
    FEATURE_TEMPLATE_SEED_NAMESPACE,
    build_feature_template_docs_seed_documents,
    build_payload,
    build_point_id,
    describe_documents,
    main as seed_main,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _login_request(**kwargs: object) -> FeatureTemplateGenerateRequest:
    base = dict(
        language="Java",
        framework="Spring Boot",
        featureName="로그인",
        level=DifficultyLevel.BEGINNER,
        includeCode=True,
        includeMissions=True,
        includeInterview=True,
    )
    base.update(kwargs)
    return FeatureTemplateGenerateRequest(**base)


def _full_llm_payload() -> dict:
    return {
        "overview": {
            "featureName": "로그인",
            "purpose": "인증",
            "useCases": [],
            "resultDescription": "JWT",
            "techStack": ["Java"],
            "learningGoals": [],
        },
        "requirements": [
            {
                "requirementId": "R-001",
                "name": "a",
                "description": "b",
                "inputValue": "",
                "processCondition": "",
                "successResult": "",
                "failureResult": "",
                "priority": "HIGH",
                "relatedScreenOrApi": "",
            }
        ] * 3,
        "flow": {"steps": ["1", "2", "3", "4", "5"], "layers": [{"layer": "C", "role": "r"}]},
        "apiSpec": [
            {
                "apiName": "로그인",
                "method": "POST",
                "endpoint": "/api/auth/login",
                "description": "",
                "requestBody": {},
                "responseBody": {},
                "status": 200,
            }
        ],
        "codeFiles": [
            {
                "fileName": "LoginController.java",
                "filePath": "x",
                "role": "c",
                "language": "java",
                "content": "class LoginController {}",
            }
        ],
        "basicQuestions": [
            {
                "questionId": "Q-001",
                "type": "short_answer",
                "question": "q",
                "choices": None,
                "answer": "a",
                "explanation": "e",
                "relatedSection": "flow",
                "difficulty": "beginner",
            }
        ] * 3,
        "missions": [
            {
                "missionId": "M-001",
                "title": "t",
                "description": "미션 목표: x",
                "missionType": "enhancement",
                "requirements": [],
                "successCriteria": [],
                "relatedRequirements": [],
                "difficulty": "beginner",
            },
            {
                "missionId": "M-002",
                "title": "t2",
                "description": "미션 목표: y",
                "missionType": "validation",
                "requirements": [],
                "successCriteria": [],
                "relatedRequirements": [],
                "difficulty": "beginner",
            },
        ],
        "interviewQuestions": [
            {
                "questionId": "IQ-001",
                "question": "q",
                "keyPoints": [],
                "sampleAnswer": "a",
                "relatedSection": "flow",
            }
        ] * 3,
        "nextRecommendations": [
            {"featureName": "a", "reason": "r", "expectedLearning": "e", "priority": 1},
            {"featureName": "b", "reason": "r", "expectedLearning": "e", "priority": 2},
            {"featureName": "c", "reason": "r", "expectedLearning": "e", "priority": 3},
        ],
    }


class _FakeRetrieverOk:
    def __init__(self, hits: list[RetrievedReference]) -> None:
        self._hits = hits
        self.calls: list[tuple[str, int | None]] = []

    def retrieve(self, query: str, top_k: int | None = None) -> list[RetrievedReference]:
        self.calls.append((query, top_k))
        return list(self._hits)


class _FakeRetrieverFailing:
    def retrieve(self, query: str, top_k: int | None = None) -> list[RetrievedReference]:
        raise RuntimeError("qdrant unreachable")


def test_feature_template_docs_seed_payload_has_required_metadata() -> None:
    docs = build_feature_template_docs_seed_documents()
    assert len(docs) >= 5
    for doc in docs:
        payload = build_payload(doc)
        for key in (
            "source",
            "category",
            "title",
            "contentPreview",
            "framework",
            "featureName",
            "content",
        ):
            assert key in payload, f"missing {key} for {doc.relative_path}"
        assert payload["source"] == "cobip_feature_template_standard"
        assert payload["category"] == "feature_template"
        assert payload["framework"] == "Spring Boot"
        assert payload["featureName"] == "로그인"
        assert len(payload["contentPreview"]) > 0


def test_feature_template_docs_seed_idempotent_point_ids() -> None:
    docs = build_feature_template_docs_seed_documents()
    ids_run1 = [build_point_id(d) for d in docs]
    ids_run2 = [build_point_id(d) for d in docs]
    assert ids_run1 == ids_run2
    assert len(set(ids_run1)) == len(ids_run1)
    for pid in ids_run1:
        parsed = uuid.UUID(pid)
        assert parsed.version == 5
    assert str(FEATURE_TEMPLATE_SEED_NAMESPACE)


def test_seed_dry_run_lists_feature_template_docs(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def _boom(*_a, **_kw):
        raise AssertionError("must not upsert in dry-run")

    monkeypatch.setattr(
        "scripts.seed_qdrant_feature_template_docs.apply_feature_template_docs_seed",
        _boom,
    )
    rc = seed_main(["--dry-run", "--json"])
    assert rc == 0
    import json

    summary = json.loads(capsys.readouterr().out.strip())
    assert summary["documentCount"] >= 5
    assert summary["upsert"] is None


def test_generate_calls_rag_retrieval_on_llm_full_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "FEATURE_TEMPLATE_LLM_FULL_FIRST_ENABLED", True)
    monkeypatch.setattr(settings, "RAG_ENABLED", True)

    calls: list[str] = []

    def fake_retrieve(**kwargs: Any):
        calls.append(kwargs.get("query") or "")
        return rag_service.FeatureTemplateRagRetrieval(
            attempted=True,
            status="success",
            references=[
                {
                    "title": "Spring Boot 로그인 표준",
                    "content": "POST /api/auth/login endpoint standard",
                    "source": "cobip_feature_template_standard",
                    "category": "feature_template",
                    "framework": "Spring Boot",
                    "featureName": "로그인",
                }
            ],
            query=kwargs.get("query"),
            retrieved_count=1,
        )

    monkeypatch.setattr(
        rag_service,
        "retrieve_feature_template_rag_references",
        fake_retrieve,
    )

    gen = FeatureTemplateGenerator()
    monkeypatch.setattr(gen._llm_service, "generate_json", lambda *_a, **_k: _full_llm_payload())
    gen.generate(_login_request())

    assert len(calls) == 1
    assert "Spring Boot" in calls[0]
    assert "로그인" in calls[0]
    assert "JWT" in calls[0]


def test_rag_context_injected_into_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _login_request(
        referenceContext={
            "ragReferences": [
                {
                    "title": "Spring Boot 로그인 표준",
                    "content": "POST /api/auth/login 으로 JWT accessToken을 발급한다.",
                    "source": "cobip_feature_template_standard",
                    "category": "feature_template",
                    "framework": "Spring Boot",
                    "featureName": "로그인",
                }
            ]
        }
    )
    prompt, applied, _ = build_feature_template_prompt_with_applied_rags(request)
    assert "[검색 근거 / RAG Context]" in prompt
    assert "POST /api/auth/login" in prompt
    assert len(applied) == 1
    assert applied[0]["usedInPrompt"] is True


def test_applied_references_returned_from_generate_with_qdrant_hits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "RAG_ENABLED", True)

    def fake_retrieve(**kwargs: Any):
        return rag_service.FeatureTemplateRagRetrieval(
            attempted=True,
            status="success",
            references=[
                {
                    "title": "Spring Boot 로그인 기능템플릿 표준",
                    "content": "Spring Boot 로그인 기능은 POST /api/auth/login endpoint를 사용한다.",
                    "source": "cobip_feature_template_standard",
                    "category": "feature_template",
                    "framework": "Spring Boot",
                    "featureName": "로그인",
                }
            ],
            query="q",
            retrieved_count=1,
        )

    monkeypatch.setattr(
        rag_service,
        "retrieve_feature_template_rag_references",
        fake_retrieve,
    )

    gen = FeatureTemplateGenerator()
    monkeypatch.setattr(gen._llm_service, "generate_json", lambda *_a, **_k: _full_llm_payload())
    result = gen.generate(_login_request())

    assert result.source == "ollama"
    assert result.generationMode == "quality_llm_full"
    assert result.fallbackUsed is False
    assert len(result.appliedReferences) >= 1
    ref = result.appliedReferences[0]
    assert ref["usedInPrompt"] is True
    assert ref.get("source") == "cobip_feature_template_standard"
    assert ref.get("category") == "feature_template"
    assert ref.get("framework") == "Spring Boot"
    assert ref.get("featureName") == "로그인"
    assert "POST /api/auth/login" in ref.get("contentPreview", "")


def test_rag_failure_still_generates_llm_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "RAG_ENABLED", True)

    def fake_retrieve(**kwargs: Any):
        return rag_service.FeatureTemplateRagRetrieval(
            attempted=True,
            status="failed",
            references=[],
            query="q",
            retrieved_count=0,
            failure_reason="retrieve_failed:RuntimeError",
        )

    monkeypatch.setattr(
        rag_service,
        "retrieve_feature_template_rag_references",
        fake_retrieve,
    )

    gen = FeatureTemplateGenerator()
    monkeypatch.setattr(gen._llm_service, "generate_json", lambda *_a, **_k: _full_llm_payload())
    result = gen.generate(_login_request())

    assert result.source == "ollama"
    assert result.fallbackUsed is False
    assert result.appliedReferences == []


def test_hit_to_reference_uses_cobip_payload_source() -> None:
    hit = RetrievedReference(
        id="x",
        title="Spring Boot 로그인 표준",
        content="POST /api/auth/login",
        score=0.9,
        sourceType="document",
        metadata={
            "source": "cobip_feature_template_standard",
            "category": "feature_template",
            "framework": "Spring Boot",
            "featureName": "로그인",
            "path": "docs/rag/feature-template/spring-boot-login-standard.md",
        },
    ).model_dump()
    ref = rag_service._hit_to_reference(hit)
    assert ref is not None
    assert ref["source"] == "cobip_feature_template_standard"
    assert ref["category"] == "feature_template"
    assert ref["framework"] == "Spring Boot"
    assert ref["featureName"] == "로그인"

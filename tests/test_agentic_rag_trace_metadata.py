"""POST /ai/agentic-rag/run — trace metadata (Agentic RAG 4차)."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.enums import DifficultyLevel
from app.schemas.chat import AgentPayload, AgentTrace, ChatResponseData
from app.schemas.feature_template import (
    FeatureTemplateData,
    FeatureTemplateGenerateResult,
    FlowSchema,
    OverviewSchema,
)
from app.services.feature_template_generator import FeatureTemplateGenerator

_MOCK_RAG = {
    "title": "Spring Boot 로그인 API 가이드",
    "content": (
        "로그인 API는 POST /api/auth/login 형태로 구성하고, "
        "요청 본문에는 email과 password를 포함한다. "
        "비밀번호는 평문 저장하지 않고 BCrypt로 검증한다."
    ),
    "source": "internal-docs",
    "score": 0.91,
}


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


def test_trace_metadata_feature_template_with_rag(monkeypatch: pytest.MonkeyPatch) -> None:
    applied = [
        {
            "title": "Spring Boot 로그인 API 가이드",
            "source": "internal-docs",
            "score": 0.91,
            "contentPreview": "POST /api/auth/login",
            "usedInPrompt": True,
        }
    ]

    def fake_generate(self, request):
        assert request.referenceContext is not None
        return FeatureTemplateGenerateResult(
            template=_minimal_template(),
            source="ollama",
            appliedReferences=applied,
        )

    monkeypatch.setattr(FeatureTemplateGenerator, "generate", fake_generate)

    client = TestClient(app)
    resp = client.post(
        "/ai/agentic-rag/run",
        json={
            "message": "로그인 기능템플릿 생성해줘",
            "featureTemplate": {
                "language": "java",
                "framework": "spring-boot",
                "featureName": "로그인",
                "level": "beginner",
                "includeCode": False,
                "includeMissions": False,
                "includeInterview": False,
                "referenceContext": {"ragReferences": [_MOCK_RAG]},
            },
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    tr = data["trace"]
    assert data["result"]["generationMode"] == "skeleton"
    assert data["result"]["skeletonFirst"] is True
    assert data["result"]["deferredSections"] == [
        "codeFiles",
        "missions",
        "interviewQuestions",
    ]
    assert tr["ragContextAvailable"] is True
    assert tr["ragReferenceCount"] == 1
    assert tr["appliedReferenceCount"] == 1
    assert tr["source"] == "ollama"
    assert tr["resultType"] == "feature_template"
    assert tr["fallbackUsed"] is False
    assert tr["intentReason"]
    assert tr["handlerReason"]
    assert tr["routeDecision"]
    assert tr["executionMode"] == "rule_based"
    assert tr["generationMode"] == "skeleton"
    assert tr["skeletonFirst"] is True
    assert tr["deferredSections"] == ["codeFiles", "missions", "interviewQuestions"]
    assert "classifier" in tr
    assert "handler" in tr
    assert "steps" in tr
    assert "latencyMs" in tr
    assert "toolCandidates" in tr
    assert "trace_metadata_enrichment" in tr["steps"]
    assert "rag_context_detection" in tr["steps"]


def test_trace_metadata_feature_template_no_rag(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_generate(self, request):
        return FeatureTemplateGenerateResult(
            template=_minimal_template(),
            source="ollama",
            appliedReferences=[],
        )

    monkeypatch.setattr(FeatureTemplateGenerator, "generate", fake_generate)

    client = TestClient(app)
    resp = client.post(
        "/ai/agentic-rag/run",
        json={
            "message": "로그인 기능템플릿 생성해줘",
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
    tr = resp.json()["data"]["trace"]
    assert tr["ragContextAvailable"] is False
    assert tr["ragReferenceCount"] == 0
    assert tr["appliedReferenceCount"] == 0


def test_trace_metadata_chat_path(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_answer(self, request, *, apply_rag, variant="default", agent):
        return ChatResponseData(
            answer="ok",
            source="ollama",
            ragUsed=False,
            references=[],
            agent=AgentPayload(
                enabled=True,
                intent="GENERAL_CHAT",
                mode="rule_based",
                trace=AgentTrace(
                    classifier="HybridIntentClassifier",
                    handler="GeneralChatHandler",
                    llmIntentUsed=False,
                    steps=["rule_based_intent_classification"],
                    latencyMs=1,
                    toolCandidates=["general_chat"],
                ),
            ),
        )

    monkeypatch.setattr("app.services.agent_handlers.ChatService.answer", fake_answer)

    client = TestClient(app)
    resp = client.post(
        "/ai/agentic-rag/run",
        json={"message": "안녕"},
    )
    assert resp.status_code == 200
    tr = resp.json()["data"]["trace"]
    assert tr["resultType"] == "chat"
    assert tr["appliedReferenceCount"] == 0
    assert tr["ragContextAvailable"] is False
    assert tr["source"] == "ollama"
    assert tr["handlerReason"]


def test_trace_metadata_fallback_used(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_generate(self, request):
        return FeatureTemplateGenerateResult(
            template=_minimal_template(),
            source="fallback",
            appliedReferences=[],
            generationMode="fallback",
        )

    monkeypatch.setattr(FeatureTemplateGenerator, "generate", fake_generate)

    client = TestClient(app)
    resp = client.post(
        "/ai/agentic-rag/run",
        json={
            "message": "로그인 기능템플릿 생성해줘",
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
    assert tr["fallbackUsed"] is True
    assert tr["source"] == "fallback"
    assert tr["generationMode"] == "fallback"


def test_trace_metadata_excludes_empty_content_reference(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_generate(self, request):
        return FeatureTemplateGenerateResult(
            template=_minimal_template(),
            source="ollama",
            appliedReferences=[],
        )

    monkeypatch.setattr(FeatureTemplateGenerator, "generate", fake_generate)

    client = TestClient(app)
    resp = client.post(
        "/ai/agentic-rag/run",
        json={
            "message": "로그인 기능템플릿 생성해줘",
            "featureTemplate": {
                "language": "java",
                "featureName": "로그인",
                "level": "beginner",
                "includeCode": False,
                "includeMissions": False,
                "includeInterview": False,
                "referenceContext": {
                    "ragReferences": [{"title": "빈 문서", "source": "internal-docs"}]
                },
            },
        },
    )
    tr = resp.json()["data"]["trace"]
    assert tr["ragReferenceCount"] == 0
    assert tr["ragContextAvailable"] is False


def test_trace_metadata_max_five_usable_rag(monkeypatch: pytest.MonkeyPatch) -> None:
    refs = [{"title": f"T{i}", "content": f"c{i}", "source": "s"} for i in range(6)]

    def fake_generate(self, request):
        from app.services.prompt_builder import (
            build_applied_references_payload,
            extract_raw_rag_references_from_reference_context,
            select_usable_rag_references,
        )

        raw = extract_raw_rag_references_from_reference_context(request.referenceContext)
        sel = select_usable_rag_references(raw)
        return FeatureTemplateGenerateResult(
            template=_minimal_template(),
            source="ollama",
            appliedReferences=build_applied_references_payload(sel),
        )

    monkeypatch.setattr(FeatureTemplateGenerator, "generate", fake_generate)

    client = TestClient(app)
    resp = client.post(
        "/ai/agentic-rag/run",
        json={
            "message": "로그인 기능템플릿 생성해줘",
            "featureTemplate": {
                "language": "java",
                "featureName": "로그인",
                "level": "beginner",
                "includeCode": False,
                "includeMissions": False,
                "includeInterview": False,
                "referenceContext": {"ragReferences": refs},
            },
        },
    )
    tr = resp.json()["data"]["trace"]
    assert tr["ragReferenceCount"] == 5
    assert tr["appliedReferenceCount"] == 5

from fastapi.testclient import TestClient

from app.main import app
from app.models.enums import DifficultyLevel
from app.schemas.chat import AgentPayload, ChatResponseData
from app.schemas.feature_template import (
    FeatureTemplateData,
    FeatureTemplateGenerateResult,
    FlowSchema,
    OverviewSchema,
)
from app.services.feature_template_generator import FeatureTemplateGenerator
from app.services.prompt_builder import build_feature_template_prompt_with_applied_rags

_RAG_REFERENCE = {
    "title": "로그인 요구사항",
    "source": "manual",
    "content": "로그인은 이메일과 비밀번호를 입력받고 JWT를 발급한다.",
}


def _minimal_template(feature_name: str = "로그인") -> FeatureTemplateData:
    return FeatureTemplateData(
        overview=OverviewSchema(
            featureName=feature_name,
            purpose="사용자 인증 기능을 학습한다.",
            useCases=[],
            resultDescription="로그인 기능이 동작한다.",
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


def test_agentic_rag_routes_feature_template_generate(
    monkeypatch,
) -> None:
    def fake_generate(self, request):
        assert request.featureName == "로그인"
        assert request.referenceContext is not None
        assert request.referenceContext["agenticUserMessage"]
        return FeatureTemplateGenerateResult(
            template=_minimal_template(request.featureName),
            source="fallback",
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
                "framework": "spring-boot",
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
    assert body["data"]["intent"] == "feature_template_generate"
    assert body["data"]["resultType"] == "feature_template"
    assert body["data"]["result"]["template"]["overview"]["featureName"] == "로그인"
    assert body["data"]["result"].get("appliedReferences") == []
    assert body["data"]["trace"]["handler"] == "FeatureTemplateGenerator.generate"
    assert "feature_template_generate_execution" in body["data"]["trace"]["steps"]


def test_agentic_rag_feature_template_reference_context_rag_applied(
    monkeypatch,
) -> None:
    def fake_generate(self, request):
        assert request.referenceContext is not None
        assert request.referenceContext["userContext"] == "사용자 추가 맥락"
        assert request.referenceContext["ragReferences"] == [_RAG_REFERENCE]
        _prompt, applied, _meta = build_feature_template_prompt_with_applied_rags(request)
        return FeatureTemplateGenerateResult(
            template=_minimal_template(request.featureName),
            source="ollama",
            appliedReferences=applied,
        )

    monkeypatch.setattr(FeatureTemplateGenerator, "generate", fake_generate)

    client = TestClient(app)
    resp = client.post(
        "/ai/agentic-rag/run",
        json={
            "message": "Spring Boot 로그인 기능템플릿 생성해줘",
            "context": "사용자 추가 맥락",
            "featureTemplate": {
                "language": "Java",
                "framework": "Spring Boot",
                "featureName": "로그인",
                "level": "beginner",
                "includeCode": True,
                "includeMissions": True,
                "includeInterview": True,
                "referenceContext": {
                    "ragReferences": [_RAG_REFERENCE],
                },
            },
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    applied = body["data"]["result"]["appliedReferences"]
    assert len(applied) == 1
    assert applied[0]["title"] == "로그인 요구사항"
    assert applied[0]["source"] == "manual"
    assert "JWT" in applied[0]["contentPreview"]
    assert applied[0]["usedInPrompt"] is True
    assert body["data"]["result"]["request"]["referenceContext"]["userContext"] == "사용자 추가 맥락"
    trace = body["data"]["trace"]
    assert trace["ragContextAvailable"] is True
    assert trace["ragReferenceCount"] == 1
    assert trace["appliedReferenceCount"] == 1


def test_agentic_rag_root_reference_context_is_ignored_for_feature_template(
    monkeypatch,
) -> None:
    def fake_generate(self, request):
        assert request.referenceContext is not None
        assert "ragReferences" not in request.referenceContext
        _prompt, applied, _meta = build_feature_template_prompt_with_applied_rags(request)
        return FeatureTemplateGenerateResult(
            template=_minimal_template(request.featureName),
            source="ollama",
            appliedReferences=applied,
        )

    monkeypatch.setattr(FeatureTemplateGenerator, "generate", fake_generate)

    client = TestClient(app)
    resp = client.post(
        "/ai/agentic-rag/run",
        json={
            "message": "로그인 기능템플릿 생성해줘",
            "referenceContext": {
                "ragReferences": [_RAG_REFERENCE],
            },
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
    assert body["data"]["result"]["appliedReferences"] == []
    trace = body["data"]["trace"]
    assert trace["ragContextAvailable"] is False
    assert trace["ragReferenceCount"] == 0
    assert trace["appliedReferenceCount"] == 0


def test_agentic_rag_message_based_feature_template_generation_still_routes(
    monkeypatch,
) -> None:
    def fake_generate(self, request):
        assert request.featureName == "로그인"
        return FeatureTemplateGenerateResult(
            template=_minimal_template(request.featureName),
            source="fallback",
            appliedReferences=[],
        )

    monkeypatch.setattr(FeatureTemplateGenerator, "generate", fake_generate)

    client = TestClient(app)
    resp = client.post(
        "/ai/agentic-rag/run",
        json={
            "message": "로그인 기능템플릿 만들어줘",
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["intent"] == "feature_template_generate"
    assert body["data"]["resultType"] == "feature_template"
    assert body["data"]["result"]["template"]["overview"]["featureName"] == "로그인"


def test_agentic_rag_routes_chat(monkeypatch) -> None:
    def fake_answer(self, request, *, apply_rag, variant="default", agent):
        assert request.message == "안녕"
        return ChatResponseData(
            answer="안녕하세요.",
            source="fallback",
            ragUsed=False,
            references=[],
            agent=AgentPayload(
                enabled=agent.enabled,
                intent=agent.intent,
                mode=agent.mode,
                trace=agent.trace,
            ),
        )

    monkeypatch.setattr("app.services.agent_handlers.ChatService.answer", fake_answer)

    client = TestClient(app)
    resp = client.post(
        "/ai/agentic-rag/run",
        json={"message": "안녕"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["intent"] == "chat"
    assert body["data"]["resultType"] == "chat"
    assert body["data"]["result"]["answer"] == "안녕하세요."
    assert body["data"]["trace"]["handler"] == "AgentOrchestrator.run_chat"


def test_agentic_rag_login_api_spec_includes_enriched_documentation(
    monkeypatch,
) -> None:
    from app.core.config import settings
    from tests.test_feature_template_llm_full_first import _full_llm_payload

    monkeypatch.setattr(settings, "RAG_ENABLED", False)
    monkeypatch.setattr(settings, "FEATURE_TEMPLATE_CACHE_ENABLED", False)
    monkeypatch.setattr(
        "app.services.feature_template_generator.LLMService.generate_json",
        lambda *_a, **_k: _full_llm_payload(),
    )

    client = TestClient(app)
    resp = client.post(
        "/ai/agentic-rag/run",
        json={
            "message": "Spring Boot 로그인 기능템플릿 생성해줘",
            "featureTemplate": {
                "language": "Java",
                "framework": "Spring Boot",
                "featureName": "로그인",
                "level": "beginner",
                "includeCode": True,
                "includeMissions": True,
                "includeInterview": True,
            },
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["result"]["source"] == "ollama"
    assert body["data"]["result"]["generationMode"] == "quality_llm_full"
    assert body["data"]["trace"]["fallbackUsed"] is False

    api = body["data"]["result"]["template"]["apiSpec"][0]
    assert api["endpoint"] == "/api/auth/login"
    assert len(api["requestFields"]) >= 2
    assert len(api["statusCodes"]) >= 3
    assert len(api["errorResponses"]) >= 2
    assert len(api["frontendNotes"]) >= 2

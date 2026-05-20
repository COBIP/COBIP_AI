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
    assert body["data"]["trace"]["handler"] == "FeatureTemplateGenerator.generate"
    assert "feature_template_generate_execution" in body["data"]["trace"]["steps"]


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

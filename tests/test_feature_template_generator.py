"""FeatureTemplateGenerator — normalizer 경유 및 mock 경로."""

from unittest.mock import MagicMock

import pytest

from app.models.enums import DifficultyLevel
from app.schemas.feature_template import FeatureTemplateGenerateRequest
from app.services.feature_template_generator import FeatureTemplateGenerator

_CANONICAL_KEYS = frozenset(
    {
        "overview",
        "requirements",
        "flow",
        "apiSpec",
        "codeFiles",
        "basicQuestions",
        "missions",
        "interviewQuestions",
        "nextRecommendations",
    }
)


@pytest.fixture
def minimal_request() -> FeatureTemplateGenerateRequest:
    return FeatureTemplateGenerateRequest(
        language="java",
        featureName="smoke",
        level=DifficultyLevel.BEGINNER,
        includeCode=False,
        includeMissions=False,
        includeInterview=False,
    )


def test_generate_fallback_has_all_sections(minimal_request: FeatureTemplateGenerateRequest) -> None:
    """OLLAMA 미설정 등으로 LLM이 실패해도 mock 결과는 9개 섹션을 갖춘다."""
    gen = FeatureTemplateGenerator(llm_service=MagicMock())
    gen._llm_service.generate_json.side_effect = RuntimeError("no llm")

    result = gen.generate(minimal_request)
    data = result.template.model_dump()
    assert set(data.keys()) == _CANONICAL_KEYS
    assert result.source == "fallback"


def test_generate_success_path_uses_normalizer(
    minimal_request: FeatureTemplateGenerateRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    gen = FeatureTemplateGenerator()

    def fake_json(_prompt: str) -> dict:
        return {
            "overview": {
                "featureName": "smoke",
                "purpose": "p",
                "useCases": [],
                "resultDescription": "r",
                "techStack": [],
                "learningGoals": [],
            },
            "requirements": [],
            "flow": {"steps": [], "layers": []},
            "apiSpec": [],
            "codeFiles": [],
            "basicQuestions": [],
            "missions": [],
            "interviewQuestions": [],
            "nextRecommendations": [],
        }

    monkeypatch.setattr(gen._llm_service, "generate_json", fake_json)
    result = gen.generate(minimal_request)
    assert result.source == "ollama"
    assert set(result.template.model_dump().keys()) == _CANONICAL_KEYS


def test_regenerate_section_success_path_uses_normalizer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.schemas.feature_template import FeatureTemplateRegenerateSectionRequest

    gen = FeatureTemplateGenerator()

    def fake_json(_prompt: str) -> dict:
        return {
            "requirements": [
                {
                    "requirementId": "R-001",
                    "name": "n",
                    "description": "d",
                    "inputValue": "i",
                    "processCondition": "p",
                    "successResult": "s",
                    "failureResult": "f",
                    "priority": "HIGH",
                    "relatedScreenOrApi": "a",
                }
            ]
        }

    monkeypatch.setattr(gen._llm_service, "generate_json", fake_json)
    result = gen.regenerate_section(
        FeatureTemplateRegenerateSectionRequest(
            section="requirements",
            language="java",
            featureName="x",
            level=DifficultyLevel.BEGINNER,
        )
    )
    assert result.source == "ollama"
    assert result.section == "requirements"
    assert isinstance(result.content, list)
    assert len(result.content) == 1
    assert result.content[0]["requirementId"] == "R-001"


def test_regenerate_section_accepts_llm_snake_case_section_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.schemas.feature_template import FeatureTemplateRegenerateSectionRequest

    gen = FeatureTemplateGenerator()

    def fake_json(_prompt: str) -> dict:
        return {
            "api_spec": [
                {
                    "apiName": "x",
                    "method": "GET",
                    "endpoint": "/x",
                    "description": "d",
                    "requestBody": {},
                    "responseBody": {},
                    "status": 200,
                }
            ]
        }

    monkeypatch.setattr(gen._llm_service, "generate_json", fake_json)
    result = gen.regenerate_section(
        FeatureTemplateRegenerateSectionRequest(
            section="apiSpec",
            language="java",
            featureName="x",
            level=DifficultyLevel.BEGINNER,
        )
    )
    assert result.section == "apiSpec"
    assert len(result.content) == 1
    assert result.content[0]["apiName"] == "x"

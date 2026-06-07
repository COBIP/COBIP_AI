"""FeatureTemplateGenerator — normalizer 경유 및 mock 경로."""

from unittest.mock import MagicMock

import pytest

from app.models.enums import DifficultyLevel
from app.schemas.feature_template import FeatureTemplateGenerateRequest
from app.core.config import settings
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


def test_generate_fallback_has_all_sections(
    minimal_request: FeatureTemplateGenerateRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OLLAMA 미설정 등으로 LLM이 실패해도 mock 결과는 9개 섹션을 갖춘다."""
    monkeypatch.setattr(settings, "FEATURE_TEMPLATE_INSTANT_SKELETON_ENABLED", False)
    gen = FeatureTemplateGenerator(llm_service=MagicMock())
    gen._llm_service.generate_json.side_effect = RuntimeError("no llm")

    result = gen.generate(minimal_request)
    data = result.template.model_dump()
    assert set(data.keys()) == _CANONICAL_KEYS
    assert result.source == "fallback"
    assert result.appliedReferences == []
    assert result.generationMode == "fallback"
    assert result.skeletonFirst is True
    assert result.fallbackUsed is True
    assert result.initialLlmEnhancementAttempted is True
    assert result.initialLlmEnhancementSucceeded is False
    assert result.deferredSections == ["codeFiles", "missions", "interviewQuestions"]
    assert isinstance(result.fastSkeletonEnabled, bool)


def test_generate_success_path_uses_normalizer(
    minimal_request: FeatureTemplateGenerateRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    gen = FeatureTemplateGenerator()
    seen: dict[str, object] = {}

    def fake_json(_prompt: str, **kwargs: object) -> dict:
        seen.update(kwargs)
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
    assert result.appliedReferences == []
    assert result.generationMode == "quality_llm_full"
    assert result.skeletonFirst is False
    assert result.fallbackUsed is False
    assert result.initialLlmEnhancementAttempted is True
    assert result.initialLlmEnhancementSucceeded is True
    assert result.deferredSections == ["codeFiles", "missions", "interviewQuestions"]
    assert result.fastSkeletonEnabled is False
    assert seen["timeout_seconds"] == settings.FEATURE_TEMPLATE_LLM_TIMEOUT_SECONDS


def test_regenerate_section_success_path_uses_normalizer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.schemas.feature_template import FeatureTemplateRegenerateSectionRequest

    gen = FeatureTemplateGenerator()

    def fake_json(_prompt: str, **_kwargs: object) -> dict:
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
    assert result.generationMode == "section_regenerated"
    assert isinstance(result.content, list)
    assert len(result.content) == 1
    assert result.content[0]["requirementId"] == "R-001"


def test_regenerate_section_accepts_llm_snake_case_section_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.schemas.feature_template import FeatureTemplateRegenerateSectionRequest

    gen = FeatureTemplateGenerator()

    def fake_json(_prompt: str, **_kwargs: object) -> dict:
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


def test_generate_uses_feature_template_timeout(
    minimal_request: FeatureTemplateGenerateRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "FEATURE_TEMPLATE_INSTANT_SKELETON_ENABLED", False)
    gen = FeatureTemplateGenerator()
    monkeypatch.setattr(settings, "FEATURE_TEMPLATE_LLM_TIMEOUT_SECONDS", 123)

    gen._llm_service.generate_json = MagicMock(
        return_value={
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
    )

    gen.generate(minimal_request)

    assert gen._llm_service.generate_json.call_args.kwargs["timeout_seconds"] == 123

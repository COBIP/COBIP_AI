"""17차 fast skeleton 프로필 검증."""

from app.core.config import settings
from app.models.enums import DifficultyLevel
from app.schemas.feature_template import FeatureTemplateGenerateRequest
from app.services.feature_template_generator import FeatureTemplateGenerator
from app.services.feature_template_normalizer import FeatureTemplateNormalizer
from app.services.prompt_builder import (
    build_feature_template_prompt,
    is_fast_skeleton_enabled_for_initial_generate,
)


def _req(**kwargs: object) -> FeatureTemplateGenerateRequest:
    base = dict(
        language="java",
        framework="spring-boot",
        featureName="로그인",
        level=DifficultyLevel.BEGINNER,
        includeCode=True,
        includeMissions=True,
        includeInterview=True,
    )
    base.update(kwargs)
    return FeatureTemplateGenerateRequest(**base)


def test_fast_skeleton_enabled_by_default() -> None:
    assert is_fast_skeleton_enabled_for_initial_generate() is True


def test_fast_skeleton_prompt_shorter_than_legacy(monkeypatch) -> None:
    fast_text = build_feature_template_prompt(_req())
    monkeypatch.setattr(settings, "FEATURE_TEMPLATE_FAST_SKELETON_ENABLED", False)
    legacy_text = build_feature_template_prompt(_req())
    assert len(fast_text) < len(legacy_text)


def test_fast_skeleton_prompt_has_tight_limits(monkeypatch) -> None:
    monkeypatch.setattr(settings, "FEATURE_TEMPLATE_FAST_SKELETON_ENABLED", True)
    text = build_feature_template_prompt(_req())
    assert "fast skeleton" in text or "[fast skeleton 초안 모드]" in text
    assert "steps 3~4개" in text
    assert "requirements: 정확히 3개" in text
    assert "codeFiles: includeCode와 무관하게 반드시 []" in text
    assert "LoginController.java" not in text


def test_fast_skeleton_include_code_still_forbids_codefiles(monkeypatch) -> None:
    monkeypatch.setattr(settings, "FEATURE_TEMPLATE_FAST_SKELETON_ENABLED", True)
    text = build_feature_template_prompt(_req(includeCode=True))
    assert "코드 본문·stub·파일명 나열은 금지" in text
    assert '"codeFiles": []' in text


def test_fast_skeleton_trace_field_on_generate_result(monkeypatch) -> None:
    from unittest.mock import MagicMock

    monkeypatch.setattr(settings, "FEATURE_TEMPLATE_FAST_SKELETON_ENABLED", True)
    gen = FeatureTemplateGenerator(llm_service=MagicMock())
    gen._llm_service.generate_json.side_effect = RuntimeError("no llm")
    result = gen.generate(_req())
    assert result.fastSkeletonEnabled is True


def test_normalizer_fills_login_baseline_from_minimal_llm_dict() -> None:
    request = _req(includeCode=False, includeMissions=False, includeInterview=False)
    minimal = {
        "overview": {
            "featureName": "로그인",
            "purpose": "짧은 목적",
            "useCases": [],
            "resultDescription": "짧은 결과",
            "techStack": ["java"],
            "learningGoals": [],
        },
        "requirements": [],
        "flow": {"steps": ["1) a"], "layers": []},
        "apiSpec": [],
        "codeFiles": [],
        "basicQuestions": [],
        "missions": [],
        "interviewQuestions": [],
        "nextRecommendations": [],
    }
    normalized = FeatureTemplateNormalizer.normalize(minimal, request)
    assert len(normalized["requirements"]) >= 3
    assert normalized["overview"]["learningGoals"]
    assert normalized["codeFiles"] == []
    assert normalized["missions"] == []
    assert normalized["interviewQuestions"] == []

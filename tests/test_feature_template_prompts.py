"""기능템플릿 LLM 프롬프트 문자열 검증 (7-3)."""

from app.models.enums import DifficultyLevel
from app.schemas.feature_template import FeatureTemplateGenerateRequest
from app.services.prompt_builder import build_feature_template_prompt


def _req(**kwargs: object) -> FeatureTemplateGenerateRequest:
    base = dict(
        language="java",
        featureName="로그인",
        level=DifficultyLevel.BEGINNER,
        includeCode=True,
        includeMissions=True,
        includeInterview=True,
    )
    base.update(kwargs)
    return FeatureTemplateGenerateRequest(**base)


def test_prompt_contains_json_only_and_no_markdown_rules() -> None:
    text = build_feature_template_prompt(_req())
    assert "단일 JSON" in text or "JSON 객체만" in text
    assert "마크다운 코드블록" in text or "```" in text
    assert "JSON 바깥" in text


def test_prompt_lists_nine_top_level_keys() -> None:
    text = build_feature_template_prompt(_req())
    for key in (
        "overview",
        "requirements",
        "flow",
        "apiSpec",
        "codeFiles",
        "basicQuestions",
        "missions",
        "interviewQuestions",
        "nextRecommendations",
    ):
        assert key in text


def test_prompt_include_flags_and_empty_array_rules() -> None:
    text = build_feature_template_prompt(
        _req(includeCode=False, includeMissions=False, includeInterview=False)
    )
    assert "includeCode" in text or "includeCode:" in text
    assert "false" in text.lower()
    assert "codeFiles" in text and "[]" in text
    assert "missions" in text
    assert "interviewQuestions" in text


def test_prompt_camel_case_emphasis() -> None:
    text = build_feature_template_prompt(_req())
    assert "camelCase" in text


def test_prompt_passes_language_framework_feature_level() -> None:
    text = build_feature_template_prompt(
        _req(
            language="python",
            framework="fastapi",
            featureName="게시판",
            level=DifficultyLevel.INTERMEDIATE,
        )
    )
    assert "python" in text
    assert "fastapi" in text
    assert "게시판" in text
    assert "intermediate" in text


def test_prompt_quality_minimums() -> None:
    text = build_feature_template_prompt(_req())
    assert "최소 3개" in text
    assert "apiSpec" in text and "최소 1개" in text
    assert "5단계" in text or "5개 이상" in text


def test_prompt_maps_conceptual_fields_to_schema_without_extra_keys() -> None:
    """교육용 개념(goal/hints/keywords 등)은 스키마 필드에 녹이라는 지시가 포함된다."""
    text = build_feature_template_prompt(_req())
    assert "미션 목표:" in text
    assert "hints 라는 key 는 쓰지 않는다" in text
    assert "keywords key 금지" in text
    assert "nextFeatureName 개념" in text
    assert "title key 금지" in text


def test_prompt_forbids_schema_unknown_top_level_field_names() -> None:
    text = build_feature_template_prompt(_req())
    assert "goal/hints 단독 key" in text or "스키마에 없는 필드명" in text

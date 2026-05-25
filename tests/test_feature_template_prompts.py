"""기능템플릿 LLM 프롬프트 문자열 검증 (7-3, 7-4)."""

from app.models.enums import DifficultyLevel
from app.schemas.feature_template import FeatureTemplateGenerateRequest
from app.services.prompt_builder import (
    build_feature_template_prompt,
    build_feature_template_section_prompt,
)


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


def test_prompt_forbids_placeholder_dummy_phrases() -> None:
    text = build_feature_template_prompt(_req())
    assert "더미" in text or "준비용" in text or "플레이스홀더" in text
    assert "실제 동작 가능한 코드 문자열" in text
    assert "LoginService.java" in text
    assert '"codeFiles": []' in text


def test_prompt_quality_minimums() -> None:
    text = build_feature_template_prompt(_req())
    assert "requirements: 정확히 3개" in text
    assert "basicQuestions: 정확히 3개" in text


def test_prompt_initial_generation_lightweight_policy() -> None:
    text = build_feature_template_prompt(_req())
    assert "skeleton-first" in text
    assert "전체 구조만 빠르게" in text
    assert "regenerate-section" in text
    assert "requirements: 정확히 3개" in text
    assert "steps 정확히 5개" in text
    assert "basicQuestions: 정확히 3개" in text
    assert "nextRecommendations: 정확히 3개" in text


def test_prompt_limits_initial_codefiles_volume() -> None:
    text = build_feature_template_prompt(_req(framework="Spring Boot"))
    assert "상세 코드를 만들지 않는다" in text
    assert "최대 4개 짧은 stub" in text
    assert "LoginController.java" in text
    assert "LoginService.java" in text
    assert "LoginRequest.java" in text
    assert "LoginResponse.java" in text
    assert "상세 코드는 regenerate-section에서 생성" in text


def test_prompt_limits_optional_sections_for_initial_generation() -> None:
    text = build_feature_template_prompt(_req())
    assert "missions: includeMissions=true여도 최초 generate에서는 []를 우선 반환" in text
    assert "interviewQuestions: includeInterview=true여도 최초 generate에서는 []를 우선 반환" in text
    assert "nextRecommendations: 정확히 3개만 추천" in text


def test_prompt_keeps_empty_array_rules_when_flags_false() -> None:
    text = build_feature_template_prompt(
        _req(includeCode=False, includeMissions=False, includeInterview=False)
    )
    assert "codeFiles: includeCode=false 이므로 반드시 []" in text
    assert "missions: includeMissions=false 이므로 반드시 []" in text
    assert "interviewQuestions: includeInterview=false 이므로 반드시 []" in text
    assert '"codeFiles": []' in text
    assert '"missions": []' in text
    assert '"interviewQuestions": []' in text


def test_prompt_maps_conceptual_fields_to_schema_without_extra_keys() -> None:
    """교육용 개념(goal/hints/keywords 등)은 스키마 필드에 녹이라는 지시가 포함된다."""
    text = build_feature_template_prompt(_req())
    assert "상세 실습 미션은 regenerate-section에서 생성" in text
    assert "goal/hints/keywords/title" in text
    assert "nextFeatureName 단독 key" in text


def test_prompt_forbids_schema_unknown_top_level_field_names() -> None:
    text = build_feature_template_prompt(_req())
    assert "goal/hints 단독 key" in text or "스키마에 없는 필드명" in text


def test_section_prompt_single_root_key_and_quality_rules() -> None:
    base = FeatureTemplateGenerateRequest(
        language="java",
        featureName="로그인",
        level=DifficultyLevel.BEGINNER,
        includeCode=True,
        includeMissions=True,
        includeInterview=True,
    )
    text = build_feature_template_section_prompt(
        "requirements",
        base,
        previous_content=None,
        current_template=None,
        user_instruction=None,
        extra_tech_stack=["Spring Boot"],
    )
    assert "requirements" in text
    assert "단일 JSON" in text or "JSON 객체" in text
    assert "마크다운 코드블록" in text or "```" in text
    assert "최소 3개" in text


def test_prompt_7_4_content_quality_minimums_and_api_json() -> None:
    """7-4: 실무형 품질 지시·최소 개수·apiSpec 예시 JSON·스키마 밖 key 금지 유지."""
    text = build_feature_template_prompt(_req())
    assert "requirements: 정확히 3개" in text
    assert "basicQuestions: 정확히 3개" in text
    assert "nextRecommendations: 정확히 3개" in text
    assert "missions: includeMissions=true여도 최초 generate에서는 []" in text
    assert "interviewQuestions: includeInterview=true여도 최초 generate에서는 []" in text
    assert "requestBody/responseBody는 필드 예시가 있는 JSON 객체" in text
    assert "goal/hints/keywords/title" in text


def test_prompt_is_short_when_optional_sections_disabled() -> None:
    text = build_feature_template_prompt(
        _req(includeCode=False, includeMissions=False, includeInterview=False)
    )
    assert len(text) < 6000


def test_prompt_omits_code_details_when_include_code_false() -> None:
    text = build_feature_template_prompt(
        _req(framework="Spring Boot", includeCode=False)
    )
    assert "LoginController.java" not in text
    assert "LoginService.java" not in text
    assert "LoginRequest.java" not in text
    assert "LoginResponse.java" not in text
    assert "파일당 content 20~40줄" not in text
    assert '"codeFiles": []' in text


def test_prompt_omits_mission_details_when_include_missions_false() -> None:
    text = build_feature_template_prompt(_req(includeMissions=False))
    assert "missionId" not in text
    assert "미션 목표:" not in text
    assert '"missions": []' in text


def test_prompt_omits_interview_details_when_include_interview_false() -> None:
    text = build_feature_template_prompt(_req(includeInterview=False))
    assert "sampleAnswer" not in text
    assert "keyPoints" not in text
    assert '"interviewQuestions": []' in text


def test_prompt_skeleton_first_keeps_heavy_sections_empty_even_when_flags_true() -> None:
    text = build_feature_template_prompt(_req())
    assert '"codeFiles": []' in text
    assert '"missions": []' in text
    assert '"interviewQuestions": []' in text
    assert "regenerate-section" in text


def test_prompt_length_stays_small_with_skeleton_first_full_options() -> None:
    text = build_feature_template_prompt(_req(framework="Spring Boot"))
    assert len(text) < 5000

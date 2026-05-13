"""FeatureTemplateNormalizer — 필수 섹션·별칭·타입 보정."""

import pytest

from app.models.enums import DifficultyLevel
from app.schemas.feature_template import FeatureTemplateData, FeatureTemplateGenerateRequest
from app.services.feature_template_normalizer import FeatureTemplateNormalizer

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
def sample_request() -> FeatureTemplateGenerateRequest:
    return FeatureTemplateGenerateRequest(
        language="java",
        framework="spring-boot",
        featureName="로그인",
        level=DifficultyLevel.BEGINNER,
        includeCode=True,
        includeMissions=True,
        includeInterview=True,
    )


def test_normalize_empty_dict_has_all_sections(sample_request: FeatureTemplateGenerateRequest) -> None:
    out = FeatureTemplateNormalizer.normalize({}, sample_request)
    assert set(out.keys()) == _CANONICAL_KEYS
    assert isinstance(out["requirements"], list)
    assert isinstance(out["flow"], dict)
    assert out["flow"]["steps"] == []
    assert out["flow"]["layers"] == []
    assert out["overview"]["featureName"] == "로그인"


def test_normalize_partial_overview_merged(sample_request: FeatureTemplateGenerateRequest) -> None:
    raw = {"overview": {"purpose": "테스트 목적"}}
    out = FeatureTemplateNormalizer.normalize(raw, sample_request)
    assert out["overview"]["purpose"] == "테스트 목적"
    assert out["overview"]["featureName"] == "로그인"
    assert out["overview"]["useCases"] == []


def test_snake_case_aliases(sample_request: FeatureTemplateGenerateRequest) -> None:
    raw = {
        "api_spec": [{"apiName": "x", "method": "GET", "endpoint": "/", "description": "d", "requestBody": {}, "responseBody": {}, "status": 200}],
        "basic_questions": [],
        "interview": [],
        "next_recommendations": [],
    }
    out = FeatureTemplateNormalizer.normalize(raw, sample_request)
    assert out["apiSpec"][0]["apiName"] == "x"
    assert out["basicQuestions"] == []
    assert out["interviewQuestions"] == []
    assert out["nextRecommendations"] == []


def test_code_view_files_unwrap(sample_request: FeatureTemplateGenerateRequest) -> None:
    raw = {
        "code_view": {
            "files": [
                {
                    "fileName": "A.java",
                    "role": "x",
                    "language": "java",
                    "content": "// ok",
                }
            ]
        }
    }
    out = FeatureTemplateNormalizer.normalize(raw, sample_request)
    assert len(out["codeFiles"]) == 1
    assert out["codeFiles"][0]["fileName"] == "A.java"


def test_include_flags_force_empty_sections(sample_request: FeatureTemplateGenerateRequest) -> None:
    req = sample_request.model_copy(
        update={
            "includeCode": False,
            "includeMissions": False,
            "includeInterview": False,
        }
    )
    raw = {
        "codeFiles": [{"fileName": "x", "role": "r", "language": "java", "content": "c"}],
        "missions": [{"missionId": "m", "title": "t", "description": "d", "missionType": "implementation", "requirements": [], "successCriteria": [], "relatedRequirements": [], "difficulty": "beginner"}],
        "interviewQuestions": [{"questionId": "q", "question": "?", "keyPoints": [], "sampleAnswer": "a"}],
    }
    out = FeatureTemplateNormalizer.normalize(raw, req)
    assert out["codeFiles"] == []
    assert out["missions"] == []
    assert out["interviewQuestions"] == []


def test_weird_types_do_not_raise(sample_request: FeatureTemplateGenerateRequest) -> None:
    raw = {
        "requirements": "not-a-list",
        "flow": "not-a-dict",
        "apiSpec": None,
    }
    out = FeatureTemplateNormalizer.normalize(raw, sample_request)
    template = FeatureTemplateData(**out)
    assert template.requirements == []
    assert template.flow.steps == []
    assert template.apiSpec == []


def test_pydantic_round_trip_after_normalize(sample_request: FeatureTemplateGenerateRequest) -> None:
    out = FeatureTemplateNormalizer.normalize({"overview": {}}, sample_request)
    template = FeatureTemplateData(**out)
    dumped = template.model_dump()
    assert set(dumped.keys()) == _CANONICAL_KEYS


def test_requirements_missing_priority_and_related_get_defaults(
    sample_request: FeatureTemplateGenerateRequest,
) -> None:
    raw = {
        "requirements": [
            {
                "requirementId": "r1",
                "name": "요구1",
                "description": "설명",
                "inputValue": "입력",
                "processCondition": "조건",
                "successResult": "성공",
                "failureResult": "실패",
            }
        ],
    }
    out = FeatureTemplateNormalizer.normalize(raw, sample_request)
    assert out["requirements"][0]["priority"] == "MEDIUM"
    assert out["requirements"][0]["relatedScreenOrApi"] == "로그인 화면 / 로그인 API"
    template = FeatureTemplateData(**out)
    assert template.requirements[0].priority == "MEDIUM"
    assert template.requirements[0].relatedScreenOrApi == "로그인 화면 / 로그인 API"


def test_requirements_defaults_without_request_use_generic_related() -> None:
    raw = {
        "requirements": [
            {
                "requirementId": "r1",
                "name": "요구1",
                "description": "설명",
                "inputValue": "입력",
                "processCondition": "조건",
                "successResult": "성공",
                "failureResult": "실패",
            }
        ],
    }
    out = FeatureTemplateNormalizer.normalize(raw, None)
    assert out["requirements"][0]["priority"] == "MEDIUM"
    assert out["requirements"][0]["relatedScreenOrApi"] == "관련 화면 / API"
    FeatureTemplateData(**out)

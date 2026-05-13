"""FeatureTemplateNormalizer — 필수 섹션·별칭·타입 보정."""

import json

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
    req = sample_request.model_copy(update={"includeInterview": False})
    raw = {
        "api_spec": [{"apiName": "x", "method": "GET", "endpoint": "/", "description": "d", "requestBody": {}, "responseBody": {}, "status": 200}],
        "basic_questions": [],
        "interview": [],
        "next_recommendations": [],
    }
    out = FeatureTemplateNormalizer.normalize(raw, req)
    assert out["apiSpec"][0]["apiName"] == "x"
    assert out["basicQuestions"] == []
    assert out["interviewQuestions"] == []
    assert len(out["nextRecommendations"]) >= 3


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
    assert len(out["codeFiles"]) >= 4
    names = [f["fileName"] for f in out["codeFiles"]]
    assert "A.java" in names
    assert "LoginController.java" in names
    a = next(f for f in out["codeFiles"] if f["fileName"] == "A.java")
    assert a["content"] == "// ok"


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
    req = sample_request.model_copy(update={"framework": None, "featureName": "다른기능"})
    raw = {
        "requirements": "not-a-list",
        "flow": "not-a-dict",
        "apiSpec": None,
    }
    out = FeatureTemplateNormalizer.normalize(raw, req)
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


def test_missions_missing_optional_fields_get_defaults_and_pass_pydantic(
    sample_request: FeatureTemplateGenerateRequest,
) -> None:
    raw = {
        "missions": [
            {
                "missionId": "m1",
                "title": "미션 1",
                "description": "설명 1",
            },
            {
                "missionId": "m2",
                "title": "미션 2",
                "description": "설명 2",
                "missionType": "quiz",
            },
        ],
    }
    out = FeatureTemplateNormalizer.normalize(raw, sample_request)
    assert out["missions"][0]["missionType"] == "implementation"
    assert out["missions"][0]["requirements"] == [
        "미션 목표를 이해하고 필요한 기능을 구현한다.",
    ]
    assert out["missions"][0]["successCriteria"] == [
        "요구사항에 맞게 기능이 정상 동작한다.",
    ]
    assert out["missions"][0]["relatedRequirements"] == []
    assert out["missions"][0]["difficulty"] == "beginner"
    assert out["missions"][1]["missionType"] == "quiz"
    assert out["missions"][1]["requirements"] == [
        "미션 목표를 이해하고 필요한 기능을 구현한다.",
    ]
    FeatureTemplateData(**out)


def test_missions_difficulty_uses_request_level_when_missing() -> None:
    req = FeatureTemplateGenerateRequest(
        language="java",
        framework=None,
        featureName="테스트",
        level=DifficultyLevel.ADVANCED,
        includeCode=False,
        includeMissions=True,
        includeInterview=False,
    )
    raw = {
        "missions": [
            {
                "missionId": "m1",
                "title": "t",
                "description": "d",
                "requirements": ["r"],
                "successCriteria": ["s"],
                "relatedRequirements": [],
            }
        ],
    }
    out = FeatureTemplateNormalizer.normalize(raw, req)
    assert out["missions"][0]["difficulty"] == "advanced"
    FeatureTemplateData(**out)


_PLACEHOLDER_SUBSTRINGS = (
    "실제 동작 가능한 코드 문자열",
    "...",
    "TODO",
    "예시 코드",
    "생략",
    "placeholder",
    "플레이스홀더",
)


def _assert_no_placeholder_substrings(blob: object) -> None:
    dumped = json.dumps(blob, ensure_ascii=False)
    for marker in _PLACEHOLDER_SUBSTRINGS:
        assert marker not in dumped


def test_codefiles_placeholder_content_replaced_with_java(sample_request: FeatureTemplateGenerateRequest) -> None:
    raw = {
        "codeFiles": [
            {
                "fileName": "X.java",
                "role": "r",
                "language": "java",
                "content": "실제 동작 가능한 코드 문자열",
            }
        ],
    }
    out = FeatureTemplateNormalizer.normalize(raw, sample_request)
    ctrl = next(f for f in out["codeFiles"] if f["fileName"] == "LoginController.java")
    assert "실제 동작 가능한 코드 문자열" not in ctrl["content"]
    assert "@RestController" in ctrl["content"]
    FeatureTemplateData(**out)


def test_interview_placeholder_ellipsis_replaced(sample_request: FeatureTemplateGenerateRequest) -> None:
    raw = {
        "interviewQuestions": [
            {
                "questionId": "q1",
                "question": "...",
                "keyPoints": ["..."],
                "sampleAnswer": "...",
            }
        ],
    }
    out = FeatureTemplateNormalizer.normalize(raw, sample_request)
    assert "..." not in out["interviewQuestions"][0]["question"]
    assert out["interviewQuestions"][0]["keyPoints"]
    FeatureTemplateData(**out)


def test_next_recommendations_padded_when_short(sample_request: FeatureTemplateGenerateRequest) -> None:
    raw = {"nextRecommendations": []}
    out = FeatureTemplateNormalizer.normalize(raw, sample_request)
    assert len(out["nextRecommendations"]) >= 3
    names = {x["featureName"] for x in out["nextRecommendations"]}
    assert "회원가입" in names or "JWT 인증" in names or "권한 관리" in names
    FeatureTemplateData(**out)


def test_codefiles_single_entry_padded_to_at_least_three(sample_request: FeatureTemplateGenerateRequest) -> None:
    raw = {
        "codeFiles": [
            {
                "fileName": "Only.java",
                "role": "main",
                "language": "java",
                "content": "class Only { }",
            }
        ],
    }
    out = FeatureTemplateNormalizer.normalize(raw, sample_request)
    assert len(out["codeFiles"]) >= 4
    FeatureTemplateData(**out)


def test_normalized_payload_has_no_placeholder_substrings(sample_request: FeatureTemplateGenerateRequest) -> None:
    raw = {
        "codeFiles": [
            {
                "fileName": "Bad.java",
                "role": "r",
                "language": "java",
                "content": "실제 동작 가능한 코드 문자열",
            }
        ],
        "interviewQuestions": [
            {
                "questionId": "q1",
                "question": "TODO 질문",
                "keyPoints": ["예시 코드"],
                "sampleAnswer": "생략",
            }
        ],
        "nextRecommendations": [],
    }
    out = FeatureTemplateNormalizer.normalize(raw, sample_request)
    _assert_no_placeholder_substrings(
        {
            "codeFiles": out["codeFiles"],
            "interviewQuestions": out["interviewQuestions"],
            "nextRecommendations": out["nextRecommendations"],
        }
    )
    assert "source" not in out
    FeatureTemplateData(**out)


def test_missions_goal_and_hints_absorbed_into_lists(sample_request: FeatureTemplateGenerateRequest) -> None:
    raw = {
        "missions": [
            {
                "missionId": "m1",
                "title": "t",
                "description": "d",
                "goal": "목표 한 줄",
                "hints": ["힌트1", "힌트2"],
            }
        ],
    }
    out = FeatureTemplateNormalizer.normalize(raw, sample_request)
    assert out["missions"][0]["requirements"] == ["목표 한 줄", "힌트1", "힌트2"]
    assert "goal" not in out["missions"][0]
    assert "hints" not in out["missions"][0]
    FeatureTemplateData(**out)


_LOGIN_CTRL_SNIPPET = """package com.example.auth;
import org.springframework.web.bind.annotation.RestController;
@RestController
public class LoginController { }
"""


def test_auth_service_controller_body_dropped_when_login_service_present(
    sample_request: FeatureTemplateGenerateRequest,
) -> None:
    raw = {
        "codeFiles": [
            {
                "fileName": "LoginService.java",
                "role": "svc",
                "language": "java",
                "content": "package com.example.auth;\n@Service\npublic class LoginService {\n  public String login() { return \"x\"; }\n}\n",
            },
            {
                "fileName": "AuthService.java",
                "role": "svc",
                "language": "java",
                "content": _LOGIN_CTRL_SNIPPET,
            },
        ],
    }
    out = FeatureTemplateNormalizer.normalize(raw, sample_request)
    names = [f["fileName"] for f in out["codeFiles"]]
    assert "AuthService.java" not in names
    svc = next(f for f in out["codeFiles"] if f["fileName"] == "LoginService.java")
    assert "@RestController" not in svc["content"]
    assert "class LoginService" in svc["content"]
    FeatureTemplateData(**out)


def test_login_service_with_rest_controller_replaced(sample_request: FeatureTemplateGenerateRequest) -> None:
    raw = {
        "codeFiles": [
            {
                "fileName": "LoginService.java",
                "role": "svc",
                "language": "java",
                "content": _LOGIN_CTRL_SNIPPET,
            },
        ],
    }
    out = FeatureTemplateNormalizer.normalize(raw, sample_request)
    svc = next(f for f in out["codeFiles"] if f["fileName"] == "LoginService.java")
    assert "@Service" in svc["content"]
    assert "@RestController" not in svc["content"]
    assert "login(LoginRequest request)" in svc["content"]
    FeatureTemplateData(**out)


def test_codefile_basename_strips_path(sample_request: FeatureTemplateGenerateRequest) -> None:
    raw = {
        "codeFiles": [
            {
                "fileName": "src/main/java/com/example/auth/LoginController.java",
                "role": "c",
                "language": "java",
                "content": _LOGIN_CTRL_SNIPPET,
            },
        ],
    }
    out = FeatureTemplateNormalizer.normalize(raw, sample_request)
    lc = next(f for f in out["codeFiles"] if f["fileName"] == "LoginController.java")
    assert lc["fileName"] == "LoginController.java"
    assert lc["filePath"].endswith("com/example/auth/LoginController.java")
    FeatureTemplateData(**out)


def test_codefile_filepath_matches_custom_package(sample_request: FeatureTemplateGenerateRequest) -> None:
    raw = {
        "codeFiles": [
            {
                "fileName": "LoginRequest.java",
                "role": "dto",
                "language": "java",
                "content": "package com.example.demo;\npublic record LoginRequest(String username, String password) {}\n",
            },
        ],
    }
    out = FeatureTemplateNormalizer.normalize(raw, sample_request)
    lr = next(f for f in out["codeFiles"] if f["fileName"] == "LoginRequest.java")
    assert "com/example/demo/LoginRequest.java" in lr["filePath"].replace("\\", "/")
    FeatureTemplateData(**out)


def test_duplicate_login_controller_deduped(sample_request: FeatureTemplateGenerateRequest) -> None:
    raw = {
        "codeFiles": [
            {"fileName": "LoginController.java", "role": "c", "language": "java", "content": _LOGIN_CTRL_SNIPPET},
            {
                "fileName": "LoginController.java",
                "role": "c2",
                "language": "java",
                "content": "package com.example.auth;\n@RestController\nclass LoginController { int b = 2; }\n",
            },
        ],
    }
    out = FeatureTemplateNormalizer.normalize(raw, sample_request)
    assert sum(1 for f in out["codeFiles"] if f["fileName"] == "LoginController.java") == 1
    FeatureTemplateData(**out)


def test_login_spring_has_four_canonical_files(sample_request: FeatureTemplateGenerateRequest) -> None:
    out = FeatureTemplateNormalizer.normalize({"codeFiles": []}, sample_request)
    names = [f["fileName"] for f in out["codeFiles"]]
    for req in ("LoginController.java", "LoginService.java", "LoginRequest.java", "LoginResponse.java"):
        assert req in names
    assert names.index("LoginController.java") < names.index("LoginService.java")
    FeatureTemplateData(**out)


def test_login_canonical_files_declare_matching_types(sample_request: FeatureTemplateGenerateRequest) -> None:
    out = FeatureTemplateNormalizer.normalize({"codeFiles": []}, sample_request)
    by = {f["fileName"]: f["content"] for f in out["codeFiles"]}
    assert "class LoginController" in by["LoginController.java"]
    assert "class LoginService" in by["LoginService.java"]
    assert "record LoginRequest" in by["LoginRequest.java"]
    assert "record LoginResponse" in by["LoginResponse.java"]


def test_login_codefiles_no_placeholders_and_no_source_key(sample_request: FeatureTemplateGenerateRequest) -> None:
    out = FeatureTemplateNormalizer.normalize(
        {
            "codeFiles": [
                {
                    "fileName": "LoginService.java",
                    "role": "x",
                    "language": "java",
                    "content": "실제 동작 가능한 코드 문자열",
                }
            ]
        },
        sample_request,
    )
    dumped = json.dumps(out["codeFiles"], ensure_ascii=False)
    for marker in (
        "실제 동작 가능한 코드 문자열",
        "...",
        "TODO",
        "예시 코드",
        "생략",
        "placeholder",
        "플레이스홀더",
    ):
        assert marker not in dumped
    assert "source" not in out
    FeatureTemplateData(**out)


def test_final_defense_adds_login_response_when_only_three_core_files(
    sample_request: FeatureTemplateGenerateRequest,
) -> None:
    from app.services import feature_template_normalizer as ft_norm

    canon = ft_norm._canonical_login_spring_four()
    raw = {
        "codeFiles": [
            dict(canon["LoginController.java"]),
            dict(canon["LoginService.java"]),
            dict(canon["LoginRequest.java"]),
        ],
    }
    out = FeatureTemplateNormalizer.normalize(raw, sample_request)
    names = [f["fileName"] for f in out["codeFiles"]]
    assert "LoginResponse.java" in names
    FeatureTemplateData(**out)


def test_final_defense_fills_empty_requirements_for_login(sample_request: FeatureTemplateGenerateRequest) -> None:
    out = FeatureTemplateNormalizer.normalize({"requirements": []}, sample_request)
    assert len(out["requirements"]) >= 3
    for r in out["requirements"]:
        assert r.get("priority")
        assert r.get("relatedScreenOrApi")
    FeatureTemplateData(**out)


def test_final_defense_default_requirement_ids(sample_request: FeatureTemplateGenerateRequest) -> None:
    out = FeatureTemplateNormalizer.normalize({"requirements": []}, sample_request)
    ids = [r["requirementId"] for r in out["requirements"]]
    assert "R-001" in ids and "R-002" in ids and "R-003" in ids
    FeatureTemplateData(**out)


def test_final_defense_does_not_add_source_key(sample_request: FeatureTemplateGenerateRequest) -> None:
    out = FeatureTemplateNormalizer.normalize(
        {
            "requirements": [],
            "codeFiles": [],
        },
        sample_request,
    )
    assert "source" not in out
    FeatureTemplateData(**out)

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
    # 로그인 도메인은 11차/19차 품질 정책에 따라 flow.steps/layers가 빈약하면 기본값으로 보정된다.
    assert len(out["flow"]["steps"]) >= 3
    assert len(out["flow"]["layers"]) >= 3
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
    assert len(out["basicQuestions"]) >= 3
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
    # 로그인 도메인 R-001~R-003은 11차 정책상 HIGH로 강제된다.
    assert out["requirements"][0]["priority"] == "HIGH"
    # 로그인 도메인은 relatedScreenOrApi를 POST /api/auth/login으로 정렬한다.
    assert out["requirements"][0]["relatedScreenOrApi"] == "POST /api/auth/login"
    template = FeatureTemplateData(**out)
    assert template.requirements[0].priority == "HIGH"
    assert template.requirements[0].relatedScreenOrApi == "POST /api/auth/login"


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
    assert out["missions"][1]["difficulty"] == "beginner"
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


def test_final_defense_include_code_snake_alias_still_runs_codefiles() -> None:
    from types import SimpleNamespace

    from app.services import feature_template_normalizer as ft

    canon = ft._canonical_login_spring_four()
    lc = dict(canon["LoginController.java"])
    lc["fileName"] = "src/main/java/com/example/auth/LoginController.java"
    one_req = {
        "requirementId": "r0",
        "name": "n",
        "description": "d",
        "inputValue": "i",
        "processCondition": "p",
        "successResult": "s",
        "failureResult": "f",
        "priority": "HIGH",
        "relatedScreenOrApi": "api",
    }
    req = SimpleNamespace(
        language="java",
        framework="spring-boot",
        featureName="로그인",
        level=DifficultyLevel.BEGINNER,
        include_code=True,
    )
    norm: dict = {"requirements": [one_req], "codeFiles": [lc, dict(canon["LoginService.java"])]}
    changed: list[str] = []
    ft._ensure_final_login_defense(norm, req, changed)
    names = [f["fileName"] for f in norm["codeFiles"]]
    assert len(norm["codeFiles"]) >= 4
    for need in ("LoginController.java", "LoginService.java", "LoginRequest.java", "LoginResponse.java"):
        assert need in names
    assert all("/" not in str(f.get("fileName", "")) for f in norm["codeFiles"])


def test_final_defense_long_path_normalized_to_basename(sample_request: FeatureTemplateGenerateRequest) -> None:
    from app.services import feature_template_normalizer as ft

    canon = ft._canonical_login_spring_four()
    raw = dict(canon["LoginController.java"])
    raw["fileName"] = "src/main/java/com/example/auth/LoginController.java"
    out = FeatureTemplateNormalizer.normalize(
        {
            "codeFiles": [raw, dict(canon["LoginService.java"])],
            "requirements": [
                {
                    "requirementId": "r0",
                    "name": "n",
                    "description": "d",
                    "inputValue": "i",
                    "processCondition": "p",
                    "successResult": "s",
                    "failureResult": "f",
                    "priority": "HIGH",
                    "relatedScreenOrApi": "api",
                }
            ],
        },
        sample_request,
    )
    lc = next(f for f in out["codeFiles"] if f["fileName"] == "LoginController.java")
    assert lc["fileName"] == "LoginController.java"
    assert "/" not in lc["fileName"]
    assert len(out["codeFiles"]) >= 4
    FeatureTemplateData(**out)


def test_final_defense_adds_request_and_response_when_missing_only_controller_service(
    sample_request: FeatureTemplateGenerateRequest,
) -> None:
    from app.services import feature_template_normalizer as ft

    canon = ft._canonical_login_spring_four()
    out = FeatureTemplateNormalizer.normalize(
        {
            "codeFiles": [dict(canon["LoginController.java"]), dict(canon["LoginService.java"])],
            "requirements": [
                {
                    "requirementId": "r0",
                    "name": "n",
                    "description": "d",
                    "inputValue": "i",
                    "processCondition": "p",
                    "successResult": "s",
                    "failureResult": "f",
                    "priority": "HIGH",
                    "relatedScreenOrApi": "api",
                }
            ],
        },
        sample_request,
    )
    names = [f["fileName"] for f in out["codeFiles"]]
    assert "LoginRequest.java" in names
    assert "LoginResponse.java" in names
    assert all("/" not in str(n) for n in names)
    FeatureTemplateData(**out)


def test_login_api_endpoint_and_body_are_normalized(sample_request: FeatureTemplateGenerateRequest) -> None:
    req = sample_request.model_copy(
        update={"includeCode": False, "includeMissions": False, "includeInterview": False}
    )
    raw = {
        "apiSpec": [
            {
                "apiName": "",
                "method": "POST",
                "endpoint": "/api/feature",
                "description": "",
                "requestBody": {},
                "responseBody": {},
                "status": 200,
            }
        ]
    }
    out = FeatureTemplateNormalizer.normalize(raw, req)
    api = out["apiSpec"][0]
    assert api["endpoint"] == "/api/auth/login"
    assert "email" in api["requestBody"]
    assert "password" in api["requestBody"]
    # 11차 정책은 responseBody에 success/message/data 래퍼를 사용한다.
    assert api["responseBody"]["data"]["accessToken"] == "string"
    assert api["responseBody"]["data"]["tokenType"] == "Bearer"
    assert "user" in api["responseBody"]["data"]
    assert out["codeFiles"] == []
    assert out["missions"] == []
    assert out["interviewQuestions"] == []
    FeatureTemplateData(**out)


def test_login_requirement_related_screen_or_api_is_normalized(
    sample_request: FeatureTemplateGenerateRequest,
) -> None:
    raw = {
        "requirements": [
            {
                "requirementId": "R-001",
                "name": "로그인",
                "description": "로그인한다.",
                "inputValue": "email/password",
                "processCondition": "검증",
                "successResult": "성공",
                "failureResult": "실패",
                "priority": "HIGH",
                "relatedScreenOrApi": "/api/feature",
            }
        ]
    }
    out = FeatureTemplateNormalizer.normalize(raw, sample_request)
    assert len(out["requirements"]) >= 3
    assert out["requirements"][0]["relatedScreenOrApi"] == "POST /api/auth/login"
    FeatureTemplateData(**out)


def test_login_basic_questions_are_padded_and_poor_values_fixed(
    sample_request: FeatureTemplateGenerateRequest,
) -> None:
    raw = {
        "basicQuestions": [
            {
                "questionId": "Q-001",
                "type": "multiple_choice",
                "question": "로그인 질문",
                "choices": ["A", "B", "C", "D"],
                "answer": "",
                "explanation": "설명",
                "relatedSection": "",
                "difficulty": "",
            }
        ]
    }
    out = FeatureTemplateNormalizer.normalize(raw, sample_request)
    assert len(out["basicQuestions"]) >= 3
    first = out["basicQuestions"][0]
    assert first["choices"] is None
    assert first["answer"]
    assert first["answer"] != "정답"
    assert first["explanation"]
    assert first["explanation"] != "설명"
    assert first["relatedSection"]
    assert first["difficulty"] == "beginner"
    FeatureTemplateData(**out)


def test_login_overview_learning_goals_are_filled(sample_request: FeatureTemplateGenerateRequest) -> None:
    raw = {"overview": {"featureName": "로그인", "learningGoals": []}}
    out = FeatureTemplateNormalizer.normalize(raw, sample_request)
    assert len(out["overview"]["learningGoals"]) >= 2
    assert any("토큰" in goal or "인증" in goal for goal in out["overview"]["learningGoals"])
    FeatureTemplateData(**out)


def test_login_quality_normalization_preserves_disabled_optional_sections(
    sample_request: FeatureTemplateGenerateRequest,
) -> None:
    req = sample_request.model_copy(
        update={"includeCode": False, "includeMissions": False, "includeInterview": False}
    )
    raw = {
        "codeFiles": [{"fileName": "X.java", "role": "x", "language": "java", "content": "x"}],
        "missions": [
            {
                "missionId": "M-1",
                "title": "x",
                "description": "x",
                "missionType": "implementation",
                "requirements": [],
                "successCriteria": [],
                "relatedRequirements": [],
                "difficulty": "beginner",
            }
        ],
        "interviewQuestions": [
            {
                "questionId": "I-1",
                "question": "x",
                "keyPoints": [],
                "sampleAnswer": "x",
                "relatedSection": "flow",
            }
        ],
        "apiSpec": [{"endpoint": "/api/feature", "status": 200}],
    }
    out = FeatureTemplateNormalizer.normalize(raw, req)
    assert out["codeFiles"] == []
    assert out["missions"] == []
    assert out["interviewQuestions"] == []
    assert out["apiSpec"][0]["endpoint"] == "/api/auth/login"
    FeatureTemplateData(**out)


# --- Agentic RAG 11차: 운영 품질 보정 추가 검증 ---------------------------------


def test_login_api_name_path_replaced_with_korean(
    sample_request: FeatureTemplateGenerateRequest,
) -> None:
    raw = {
        "apiSpec": [
            {
                "apiName": "/api/feature",
                "method": "POST",
                "endpoint": "/api/feature",
                "description": "",
                "requestBody": {"field": "email", "type": "string"},
                "responseBody": {"data": {"token": "example_token"}},
                "status": 200,
            }
        ]
    }
    out = FeatureTemplateNormalizer.normalize(raw, sample_request)
    api = out["apiSpec"][0]
    assert api["apiName"] in {"로그인 API", "로그인"}
    assert api["endpoint"] == "/api/auth/login"
    assert "email" in api["requestBody"]
    assert "password" in api["requestBody"]
    assert api["responseBody"]["data"]["accessToken"] == "string"
    FeatureTemplateData(**out)


def test_login_requirement_input_value_filled_when_blank(
    sample_request: FeatureTemplateGenerateRequest,
) -> None:
    raw = {
        "requirements": [
            {
                "requirementId": "R-001",
                "name": "",
                "description": "",
                "inputValue": "",
                "processCondition": "",
                "successResult": "",
                "failureResult": "",
                "priority": "",
                "relatedScreenOrApi": "",
            }
        ]
    }
    out = FeatureTemplateNormalizer.normalize(raw, sample_request)
    reqs = out["requirements"]
    assert len(reqs) >= 3
    assert reqs[0]["inputValue"]
    assert reqs[0]["processCondition"]
    assert reqs[0]["successResult"]
    assert reqs[0]["failureResult"]
    assert all(r["priority"] == "HIGH" for r in reqs[:3])
    assert all(
        "/api/auth/login" in r["relatedScreenOrApi"].lower()
        or "logincontroller" in r["relatedScreenOrApi"].lower()
        or "loginservice" in r["relatedScreenOrApi"].lower()
        or "loginresponse" in r["relatedScreenOrApi"].lower()
        for r in reqs[:3]
    )
    FeatureTemplateData(**out)


def test_login_flow_layers_expanded_when_only_controller(
    sample_request: FeatureTemplateGenerateRequest,
) -> None:
    raw = {
        "flow": {
            "steps": ["1. start"],
            "layers": [{"layer": "Controller", "role": "수신"}],
        }
    }
    out = FeatureTemplateNormalizer.normalize(raw, sample_request)
    layer_names = {layer["layer"] for layer in out["flow"]["layers"]}
    for required in ("Controller", "Service", "DB"):
        assert required in layer_names
    assert "Client" in layer_names
    assert len(out["flow"]["steps"]) >= 3
    FeatureTemplateData(**out)


def test_login_overview_learning_goals_include_layer_dto_bcrypt(
    sample_request: FeatureTemplateGenerateRequest,
) -> None:
    raw = {"overview": {"featureName": "로그인", "learningGoals": ["Spring Boot 사용"]}}
    out = FeatureTemplateNormalizer.normalize(raw, sample_request)
    goals = out["overview"]["learningGoals"]
    assert len(goals) >= 3
    joined = " ".join(goals)
    assert "Controller" in joined
    assert "DTO" in joined
    assert "BCrypt" in joined or "해시" in joined
    FeatureTemplateData(**out)


def test_login_next_recommendations_dedupe_space_variants_and_resort(
    sample_request: FeatureTemplateGenerateRequest,
) -> None:
    raw = {
        "nextRecommendations": [
            {
                "featureName": "회원 가입",
                "reason": "다음 학습",
                "expectedLearning": "회원 가입을 학습",
                "priority": 9,
            },
            {
                "featureName": "회원가입",
                "reason": "다음 학습",
                "expectedLearning": "회원가입을 학습",
                "priority": 9,
            },
            {
                "featureName": "JWT 인증",
                "reason": "토큰 인증",
                "expectedLearning": "JWT 학습",
                "priority": 9,
            },
        ]
    }
    out = FeatureTemplateNormalizer.normalize(raw, sample_request)
    names = [item["featureName"] for item in out["nextRecommendations"]]
    assert "회원 가입" not in names
    assert names.count("회원가입") == 1
    assert len(out["nextRecommendations"]) >= 3
    assert [item["priority"] for item in out["nextRecommendations"]] == list(
        range(1, len(out["nextRecommendations"]) + 1)
    )
    FeatureTemplateData(**out)


def test_login_quality_normalization_keeps_login_final_guard(
    sample_request: FeatureTemplateGenerateRequest,
) -> None:
    out = FeatureTemplateNormalizer.normalize({"codeFiles": []}, sample_request)
    names = [f["fileName"] for f in out["codeFiles"]]
    for required in (
        "LoginController.java",
        "LoginService.java",
        "LoginRequest.java",
        "LoginResponse.java",
    ):
        assert required in names
    FeatureTemplateData(**out)

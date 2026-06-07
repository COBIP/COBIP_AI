"""Spring Boot 로그인 LLM full-first 결과 품질 guard 검증."""

import json

import pytest

from app.models.enums import DifficultyLevel
from app.schemas.feature_template import FeatureTemplateData, FeatureTemplateGenerateRequest
from app.services.feature_template_normalizer import FeatureTemplateNormalizer


@pytest.fixture
def login_request() -> FeatureTemplateGenerateRequest:
    return FeatureTemplateGenerateRequest(
        language="Java",
        framework="Spring Boot",
        featureName="로그인",
        level=DifficultyLevel.BEGINNER,
        includeCode=True,
        includeMissions=True,
        includeInterview=True,
    )


def _llm_like_login_payload() -> dict:
    return {
        "overview": {
            "featureName": "로그인",
            "purpose": "사용자 인증",
            "useCases": ["회원 전용 페이지"],
            "resultDescription": "JWT 발급",
            "techStack": ["Java", "Spring Boot"],
            "learningGoals": ["인증 흐름"],
        },
        "requirements": [
            {
                "requirementId": "R-001",
                "name": "로그인 요청",
                "description": "로그인 페이지 방문 시 POST /api/feature 요청",
                "inputValue": "username, password",
                "processCondition": "검증",
                "successResult": "POST /api/feature 성공",
                "failureResult": "실패",
                "priority": "HIGH",
                "relatedScreenOrApi": "/api/feature",
            },
            {
                "requirementId": "R-002",
                "name": "인증",
                "description": "비밀번호 검증",
                "inputValue": "password",
                "processCondition": "BCrypt",
                "successResult": "성공",
                "failureResult": "401",
                "priority": "HIGH",
                "relatedScreenOrApi": "LoginService",
            },
            {
                "requirementId": "R-003",
                "name": "응답",
                "description": "토큰 반환",
                "inputValue": "user",
                "processCondition": "JWT",
                "successResult": "200",
                "failureResult": "-",
                "priority": "HIGH",
                "relatedScreenOrApi": "LoginResponse",
            },
        ],
        "flow": {
            "steps": [
                "1. POST /api/feature 요청",
                "2. 검증",
                "3. 응답",
            ],
            "layers": [{"layer": "Controller", "role": "수신"}],
        },
        "apiSpec": [
            {
                "apiName": "로그인",
                "method": "POST",
                "endpoint": "/api/feature",
                "description": "로그인",
                "requestBody": {"username": "u"},
                "responseBody": {"token": "t"},
                "status": 200,
            }
        ],
        "codeFiles": [
            {
                "fileName": "src/main/java/com/example/login/LoginRequest.java",
                "filePath": "src/main/java/com/example/login/LoginRequest.java",
                "role": "데이터 접근",
                "language": "java",
                "content": (
                    "package com.example.login;\n"
                    "public class LoginRequest {\n"
                    "  private String username;\n"
                    "  private String password;\n"
                    "  public String getUsername() { return username; }\n"
                    "  public String getPassword() { return password; }\n"
                    "}\n"
                ),
            },
            {
                "fileName": "LoginService.java",
                "filePath": "src/main/java/com/example/auth/LoginService.java",
                "role": "Service",
                "language": "java",
                "content": (
                    "package com.example.auth;\n"
                    "@Service\n"
                    "public class LoginService {\n"
                    "  public LoginResponse login(LoginRequest request) {\n"
                    "    String u = request.username();\n"
                    "    String p = request.password();\n"
                    "    return new LoginResponse(\"t\", \"Bearer\", u);\n"
                    "  }\n"
                    "}\n"
                ),
            },
            {
                "fileName": "LoginController.java",
                "filePath": "src/main/java/com/example/auth/LoginController.java",
                "role": "Controller",
                "language": "java",
                "content": (
                    "package com.example.auth;\n"
                    "@RestController\n"
                    "@RequestMapping(\"/api/auth\")\n"
                    "public class LoginController {\n"
                    "  private final LoginService loginService;\n"
                    "  public LoginController(LoginService loginService) { this.loginService = loginService; }\n"
                    "  @PostMapping(\"/login\")\n"
                    "  public ResponseEntity<LoginResponse> login(@RequestBody LoginRequest request) {\n"
                    "    return ResponseEntity.ok(loginService.login(request));\n"
                    "  }\n"
                    "}\n"
                ),
            },
        ],
        "basicQuestions": [
            {
                "questionId": "Q-1",
                "type": "short_answer",
                "question": "로그인 API endpoint는 POST /api/feature 입니까?",
                "choices": None,
                "answer": "POST /api/feature",
                "explanation": "/api/feature 로 요청",
                "relatedSection": "apiSpec",
                "difficulty": "beginner",
            }
        ],
        "missions": [
            {
                "missionId": "M-1",
                "title": "JWT",
                "description": "POST /api/feature 로 JWT 발급 구현",
                "missionType": "implementation",
                "requirements": ["POST /api/feature 호출"],
                "successCriteria": ["/api/feature 200 응답"],
                "relatedRequirements": ["R-001"],
                "difficulty": "beginner",
            },
            {
                "missionId": "M-2",
                "title": "검증",
                "description": "입력 검증",
                "missionType": "validation",
                "requirements": ["@Valid"],
                "successCriteria": ["400"],
                "relatedRequirements": ["R-002"],
                "difficulty": "beginner",
            },
        ],
        "interviewQuestions": [
            {
                "questionId": "IQ-1",
                "question": "POST /api/feature 흐름을 설명하시오",
                "keyPoints": ["/api/feature", "JWT"],
                "sampleAnswer": "POST /api/feature 후 토큰",
                "relatedSection": "flow",
            }
        ],
        "nextRecommendations": [],
    }


def _dump_has_api_feature(obj: object) -> bool:
    text = json.dumps(obj, ensure_ascii=False)
    return "/api/feature" in text


def test_login_full_first_scrubs_api_feature_placeholders(
    login_request: FeatureTemplateGenerateRequest,
) -> None:
    out = FeatureTemplateNormalizer.normalize(_llm_like_login_payload(), login_request)

    assert not _dump_has_api_feature(out["requirements"])
    assert not _dump_has_api_feature(out["flow"])
    assert out["apiSpec"][0]["endpoint"] == "/api/auth/login"
    assert not _dump_has_api_feature(out["basicQuestions"])
    assert not _dump_has_api_feature(out["missions"])
    assert not _dump_has_api_feature(out["interviewQuestions"])
    FeatureTemplateData(**out)


def test_login_codefiles_package_and_path_unified(
    login_request: FeatureTemplateGenerateRequest,
) -> None:
    out = FeatureTemplateNormalizer.normalize(_llm_like_login_payload(), login_request)
    by_name = {f["fileName"]: f for f in out["codeFiles"]}

    req = by_name["LoginRequest.java"]
    assert "/com/example/auth/" in req["filePath"]
    assert "package com.example.auth;" in req["content"]
    assert "com.example.login" not in req["content"]

    svc = by_name["LoginService.java"]
    assert "/com/example/auth/" in svc["filePath"]
    assert "package com.example.auth;" in svc["content"]
    FeatureTemplateData(**out)


def test_login_service_uses_getter_accessors_for_class_dto(
    login_request: FeatureTemplateGenerateRequest,
) -> None:
    out = FeatureTemplateNormalizer.normalize(_llm_like_login_payload(), login_request)
    svc = next(f for f in out["codeFiles"] if f["fileName"] == "LoginService.java")
    assert "request.getUsername()" in svc["content"]
    assert "request.getPassword()" in svc["content"]
    assert "request.username()" not in svc["content"]
    assert "request.password()" not in svc["content"]


def test_login_request_role_is_request_dto(
    login_request: FeatureTemplateGenerateRequest,
) -> None:
    out = FeatureTemplateNormalizer.normalize(_llm_like_login_payload(), login_request)
    req = next(f for f in out["codeFiles"] if f["fileName"] == "LoginRequest.java")
    assert req["role"] == "요청 DTO"


def test_login_spring_boot_four_core_codefiles_guaranteed(
    login_request: FeatureTemplateGenerateRequest,
) -> None:
    out = FeatureTemplateNormalizer.normalize(_llm_like_login_payload(), login_request)
    names = {f["fileName"] for f in out["codeFiles"]}
    for required in (
        "LoginController.java",
        "LoginService.java",
        "LoginRequest.java",
        "LoginResponse.java",
    ):
        assert required in names

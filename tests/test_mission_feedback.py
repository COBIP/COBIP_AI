"""Mission feedback evidence grader + API contract tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.models.enums import DifficultyLevel
from app.schemas.evaluation import MissionFeedbackRequest
from app.services.feature_template_bucket_guards import _canonical_crud_codefiles, _canonical_jwt_codefiles, _canonical_signup_codefiles
from app.services.mission_feedback_service import MissionFeedbackService

_RESPONSE_FIELDS = frozenset(
    {
        "passed",
        "score",
        "summary",
        "satisfiedRequirements",
        "missingRequirements",
        "apiSpecIssues",
        "codeIssues",
        "improvementSuggestions",
        "nextAction",
    }
)


def _signup_canonical_submitted() -> list[dict]:
    return [
        {
            "fileName": name,
            "filePath": item["filePath"],
            "language": "java",
            "content": item["content"],
        }
        for name, item in _canonical_signup_codefiles().items()
    ]


def _crud_canonical_submitted() -> list[dict]:
    return [
        {
            "fileName": name,
            "filePath": item["filePath"],
            "language": "java",
            "content": item["content"],
        }
        for name, item in _canonical_crud_codefiles().items()
    ]


def _jwt_canonical_submitted() -> list[dict]:
    return [
        {
            "fileName": name,
            "filePath": item["filePath"],
            "language": "java",
            "content": item["content"],
        }
        for name, item in _canonical_jwt_codefiles().items()
    ]


def _signup_five_requirements() -> list[dict]:
    return [
        {
            "requirementId": "R-001",
            "name": "입력값 검증",
            "description": "email password nickname validation",
            "inputValue": "dto",
            "processCondition": "valid",
            "successResult": "ok",
            "failureResult": "400",
            "priority": "HIGH",
            "relatedScreenOrApi": "POST /api/auth/signup",
        },
        {
            "requirementId": "R-002",
            "name": "이메일 중복 검사",
            "description": "existsByEmail duplicate email",
            "inputValue": "email",
            "processCondition": "unique",
            "successResult": "ok",
            "failureResult": "409",
            "priority": "HIGH",
            "relatedScreenOrApi": "SignupService",
        },
        {
            "requirementId": "R-003",
            "name": "비밀번호 해시 저장",
            "description": "PasswordEncoder BCrypt hash password",
            "inputValue": "password",
            "processCondition": "encode",
            "successResult": "201",
            "failureResult": "400",
            "priority": "HIGH",
            "relatedScreenOrApi": "POST /api/auth/signup",
        },
        {
            "requirementId": "R-004",
            "name": "회원 저장",
            "description": "User UserRepository save signup",
            "inputValue": "dto",
            "processCondition": "persist",
            "successResult": "saved",
            "failureResult": "409",
            "priority": "HIGH",
            "relatedScreenOrApi": "UserRepository",
        },
        {
            "requirementId": "R-005",
            "name": "회원가입 성공 응답",
            "description": "SignupResponse signup response",
            "inputValue": "result",
            "processCondition": "201",
            "successResult": "ok",
            "failureResult": "400",
            "priority": "HIGH",
            "relatedScreenOrApi": "POST /api/auth/signup",
        },
    ]


def _signup_partial_evidence_code() -> list[dict]:
    """운영 재현: 핵심 endpoint/controller는 있으나 evidence 4건 수준."""

    return [
        {
            "fileName": "SignupController.java",
            "filePath": "src/main/java/com/example/auth/SignupController.java",
            "language": "java",
            "content": """
package com.example.auth;
import org.springframework.web.bind.annotation.*;
@RestController
@RequestMapping("/api/auth")
public class SignupController {
    private final SignupService signupService;
    public SignupController(SignupService signupService) { this.signupService = signupService; }
    @PostMapping("/signup")
    public SignupResponse signup(@RequestBody SignupRequest request) {
        return signupService.signup(request);
    }
}
""",
        },
        {
            "fileName": "SignupService.java",
            "filePath": "src/main/java/com/example/auth/SignupService.java",
            "language": "java",
            "content": """
package com.example.auth;
import org.springframework.stereotype.Service;
@Service
public class SignupService {
    private final UserRepository userRepository;
    public SignupService(UserRepository userRepository) { this.userRepository = userRepository; }
    public SignupResponse signup(SignupRequest request) {
        if (userRepository.existsByEmail(request.getEmail())) {
            throw new IllegalStateException("duplicate");
        }
        return new SignupResponse(1L, request.getEmail(), request.getNickname());
    }
}
""",
        },
        {
            "fileName": "SignupRequest.java",
            "filePath": "src/main/java/com/example/auth/SignupRequest.java",
            "language": "java",
            "content": "package com.example.auth; public class SignupRequest { private String email; private String nickname; public String getEmail(){return email;} public String getNickname(){return nickname;} }",
        },
        {
            "fileName": "UserRepository.java",
            "filePath": "src/main/java/com/example/auth/UserRepository.java",
            "language": "java",
            "content": "package com.example.auth; public interface UserRepository { boolean existsByEmail(String email); }",
        },
    ]


def _base_mission_payload(
    feature_name: str,
    submitted: list[dict],
    *,
    api_specs: list[dict] | None = None,
) -> dict:
    if feature_name == "회원가입":
        api_specs = api_specs or [
            {
                "apiName": "회원가입",
                "method": "POST",
                "endpoint": "/api/auth/signup",
                "description": "signup",
                "requestBody": {},
                "responseBody": {},
                "status": 201,
            }
        ]
        requirements = [
            {
                "requirementId": "R-001",
                "name": "입력값 검증",
                "description": "email password nickname validation",
                "inputValue": "dto",
                "processCondition": "valid",
                "successResult": "ok",
                "failureResult": "400",
                "priority": "HIGH",
                "relatedScreenOrApi": "POST /api/auth/signup",
            },
            {
                "requirementId": "R-002",
                "name": "이메일 중복 검사",
                "description": "existsByEmail duplicate",
                "inputValue": "email",
                "processCondition": "unique",
                "successResult": "ok",
                "failureResult": "409",
                "priority": "HIGH",
                "relatedScreenOrApi": "SignupService",
            },
            {
                "requirementId": "R-003",
                "name": "비밀번호 해시 저장",
                "description": "PasswordEncoder BCrypt hash",
                "inputValue": "password",
                "processCondition": "encode",
                "successResult": "201",
                "failureResult": "400",
                "priority": "HIGH",
                "relatedScreenOrApi": "POST /api/auth/signup",
            },
        ]
    elif "CRUD" in feature_name:
        api_specs = api_specs or [
            {"apiName": "create", "method": "POST", "endpoint": "/api/posts", "description": "d", "requestBody": {}, "responseBody": {}, "status": 201},
            {"apiName": "list", "method": "GET", "endpoint": "/api/posts", "description": "d", "requestBody": {}, "responseBody": {}, "status": 200},
            {"apiName": "get", "method": "GET", "endpoint": "/api/posts/{postId}", "description": "d", "requestBody": {}, "responseBody": {}, "status": 200},
            {"apiName": "update", "method": "PUT", "endpoint": "/api/posts/{postId}", "description": "d", "requestBody": {}, "responseBody": {}, "status": 200},
            {"apiName": "delete", "method": "DELETE", "endpoint": "/api/posts/{postId}", "description": "d", "requestBody": {}, "responseBody": {}, "status": 204},
        ]
        requirements = [
            {
                "requirementId": f"R-00{i}",
                "name": name,
                "description": f"{name} PostController PostService PostRepository",
                "inputValue": "dto",
                "processCondition": "ok",
                "successResult": "200",
                "failureResult": "404",
                "priority": "HIGH",
                "relatedScreenOrApi": "/api/posts",
            }
            for i, name in enumerate(
                ["게시글 생성", "게시글 목록 조회", "게시글 단건 조회", "게시글 수정", "게시글 삭제"],
                start=1,
            )
        ]
    else:
        api_specs = api_specs or [
            {"apiName": "login", "method": "POST", "endpoint": "/api/auth/login", "description": "d", "requestBody": {}, "responseBody": {}, "status": 200},
            {"apiName": "me", "method": "GET", "endpoint": "/api/users/me", "description": "d", "requestBody": {}, "responseBody": {}, "status": 200},
        ]
        requirements = [
            {
                "requirementId": "R-001",
                "name": "JWT 로그인",
                "description": "login JwtTokenProvider token",
                "inputValue": "credentials",
                "processCondition": "auth",
                "successResult": "token",
                "failureResult": "401",
                "priority": "HIGH",
                "relatedScreenOrApi": "POST /api/auth/login",
            },
            {
                "requirementId": "R-002",
                "name": "보호 API 인증",
                "description": "JwtAuthenticationFilter Bearer SecurityConfig",
                "inputValue": "header",
                "processCondition": "valid token",
                "successResult": "200",
                "failureResult": "401",
                "priority": "HIGH",
                "relatedScreenOrApi": "GET /api/users/me",
            },
        ]

    return {
        "featureName": feature_name,
        "mission": {
            "missionId": "M-001",
            "title": "구현 미션",
            "description": "기능 구현",
            "missionType": "implementation",
            "requirements": ["구현"],
            "successCriteria": ["동작"],
            "relatedRequirements": ["R-001"],
            "difficulty": DifficultyLevel.BEGINNER.value,
        },
        "submittedCode": submitted,
        "requirements": requirements,
        "apiSpecs": api_specs,
    }


class TestMissionFeedbackGrader:
    def test_signup_canonical_passes(self) -> None:
        req = MissionFeedbackRequest(**_base_mission_payload("회원가입", _signup_canonical_submitted()))
        result = MissionFeedbackService().generate_feedback(req)
        assert result.score >= 70
        assert result.passed is True

    def test_signup_partial_evidence_score_70_plus_passes(self) -> None:
        """운영 케이스: requirements 5/5, evidence ~4건, score>=70 → passed=true."""

        payload = _base_mission_payload("회원가입", _signup_partial_evidence_code())
        payload["requirements"] = _signup_five_requirements()
        req = MissionFeedbackRequest(**payload)
        result = MissionFeedbackService().generate_feedback(req)
        assert len(result.satisfiedRequirements) == 5
        assert result.score >= 70
        assert result.apiSpecIssues == []
        assert result.codeIssues == []
        assert result.passed is True
        assert "evidence" in result.summary

    def test_crud_canonical_passes(self) -> None:
        req = MissionFeedbackRequest(
            **_base_mission_payload("게시글 CRUD", _crud_canonical_submitted())
        )
        result = MissionFeedbackService().generate_feedback(req)
        assert result.score >= 70
        assert result.passed is True

    def test_jwt_canonical_passes(self) -> None:
        req = MissionFeedbackRequest(
            **_base_mission_payload("JWT 인증", _jwt_canonical_submitted())
        )
        result = MissionFeedbackService().generate_feedback(req)
        assert result.score >= 70
        assert result.passed is True

    def test_empty_submitted_fails(self) -> None:
        req = MissionFeedbackRequest(**_base_mission_payload("회원가입", []))
        result = MissionFeedbackService().generate_feedback(req)
        assert result.passed is False
        assert result.score == 0

    def test_missing_endpoint_fails(self) -> None:
        bad = [
            {
                "fileName": "OnlyService.java",
                "filePath": None,
                "language": "java",
                "content": "class OnlyService { void run() {} }",
            }
        ]
        req = MissionFeedbackRequest(**_base_mission_payload("회원가입", bad))
        result = MissionFeedbackService().generate_feedback(req)
        assert result.passed is False

    def test_failed_feedback_is_coaching_style(self) -> None:
        """불합격: summary가 문제+수정방향을 설명하고, missing/suggestion/nextAction이 구체적."""
        bad = [
            {
                "fileName": "OnlyService.java",
                "filePath": None,
                "language": "java",
                "content": "class OnlyService { void run() {} }",
            }
        ]
        req = MissionFeedbackRequest(**_base_mission_payload("회원가입", bad))
        result = MissionFeedbackService().generate_feedback(req)

        # summary는 점수만이 아니라 가장 큰 문제 + 수정 방향을 설명한다.
        assert "evidence" in result.summary
        assert "가장 큰 문제" in result.summary
        assert "수정 방향" in result.summary

        # missingRequirements는 이름 나열이 아니라 이유 + 구현 위치를 포함한다.
        assert result.missingRequirements
        assert any("필요하며" in item and "구현" in item for item in result.missingRequirements)

        # improvementSuggestions는 바로 따라 할 수 있는 액션 문장이다.
        assert result.improvementSuggestions
        assert any(
            ("@Valid" in s) or ("PasswordEncoder" in s) or ("repository" in s)
            for s in result.improvementSuggestions
        )

        # nextAction은 가장 먼저 할 일 하나를 제시한다.
        assert result.nextAction.startswith("가장 먼저")

    def test_passed_summary_and_next_action_are_descriptive(self) -> None:
        req = MissionFeedbackRequest(
            **_base_mission_payload("회원가입", _signup_canonical_submitted())
        )
        result = MissionFeedbackService().generate_feedback(req)
        assert result.passed is True
        assert "통과" in result.summary
        assert len(result.nextAction) > 15

    def test_password_code_issue_has_cause_impact_fix(self) -> None:
        insecure = [
            {
                "fileName": "SignupController.java",
                "filePath": None,
                "language": "java",
                "content": (
                    '@RestController\n'
                    '@RequestMapping("/api/auth")\n'
                    'class SignupController {\n'
                    '  @PostMapping("/signup")\n'
                    '  String signup(@RequestBody SignupRequest r) {\n'
                    '    String password = r.getPassword();\n'
                    '    repository.save(password);\n'
                    '    return "ok";\n'
                    '  }\n'
                    '}\n'
                ),
            }
        ]
        req = MissionFeedbackRequest(**_base_mission_payload("회원가입", insecure))
        result = MissionFeedbackService().generate_feedback(req)
        assert result.codeIssues
        issue = result.codeIssues[0]
        assert "원인" in issue.message and "영향" in issue.message
        assert "수정" in issue.suggestion

    def test_missing_controller_fails(self) -> None:
        bad = [
            {
                "fileName": "Helper.java",
                "filePath": None,
                "language": "java",
                "content": '@PostMapping("/api/auth/signup") class Helper { void signup() {} }',
            }
        ]
        req = MissionFeedbackRequest(**_base_mission_payload("회원가입", bad))
        result = MissionFeedbackService().generate_feedback(req)
        assert result.passed is False

    def test_renamed_file_content_still_counts(self) -> None:
        canonical = _signup_canonical_submitted()
        canonical[0]["fileName"] = "MySignupController.java"
        req = MissionFeedbackRequest(**_base_mission_payload("회원가입", canonical))
        result = MissionFeedbackService().generate_feedback(req)
        assert result.score >= 70

    def test_fe_api_spec_alias_no_422(self) -> None:
        payload = _base_mission_payload("회원가입", _signup_canonical_submitted())
        payload["apiSpec"] = payload.pop("apiSpecs")
        payload["apiSpec"][0]["requestHeaders"] = {"Content-Type": "application/json"}
        MissionFeedbackRequest(**payload)


class TestMissionFeedbackApi:
    def test_endpoint_contract(self) -> None:
        client = TestClient(app)
        payload = _base_mission_payload("회원가입", _signup_canonical_submitted())
        resp = client.post("/ai/mission/feedback", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("success") is True
        data = body["data"]
        assert set(data.keys()) == _RESPONSE_FIELDS
        assert data["score"] >= 70
        assert data["passed"] is True

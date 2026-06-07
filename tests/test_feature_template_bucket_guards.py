"""기능 bucket guard — 운영 재현 케이스 검증."""

from __future__ import annotations

import pytest

from app.models.enums import DifficultyLevel
from app.schemas.feature_template import FeatureTemplateData, FeatureTemplateGenerateRequest
from app.services.feature_template_bucket_guards import detect_feature_template_bucket
from app.services.feature_template_normalizer import FeatureTemplateNormalizer
from app.services.prompt_builder import build_feature_template_prompt_with_applied_rags


def _req(feature_name: str, **kwargs: object) -> FeatureTemplateGenerateRequest:
    base = dict(
        language="Java",
        framework="Spring Boot",
        featureName=feature_name,
        level=DifficultyLevel.BEGINNER,
        includeCode=True,
        includeMissions=True,
        includeInterview=True,
    )
    base.update(kwargs)
    return FeatureTemplateGenerateRequest(**base)


def _bad_app_login_codefiles() -> list[dict]:
    return [
        {
            "fileName": "AppController.java",
            "filePath": None,
            "role": "데이터 접근",
            "language": "java",
            "content": """
package com.example.auth;
@RestController
public class AppController {
  @PostMapping("/login")
  public void login() {}
}
""",
        },
        {
            "fileName": "AppService.java",
            "filePath": None,
            "role": "데이터 접근",
            "language": "java",
            "content": "class AppService { void login(String username, String password) {} }",
        },
    ]


class TestBucketDetection:
    @pytest.mark.parametrize(
        "name,expected",
        [
            ("로그인", "login"),
            ("회원가입", "signup"),
            ("게시글 CRUD", "crud"),
            ("JWT 인증", "jwt_auth"),
            ("댓글 작성", "generic"),
        ],
    )
    def test_detect_bucket(self, name: str, expected: str) -> None:
        assert detect_feature_template_bucket(name, "Spring Boot") == expected


class TestSignupBucketGuard:
    def test_signup_bad_llm_output_corrected(self) -> None:
        raw = {
            "overview": {
                "featureName": "회원가입",
                "purpose": "",
                "useCases": [],
                "resultDescription": "",
                "techStack": [],
                "learningGoals": [],
            },
            "requirements": [],
            "flow": {"steps": [], "layers": []},
            "apiSpec": [],
            "codeFiles": _bad_app_login_codefiles(),
            "basicQuestions": [],
            "missions": [],
            "interviewQuestions": [
                {
                    "questionId": "IQ-001",
                    "question": "로그인 흐름?",
                    "keyPoints": [],
                    "sampleAnswer": "login",
                    "relatedSection": "flow",
                }
            ],
            "nextRecommendations": [],
        }
        out = FeatureTemplateNormalizer.normalize(raw, _req("회원가입"))
        FeatureTemplateData(**out)
        names = {f["fileName"] for f in out["codeFiles"]}
        blob = str(out)
        assert "SignupController.java" in names
        assert "SignupService.java" in names
        assert "UserRepository.java" in names
        assert "/api/auth/signup" in blob
        assert "AppController" not in blob
        assert "/api/auth/login" not in blob
        assert len(out["requirements"]) >= 3
        assert len(out["apiSpec"]) >= 1
        assert len(out["flow"]["steps"]) >= 3
        assert len(out["basicQuestions"]) >= 3
        for f in out["codeFiles"]:
            assert f.get("filePath")
            assert f["filePath"].endswith(f["fileName"])


class TestCrudBucketGuard:
    def test_crud_bad_llm_output_corrected(self) -> None:
        raw = {
            "overview": {
                "featureName": "게시글 CRUD",
                "purpose": "",
                "useCases": [],
                "resultDescription": "",
                "techStack": [],
                "learningGoals": [],
            },
            "requirements": [],
            "flow": {"steps": [], "layers": []},
            "apiSpec": [],
            "codeFiles": [
                {
                    "fileName": "CRUDController.java",
                    "filePath": None,
                    "role": "데이터 접근",
                    "language": "java",
                    "content": '@PostMapping("/login") class CRUDController { UserRepository repo; }',
                }
            ],
            "basicQuestions": [],
            "missions": [],
            "interviewQuestions": [],
            "nextRecommendations": [],
        }
        out = FeatureTemplateNormalizer.normalize(
            raw, _req("게시글 CRUD", includeMissions=False, includeInterview=False)
        )
        names = {f["fileName"] for f in out["codeFiles"]}
        blob = str(out)
        for req in (
            "PostController.java",
            "PostService.java",
            "PostRepository.java",
            "Post.java",
            "PostCreateRequest.java",
            "PostUpdateRequest.java",
            "PostResponse.java",
        ):
            assert req in names
        assert "/api/posts" in blob
        assert "CRUDController" not in blob
        assert "UserRepository" not in blob
        assert "/api/auth/login" not in blob
        assert len(out["apiSpec"]) >= 5
        by = {f["fileName"]: f["role"] for f in out["codeFiles"]}
        assert by["PostController.java"] == "REST API 컨트롤러"
        assert by["PostRepository.java"] == "데이터 접근 Repository"
        assert by["PostCreateRequest.java"] == "요청 DTO"


class TestJwtBucketGuard:
    def test_jwt_mismatched_files_corrected(self) -> None:
        raw = {
            "overview": {
                "featureName": "JWT 인증",
                "purpose": "",
                "useCases": [],
                "resultDescription": "",
                "techStack": [],
                "learningGoals": [],
            },
            "requirements": [],
            "flow": {"steps": [], "layers": []},
            "apiSpec": [],
            "codeFiles": [
                {
                    "fileName": "JWTController.java",
                    "filePath": "src/main/java/com/example/auth/JwtTokenProvider.java",
                    "role": "REST API 컨트롤러",
                    "language": "java",
                    "content": "public class JWTController {}",
                },
                {
                    "fileName": "JWTController.java",
                    "filePath": "src/main/java/com/example/auth/JwtAuthenticationFilter.java",
                    "role": "REST API 컨트롤러",
                    "language": "java",
                    "content": "public class JWTController {}",
                },
                {
                    "fileName": "JWTController.java",
                    "filePath": "src/main/java/com/example/auth/SecurityConfig.java",
                    "role": "REST API 컨트롤러",
                    "language": "java",
                    "content": "public class JWTController {}",
                },
            ],
            "basicQuestions": [],
            "missions": [],
            "interviewQuestions": [],
            "nextRecommendations": [],
        }
        out = FeatureTemplateNormalizer.normalize(
            raw,
            _req(
                "JWT 인증",
                level=DifficultyLevel.INTERMEDIATE,
                includeMissions=False,
                includeInterview=False,
            ),
        )
        names = [f["fileName"] for f in out["codeFiles"]]
        assert names.count("JWTController.java") == 0
        assert "JwtTokenProvider.java" in names
        assert "JwtAuthenticationFilter.java" in names
        assert "SecurityConfig.java" in names
        assert "CustomUserDetailsService.java" in names
        by = {f["fileName"]: f for f in out["codeFiles"]}
        assert by["JwtTokenProvider.java"]["role"] == "인증/토큰 Provider"
        assert by["JwtAuthenticationFilter.java"]["role"] == "인증/인가 필터"
        assert by["SecurityConfig.java"]["role"] == "설정 클래스"
        blob = str(out)
        assert "/api/auth/login" in blob
        assert "AuthController.java" in names
        endpoints = [s.get("endpoint", "") for s in out.get("apiSpec", []) if isinstance(s, dict)]
        assert "/api/auth/login" in endpoints
        for f in out["codeFiles"]:
            fn = f["fileName"]
            assert f["filePath"].endswith(fn)
            cls = fn[:-5]
            assert f"class {cls}" in f["content"] or f"interface {cls}" in f["content"]


class TestGenericBucketGuard:
    def test_unknown_feature_gets_baseline(self) -> None:
        raw = {
            "overview": {
                "featureName": "댓글 작성",
                "purpose": "",
                "useCases": [],
                "resultDescription": "",
                "techStack": [],
                "learningGoals": [],
            },
            "requirements": [],
            "flow": {"steps": [], "layers": []},
            "apiSpec": [],
            "codeFiles": [{"fileName": "X.java", "role": "데이터 접근", "language": "java", "content": ""}],
            "basicQuestions": [],
            "missions": [],
            "interviewQuestions": [],
            "nextRecommendations": [],
        }
        out = FeatureTemplateNormalizer.normalize(
            raw, _req("댓글 작성", includeMissions=False, includeInterview=False)
        )
        assert len(out["requirements"]) >= 3
        assert len(out["apiSpec"]) >= 1
        assert len(out["flow"]["steps"]) >= 3
        assert len(out["codeFiles"]) >= 4
        for f in out["codeFiles"]:
            assert f.get("filePath")
            assert f["role"] != "데이터 접근"


class TestBucketPromptConstraints:
    def test_signup_prompt_has_bucket_constraints(self) -> None:
        prompt, _, _ = build_feature_template_prompt_with_applied_rags(_req("회원가입"))
        assert "signup" in prompt
        assert "SignupController" in prompt
        assert "/api/auth/signup" in prompt

    def test_jwt_prompt_allows_login_endpoint(self) -> None:
        prompt, _, _ = build_feature_template_prompt_with_applied_rags(
            _req("JWT 인증", includeMissions=False, includeInterview=False)
        )
        assert "jwt_auth" in prompt
        assert "POST /api/auth/login" in prompt
        assert "GET /api/users/me" in prompt

    def test_crud_prompt_has_bucket_constraints(self) -> None:
        prompt, _, _ = build_feature_template_prompt_with_applied_rags(
            _req("게시글 CRUD", includeMissions=False, includeInterview=False)
        )
        assert "crud" in prompt.lower()
        assert "PostController" in prompt

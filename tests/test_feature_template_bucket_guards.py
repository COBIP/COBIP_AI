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


def _crud_junk_module_codefiles() -> list[dict]:
    junk = []
    for i in range(3):
        junk.append(
            {
                "fileName": f"module_{i}.py.java",
                "filePath": f"src/main/java/com/example/post/module_{i}.py.java",
                "role": "데이터 접근",
                "language": "java",
                "content": f"public class module_{i} {{}}",
            }
        )
    return junk


def _crud_canonical_codefiles() -> list[dict]:
    return [
        {
            "fileName": "PostController.java",
            "filePath": "src/main/java/com/example/post/PostController.java",
            "role": "REST API 컨트롤러",
            "language": "java",
            "content": "package com.example.post;\npublic class PostController {}",
        },
        {
            "fileName": "PostService.java",
            "filePath": "src/main/java/com/example/post/PostService.java",
            "role": "비즈니스 로직 서비스",
            "language": "java",
            "content": "package com.example.post;\npublic class PostService {}",
        },
        {
            "fileName": "PostRepository.java",
            "filePath": "src/main/java/com/example/post/PostRepository.java",
            "role": "데이터 접근 Repository",
            "language": "java",
            "content": "package com.example.post;\npublic interface PostRepository {}",
        },
        {
            "fileName": "Post.java",
            "filePath": "src/main/java/com/example/post/Post.java",
            "role": "엔티티",
            "language": "java",
            "content": "package com.example.post;\npublic class Post {}",
        },
        {
            "fileName": "PostCreateRequest.java",
            "filePath": "src/main/java/com/example/post/PostCreateRequest.java",
            "role": "요청 DTO",
            "language": "java",
            "content": "package com.example.post;\npublic class PostCreateRequest {}",
        },
        {
            "fileName": "PostUpdateRequest.java",
            "filePath": "src/main/java/com/example/post/PostUpdateRequest.java",
            "role": "요청 DTO",
            "language": "java",
            "content": "package com.example.post;\npublic class PostUpdateRequest {}",
        },
        {
            "fileName": "PostResponse.java",
            "filePath": "src/main/java/com/example/post/PostResponse.java",
            "role": "응답 DTO",
            "language": "java",
            "content": "package com.example.post;\npublic class PostResponse {}",
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

    def test_signup_strips_login_and_users_me_from_api_spec(self) -> None:
        """운영 flaky 재현: LLM이 login/users/me endpoint를 섞어도 signup만 유지."""

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
            "apiSpec": [
                {
                    "apiName": "회원가입",
                    "method": "POST",
                    "endpoint": "/api/auth/signup",
                    "requestBody": {"email": "a@b.com", "password": "pw", "nickname": "n"},
                    "responseBody": {"userId": 1},
                    "status": 201,
                },
                {
                    "apiName": "로그인",
                    "method": "POST",
                    "endpoint": "/api/auth/login",
                    "requestBody": {"email": "a@b.com", "password": "pw"},
                    "responseBody": {"accessToken": "jwt"},
                    "status": 200,
                },
                {
                    "apiName": "내 정보",
                    "method": "GET",
                    "endpoint": "/api/users/me",
                    "requestHeaders": {"Authorization": "Bearer token"},
                    "responseBody": {"email": "a@b.com"},
                    "status": 200,
                },
            ],
            "codeFiles": _bad_app_login_codefiles()
            + [
                {
                    "fileName": "module_0.py.java",
                    "filePath": "src/main/java/com/example/auth/module_0.py.java",
                    "role": "데이터 접근",
                    "language": "java",
                    "content": "public class module_0 {}",
                }
            ],
            "basicQuestions": [],
            "missions": [],
            "interviewQuestions": [],
            "nextRecommendations": [],
        }
        out = FeatureTemplateNormalizer.normalize(
            raw, _req("회원가입", includeMissions=False, includeInterview=False)
        )
        FeatureTemplateData(**out)

        methods = {
            (str(s.get("method", "")).upper(), s.get("endpoint", ""))
            for s in out.get("apiSpec", [])
            if isinstance(s, dict)
        }
        names = {f["fileName"] for f in out["codeFiles"]}
        blob = str(out)
        assert len(out["apiSpec"]) == 1
        assert methods == {("POST", "/api/auth/signup")}
        assert "/api/auth/login" not in blob
        assert "/api/users/me" not in blob
        assert "AppController" not in blob
        assert "module_" not in blob
        for req in (
            "SignupController.java",
            "SignupService.java",
            "SignupRequest.java",
            "SignupResponse.java",
            "User.java",
            "UserRepository.java",
        ):
            assert req in names
        _assert_api_spec_schema_fields(out["apiSpec"])


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

    def test_crud_strips_module_py_java_junk(self) -> None:
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
            "apiSpec": [
                {"method": "POST", "endpoint": "/api/posts"},
                {"method": "GET", "endpoint": "/api/posts"},
                {"method": "GET", "endpoint": "/api/posts/{postId}"},
                {"method": "PUT", "endpoint": "/api/posts/{postId}"},
                {"method": "DELETE", "endpoint": "/api/posts/{postId}"},
            ],
            "codeFiles": _crud_canonical_codefiles() + _crud_junk_module_codefiles(),
            "basicQuestions": [],
            "missions": [],
            "interviewQuestions": [],
            "nextRecommendations": [],
        }
        out = FeatureTemplateNormalizer.normalize(
            raw, _req("게시글 CRUD", includeMissions=False, includeInterview=False)
        )
        names = {f["fileName"] for f in out["codeFiles"]}
        assert len(out["codeFiles"]) == 7
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
        blob = str(out)
        assert "module_" not in blob
        assert ".py.java" not in blob
        assert "AppController" not in blob
        assert "CRUDController" not in blob
        assert "/api/auth/login" not in blob
        endpoints = [s.get("endpoint", "") for s in out.get("apiSpec", []) if isinstance(s, dict)]
        assert endpoints.count("/api/posts") >= 1
        assert len(endpoints) >= 5

    def test_crud_strips_auth_endpoints_and_validates(self) -> None:
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
            "apiSpec": [
                {"method": "POST", "endpoint": "/api/posts"},
                {"method": "GET", "endpoint": "/api/posts"},
                {"method": "GET", "endpoint": "/api/posts/{postId}"},
                {"method": "PUT", "endpoint": "/api/posts/{postId}"},
                {"method": "DELETE", "endpoint": "/api/posts/{postId}"},
                {"method": "POST", "endpoint": "/api/auth/login"},
                {"method": "POST", "endpoint": "/api/auth/signup"},
                {"method": "GET", "endpoint": "/api/users/me"},
            ],
            "codeFiles": _crud_canonical_codefiles(),
            "basicQuestions": [],
            "missions": [],
            "interviewQuestions": [],
            "nextRecommendations": [],
        }
        out = FeatureTemplateNormalizer.normalize(
            raw, _req("게시글 CRUD", includeMissions=False, includeInterview=False)
        )
        FeatureTemplateData(**out)

        methods = {
            (str(s.get("method", "")).upper(), s.get("endpoint", ""))
            for s in out.get("apiSpec", [])
            if isinstance(s, dict)
        }
        blob = str(out)
        assert len(out["apiSpec"]) == 5
        assert ("/api/auth/login" not in blob) and ("/api/auth/signup" not in blob)
        assert ("/api/users/me" not in blob)
        assert ("POST", "/api/posts") in methods
        assert ("DELETE", "/api/posts/{postId}") in methods
        _assert_api_spec_schema_fields(out["apiSpec"])

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

    def test_jwt_strips_signup_endpoint_and_keeps_canonical_api(self) -> None:
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
            "apiSpec": [
                {
                    "apiName": "로그인",
                    "method": "POST",
                    "endpoint": "/api/auth/login",
                    "authenticationRequired": False,
                },
                {
                    "apiName": "회원가입",
                    "method": "POST",
                    "endpoint": "/api/auth/signup",
                    "authenticationRequired": False,
                },
            ],
            "codeFiles": [
                {
                    "fileName": "JwtTokenProvider.java",
                    "filePath": "src/main/java/com/example/security/JwtTokenProvider.java",
                    "role": "인증/토큰 Provider",
                    "language": "java",
                    "content": "package com.example.security;\npublic class JwtTokenProvider {}",
                },
                {
                    "fileName": "JwtAuthenticationFilter.java",
                    "filePath": "src/main/java/com/example/security/JwtAuthenticationFilter.java",
                    "role": "인증/인가 필터",
                    "language": "java",
                    "content": "package com.example.security;\npublic class JwtAuthenticationFilter {}",
                },
                {
                    "fileName": "SecurityConfig.java",
                    "filePath": "src/main/java/com/example/security/SecurityConfig.java",
                    "role": "설정 클래스",
                    "language": "java",
                    "content": "package com.example.security;\npublic class SecurityConfig {}",
                },
                {
                    "fileName": "AuthController.java",
                    "filePath": "src/main/java/com/example/security/AuthController.java",
                    "role": "REST API 컨트롤러",
                    "language": "java",
                    "content": 'package com.example.security;\n@PostMapping("/api/auth/login")\npublic class AuthController {}',
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
        names = {f["fileName"] for f in out["codeFiles"]}
        endpoints = [s.get("endpoint", "") for s in out.get("apiSpec", []) if isinstance(s, dict)]
        methods = {
            (str(s.get("method", "")).upper(), s.get("endpoint", ""))
            for s in out.get("apiSpec", [])
            if isinstance(s, dict)
        }
        blob = str(out)
        assert "/api/auth/signup" not in blob
        assert ("POST", "/api/auth/login") in methods
        assert ("GET", "/api/users/me") in methods
        assert "/api/auth/login" in endpoints
        assert "/api/users/me" in endpoints
        for req in (
            "AuthController.java",
            "JwtTokenProvider.java",
            "JwtAuthenticationFilter.java",
            "SecurityConfig.java",
        ):
            assert req in names
        assert "AppController" not in blob
        assert "JWTController" not in blob

    def test_jwt_api_spec_schema_compliant_and_validates(self) -> None:
        """운영 500 재현: description/requestBody 누락·requestHeaders dict → schema 통과."""

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
            "apiSpec": [
                {
                    "apiName": "로그인",
                    "method": "POST",
                    "endpoint": "/api/auth/login",
                    "authenticationRequired": False,
                    "requestBody": {"email": "u@ex.com", "password": "pw"},
                    "responseBody": {"accessToken": "jwt", "tokenType": "Bearer"},
                    "status": 200,
                },
                {
                    "apiName": "회원가입",
                    "method": "POST",
                    "endpoint": "/api/auth/signup",
                    "authenticationRequired": False,
                },
                {
                    "apiName": "내 정보",
                    "method": "GET",
                    "endpoint": "/api/users/me",
                    "authenticationRequired": True,
                    "requestHeaders": {"Authorization": "Bearer {accessToken}"},
                    "responseBody": {"email": "u@ex.com"},
                    "status": 200,
                },
            ],
            "codeFiles": [],
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
        FeatureTemplateData(**out)

        endpoints = [s.get("endpoint", "") for s in out.get("apiSpec", []) if isinstance(s, dict)]
        methods = {
            (str(s.get("method", "")).upper(), s.get("endpoint", ""))
            for s in out.get("apiSpec", [])
            if isinstance(s, dict)
        }
        blob = str(out)
        assert "/api/auth/signup" not in blob
        assert ("POST", "/api/auth/login") in methods
        assert ("GET", "/api/users/me") in methods
        assert len(out["apiSpec"]) == 2

        for item in out["apiSpec"]:
            assert isinstance(item, dict)
            assert item.get("description")
            assert item.get("requestBody") is not None
            assert item.get("responseBody") is not None
            headers = item.get("requestHeaders")
            assert isinstance(headers, list)
            for header in headers:
                assert isinstance(header, dict)
                assert header.get("name")

        login_spec = next(s for s in out["apiSpec"] if s.get("endpoint") == "/api/auth/login")
        me_spec = next(s for s in out["apiSpec"] if s.get("endpoint") == "/api/users/me")
        assert login_spec["requestBody"] == {
            "email": "u@ex.com",
            "password": "pw",
        }
        assert me_spec["requestBody"] == {}
        assert me_spec["requestHeaders"] == [
            {
                "name": "Authorization",
                "value": "Bearer {accessToken}",
                "required": True,
                "description": "",
            }
        ]

        names = {f["fileName"] for f in out["codeFiles"]}
        for req in (
            "AuthController.java",
            "JwtTokenProvider.java",
            "JwtAuthenticationFilter.java",
            "SecurityConfig.java",
            "CustomUserDetailsService.java",
            "LoginRequest.java",
            "LoginResponse.java",
        ):
            assert req in names
        assert "/api/auth/login" in endpoints
        assert "/api/users/me" in endpoints
        _assert_api_spec_schema_fields(out["apiSpec"])


def _assert_api_spec_schema_fields(api_spec: list) -> None:
    for item in api_spec:
        assert isinstance(item, dict)
        assert item.get("description")
        assert item.get("requestBody") is not None
        assert item.get("responseBody") is not None
        headers = item.get("requestHeaders")
        assert isinstance(headers, list)
        for header in headers:
            assert isinstance(header, dict)
            assert header.get("name")


class TestBucketApiSpecInvariants:
    @pytest.mark.parametrize(
        "feature,kwargs",
        [
            ("회원가입", {"includeMissions": False, "includeInterview": False}),
            ("게시글 CRUD", {"includeMissions": False, "includeInterview": False}),
            (
                "JWT 인증",
                {
                    "level": DifficultyLevel.INTERMEDIATE,
                    "includeMissions": False,
                    "includeInterview": False,
                },
            ),
            ("댓글 작성", {"includeMissions": False, "includeInterview": False}),
        ],
    )
    def test_all_buckets_api_spec_schema_and_codefile_invariants(
        self, feature: str, kwargs: dict
    ) -> None:
        raw = {
            "overview": {
                "featureName": feature,
                "purpose": "",
                "useCases": [],
                "resultDescription": "",
                "techStack": [],
                "learningGoals": [],
            },
            "requirements": [],
            "flow": {"steps": [], "layers": []},
            "apiSpec": [
                {"method": "POST", "endpoint": "/api/auth/login"},
                {"method": "POST", "endpoint": "/api/auth/signup"},
                {"method": "GET", "endpoint": "/api/users/me"},
                {"method": "POST", "endpoint": "/api/posts"},
            ],
            "codeFiles": [
                {
                    "fileName": "module_0.py.java",
                    "filePath": "src/main/java/com/example/app/module_0.py.java",
                    "role": "데이터 접근",
                    "language": "java",
                    "content": "public class module_0 {}",
                },
                {
                    "fileName": "AppController.java",
                    "filePath": "src/main/java/com/example/app/AppController.java",
                    "role": "REST API 컨트롤러",
                    "language": "java",
                    "content": "public class AppController {}",
                },
            ],
            "basicQuestions": [],
            "missions": [],
            "interviewQuestions": [],
            "nextRecommendations": [],
        }
        out = FeatureTemplateNormalizer.normalize(raw, _req(feature, **kwargs))
        FeatureTemplateData(**out)
        _assert_api_spec_schema_fields(out["apiSpec"])
        for f in out["codeFiles"]:
            fn = f["fileName"]
            assert ".py.java" not in fn
            assert not fn.startswith("module_")
            assert fn.endswith(".java")
            assert f["filePath"].endswith(fn)
            cls = fn[:-5]
            assert f"class {cls}" in f["content"] or f"interface {cls}" in f["content"]
        blob = str(out)
        assert "AppController" not in blob
        assert "JWTController" not in blob
        assert "CRUDController" not in blob


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


class TestJavaCodefileSanitization:
    def test_invalid_java_filenames_removed_across_buckets(self) -> None:
        junk = {
            "fileName": "module_0.py.java",
            "filePath": "src/main/java/com/example/post/module_0.py.java",
            "role": "데이터 접근",
            "language": "java",
            "content": "public class module_0 {}",
        }
        for feature in ("게시글 CRUD", "JWT 인증", "회원가입"):
            raw = {
                "overview": {
                    "featureName": feature,
                    "purpose": "",
                    "useCases": [],
                    "resultDescription": "",
                    "techStack": [],
                    "learningGoals": [],
                },
                "requirements": [],
                "flow": {"steps": [], "layers": []},
                "apiSpec": [],
                "codeFiles": [junk],
                "basicQuestions": [],
                "missions": [],
                "interviewQuestions": [],
                "nextRecommendations": [],
            }
            kwargs: dict = {"includeMissions": False, "includeInterview": False}
            if feature == "JWT 인증":
                kwargs["level"] = DifficultyLevel.INTERMEDIATE
            out = FeatureTemplateNormalizer.normalize(raw, _req(feature, **kwargs))
            for f in out["codeFiles"]:
                fn = f["fileName"]
                assert ".py.java" not in fn
                assert not fn.startswith("module_")
                assert fn.endswith(".java")
                assert fn[0].isupper()

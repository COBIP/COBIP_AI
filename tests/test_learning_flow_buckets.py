"""기능템플릿 bucket별 학습 플로우 invariant 통합 테스트."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.feature_template import FeatureTemplateData
from app.services.feature_template_normalizer import FeatureTemplateNormalizer

from tests.test_feature_template_bucket_guards import _req


def _normalize_bucket(feature_name: str) -> dict:
    return FeatureTemplateNormalizer.normalize(
        {
            "overview": {
                "featureName": feature_name,
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
            "codeFiles": [],
            "basicQuestions": [],
            "missions": [
                {
                    "missionId": "M-bad",
                    "title": "JWT만 구현",
                    "description": "login token only",
                    "missionType": "implementation",
                    "requirements": ["jwt"],
                    "successCriteria": ["token"],
                    "relatedRequirements": ["R-001"],
                    "difficulty": "beginner",
                }
            ],
            "interviewQuestions": [],
            "nextRecommendations": [],
        },
        _req(feature_name),
    )


class TestBucketLearningFlowInvariants:
    def test_signup_sections_aligned(self) -> None:
        out = _normalize_bucket("회원가입")
        FeatureTemplateData(**out)
        endpoints = {(s["method"], s["endpoint"]) for s in out["apiSpec"]}
        names = {f["fileName"] for f in out["codeFiles"]}
        blob = str(out).lower()
        assert ("POST", "/api/auth/signup") in endpoints
        assert "/api/auth/login" not in blob
        assert "SignupController.java" in names
        assert len(out["requirements"]) >= 3
        assert len(out["basicQuestions"]) >= 3
        assert len(out["missions"]) >= 2
        assert len(out["interviewQuestions"]) >= 3
        assert len(out["nextRecommendations"]) >= 3
        assert "signup" in blob or "회원가입" in blob

    def test_crud_sections_aligned(self) -> None:
        out = _normalize_bucket("게시글 CRUD")
        FeatureTemplateData(**out)
        endpoints = {s["endpoint"] for s in out["apiSpec"]}
        blob = str(out).lower()
        for ep in (
            "/api/posts",
            "/api/posts/{postId}",
        ):
            assert ep in endpoints or any(ep.replace("{postId}", "") in e for e in endpoints)
        assert "/api/auth/login" not in blob
        assert "/api/auth/signup" not in blob
        assert "PostController.java" in {f["fileName"] for f in out["codeFiles"]}
        assert len(out["missions"]) >= 2
        assert "post" in blob

    def test_jwt_sections_aligned(self) -> None:
        out = _normalize_bucket("JWT 인증")
        FeatureTemplateData(**out)
        methods = {(s["method"], s["endpoint"]) for s in out["apiSpec"]}
        blob = str(out).lower()
        assert ("POST", "/api/auth/login") in methods
        assert ("GET", "/api/users/me") in methods
        assert "/api/auth/signup" not in blob
        assert "JwtTokenProvider.java" in {f["fileName"] for f in out["codeFiles"]}
        assert len(out["interviewQuestions"]) >= 3

    def test_generate_signup_api(self) -> None:
        client = TestClient(app)
        resp = client.post(
            "/ai/feature-template/generate",
            json={
                "language": "Java",
                "framework": "Spring Boot",
                "featureName": "회원가입",
                "level": "beginner",
                "includeCode": True,
                "includeMissions": True,
                "includeInterview": True,
            },
        )
        assert resp.status_code == 200
        template = resp.json()["data"]["template"]
        blob = str(template).lower()
        assert any(
            s.get("endpoint") == "/api/auth/signup" for s in template["apiSpec"]
        )
        assert "/api/auth/login" not in blob or "login" in template["missions"][0]["title"].lower()

    def test_generate_crud_api(self) -> None:
        client = TestClient(app)
        resp = client.post(
            "/ai/feature-template/generate",
            json={
                "language": "Java",
                "framework": "Spring Boot",
                "featureName": "게시글 CRUD",
                "level": "beginner",
                "includeCode": True,
                "includeMissions": True,
                "includeInterview": True,
            },
        )
        assert resp.status_code == 200
        template = resp.json()["data"]["template"]
        endpoints = {s["endpoint"] for s in template["apiSpec"]}
        assert "/api/posts" in endpoints
        assert "/api/auth/login" not in str(template)

    def test_generate_jwt_api(self) -> None:
        client = TestClient(app)
        resp = client.post(
            "/ai/feature-template/generate",
            json={
                "language": "Java",
                "framework": "Spring Boot",
                "featureName": "JWT 로그인 인증 기능",
                "level": "beginner",
                "includeCode": True,
                "includeMissions": True,
                "includeInterview": True,
            },
        )
        assert resp.status_code == 200
        template = resp.json()["data"]["template"]
        methods = {(s["method"], s["endpoint"]) for s in template["apiSpec"]}
        assert ("POST", "/api/auth/login") in methods
        assert "/api/auth/signup" not in str(template)

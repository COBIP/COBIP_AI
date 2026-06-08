"""Bucket section consistency — requirements/overview/missions/questions 보정."""

from __future__ import annotations

import pytest

from app.schemas.feature_template import FeatureTemplateData
from app.services.feature_template_normalizer import FeatureTemplateNormalizer

from tests.test_feature_template_bucket_guards import _req

_SIGNUP_BAD_REQUIREMENTS = [
    {
        "requirementId": "R-001",
        "name": "사용자 등록",
        "description": "등록",
        "inputValue": "x",
        "processCondition": "x",
        "successResult": "ok",
        "failureResult": "fail",
        "priority": "HIGH",
        "relatedScreenOrApi": "api",
    },
    {
        "requirementId": "R-002",
        "name": "사용자 정보 수정",
        "description": "수정",
        "inputValue": "x",
        "processCondition": "x",
        "successResult": "ok",
        "failureResult": "fail",
        "priority": "HIGH",
        "relatedScreenOrApi": "api",
    },
    {
        "requirementId": "R-003",
        "name": "사용자 정보 삭제",
        "description": "삭제",
        "inputValue": "x",
        "processCondition": "x",
        "successResult": "ok",
        "failureResult": "fail",
        "priority": "HIGH",
        "relatedScreenOrApi": "api",
    },
]


def _base_raw(feature_name: str, **overrides: object) -> dict:
    base = {
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
        "apiSpec": [],
        "codeFiles": [],
        "basicQuestions": [],
        "missions": [],
        "interviewQuestions": [],
        "nextRecommendations": [],
    }
    base.update(overrides)
    return base


class TestSignupSectionConsistency:
    def test_bad_requirements_replaced_with_canonical(self) -> None:
        raw = _base_raw(
            "회원가입",
            requirements=_SIGNUP_BAD_REQUIREMENTS,
            codeFiles=[
                {
                    "fileName": "AppController.java",
                    "role": "x",
                    "language": "java",
                    "content": '@PostMapping("/login") class AppController {}',
                }
            ],
        )
        out = FeatureTemplateNormalizer.normalize(raw, _req("회원가입"))
        FeatureTemplateData(**out)
        names = {r["name"] for r in out["requirements"]}
        blob = str(out)
        assert "사용자 정보 수정" not in blob
        assert "사용자 정보 삭제" not in blob
        assert "입력값 검증" in names
        assert "이메일 중복 검사" in names
        assert "비밀번호 해시 저장" in names
        assert len(out["requirements"]) >= 5

    def test_bad_use_cases_replaced(self) -> None:
        raw = _base_raw(
            "회원가입",
            overview={
                "featureName": "회원가입",
                "purpose": "사용자 CRUD 관리",
                "useCases": ["사용자 정보 수정", "사용자 정보 삭제"],
                "resultDescription": "CRUD 완료",
                "techStack": [],
                "learningGoals": [],
            },
        )
        out = FeatureTemplateNormalizer.normalize(raw, _req("회원가입"))
        blob = str(out["overview"])
        assert "사용자 정보 수정" not in blob
        assert "가입" in blob or "회원" in blob
        assert len(out["overview"]["useCases"]) >= 2

    def test_generic_mission_titles_replaced(self) -> None:
        raw = _base_raw(
            "회원가입",
            missions=[
                {
                    "missionId": "M-001",
                    "title": "구현 미션 1",
                    "description": "사용자 정보 삭제 구현",
                    "missionType": "implementation",
                    "requirements": ["delete"],
                    "successCriteria": ["ok"],
                    "relatedRequirements": ["R-001"],
                    "difficulty": "beginner",
                },
                {
                    "missionId": "M-002",
                    "title": "구현 미션 2",
                    "description": "수정",
                    "missionType": "implementation",
                    "requirements": ["update"],
                    "successCriteria": ["ok"],
                    "relatedRequirements": ["R-002"],
                    "difficulty": "beginner",
                },
            ],
        )
        out = FeatureTemplateNormalizer.normalize(raw, _req("회원가입"))
        titles = [m["title"] for m in out["missions"]]
        assert "구현 미션 1" not in titles
        assert "구현 미션 2" not in titles
        assert any("이메일" in t or "비밀번호" in t or "회원가입" in t for t in titles)

    def test_signup_api_spec_and_codefiles_preserved(self) -> None:
        raw = _base_raw("회원가입", requirements=_SIGNUP_BAD_REQUIREMENTS)
        out = FeatureTemplateNormalizer.normalize(raw, _req("회원가입"))
        endpoints = {(s["method"], s["endpoint"]) for s in out["apiSpec"]}
        assert endpoints == {("POST", "/api/auth/signup")}
        code_names = {f["fileName"] for f in out["codeFiles"]}
        assert "SignupController.java" in code_names
        assert "UserRepository.java" in code_names


class TestCrudSectionConsistency:
    def test_signup_pollution_in_requirements_replaced(self) -> None:
        raw = _base_raw(
            "게시글 CRUD",
            requirements=[
                {
                    "requirementId": "R-001",
                    "name": "회원가입",
                    "description": "이메일 중복 검사",
                    "inputValue": "x",
                    "processCondition": "x",
                    "successResult": "ok",
                    "failureResult": "fail",
                    "priority": "HIGH",
                    "relatedScreenOrApi": "signup",
                },
                {
                    "requirementId": "R-002",
                    "name": "JWT 토큰 발급",
                    "description": "access token",
                    "inputValue": "x",
                    "processCondition": "x",
                    "successResult": "ok",
                    "failureResult": "fail",
                    "priority": "HIGH",
                    "relatedScreenOrApi": "jwt",
                },
                {
                    "requirementId": "R-003",
                    "name": "비밀번호 해시",
                    "description": "bcrypt",
                    "inputValue": "x",
                    "processCondition": "x",
                    "successResult": "ok",
                    "failureResult": "fail",
                    "priority": "HIGH",
                    "relatedScreenOrApi": "auth",
                },
                {
                    "requirementId": "R-004",
                    "name": "extra",
                    "description": "x",
                    "inputValue": "x",
                    "processCondition": "x",
                    "successResult": "ok",
                    "failureResult": "fail",
                    "priority": "LOW",
                    "relatedScreenOrApi": "x",
                },
                {
                    "requirementId": "R-005",
                    "name": "extra2",
                    "description": "x",
                    "inputValue": "x",
                    "processCondition": "x",
                    "successResult": "ok",
                    "failureResult": "fail",
                    "priority": "LOW",
                    "relatedScreenOrApi": "x",
                },
            ],
        )
        out = FeatureTemplateNormalizer.normalize(
            raw, _req("게시글 CRUD", includeMissions=True, includeInterview=True)
        )
        names = {r["name"] for r in out["requirements"]}
        assert "게시글 생성" in names
        assert "게시글 삭제" in names
        assert "회원가입" not in str(out["requirements"])
        endpoints = {s["endpoint"] for s in out["apiSpec"]}
        assert "/api/posts" in endpoints

    def test_crud_missions_not_generic(self) -> None:
        raw = _base_raw(
            "게시글 CRUD",
            missions=[
                {
                    "missionId": "M-001",
                    "title": "구현 미션 1",
                    "description": "회원가입",
                    "missionType": "implementation",
                    "requirements": ["signup"],
                    "successCriteria": ["ok"],
                    "relatedRequirements": ["R-001"],
                    "difficulty": "beginner",
                },
                {
                    "missionId": "M-002",
                    "title": "API 구현",
                    "description": "jwt",
                    "missionType": "implementation",
                    "requirements": ["jwt"],
                    "successCriteria": ["ok"],
                    "relatedRequirements": ["R-002"],
                    "difficulty": "beginner",
                },
            ],
        )
        out = FeatureTemplateNormalizer.normalize(raw, _req("게시글 CRUD"))
        titles = [m["title"] for m in out["missions"]]
        assert "구현 미션 1" not in titles
        assert any("게시글" in t for t in titles)


class TestJwtSectionConsistency:
    def test_signup_crud_pollution_replaced(self) -> None:
        raw = _base_raw(
            "JWT 인증",
            requirements=[
                {
                    "requirementId": "R-001",
                    "name": "회원가입",
                    "description": "signup",
                    "inputValue": "x",
                    "processCondition": "x",
                    "successResult": "ok",
                    "failureResult": "fail",
                    "priority": "HIGH",
                    "relatedScreenOrApi": "/api/auth/signup",
                },
                {
                    "requirementId": "R-002",
                    "name": "게시글 CRUD",
                    "description": "posts",
                    "inputValue": "x",
                    "processCondition": "x",
                    "successResult": "ok",
                    "failureResult": "fail",
                    "priority": "HIGH",
                    "relatedScreenOrApi": "/api/posts",
                },
                {
                    "requirementId": "R-003",
                    "name": "사용자 정보 삭제",
                    "description": "delete user",
                    "inputValue": "x",
                    "processCondition": "x",
                    "successResult": "ok",
                    "failureResult": "fail",
                    "priority": "HIGH",
                    "relatedScreenOrApi": "user",
                },
                {
                    "requirementId": "R-004",
                    "name": "extra",
                    "description": "x",
                    "inputValue": "x",
                    "processCondition": "x",
                    "successResult": "ok",
                    "failureResult": "fail",
                    "priority": "LOW",
                    "relatedScreenOrApi": "x",
                },
            ],
        )
        out = FeatureTemplateNormalizer.normalize(raw, _req("JWT 인증"))
        names = {r["name"] for r in out["requirements"]}
        assert "accessToken 발급" in names or "로그인 요청 검증" in names
        assert "회원가입" not in str(out["requirements"])
        assert "게시글" not in str(out["requirements"])
        methods = {(s["method"], s["endpoint"]) for s in out["apiSpec"]}
        assert ("POST", "/api/auth/login") in methods
        assert ("GET", "/api/users/me") in methods


class TestGenericTitleGuard:
    @pytest.mark.parametrize(
        "title",
        ["구현 미션 1", "기본 문제 1", "핵심 점검 1", "기능 구현", "API 구현"],
    )
    def test_generic_mission_title_detected(self, title: str) -> None:
        from app.services.feature_template_bucket_guards import _is_generic_title

        assert _is_generic_title(title) is True

    def test_specific_title_not_generic(self) -> None:
        from app.services.feature_template_bucket_guards import _is_generic_title

        assert _is_generic_title("이메일 중복 검사 구현하기") is False

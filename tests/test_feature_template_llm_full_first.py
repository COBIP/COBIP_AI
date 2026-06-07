"""24차: LLM full-first generate 경로 검증."""

from unittest.mock import MagicMock

import pytest

from app.core.config import settings
from app.models.enums import DifficultyLevel
from app.schemas.feature_template import FeatureTemplateGenerateRequest
from app.services.feature_template_generator import FeatureTemplateGenerator
from app.services.feature_template_instant_skeleton import (
    QUALITY_INSTANT_FULL_GENERATION_MODE,
)


def _full_llm_payload(**overrides: object) -> dict:
    base = {
        "overview": {
            "featureName": "로그인",
            "purpose": "사용자 인증",
            "useCases": ["회원 전용 페이지"],
            "resultDescription": "토큰 발급",
            "techStack": ["Java", "Spring Boot"],
            "learningGoals": ["인증 흐름 이해"],
        },
        "requirements": [
            {
                "requirementId": "R-001",
                "name": "로그인 입력",
                "description": "아이디와 비밀번호 입력",
                "inputValue": "username, password",
                "processCondition": "필수값 검증",
                "successResult": "요청 전달",
                "failureResult": "400",
                "priority": "HIGH",
                "relatedScreenOrApi": "POST /api/auth/login",
            },
            {
                "requirementId": "R-002",
                "name": "비밀번호 검증",
                "description": "해시 비교",
                "inputValue": "password",
                "processCondition": "BCrypt",
                "successResult": "인증 성공",
                "failureResult": "401",
                "priority": "HIGH",
                "relatedScreenOrApi": "LoginService",
            },
            {
                "requirementId": "R-003",
                "name": "토큰 발급",
                "description": "JWT 발급",
                "inputValue": "user",
                "processCondition": "JwtProvider",
                "successResult": "200",
                "failureResult": "-",
                "priority": "HIGH",
                "relatedScreenOrApi": "POST /api/auth/login",
            },
        ],
        "flow": {
            "steps": ["1", "2", "3", "4", "5"],
            "layers": [
                {"layer": "Controller", "role": "수신"},
                {"layer": "Service", "role": "인증"},
                {"layer": "Repository", "role": "조회"},
                {"layer": "DB", "role": "저장"},
            ],
        },
        "apiSpec": [
            {
                "apiName": "로그인",
                "method": "POST",
                "endpoint": "/api/auth/login",
                "description": "로그인 API",
                "requestBody": {"username": "user"},
                "responseBody": {"accessToken": "jwt"},
                "status": 200,
            }
        ],
        "codeFiles": [
            {
                "fileName": "LoginController.java",
                "filePath": "src/LoginController.java",
                "role": "Controller",
                "language": "java",
                "content": "public class LoginController {}",
            }
        ],
        "basicQuestions": [
            {
                "questionId": "Q-001",
                "type": "short_answer",
                "question": "역할?",
                "choices": None,
                "answer": "인증",
                "explanation": "Service가 인증",
                "relatedSection": "flow",
                "difficulty": "beginner",
            },
            {
                "questionId": "Q-002",
                "type": "short_answer",
                "question": "검증?",
                "choices": None,
                "answer": "BCrypt",
                "explanation": "해시 비교",
                "relatedSection": "codeFiles",
                "difficulty": "beginner",
            },
            {
                "questionId": "Q-003",
                "type": "short_answer",
                "question": "응답?",
                "choices": None,
                "answer": "JWT",
                "explanation": "토큰 발급",
                "relatedSection": "apiSpec",
                "difficulty": "beginner",
            },
        ],
        "missions": [
            {
                "missionId": "M-001",
                "title": "JWT 적용",
                "description": "미션 목표: JWT 전환",
                "missionType": "enhancement",
                "requirements": ["accessToken"],
                "successCriteria": ["토큰 발급"],
                "relatedRequirements": ["R-003"],
                "difficulty": "beginner",
            },
            {
                "missionId": "M-002",
                "title": "입력 검증",
                "description": "미션 목표: Bean Validation",
                "missionType": "validation",
                "requirements": ["@Valid"],
                "successCriteria": ["400 응답"],
                "relatedRequirements": ["R-001"],
                "difficulty": "beginner",
            },
        ],
        "interviewQuestions": [
            {
                "questionId": "IQ-001",
                "question": "로그인 흐름?",
                "keyPoints": ["Controller", "Service"],
                "sampleAnswer": "요청 수신 후 인증",
                "relatedSection": "flow",
            },
            {
                "questionId": "IQ-002",
                "question": "계층 분리?",
                "keyPoints": ["관심사 분리"],
                "sampleAnswer": "Controller/Service/Repository",
                "relatedSection": "flow",
            },
            {
                "questionId": "IQ-003",
                "question": "비밀번호 저장?",
                "keyPoints": ["BCrypt"],
                "sampleAnswer": "해시 저장",
                "relatedSection": "codeFiles",
            },
        ],
        "nextRecommendations": [
            {
                "featureName": "회원가입",
                "reason": "짝 기능",
                "expectedLearning": "사용자 생성",
                "priority": 1,
            },
            {
                "featureName": "JWT",
                "reason": "확장",
                "expectedLearning": "토큰",
                "priority": 2,
            },
            {
                "featureName": "권한",
                "reason": "인가",
                "expectedLearning": "Role",
                "priority": 3,
            },
        ],
    }
    base.update(overrides)
    return base


def _login_request(**kwargs: object) -> FeatureTemplateGenerateRequest:
    base = dict(
        language="Java",
        framework="Spring Boot",
        featureName="로그인",
        level=DifficultyLevel.BEGINNER,
        includeCode=True,
        includeMissions=True,
        includeInterview=True,
    )
    base.update(kwargs)
    return FeatureTemplateGenerateRequest(**base)


def test_llm_full_first_success_returns_ollama_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "FEATURE_TEMPLATE_LLM_FULL_FIRST_ENABLED", True)
    gen = FeatureTemplateGenerator()
    monkeypatch.setattr(gen._llm_service, "generate_json", lambda *_a, **_k: _full_llm_payload())

    result = gen.generate(_login_request())

    assert result.source == "ollama"
    assert result.generationMode == "quality_llm_full"
    assert result.fallbackUsed is False
    assert result.instantSkeletonUsed is False
    assert result.skeletonFirst is False
    assert result.initialLlmEnhancementAttempted is True
    assert result.initialLlmEnhancementSucceeded is True
    assert result.initialLlmEnhancementMs is not None
    assert result.deferredSections == []
    assert len(result.template.codeFiles) >= 1
    assert len(result.template.missions) >= 2
    assert len(result.template.interviewQuestions) >= 3


def test_llm_full_first_includes_rag_applied_references(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "FEATURE_TEMPLATE_LLM_FULL_FIRST_ENABLED", True)
    gen = FeatureTemplateGenerator()
    monkeypatch.setattr(gen._llm_service, "generate_json", lambda *_a, **_k: _full_llm_payload())

    request = _login_request(
        referenceContext={
            "ragReferences": [
                {
                    "title": "로그인 가이드",
                    "content": "Spring Security 로그인 처리 예시",
                    "sourceType": "doc",
                    "score": 0.9,
                }
            ]
        }
    )
    result = gen.generate(request)

    assert result.source == "ollama"
    assert len(result.appliedReferences) >= 1
    assert result.appliedReferences[0]["usedInPrompt"] is True


def test_llm_failure_falls_back_to_instant_skeleton(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "FEATURE_TEMPLATE_INSTANT_SKELETON_ENABLED", True)
    gen = FeatureTemplateGenerator(llm_service=MagicMock())
    gen._llm_service.generate_json.side_effect = RuntimeError("ollama timeout")

    result = gen.generate(_login_request(includeCode=False, includeMissions=False, includeInterview=False))

    assert result.source == "instant"
    assert result.fallbackUsed is True
    assert result.initialLlmEnhancementAttempted is True
    assert result.initialLlmEnhancementSucceeded is False
    assert result.instantSkeletonUsed is True


def test_llm_failure_instant_disabled_falls_back_to_mock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "FEATURE_TEMPLATE_INSTANT_SKELETON_ENABLED", False)
    gen = FeatureTemplateGenerator(llm_service=MagicMock())
    gen._llm_service.generate_json.side_effect = RuntimeError("connection error")

    result = gen.generate(_login_request())

    assert result.source == "fallback"
    assert result.fallbackUsed is True
    assert result.initialLlmEnhancementAttempted is True
    assert result.initialLlmEnhancementSucceeded is False


def test_include_false_populates_deferred_sections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "FEATURE_TEMPLATE_LLM_FULL_FIRST_ENABLED", True)
    gen = FeatureTemplateGenerator()
    payload = _full_llm_payload()
    payload["codeFiles"] = []
    payload["missions"] = []
    payload["interviewQuestions"] = []
    monkeypatch.setattr(gen._llm_service, "generate_json", lambda *_a, **_k: payload)

    result = gen.generate(
        _login_request(includeCode=False, includeMissions=False, includeInterview=False)
    )

    assert result.source == "ollama"
    assert set(result.deferredSections) == {"codeFiles", "missions", "interviewQuestions"}


def test_llm_failure_with_full_includes_uses_instant_full_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "FEATURE_TEMPLATE_INSTANT_SKELETON_ENABLED", True)
    gen = FeatureTemplateGenerator(llm_service=MagicMock())
    gen._llm_service.generate_json.side_effect = RuntimeError("json parse error")

    result = gen.generate(_login_request())

    assert result.source == "instant"
    assert result.generationMode == QUALITY_INSTANT_FULL_GENERATION_MODE
    assert result.fallbackUsed is True
    assert len(result.template.codeFiles) >= 1
    assert len(result.template.missions) >= 2
    assert len(result.template.interviewQuestions) >= 3

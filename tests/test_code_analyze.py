"""POST /ai/code/analyze 코드리뷰 + 오답피드백 테스트.

테스트 환경에서 실제 Ollama 네트워크 호출을 막기 위해
LLMService.generate_json 을 monkeypatch 한다.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.prompts.code_analyze_prompts import build_code_analyze_prompt
from app.schemas.evaluation import CodeAnalyzeRequest
from app.services.code_analyze_service import CodeAnalyzeService

_GENERATE_JSON_TARGET = "app.services.code_analyze_service.LLMService.generate_json"

_FALLBACK_PHRASE = "AI 상세 분석을 사용할 수 없어"

_SIGNUP_CODE = (
    "public class SignupService {\n"
    "    public void signup(String email, String password) {\n"
    "        if (userRepository.existsByEmail(email)) { throw new RuntimeException(); }\n"
    "        String hashed = passwordEncoder.encode(password);\n"
    "        userRepository.save(new User(email, hashed));\n"
    "    }\n"
    "}\n"
)

_EMPTY_SIGNUP_CODE = (
    "public class SignupService {\n"
    "    public void signup(String email, String password) { }\n"
    "}\n"
)


def _llm_payload() -> dict:
    return {
        "summary": "회원가입 서비스 코드입니다.",
        "explanation": "Controller 없이 Service 단일 클래스로 구성되어 있습니다.",
        "potentialIssues": ["예외 메시지가 일반적입니다."],
        "improvementSuggestions": ["커스텀 예외 사용을 검토하세요."],
        "satisfiedRequirements": ["이메일 중복 검사를 수행한다"],
        "missingRequirements": [],
        "incorrectParts": [],
        "wrongAnswerFeedback": [],
    }


def _assert_no_mock(body: dict) -> None:
    text = json.dumps(body, ensure_ascii=False)
    assert "(mock)" not in text


# ----------------------------------------------------------------------
# service 단위 (fallback 경로: generate_json 실패 유도)
# ----------------------------------------------------------------------
class TestCodeAnalyzeFallback:
    def test_minimal_fallback_no_mock(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            _GENERATE_JSON_TARGET,
            lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("llm down")),
        )
        request = CodeAnalyzeRequest(code=_SIGNUP_CODE, language="java")
        result = CodeAnalyzeService().analyze(request)

        assert result.summary
        assert result.explanation
        _assert_no_mock(result.model_dump())

    def test_code_change_changes_response(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            _GENERATE_JSON_TARGET,
            lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("llm down")),
        )
        full = CodeAnalyzeService().analyze(
            CodeAnalyzeRequest(code=_SIGNUP_CODE, language="java")
        )
        empty = CodeAnalyzeService().analyze(
            CodeAnalyzeRequest(code=_EMPTY_SIGNUP_CODE, language="java")
        )
        # 코드 내용이 다르면 요약/이슈가 달라져야 한다.
        assert full.summary != empty.summary or full.potentialIssues != empty.potentialIssues

    def test_requirements_missing_detected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            _GENERATE_JSON_TARGET,
            lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("llm down")),
        )
        request = CodeAnalyzeRequest(
            code=_EMPTY_SIGNUP_CODE,
            language="java",
            requirements=[
                "이메일 중복 검사를 수행한다",
                "비밀번호를 암호화해서 저장한다",
            ],
            successCriteria=["비밀번호 원문을 저장하지 않는다"],
        )
        result = CodeAnalyzeService().analyze(request)
        # 빈 메서드라 요구사항 근거가 없어 누락으로 잡혀야 한다.
        assert result.missingRequirements
        assert result.wrongAnswerFeedback
        _assert_no_mock(result.model_dump())

    def test_empty_code_response(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(_GENERATE_JSON_TARGET, lambda *_a, **_k: {"mock": True})
        result = CodeAnalyzeService().analyze(
            CodeAnalyzeRequest(code="   ", language="java", requirements=["a 요구사항"])
        )
        assert "코드가 없습니다" in result.summary
        assert result.missingRequirements == ["a 요구사항"]
        _assert_no_mock(result.model_dump())

    def test_mock_dict_payload_falls_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # OLLAMA_BASE_URL 미설정 시 generate_json 이 반환하는 mock dict 모사.
        monkeypatch.setattr(
            _GENERATE_JSON_TARGET,
            lambda *_a, **_k: {"mock": True, "warning": "...", "promptLength": 10},
        )
        result = CodeAnalyzeService().analyze(
            CodeAnalyzeRequest(code=_SIGNUP_CODE, language="java")
        )
        assert result.summary
        _assert_no_mock(result.model_dump())


# ----------------------------------------------------------------------
# service 단위 (LLM 정상 경로)
# ----------------------------------------------------------------------
class TestCodeAnalyzeLlmPath:
    def test_llm_payload_normalized(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(_GENERATE_JSON_TARGET, lambda *_a, **_k: _llm_payload())
        result = CodeAnalyzeService().analyze(
            CodeAnalyzeRequest(
                code=_SIGNUP_CODE,
                language="java",
                requirements=["이메일 중복 검사를 수행한다"],
            )
        )
        assert result.summary == "회원가입 서비스 코드입니다."
        assert result.satisfiedRequirements == ["이메일 중복 검사를 수행한다"]
        _assert_no_mock(result.model_dump())

    def test_llm_payload_sanitizes_mock_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        payload = _llm_payload()
        payload["summary"] = "(mock) 요약"
        payload["potentialIssues"] = ["(mock) 이슈", "정상 이슈"]
        monkeypatch.setattr(_GENERATE_JSON_TARGET, lambda *_a, **_k: payload)
        result = CodeAnalyzeService().analyze(
            CodeAnalyzeRequest(code=_SIGNUP_CODE, language="java")
        )
        _assert_no_mock(result.model_dump())
        assert "정상 이슈" in result.potentialIssues


# ----------------------------------------------------------------------
# API 통합 (TestClient)
# ----------------------------------------------------------------------
class TestCodeAnalyzeApi:
    def test_minimal_request(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(_GENERATE_JSON_TARGET, lambda *_a, **_k: _llm_payload())
        client = TestClient(app)
        resp = client.post(
            "/ai/code/analyze",
            json={"code": _SIGNUP_CODE, "language": "java"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        data = body["data"]
        for key in ("summary", "explanation", "potentialIssues", "improvementSuggestions"):
            assert key in data
        _assert_no_mock(body)

    def test_request_with_requirements(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(_GENERATE_JSON_TARGET, lambda *_a, **_k: _llm_payload())
        client = TestClient(app)
        resp = client.post(
            "/ai/code/analyze",
            json={
                "code": _SIGNUP_CODE,
                "language": "java",
                "context": "회원가입 기능 구현",
                "missionTitle": "회원가입 서비스 구현",
                "requirements": ["이메일 중복 검사를 수행한다"],
                "successCriteria": ["중복 이메일이면 가입을 막는다"],
            },
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        for key in (
            "satisfiedRequirements",
            "missingRequirements",
            "incorrectParts",
            "wrongAnswerFeedback",
        ):
            assert key in data
        _assert_no_mock(resp.json())

    def test_api_fallback_on_llm_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            _GENERATE_JSON_TARGET,
            lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("llm down")),
        )
        client = TestClient(app)
        resp = client.post(
            "/ai/code/analyze",
            json={"code": _EMPTY_SIGNUP_CODE, "language": "java"},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        _assert_no_mock(resp.json())


# ----------------------------------------------------------------------
# 프롬프트 안정화 (hotfix): max_tokens, 코드펜스 제거, truncate, 문구 구분
# ----------------------------------------------------------------------
class TestCodeAnalyzeStability:
    def test_generate_json_called_with_max_tokens_800(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict = {}

        def fake_generate_json(_self, prompt, **kwargs):
            captured["prompt"] = prompt
            captured["kwargs"] = kwargs
            return _llm_payload()

        monkeypatch.setattr(_GENERATE_JSON_TARGET, fake_generate_json)
        CodeAnalyzeService().analyze(
            CodeAnalyzeRequest(code=_SIGNUP_CODE, language="java")
        )
        assert captured["kwargs"].get("max_tokens") == 800
        assert settings.CODE_ANALYZE_MAX_TOKENS == 800

    def test_prompt_has_no_code_fence(self) -> None:
        prompt = build_code_analyze_prompt(
            code=_SIGNUP_CODE,
            language="java",
            context="회원가입",
            mission_title="회원가입",
            mission_description="설명",
            requirements=["이메일 중복 검사"],
            success_criteria=["중복 막기"],
        )
        assert "```" not in prompt
        assert "[현재 코드 시작]" in prompt
        assert "[현재 코드 끝]" in prompt

    def test_long_code_truncated_before_prompt(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict = {}

        def fake_generate_json(_self, prompt, **kwargs):
            captured["prompt"] = prompt
            return _llm_payload()

        monkeypatch.setattr(_GENERATE_JSON_TARGET, fake_generate_json)
        long_code = "int x = 0;\n" * 1000  # 약 11,000자 > 4000
        CodeAnalyzeService().analyze(
            CodeAnalyzeRequest(code=long_code, language="java")
        )
        prompt = captured["prompt"]
        # 원본 전체가 그대로 실리지 않고 truncate 마커가 있어야 한다.
        assert "이하 생략" in prompt
        assert len(prompt) < len(long_code)
        assert settings.CODE_ANALYZE_MAX_CODE_CHARS == 4000

    def test_llm_success_has_no_fallback_phrase(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(_GENERATE_JSON_TARGET, lambda *_a, **_k: _llm_payload())
        result = CodeAnalyzeService().analyze(
            CodeAnalyzeRequest(code=_SIGNUP_CODE, language="java")
        )
        text = json.dumps(result.model_dump(), ensure_ascii=False)
        assert _FALLBACK_PHRASE not in text

    def test_fallback_contains_phrase_but_no_mock(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            _GENERATE_JSON_TARGET,
            lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("disconnected")),
        )
        result = CodeAnalyzeService().analyze(
            CodeAnalyzeRequest(code=_SIGNUP_CODE, language="java")
        )
        text = json.dumps(result.model_dump(), ensure_ascii=False)
        assert _FALLBACK_PHRASE in text  # fallback 경로 식별
        _assert_no_mock(result.model_dump())

"""POST /ai/code/analyze 코드리뷰 + 오답피드백 테스트.

code analyze 는 LLMService(OpenAI-호환 /v1/chat/completions) 가 아니라
Ollama native /api/chat 엔드포인트를 직접 호출한다.

- 동작(정상/fallback) 검증: CodeAnalyzeService._call_native_ollama 를 monkeypatch.
- native HTTP 경로(URL/payload/message.content 파싱) 검증:
  code_analyze_service 모듈의 httpx.Client 를 가짜 클라이언트로 monkeypatch.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import app.services.code_analyze_service as code_analyze_module
from app.core.config import settings
from app.main import app
from app.prompts.code_analyze_prompts import build_code_analyze_prompt
from app.schemas.evaluation import CodeAnalyzeRequest
from app.services.code_analyze_service import CodeAnalyzeService

# code analyze 전용 native 호출 지점.
_NATIVE_CALL_TARGET = (
    "app.services.code_analyze_service.CodeAnalyzeService._call_native_ollama"
)

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


def _raise_llm_error(*_a, **_k):
    raise RuntimeError("llm down")


# ----------------------------------------------------------------------
# native /api/chat HTTP 경로 가짜 클라이언트
# ----------------------------------------------------------------------
class _FakeResponse:
    def __init__(self, data: dict, status_code: int = 200) -> None:
        self._data = data
        self.status_code = status_code

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._data


class _FakeClient:
    """httpx.Client 대체: post 호출 URL/payload 를 캡처하고 고정 응답을 반환한다."""

    captured: dict = {}
    response_content: str = json.dumps(_llm_payload(), ensure_ascii=False)

    def __init__(self, *_a, **_k) -> None:
        pass

    def __enter__(self) -> "_FakeClient":
        return self

    def __exit__(self, *_a) -> bool:
        return False

    def post(self, url: str, json: dict | None = None) -> _FakeResponse:  # noqa: A002
        _FakeClient.captured = {"url": url, "payload": json}
        return _FakeResponse({"message": {"content": _FakeClient.response_content}})


# ----------------------------------------------------------------------
# service 단위 (fallback 경로: native 호출 실패 유도)
# ----------------------------------------------------------------------
class TestCodeAnalyzeFallback:
    def test_minimal_fallback_no_mock(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(_NATIVE_CALL_TARGET, _raise_llm_error)
        request = CodeAnalyzeRequest(code=_SIGNUP_CODE, language="java")
        result = CodeAnalyzeService().analyze(request)

        assert result.summary
        assert result.explanation
        _assert_no_mock(result.model_dump())

    def test_code_change_changes_response(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(_NATIVE_CALL_TARGET, _raise_llm_error)
        full = CodeAnalyzeService().analyze(
            CodeAnalyzeRequest(code=_SIGNUP_CODE, language="java")
        )
        empty = CodeAnalyzeService().analyze(
            CodeAnalyzeRequest(code=_EMPTY_SIGNUP_CODE, language="java")
        )
        # 코드 내용이 다르면 요약/이슈가 달라져야 한다.
        assert full.summary != empty.summary or full.potentialIssues != empty.potentialIssues

    def test_requirements_missing_detected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(_NATIVE_CALL_TARGET, _raise_llm_error)
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
        monkeypatch.setattr(_NATIVE_CALL_TARGET, lambda *_a, **_k: {"mock": True})
        result = CodeAnalyzeService().analyze(
            CodeAnalyzeRequest(code="   ", language="java", requirements=["a 요구사항"])
        )
        assert "코드가 없습니다" in result.summary
        assert result.missingRequirements == ["a 요구사항"]
        _assert_no_mock(result.model_dump())

    def test_mock_dict_payload_falls_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # OLLAMA_BASE_URL 미설정 시 native 호출이 반환하는 mock dict 모사.
        monkeypatch.setattr(
            _NATIVE_CALL_TARGET,
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
        monkeypatch.setattr(_NATIVE_CALL_TARGET, lambda *_a, **_k: _llm_payload())
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
        monkeypatch.setattr(_NATIVE_CALL_TARGET, lambda *_a, **_k: payload)
        result = CodeAnalyzeService().analyze(
            CodeAnalyzeRequest(code=_SIGNUP_CODE, language="java")
        )
        _assert_no_mock(result.model_dump())
        assert "정상 이슈" in result.potentialIssues


# ----------------------------------------------------------------------
# native Ollama /api/chat 호출 (URL/payload/message.content 파싱)
# ----------------------------------------------------------------------
class TestCodeAnalyzeNativeOllama:
    def _patch_client(
        self, monkeypatch: pytest.MonkeyPatch, *, base_url: str
    ) -> None:
        _FakeClient.captured = {}
        _FakeClient.response_content = json.dumps(_llm_payload(), ensure_ascii=False)
        monkeypatch.setattr(settings, "OLLAMA_BASE_URL", base_url)
        monkeypatch.setattr(code_analyze_module.httpx, "Client", _FakeClient)

    def test_native_url_strips_v1_suffix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._patch_client(monkeypatch, base_url="http://172.18.0.1:11436/v1")
        CodeAnalyzeService().analyze(
            CodeAnalyzeRequest(code=_SIGNUP_CODE, language="java")
        )
        assert _FakeClient.captured["url"] == "http://172.18.0.1:11436/api/chat"

    def test_native_url_handles_trailing_slash(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._patch_client(monkeypatch, base_url="http://172.18.0.1:11436/v1/")
        CodeAnalyzeService().analyze(
            CodeAnalyzeRequest(code=_SIGNUP_CODE, language="java")
        )
        assert _FakeClient.captured["url"] == "http://172.18.0.1:11436/api/chat"

    def test_native_payload_shape(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._patch_client(monkeypatch, base_url="http://172.18.0.1:11436/v1")
        CodeAnalyzeService().analyze(
            CodeAnalyzeRequest(code=_SIGNUP_CODE, language="java")
        )
        payload = _FakeClient.captured["payload"]
        assert payload["model"] == settings.OLLAMA_MODEL
        assert payload["stream"] is False
        assert payload["messages"][0]["role"] == "user"
        assert isinstance(payload["messages"][0]["content"], str)
        assert payload["messages"][0]["content"]  # 비어 있지 않음
        assert len(payload["messages"]) == 1
        assert payload["options"]["temperature"] == 0.2
        assert payload["options"]["num_predict"] == settings.CODE_ANALYZE_MAX_TOKENS
        assert payload["options"]["num_predict"] == 800

    def test_native_message_content_parsed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._patch_client(monkeypatch, base_url="http://172.18.0.1:11436/v1")
        # message.content 가 코드펜스로 감싼 JSON 이어도 파싱돼야 한다.
        _FakeClient.response_content = (
            "```json\n" + json.dumps(_llm_payload(), ensure_ascii=False) + "\n```"
        )
        result = CodeAnalyzeService().analyze(
            CodeAnalyzeRequest(code=_SIGNUP_CODE, language="java")
        )
        assert result.summary == "회원가입 서비스 코드입니다."
        assert result.satisfiedRequirements == ["이메일 중복 검사를 수행한다"]
        _assert_no_mock(result.model_dump())


# ----------------------------------------------------------------------
# API 통합 (TestClient)
# ----------------------------------------------------------------------
class TestCodeAnalyzeApi:
    def test_minimal_request(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(_NATIVE_CALL_TARGET, lambda *_a, **_k: _llm_payload())
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
        monkeypatch.setattr(_NATIVE_CALL_TARGET, lambda *_a, **_k: _llm_payload())
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
        monkeypatch.setattr(_NATIVE_CALL_TARGET, _raise_llm_error)
        client = TestClient(app)
        resp = client.post(
            "/ai/code/analyze",
            json={"code": _EMPTY_SIGNUP_CODE, "language": "java"},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        _assert_no_mock(resp.json())


# ----------------------------------------------------------------------
# 프롬프트 안정화: num_predict 상한, 코드펜스 제거, truncate, 문구 구분
# ----------------------------------------------------------------------
class TestCodeAnalyzeStability:
    def test_native_num_predict_is_800(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _FakeClient.captured = {}
        _FakeClient.response_content = json.dumps(_llm_payload(), ensure_ascii=False)
        monkeypatch.setattr(settings, "OLLAMA_BASE_URL", "http://172.18.0.1:11436/v1")
        monkeypatch.setattr(code_analyze_module.httpx, "Client", _FakeClient)
        CodeAnalyzeService().analyze(
            CodeAnalyzeRequest(code=_SIGNUP_CODE, language="java")
        )
        assert _FakeClient.captured["payload"]["options"]["num_predict"] == 800
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

        def fake_native(_self, prompt):
            captured["prompt"] = prompt
            return _llm_payload()

        monkeypatch.setattr(_NATIVE_CALL_TARGET, fake_native)
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
        monkeypatch.setattr(_NATIVE_CALL_TARGET, lambda *_a, **_k: _llm_payload())
        result = CodeAnalyzeService().analyze(
            CodeAnalyzeRequest(code=_SIGNUP_CODE, language="java")
        )
        text = json.dumps(result.model_dump(), ensure_ascii=False)
        assert _FALLBACK_PHRASE not in text

    def test_fallback_contains_phrase_but_no_mock(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            _NATIVE_CALL_TARGET,
            lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("disconnected")),
        )
        result = CodeAnalyzeService().analyze(
            CodeAnalyzeRequest(code=_SIGNUP_CODE, language="java")
        )
        text = json.dumps(result.model_dump(), ensure_ascii=False)
        assert _FALLBACK_PHRASE in text  # fallback 경로 식별
        _assert_no_mock(result.model_dump())

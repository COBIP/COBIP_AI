"""LLMService JSON 응답 복구."""

import pytest

from app.services.llm_service import LLMService


def test_parse_json_object_from_plain_markdown_fence() -> None:
    text = '```\n{"ok": true, "items": []}\n```'

    assert LLMService._parse_json_object(text) == {"ok": True, "items": []}


def test_parse_json_object_from_json_markdown_fence() -> None:
    text = '```json\n{"overview": {}, "requirements": []}\n```'

    assert LLMService._parse_json_object(text) == {
        "overview": {},
        "requirements": [],
    }


def test_parse_json_object_after_think_and_prefix_text() -> None:
    text = '</think>\n여기 결과입니다.\n{"codeFiles": [], "missions": []}\n감사합니다.'

    assert LLMService._parse_json_object(text) == {
        "codeFiles": [],
        "missions": [],
    }


def test_parse_json_object_rejects_broken_json() -> None:
    with pytest.raises(RuntimeError, match="JSON object"):
        LLMService._parse_json_object("```json\n{ broken json\n```")


def test_call_llm_uses_custom_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    created: dict[str, object] = {}

    class DummyResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"choices": [{"message": {"content": "{}"}}]}

    class DummyClient:
        def __init__(self, *, timeout: int | float) -> None:
            created["timeout"] = timeout

        def __enter__(self) -> "DummyClient":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def post(self, _url: str, *, json: dict) -> DummyResponse:
            created["payload"] = json
            return DummyResponse()

    monkeypatch.setattr("app.services.llm_service.httpx.Client", DummyClient)

    result = LLMService().call_llm(
        [{"role": "user", "content": "x"}],
        timeout_seconds=123,
    )

    assert created["timeout"] == 123
    assert result == {"choices": [{"message": {"content": "{}"}}]}

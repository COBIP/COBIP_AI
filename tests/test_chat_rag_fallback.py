"""챗봇 RAG empty → general LLM fallback 테스트."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.chat import AgentPayload, AgentTrace, ChatResponseData
from app.schemas.rag import RetrievedReference
from app.services.chat_query_policy import (
    is_simple_concept_query,
    should_attempt_rag_for_general_chat,
)

_RAG_FAILURE_ANSWER = (
    "죄송합니다, 하지만 [검색 참고자료] 블록이 제공되지 않았습니다. "
    "따라서 제가 원하는 정보를 찾을 수 없습니다."
)

_INT_ANSWER = (
    "Java의 int는 정수형 원시 타입(primitive type)입니다. "
    "32비트 부호 있는 정수를 저장하며 기본값은 0입니다."
)


def _agent_payload(intent: str = "GENERAL_CHAT") -> AgentPayload:
    return AgentPayload(
        enabled=True,
        intent=intent,
        mode="rule_based",
        trace=AgentTrace(
            classifier="HybridIntentClassifier",
            handler="GeneralChatHandler",
            llmIntentUsed=False,
            steps=["rule_based_intent_classification"],
            latencyMs=1,
            toolCandidates=["general_chat"],
        ),
    )


class _EmptyRetriever:
    def retrieve(self, query: str, top_k: int | None = None) -> list[RetrievedReference]:
        return []


class _OkRetriever:
    def retrieve(self, query: str, top_k: int | None = None) -> list[RetrievedReference]:
        return [
            RetrievedReference(
                id="1",
                title="COBIP 기능템플릿",
                content="기능템플릿은 overview, requirements, apiSpec 등 섹션으로 구성된다.",
                score=0.9,
                sourceType="manual",
            )
        ]


@pytest.fixture
def rag_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "RAG_ENABLED", True)


def test_simple_concept_query_detection(rag_enabled: None) -> None:
    assert is_simple_concept_query("int") is True
    assert is_simple_concept_query("Java int가 뭐야?") is True
    assert is_simple_concept_query("@RequestBody가 뭐야?") is True
    assert is_simple_concept_query("DTO가 뭐야?") is True
    assert is_simple_concept_query("우리 프로젝트에서 RAG 구조 설명해줘") is False
    assert should_attempt_rag_for_general_chat("int", True) is False
    assert should_attempt_rag_for_general_chat("우리 프로젝트 RAG 구조 설명해줘", None) is True


def test_chat_int_returns_200_with_explanation(
    monkeypatch: pytest.MonkeyPatch,
    rag_enabled: None,
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_generate(self, user_prompt, system_prompt=None, **_kwargs):
        calls.append({"user": user_prompt, "system": system_prompt or ""})
        if len(calls) == 1 and _RAG_FAILURE_ANSWER in (calls[0].get("x") or ""):
            return _RAG_FAILURE_ANSWER
        return _INT_ANSWER

    monkeypatch.setattr("app.services.chat_service.LLMService.generate_text", fake_generate)
    monkeypatch.setattr(
        "app.services.chat_service.RetrieverService",
        lambda: _EmptyRetriever(),
    )

    client = TestClient(app)
    resp = client.post("/ai/chat", json={"message": "int"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    answer = body["data"]["answer"].lower()
    assert "int" in answer or "정수" in answer
    assert "검색 참고자료" not in body["data"]["answer"]
    assert "찾을 수 없" not in body["data"]["answer"]


def test_chat_java_int_no_rag_apology(
    monkeypatch: pytest.MonkeyPatch,
    rag_enabled: None,
) -> None:
    monkeypatch.setattr(
        "app.services.chat_service.LLMService.generate_text",
        lambda self, *_a, **_k: _INT_ANSWER,
    )
    monkeypatch.setattr(
        "app.services.chat_service.RetrieverService",
        lambda: _EmptyRetriever(),
    )

    client = TestClient(app)
    resp = client.post("/ai/chat", json={"message": "Java int가 뭐야?", "useRag": True})
    assert resp.status_code == 200
    answer = resp.json()["data"]["answer"]
    assert "검색 참고자료" not in answer
    assert "정보를 찾을 수 없" not in answer


def test_chat_request_body_general_explanation(
    monkeypatch: pytest.MonkeyPatch,
    rag_enabled: None,
) -> None:
    rb_answer = (
        "@RequestBody는 Spring MVC에서 HTTP 요청 본문을 메서드 파라미터로 "
        "바인딩할 때 쓰는 어노테이션입니다."
    )
    monkeypatch.setattr(
        "app.services.chat_service.LLMService.generate_text",
        lambda self, *_a, **_k: rb_answer,
    )
    monkeypatch.setattr(
        "app.services.chat_service.RetrieverService",
        lambda: _EmptyRetriever(),
    )

    client = TestClient(app)
    resp = client.post("/ai/chat", json={"message": "@RequestBody가 뭐야?"})
    assert resp.status_code == 200
    assert "RequestBody" in resp.json()["data"]["answer"]


def test_empty_rag_still_calls_llm_fallback(
    monkeypatch: pytest.MonkeyPatch,
    rag_enabled: None,
) -> None:
    llm_calls: list[str] = []

    def fake_generate(self, user_prompt, system_prompt=None, **_kwargs):
        llm_calls.append(user_prompt)
        return _INT_ANSWER

    monkeypatch.setattr("app.services.chat_service.LLMService.generate_text", fake_generate)
    monkeypatch.setattr(
        "app.services.chat_service.RetrieverService",
        lambda: _EmptyRetriever(),
    )

    from app.services.chat_service import ChatService
    from app.schemas.chat import ChatRequest

    out = ChatService().answer(
        ChatRequest(message="DTO가 뭐야?", useRag=True),
        apply_rag=True,
        agent=_agent_payload(),
    )
    assert len(llm_calls) >= 1
    assert out.answer.strip()
    assert "검색 참고자료" not in out.answer


def test_rag_failure_phrase_triggers_retry(
    monkeypatch: pytest.MonkeyPatch,
    rag_enabled: None,
) -> None:
    call_count = {"n": 0}

    def fake_generate(self, user_prompt, system_prompt=None, **_kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return _RAG_FAILURE_ANSWER
        return _INT_ANSWER

    monkeypatch.setattr("app.services.chat_service.LLMService.generate_text", fake_generate)
    monkeypatch.setattr(
        "app.services.chat_service.RetrieverService",
        lambda: _EmptyRetriever(),
    )

    from app.services.chat_service import ChatService
    from app.schemas.chat import ChatRequest

    out = ChatService().answer(
        ChatRequest(message="int"),
        apply_rag=False,
        agent=_agent_payload(),
    )
    assert call_count["n"] >= 2
    assert "검색 참고자료" not in out.answer


def test_project_rag_question_uses_rag_path(
    monkeypatch: pytest.MonkeyPatch,
    rag_enabled: None,
) -> None:
    retrieve_called = {"ok": False}

    class _TrackingRetriever(_OkRetriever):
        def retrieve(self, query: str, top_k: int | None = None) -> list[RetrievedReference]:
            retrieve_called["ok"] = True
            return super().retrieve(query, top_k)

    def fake_answer(self, request, *, apply_rag, variant="default", agent):
        assert apply_rag is True
        return ChatResponseData(
            answer="기능템플릿은 overview, requirements, apiSpec 등으로 구성됩니다.",
            source="ollama",
            ragUsed=True,
            references=[{"title": "COBIP"}],
            agent=agent,
        )

    monkeypatch.setattr("app.services.agent_handlers.ChatService.answer", fake_answer)
    monkeypatch.setattr(
        "app.services.chat_service.RetrieverService",
        _TrackingRetriever,
    )

    client = TestClient(app)
    resp = client.post(
        "/ai/chat",
        json={"message": "우리 프로젝트에서 RAG 구조 설명해줘"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["agent"]["intent"] in {"GENERAL_CHAT", "RAG_SEARCH"}
    assert "overview" in resp.json()["data"]["answer"] or "기능템플릿" in resp.json()["data"]["answer"]


def test_rag_search_empty_refs_general_fallback(
    monkeypatch: pytest.MonkeyPatch,
    rag_enabled: None,
) -> None:
    """RAG_SEARCH 경로와 동일: apply_rag=True + empty refs → 일반 LLM."""

    monkeypatch.setattr(
        "app.services.chat_service.LLMService.generate_text",
        lambda self, *_a, **_k: _INT_ANSWER,
    )
    monkeypatch.setattr(
        "app.services.chat_service.RetrieverService",
        lambda: _EmptyRetriever(),
    )

    from app.schemas.chat import ChatRequest
    from app.services.chat_service import ChatService

    out = ChatService().answer(
        ChatRequest(message="문서에서 int 설명해줘"),
        apply_rag=True,
        agent=_agent_payload("RAG_SEARCH"),
    )
    assert "검색 참고자료" not in out.answer
    assert "int" in out.answer.lower() or "정수" in out.answer

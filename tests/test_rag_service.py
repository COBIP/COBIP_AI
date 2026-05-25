"""Agentic RAG 13차: rag_service helper 단위 테스트."""

from __future__ import annotations

from typing import Any

import pytest

from app.schemas.rag import RetrievedReference
from app.services.rag_service import (
    build_feature_template_retrieval_query,
    merge_manual_and_auto_rag_references,
    retrieve_feature_template_rag_references,
)


def test_build_query_includes_framework_feature_language_level_and_message() -> None:
    q = build_feature_template_retrieval_query(
        message="Spring Boot 로그인 기능템플릿 생성해줘",
        feature_name="로그인",
        framework="Spring Boot",
        language="Java",
        level="beginner",
    )
    assert "Spring Boot" in q
    assert "로그인" in q
    assert "Java" in q
    assert "beginner" in q
    assert "기능템플릿" in q
    assert "요구사항" in q
    assert "API" in q
    assert "코드" in q


def test_build_query_handles_missing_optional_fields() -> None:
    q = build_feature_template_retrieval_query(
        message=None,
        feature_name="결제",
        framework=None,
        language="python",
        level=None,
    )
    assert q
    assert "결제" in q
    assert "python" in q
    assert "기능템플릿" in q


def test_build_query_truncates_long_input() -> None:
    long_message = "x" * 5000
    q = build_feature_template_retrieval_query(
        message=long_message,
        feature_name="결제",
        framework="Spring Boot",
        language="Java",
        level="beginner",
    )
    assert len(q) <= 256


def test_merge_manual_and_auto_dedupe_by_title_source_content_head() -> None:
    manual = [
        {"title": "Login", "source": "manual", "content": "로그인은 이메일과 비밀번호를 사용한다."},
    ]
    auto = [
        {"title": "Login", "source": "manual", "content": "로그인은 이메일과 비밀번호를 사용한다."},
        {"title": "JWT", "source": "qdrant", "content": "JWT accessToken을 발급한다."},
    ]
    merged = merge_manual_and_auto_rag_references(manual, auto)
    assert len(merged) == 2
    assert merged[0]["source"] == "manual"
    assert merged[1]["title"] == "JWT"


def test_merge_skips_empty_content_items() -> None:
    manual = [{"title": "noop", "source": "manual"}]
    auto = [{"title": "ok", "source": "qdrant", "content": "본문"}]
    merged = merge_manual_and_auto_rag_references(manual, auto)
    assert len(merged) == 1
    assert merged[0]["title"] == "ok"


class _FakeRetrieverOk:
    def __init__(self, hits: list[Any]) -> None:
        self._hits = hits
        self.calls: list[tuple[str, int | None]] = []

    def retrieve(self, query: str, top_k: int | None = None) -> list[Any]:
        self.calls.append((query, top_k))
        return list(self._hits)


class _FakeRetrieverFailing:
    def retrieve(self, query: str, top_k: int | None = None) -> list[Any]:
        raise RuntimeError("qdrant down")


def test_retrieve_disabled_returns_skipped() -> None:
    out = retrieve_feature_template_rag_references(
        query="anything",
        top_k=3,
        enabled=False,
        retriever=_FakeRetrieverOk([]),
    )
    assert out.attempted is False
    assert out.status == "skipped"
    assert out.skipped_reason == "rag_disabled"
    assert out.references == []


def test_retrieve_empty_query_returns_skipped() -> None:
    out = retrieve_feature_template_rag_references(
        query="   ",
        top_k=3,
        enabled=True,
        retriever=_FakeRetrieverOk([]),
    )
    assert out.attempted is False
    assert out.status == "skipped"
    assert out.skipped_reason == "empty_query"


def test_retrieve_success_converts_hits_into_qdrant_references() -> None:
    hits = [
        RetrievedReference(
            id="d1",
            title="Spring Login Guide",
            content="로그인은 BCrypt로 비밀번호를 검증한다.",
            score=0.95,
            sourceType="document",
            metadata={"docType": "guide", "fileName": "auth.md"},
        ),
        RetrievedReference(
            id="d2",
            title=None,
            content="OAuth2 토큰 흐름 설명.",
            score=0.5,
            sourceType=None,
            metadata={"section": "oauth"},
        ),
    ]
    out = retrieve_feature_template_rag_references(
        query="Spring Boot 로그인 기능템플릿",
        top_k=3,
        enabled=True,
        retriever=_FakeRetrieverOk(hits),
    )
    assert out.attempted is True
    assert out.status == "success"
    assert out.retrieved_count == 2
    assert len(out.references) == 2
    first = out.references[0]
    assert first["source"] == "qdrant"
    assert first["title"] == "Spring Login Guide"
    assert "BCrypt" in first["content"]
    assert first["score"] == 0.95
    assert first["metadata"]["docType"] == "guide"
    second = out.references[1]
    # title 누락 시 metadata에서 보완
    assert second["title"] == "oauth"


def test_retrieve_empty_result_returns_empty_status() -> None:
    out = retrieve_feature_template_rag_references(
        query="q",
        top_k=3,
        enabled=True,
        retriever=_FakeRetrieverOk([]),
    )
    assert out.attempted is True
    assert out.status == "empty"
    assert out.references == []
    assert out.retrieved_count == 0


def test_retrieve_failure_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    out = retrieve_feature_template_rag_references(
        query="q",
        top_k=3,
        enabled=True,
        retriever=_FakeRetrieverFailing(),
    )
    assert out.attempted is True
    assert out.status == "failed"
    assert out.failure_reason and "retrieve_failed" in out.failure_reason


def test_retrieve_hits_without_content_are_filtered() -> None:
    hits = [
        RetrievedReference(
            id="empty",
            title="공백",
            content=" ",
            score=0.5,
            sourceType=None,
            metadata={},
        ),
    ]
    # RetrievedReference content는 minimal validation을 거치지만 ' '는 통과한다.
    # rag_service는 내부적으로 strip 검사로 빈 본문을 걸러야 한다.
    out = retrieve_feature_template_rag_references(
        query="q",
        top_k=3,
        enabled=True,
        retriever=_FakeRetrieverOk(hits),
    )
    assert out.attempted is True
    # retrieved_count는 raw hit 수, references는 정규화 통과 분만 포함
    assert out.retrieved_count == 1
    assert out.references == []
    assert out.status == "empty"

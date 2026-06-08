"""챗봇 질문 유형 판별 — RAG 시도 여부·일반 개념 질문 구분."""

from __future__ import annotations

import re

from app.core.config import settings

__all__ = [
    "has_rag_signal_in_message",
    "is_simple_concept_query",
    "should_attempt_rag_for_general_chat",
]

_RAG_HINTS = (
    "문서",
    "검색",
    "찾아",
    "근거",
    "자료",
    "참고",
    "rag",
    "프로젝트",
    "cobip",
    "기능템플릿",
    "기능 템플릿",
    "문서 기준",
    "문서기준",
)

_PROJECT_DOC_HINTS = (
    "우리 프로젝트",
    "프로젝트에서",
    "프로젝트 기준",
    "cobip",
    "cobip_ai",
)

_CONCEPT_QUESTION_RE = re.compile(
    r"(뭐야|뭔가요|무엇인가요|무엇인지|무엇이|이란|란\?|설명해|설명해줘|알려줘|정의|what\s+is|what's)",
    re.IGNORECASE,
)


def has_rag_signal_in_message(message: str) -> bool:
    lower = (message or "").lower()
    lower_nospace = lower.replace(" ", "")
    for hint in _RAG_HINTS:
        h = hint.lower()
        if h in lower or h.replace(" ", "") in lower_nospace:
            return True
    return False


def _has_project_doc_signal(message: str) -> bool:
    lower = (message or "").lower()
    return any(h in lower for h in _PROJECT_DOC_HINTS)


def is_simple_concept_query(message: str) -> bool:
    """짧은 개념 질문(int, DTO, @RequestBody 등) — RAG 없이 일반 LLM 우선."""

    text = (message or "").strip()
    if not text:
        return False
    if _has_project_doc_signal(text) or has_rag_signal_in_message(text):
        return False
    if _CONCEPT_QUESTION_RE.search(text):
        return True
    compact = text.replace(" ", "")
    if len(compact) <= 16 and " " not in text:
        return True
    if len(text) <= 24 and _CONCEPT_QUESTION_RE.search(text):
        return True
    return False


def should_attempt_rag_for_general_chat(message: str, use_rag: bool | None) -> bool:
    """GENERAL_CHAT에서 Retriever를 시도할지 여부 (RAG_ENABLED 유지)."""

    if not settings.RAG_ENABLED:
        return False
    if is_simple_concept_query(message):
        return False
    if use_rag is True:
        return True
    return has_rag_signal_in_message(message)

"""Agentic RAG 13차: 기능템플릿 자동 RAG retrieval helper.

`/ai/agentic-rag/run`의 feature_template_generate 경로에서 Qdrant 기반
RetrieverService 결과를 `referenceContext.ragReferences` 형태로 변환하고,
수동으로 전달된 reference와 안전하게 병합한다.

이 모듈은 다음 원칙을 따른다.

- Qdrant/embedding 연결 실패는 절대 호출자에게 예외를 던지지 않는다.
- 검색 결과가 0개라도 정상 흐름이며, 단순히 빈 리스트와 ``status="empty"``를 반환한다.
- 수동 referenceContext.ragReferences는 항상 우선 보존되며, 자동 reference는 dedupe 후 추가된다.
"""

from __future__ import annotations

import logging
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings

__all__ = [
    "FeatureTemplateRagRetrieval",
    "RetrieverProtocol",
    "build_feature_template_retrieval_query",
    "merge_manual_and_auto_rag_references",
    "retrieve_feature_template_rag_references",
]

logger = logging.getLogger(__name__)

_AUTO_REF_SOURCE = "qdrant"
_MAX_CONTENT_CHARS = 1000
_MAX_QUERY_CHARS = 256
_MAX_MESSAGE_SNIPPET = 160

RagRetrievalStatus = Literal["success", "empty", "skipped", "failed"]
RagSourceLabel = Literal["manual", "qdrant", "manual+qdrant", "none"]


class RetrieverProtocol(Protocol):
    """`RetrieverService.retrieve`와 동일한 시그니처를 받는 최소 인터페이스."""

    def retrieve(self, query: str, top_k: int | None = None) -> list[Any]:  # pragma: no cover - protocol
        ...


class FeatureTemplateRagRetrieval(BaseModel):
    """자동 retrieval 결과 요약. orchestrator가 trace로 풀어준다."""

    model_config = ConfigDict(extra="ignore")

    attempted: bool = False
    status: RagRetrievalStatus = "skipped"
    references: list[dict[str, Any]] = Field(default_factory=list)
    query: str | None = None
    retrieved_count: int = Field(default=0, ge=0)
    failure_reason: str | None = None
    skipped_reason: str | None = None


def build_feature_template_retrieval_query(
    *,
    message: str | None,
    feature_name: str | None,
    framework: str | None,
    language: str | None,
    level: str | None,
) -> str:
    """기능템플릿 retrieval에 사용할 query 문자열을 합성한다.

    구성: ``{framework} {featureName} {language} {level} 기능템플릿 요구사항 API 코드 학습``
    뒤에 message snippet을 짧게 붙인다. 전체 길이는 ``_MAX_QUERY_CHARS``로 제한한다.
    """

    tokens: list[str] = []
    for raw in (framework, feature_name, language, level):
        if raw is None:
            continue
        text = " ".join(str(raw).split())
        if text:
            tokens.append(text)
    tokens.extend(["기능템플릿", "요구사항", "API", "코드", "학습"])
    base = " ".join(tokens).strip()

    if message:
        msg = " ".join(str(message).split())
        if msg:
            snippet = msg[:_MAX_MESSAGE_SNIPPET]
            base = f"{base} {snippet}".strip() if base else snippet

    if len(base) > _MAX_QUERY_CHARS:
        base = base[:_MAX_QUERY_CHARS].rstrip()
    return base


def _coerce_hit_to_dict(hit: Any) -> dict[str, Any] | None:
    if hit is None:
        return None
    if hasattr(hit, "model_dump"):
        try:
            value = hit.model_dump()
        except Exception:  # pragma: no cover - defensive
            return None
    elif isinstance(hit, dict):
        value = dict(hit)
    else:
        return None
    if not isinstance(value, dict):
        return None
    return value


def _hit_to_reference(hit_dict: dict[str, Any]) -> dict[str, Any] | None:
    """RetrievedReference dict → prompt_builder가 이해하는 ragReference dict."""

    content = hit_dict.get("content")
    if not isinstance(content, str) or not content.strip():
        return None
    body = content.strip()
    if len(body) > _MAX_CONTENT_CHARS:
        body = body[: _MAX_CONTENT_CHARS - 1] + "…"

    metadata_raw = hit_dict.get("metadata")
    metadata: dict[str, Any] = metadata_raw if isinstance(metadata_raw, dict) else {}

    title_val = hit_dict.get("title")
    title_s = title_val.strip() if isinstance(title_val, str) and title_val.strip() else None
    if not title_s:
        for key in ("docType", "section", "fileName", "path", "url"):
            mv = metadata.get(key)
            if isinstance(mv, str) and mv.strip():
                title_s = mv.strip()
                break

    out: dict[str, Any] = {
        "source": _AUTO_REF_SOURCE,
        "content": body,
    }
    if title_s:
        out["title"] = title_s

    source_type = hit_dict.get("sourceType")
    if isinstance(source_type, str) and source_type.strip():
        out["sourceType"] = source_type.strip()

    score = hit_dict.get("score")
    if isinstance(score, (int, float)):
        out["score"] = float(score)

    keep_meta: dict[str, Any] = {}
    for key in ("docType", "section", "fileName", "path", "url"):
        mv = metadata.get(key)
        if isinstance(mv, str) and mv.strip():
            keep_meta[key] = mv.strip()
    if keep_meta:
        out["metadata"] = keep_meta
    return out


def retrieve_feature_template_rag_references(
    *,
    query: str,
    top_k: int | None = None,
    enabled: bool | None = None,
    retriever: RetrieverProtocol | None = None,
) -> FeatureTemplateRagRetrieval:
    """기능템플릿 자동 RAG retrieval. 어떤 단계에서 실패해도 예외를 다시 던지지 않는다."""

    if enabled is None:
        enabled = settings.RAG_ENABLED
    q = (query or "").strip()

    if not enabled:
        return FeatureTemplateRagRetrieval(
            attempted=False,
            status="skipped",
            references=[],
            query=q or None,
            retrieved_count=0,
            skipped_reason="rag_disabled",
        )
    if not q:
        return FeatureTemplateRagRetrieval(
            attempted=False,
            status="skipped",
            references=[],
            query=None,
            retrieved_count=0,
            skipped_reason="empty_query",
        )

    used_retriever = retriever
    if used_retriever is None:
        try:
            from app.services.retriever_service import RetrieverService

            used_retriever = RetrieverService()
        except Exception as exc:
            logger.warning(
                "feature_template rag retriever init failed errorType=%s",
                type(exc).__name__,
            )
            return FeatureTemplateRagRetrieval(
                attempted=True,
                status="failed",
                references=[],
                query=q,
                retrieved_count=0,
                failure_reason=f"retriever_init_failed:{type(exc).__name__}",
            )

    effective_top_k = top_k if top_k is not None else settings.RAG_TOP_K
    try:
        raw_hits = used_retriever.retrieve(q, effective_top_k)
    except Exception as exc:
        logger.warning(
            "feature_template rag retrieve failed errorType=%s",
            type(exc).__name__,
        )
        return FeatureTemplateRagRetrieval(
            attempted=True,
            status="failed",
            references=[],
            query=q,
            retrieved_count=0,
            failure_reason=f"retrieve_failed:{type(exc).__name__}",
        )

    refs: list[dict[str, Any]] = []
    hit_count = 0
    for hit in raw_hits or []:
        hit_count += 1
        coerced = _coerce_hit_to_dict(hit)
        if coerced is None:
            continue
        ref = _hit_to_reference(coerced)
        if ref is None:
            continue
        refs.append(ref)

    status: RagRetrievalStatus = "success" if refs else "empty"
    return FeatureTemplateRagRetrieval(
        attempted=True,
        status=status,
        references=refs,
        query=q,
        retrieved_count=hit_count,
    )


def _ref_dedupe_key(ref: dict[str, Any]) -> str:
    """수동/자동 reference의 중복 판정 키.

    출처(`source`)는 dedupe key에 포함하지 않는다. 동일 문서가 manual/qdrant
    두 채널로 들어와도 한 번만 prompt에 포함되도록 한다.
    """

    title = ref.get("title")
    title_s = title.strip().lower() if isinstance(title, str) else ""
    content = ref.get("content")
    content_head = ""
    if isinstance(content, str):
        content_head = " ".join(content.split())[:100].lower()
    return f"{title_s}|{content_head}"


def merge_manual_and_auto_rag_references(
    manual_refs: list[Any] | None,
    auto_refs: list[Any] | None,
) -> list[dict[str, Any]]:
    """수동 reference를 우선 보존하면서 자동 reference를 dedupe 병합한다."""

    merged: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _maybe_add(raw: Any) -> None:
        if not isinstance(raw, dict):
            return
        content = raw.get("content")
        if not isinstance(content, str) or not content.strip():
            return
        key = _ref_dedupe_key(raw)
        if key in seen:
            return
        seen.add(key)
        merged.append(dict(raw))

    for raw in manual_refs or []:
        _maybe_add(raw)
    for raw in auto_refs or []:
        _maybe_add(raw)
    return merged

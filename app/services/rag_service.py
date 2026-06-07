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

import hashlib
import json
import logging
import time
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings
from app.services.cache_service import CacheService

__all__ = [
    "FeatureTemplateRagRetrieval",
    "RetrieverProtocol",
    "build_feature_template_retrieval_query",
    "classify_feature_template_bucket",
    "effective_feature_template_rag_top_k",
    "build_feature_template_rag_cache_key",
    "feature_template_rag_content_max_chars",
    "merge_manual_and_auto_rag_references",
    "rerank_feature_template_rag_references",
    "retrieve_feature_template_rag_references",
]

logger = logging.getLogger(__name__)

_AUTO_REF_SOURCE = "qdrant"
_MAX_QUERY_CHARS = 256
_MAX_MESSAGE_SNIPPET = 160
_MIN_CONTENT_MAX_CHARS = 50
_MAX_TOP_K = 10
_GENERAL_FEATURE_NAMES = frozenset({"공통", "common", ""})
_LOGIN_BUCKETS = frozenset({"login", "로그인"})
_SIGNUP_BUCKETS = frozenset({"signup", "회원가입", "sign-up", "register", "가입"})
_CRUD_BUCKETS = frozenset({"crud", "게시글 crud", "게시글", "post", "posts", "게시판"})
_JWT_AUTH_BUCKETS = frozenset({"jwt_auth", "jwt 인증", "jwt인증", "jwt authentication"})


def classify_feature_template_bucket(feature_name: str | None) -> str | None:
    """요청/문서 featureName을 검색·rerank용 bucket으로 분류."""

    raw = (feature_name or "").strip()
    if not raw:
        return None
    fn = raw.lower()
    if fn in _LOGIN_BUCKETS or raw in ("로그인", "Login"):
        return "login"
    if fn in _SIGNUP_BUCKETS or "회원가입" in raw or "signup" in fn:
        return "signup"
    if fn in _CRUD_BUCKETS or "crud" in fn or "게시글" in raw:
        return "crud"
    if "jwt" in fn or raw in ("JWT 인증", "JWT인증"):
        return "jwt_auth"
    return fn


def _feature_specific_query_tokens(bucket: str | None) -> list[str]:
    if bucket == "login":
        return ["JWT", "BCrypt", "LoginController", "LoginService", "DTO", "POST /api/auth/login"]
    if bucket == "signup":
        return [
            "회원가입",
            "SignupController",
            "SignupService",
            "BCrypt",
            "email",
            "409",
            "POST /api/auth/signup",
        ]
    if bucket == "crud":
        return [
            "CRUD",
            "게시글",
            "PostController",
            "PostService",
            "PostRepository",
            "Create",
            "Update",
            "Delete",
            "404",
        ]
    if bucket == "jwt_auth":
        return [
            "JWT",
            "JwtTokenProvider",
            "JwtAuthenticationFilter",
            "SecurityConfig",
            "Bearer",
            "Authorization",
            "authenticationRequired",
        ]
    return []


def _ref_payload_feature_name(ref: dict[str, Any]) -> str:
    meta = ref.get("metadata") if isinstance(ref.get("metadata"), dict) else {}
    for key in ("featureName",):
        val = ref.get(key) if key in ref else meta.get(key)
        if isinstance(val, str):
            return val.strip()
    return ""


def rerank_feature_template_rag_references(
    references: list[dict[str, Any]],
    *,
    feature_name: str | None = None,
    framework: str | None = None,
    top_k: int,
) -> list[dict[str, Any]]:
    """vector score + featureName/framework/category 일치로 재정렬."""

    if not references:
        return []
    if top_k < 1:
        return []

    request_bucket = classify_feature_template_bucket(feature_name)
    fw_norm = (framework or "").strip().lower()

    scored: list[tuple[float, int, dict[str, Any]]] = []
    for index, ref in enumerate(references):
        base = float(ref.get("score") or 0.0)
        ref_fn = _ref_payload_feature_name(ref)
        ref_bucket = classify_feature_template_bucket(ref_fn)
        meta = ref.get("metadata") if isinstance(ref.get("metadata"), dict) else {}
        ref_cat = (ref.get("category") or meta.get("category") or "").strip()
        ref_fw = (ref.get("framework") or meta.get("framework") or "").strip().lower()

        bonus = 0.0
        if request_bucket and ref_bucket == request_bucket:
            bonus += 2.5
        if feature_name and ref_fn and feature_name.strip() == ref_fn:
            bonus += 1.5
        if ref_fn in _GENERAL_FEATURE_NAMES:
            bonus += 0.25
        elif request_bucket and ref_bucket == "login" and request_bucket != "login":
            bonus -= 1.75
        if ref_cat == "feature_template":
            bonus += 0.15
        if fw_norm and ref_fw and "spring" in fw_norm and "spring" in ref_fw:
            bonus += 0.15

        scored.append((base + bonus, -index, ref))

    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [item[2] for item in scored[:top_k]]


def _retrieval_fetch_top_k(requested_top_k: int) -> int:
    """rerank 여유를 위해 Qdrant에서 더 많이 가져온다."""

    return min(_MAX_TOP_K, max(requested_top_k * 2, requested_top_k + 3))


def feature_template_rag_content_max_chars() -> int:
    """기능템플릿 RAG reference content 최대 길이(환경변수 기반)."""

    return max(_MIN_CONTENT_MAX_CHARS, int(settings.FEATURE_TEMPLATE_RAG_CONTENT_MAX_CHARS))


def effective_feature_template_rag_top_k(top_k: int | None = None) -> int:
    """기능템플릿 RAG 검색 top_k (1~10, 기본 settings.FEATURE_TEMPLATE_RAG_TOP_K)."""

    k = top_k if top_k is not None else settings.FEATURE_TEMPLATE_RAG_TOP_K
    return max(1, min(_MAX_TOP_K, int(k)))

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
    embedding_ms: int = 0
    qdrant_search_ms: int = 0
    reference_build_ms: int = 0
    cache_hit: bool = False
    cache_key: str | None = None


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
    fn_text = ""
    if feature_name is not None:
        fn_text = " ".join(str(feature_name).split())
        if fn_text:
            tokens.extend([fn_text, fn_text])

    bucket = classify_feature_template_bucket(feature_name)
    tokens.extend(_feature_specific_query_tokens(bucket))

    for raw in (framework, language, level):
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
    max_chars = feature_template_rag_content_max_chars()
    truncated = False
    original_len = len(body)
    if len(body) > max_chars:
        body = body[: max_chars - 1] + "…"
        truncated = True

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
    for key in ("docType", "section", "fileName", "path", "url", "category", "framework", "featureName", "source", "contentPreview"):
        mv = metadata.get(key)
        if isinstance(mv, str) and mv.strip():
            keep_meta[key] = mv.strip()
    if truncated:
        keep_meta["contentTruncated"] = True
        keep_meta["originalContentLength"] = original_len
    if keep_meta:
        out["metadata"] = keep_meta

    payload_source = metadata.get("source")
    if isinstance(payload_source, str) and payload_source.strip():
        out["source"] = payload_source.strip()
    for key in ("category", "framework", "featureName"):
        val = metadata.get(key)
        if isinstance(val, str) and val.strip():
            out[key] = val.strip()
    return out


def retrieve_feature_template_rag_references(
    *,
    query: str,
    top_k: int | None = None,
    enabled: bool | None = None,
    retriever: RetrieverProtocol | None = None,
    cache_service: CacheService | None = None,
    feature_name: str | None = None,
    framework: str | None = None,
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
            embedding_ms=0,
            qdrant_search_ms=0,
            reference_build_ms=0,
        )
    if not q:
        return FeatureTemplateRagRetrieval(
            attempted=False,
            status="skipped",
            references=[],
            query=None,
            retrieved_count=0,
            skipped_reason="empty_query",
            embedding_ms=0,
            qdrant_search_ms=0,
            reference_build_ms=0,
        )

    used_cache = cache_service or CacheService()
    effective_top_k = effective_feature_template_rag_top_k(top_k)
    cache_key = build_feature_template_rag_cache_key(
        query=q,
        top_k=effective_top_k,
        feature_name=feature_name,
    )
    if settings.RAG_RETRIEVAL_CACHE_ENABLED:
        cached = used_cache.get_json(cache_key)
        if isinstance(cached, dict):
            refs = cached.get("references")
            if isinstance(refs, list):
                return FeatureTemplateRagRetrieval(
                    attempted=True,
                    status=str(cached.get("status") or "success"),
                    references=[r for r in refs if isinstance(r, dict)],
                    query=q,
                    retrieved_count=int(cached.get("retrieved_count") or len(refs)),
                    embedding_ms=0,
                    qdrant_search_ms=0,
                    reference_build_ms=0,
                    cache_hit=True,
                    cache_key=cache_key,
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
                cache_hit=False,
                cache_key=cache_key if settings.RAG_RETRIEVAL_CACHE_ENABLED else None,
            )

    effective_top_k = effective_feature_template_rag_top_k(top_k)
    fetch_k = _retrieval_fetch_top_k(effective_top_k)
    embedding_ms = 0
    qdrant_search_ms = 0
    try:
        if hasattr(used_retriever, "retrieve_with_timing"):
            timing_result = used_retriever.retrieve_with_timing(q, fetch_k)
            raw_hits = timing_result.references
            embedding_ms = int(getattr(timing_result, "embeddingMs", 0) or 0)
            qdrant_search_ms = int(getattr(timing_result, "qdrantSearchMs", 0) or 0)
        else:
            raw_hits = used_retriever.retrieve(q, fetch_k)
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
            embedding_ms=embedding_ms,
            qdrant_search_ms=qdrant_search_ms,
            reference_build_ms=0,
            cache_hit=False,
            cache_key=cache_key if settings.RAG_RETRIEVAL_CACHE_ENABLED else None,
        )

    refs: list[dict[str, Any]] = []
    hit_count = 0
    t_ref = time.perf_counter()
    for hit in raw_hits or []:
        hit_count += 1
        coerced = _coerce_hit_to_dict(hit)
        if coerced is None:
            continue
        ref = _hit_to_reference(coerced)
        if ref is None:
            continue
        refs.append(ref)
    reference_build_ms = max(0, int((time.perf_counter() - t_ref) * 1000))

    refs = rerank_feature_template_rag_references(
        refs,
        feature_name=feature_name,
        framework=framework,
        top_k=effective_top_k,
    )

    status: RagRetrievalStatus = "success" if refs else "empty"
    out = FeatureTemplateRagRetrieval(
        attempted=True,
        status=status,
        references=refs,
        query=q,
        retrieved_count=hit_count,
        embedding_ms=embedding_ms,
        qdrant_search_ms=qdrant_search_ms,
        reference_build_ms=reference_build_ms,
        cache_hit=False,
        cache_key=cache_key if settings.RAG_RETRIEVAL_CACHE_ENABLED else None,
    )
    if settings.RAG_RETRIEVAL_CACHE_ENABLED:
        used_cache.set_json(
            cache_key,
            {
                "status": status,
                "references": refs,
                "retrieved_count": hit_count,
            },
            settings.RAG_RETRIEVAL_CACHE_TTL_SECONDS,
        )
    return out


def build_feature_template_rag_cache_key(
    *,
    query: str,
    top_k: int,
    feature_name: str | None = None,
) -> str:
    payload = {
        "query": query,
        "top_k": top_k,
        "feature_name": (feature_name or "").strip(),
        "content_max_chars": feature_template_rag_content_max_chars(),
        "collection": settings.QDRANT_COLLECTION,
        "embedding_model": settings.EMBEDDING_MODEL,
        "version": "v2",
    }
    normalized = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]
    return f"rag:feature-template:v1:{digest}"


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

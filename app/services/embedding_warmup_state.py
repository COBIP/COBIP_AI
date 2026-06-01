"""서버 startup embedding warm-up 상태 (운영 로그·health 관측용)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings
from app.services.embedding_service import EmbeddingService

__all__ = [
    "EmbeddingWarmupState",
    "get_embedding_warmup_state",
    "run_startup_embedding_warmup",
    "embedding_warmup_status_dict",
]


@dataclass
class EmbeddingWarmupState:
    embeddingWarmupEnabled: bool = False
    ragEnabled: bool = False
    embeddingModel: str = ""
    embeddingWarmupAttempted: bool = False
    embeddingWarmupSucceeded: bool = False
    embeddingWarmupMs: int | None = None
    embeddingWarmupSkippedReason: str | None = None
    embeddingWarmupErrorType: str | None = None


_state = EmbeddingWarmupState()


def get_embedding_warmup_state() -> EmbeddingWarmupState:
    return _state


def embedding_warmup_status_dict() -> dict[str, Any]:
    s = _state
    return {
        "embeddingWarmupEnabled": s.embeddingWarmupEnabled,
        "ragEnabled": s.ragEnabled,
        "embeddingModel": s.embeddingModel,
        "embeddingWarmupAttempted": s.embeddingWarmupAttempted,
        "embeddingWarmupSucceeded": s.embeddingWarmupSucceeded,
        "embeddingWarmupMs": s.embeddingWarmupMs,
        "embeddingWarmupSkippedReason": s.embeddingWarmupSkippedReason,
        "embeddingWarmupErrorType": s.embeddingWarmupErrorType,
    }


def run_startup_embedding_warmup(
    logger: logging.Logger | None = None,
) -> None:
    """FastAPI lifespan에서 호출. warm-up 실패 시에도 예외를 던지지 않는다."""

    log = logger or logging.getLogger("app")
    s = _state
    s.embeddingWarmupEnabled = settings.EMBEDDING_WARMUP_ENABLED
    s.ragEnabled = settings.RAG_ENABLED
    s.embeddingModel = settings.EMBEDDING_MODEL

    if not settings.EMBEDDING_WARMUP_ENABLED:
        s.embeddingWarmupSkippedReason = "warmup_disabled"
        log.info(
            "Embedding warm-up skipped because EMBEDDING_WARMUP_ENABLED=false "
            "(RAG_ENABLED=%s, EMBEDDING_MODEL=%s)",
            settings.RAG_ENABLED,
            settings.EMBEDDING_MODEL,
        )
        return

    if not settings.RAG_ENABLED:
        s.embeddingWarmupSkippedReason = "rag_disabled"
        log.info(
            "Embedding warm-up skipped because RAG_ENABLED=false "
            "(EMBEDDING_WARMUP_ENABLED=true, EMBEDDING_MODEL=%s)",
            settings.EMBEDDING_MODEL,
        )
        return

    warmup_text = settings.EMBEDDING_WARMUP_TEXT
    log.info(
        "Embedding warm-up started (RAG_ENABLED=true, EMBEDDING_WARMUP_ENABLED=true, "
        "EMBEDDING_MODEL=%s, textLen=%s)",
        settings.EMBEDDING_MODEL,
        len(warmup_text or ""),
    )
    s.embeddingWarmupAttempted = True
    t0 = time.perf_counter()
    ok, error_type = EmbeddingService().warm_up_with_detail(warmup_text)
    s.embeddingWarmupMs = max(0, int((time.perf_counter() - t0) * 1000))
    s.embeddingWarmupSucceeded = ok
    s.embeddingWarmupErrorType = error_type

    if ok:
        log.info(
            "Embedding warm-up completed in %s ms (shared model loaded for RAG retrieval)",
            s.embeddingWarmupMs,
        )
    else:
        log.warning(
            "Embedding warm-up failed but startup continues: elapsedMs=%s errorType=%s",
            s.embeddingWarmupMs,
            error_type or "unknown",
        )

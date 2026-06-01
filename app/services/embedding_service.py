"""sentence-transformers 기반 임베딩 service (lazy 로딩).

모델은 첫 embed 호출 시 로드한다. ChatService 등에는 이 단계에서 연결하지 않는다.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

from app.core.config import settings

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

__all__ = ["EmbeddingService"]

logger = logging.getLogger(__name__)


class EmbeddingService:
    """BGE-M3 등 설정 모델로 문장 임베딩 (GPU 미강제)."""

    _shared_model: "SentenceTransformer | None" = None
    _shared_model_lock = threading.Lock()

    def __init__(self) -> None:
        self._model: SentenceTransformer | None = None
        self._model_lock = threading.Lock()

    def _get_model(self) -> "SentenceTransformer":
        if EmbeddingService._shared_model is not None:
            return EmbeddingService._shared_model

        # shared model을 우선 사용해 요청마다 모델 재초기화를 막는다.
        with EmbeddingService._shared_model_lock:
            if EmbeddingService._shared_model is not None:
                return EmbeddingService._shared_model

            from sentence_transformers import SentenceTransformer

            name = settings.EMBEDDING_MODEL
            logger.info("embedding model load model=%s", name)
            EmbeddingService._shared_model = SentenceTransformer(name, device=None)
            return EmbeddingService._shared_model

    def _get_model_legacy_lock(self) -> "SentenceTransformer":
        """하위 호환용: 인스턴스 잠금 경로 (테스트 안전)."""
        with self._model_lock:
            if self._model is None:
                from sentence_transformers import SentenceTransformer

                name = settings.EMBEDDING_MODEL
                logger.info("embedding model load model=%s", name)
                self._model = SentenceTransformer(name, device=None)
            return self._model

    def normalize_text(self, text: str) -> str:
        return " ".join((text or "").split())

    def embed_text(self, text: str) -> list[float]:
        normalized = self.normalize_text(text)
        if not normalized:
            raise ValueError("text must not be empty")
        model = self._get_model()
        vec = model.encode(normalized, convert_to_numpy=True, show_progress_bar=False)
        return vec.tolist()

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            raise ValueError("texts must not be empty")
        cleaned: list[str] = []
        for i, raw in enumerate(texts):
            n = self.normalize_text(raw)
            if not n:
                raise ValueError(f"texts[{i}] must not be empty")
            cleaned.append(n)
        model = self._get_model()
        mat = model.encode(cleaned, convert_to_numpy=True, show_progress_bar=False)
        return [mat[i].tolist() for i in range(len(cleaned))]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """문서 배치 임베딩 (embed_texts 와 동일)."""
        if not texts:
            return []
        return self.embed_texts(texts)

    def embed_query(self, query: str) -> list[float]:
        return self.embed_text(query)

    def warm_up(self, text: str | None = None) -> bool:
        """임베딩 모델 warm-up. 실패해도 예외 대신 False를 반환한다."""

        ok, _error = self.warm_up_with_detail(text)
        return ok

    def warm_up_with_detail(self, text: str | None = None) -> tuple[bool, str | None]:
        """warm-up 수행. RAG retrieval과 동일한 shared model·embed_query 경로를 사용한다."""

        try:
            target = self.normalize_text(text or settings.EMBEDDING_WARMUP_TEXT)
            if not target:
                target = "warmup"
            # embed_query → _get_model() 로 process-level shared SentenceTransformer 로드
            _ = self.embed_query(target)
            if EmbeddingService._shared_model is None:
                logger.warning("embedding warmup finished but shared model is unset")
                return False, "shared_model_unset"
            return True, None
        except Exception as exc:  # pragma: no cover - runtime 환경 의존
            error_type = type(exc).__name__
            logger.warning("embedding warmup failed errorType=%s", error_type)
            return False, error_type

    @classmethod
    def is_shared_model_loaded(cls) -> bool:
        return cls._shared_model is not None

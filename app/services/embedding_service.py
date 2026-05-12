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

    def __init__(self) -> None:
        self._model: SentenceTransformer | None = None
        self._model_lock = threading.Lock()

    def _get_model(self) -> "SentenceTransformer":
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

"""Qdrant RAG 문서 인덱싱 (/ai/chat 미연동)."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from app.core.config import settings
from app.schemas.rag import RagIndexRequest, RagIndexResponseData
from app.services.embedding_service import EmbeddingService
from app.services.qdrant_service import QdrantService

__all__ = ["RagIndexingService"]

logger = logging.getLogger(__name__)

_DEFAULT_SOURCE = "manual"
_TITLE_MAX = 120


def _fallback_title(content: str) -> str:
    text = content.strip()
    if len(text) <= _TITLE_MAX:
        return text
    return text[: _TITLE_MAX - 1] + "…"


class RagIndexingService:
    """문서 임베딩 후 Qdrant upsert."""

    def __init__(self) -> None:
        self._embed = EmbeddingService()
        self._qdrant = QdrantService()

    def index(self, request: RagIndexRequest) -> RagIndexResponseData:
        collection = settings.QDRANT_COLLECTION
        n = len(request.documents)
        logger.info("rag index start document_count=%s", n)

        texts = [d.content for d in request.documents]
        try:
            vectors = self._embed.embed_texts(texts)
        except Exception as exc:
            logger.warning("rag index embed failed errorType=%s", type(exc).__name__)
            return RagIndexResponseData(indexedCount=0, collection=collection, ids=[])

        if not vectors:
            logger.warning("rag index embed empty vectors")
            return RagIndexResponseData(indexedCount=0, collection=collection, ids=[])

        vector_size = len(vectors[0])
        logger.info("rag index embedding complete count=%s vector_size=%s", len(vectors), vector_size)

        if not self._qdrant.ensure_collection(vector_size, collection_name=collection):
            logger.warning("rag index ensure_collection failed")
            return RagIndexResponseData(indexedCount=0, collection=collection, ids=[])

        logger.info("rag index qdrant ensure_collection ok collection=%s", collection)

        points: list[dict[str, Any]] = []
        ids_out: list[str] = []
        for doc, vec in zip(request.documents, vectors, strict=True):
            pid = (doc.id or "").strip() or str(uuid.uuid4())
            title = (doc.title or "").strip() or _fallback_title(doc.content)
            source_type = (doc.sourceType or "").strip() or _DEFAULT_SOURCE
            payload = {
                "title": title,
                "content": doc.content,
                "sourceType": source_type,
                "metadata": doc.metadata or {},
            }
            points.append({"id": pid, "vector": vec, "payload": payload})
            ids_out.append(str(pid))

        if not self._qdrant.upsert(points, collection_name=collection):
            logger.warning("rag index qdrant upsert failed")
            return RagIndexResponseData(indexedCount=0, collection=collection, ids=[])

        logger.info("rag index qdrant upsert complete indexed_count=%s", len(points))
        return RagIndexResponseData(
            indexedCount=len(points),
            collection=collection,
            ids=ids_out,
        )

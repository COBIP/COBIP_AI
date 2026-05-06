"""BGE-M3 임베딩 service 구조 (mock 단계).

이 단계에서는 실제 BGE-M3 모델을 로드하지 않고
sentence-transformers / Qdrant 연결도 하지 않는다.
- 동일 입력에 동일 벡터를 반환하도록 sha256 기반의 결정적(deterministic) 임시 벡터를 생성.
- 실제 모델 연동(추론·캐싱·배치)은 추후 단계에서 추가한다.
"""

import hashlib

__all__ = ["EmbeddingService"]


_MOCK_VECTOR_DIM = 8


class EmbeddingService:
    """BGE-M3 임베딩 service (mock 단계, 실제 모델 미사용)."""

    def normalize_text(self, text: str) -> str:
        """공백 정리: 앞뒤 공백 제거 + 내부 연속 공백을 단일 공백으로 압축."""
        return " ".join((text or "").split())

    def embed_text(self, text: str) -> list[float]:
        """단일 텍스트의 임시 임베딩 벡터를 반환한다 (mock).

        동일 텍스트는 동일 벡터를 보장한다 (sha256 기반).
        """
        normalized = self.normalize_text(text)
        return self._mock_vector(normalized)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """문서 리스트에 대한 임시 임베딩 벡터 리스트 반환 (mock)."""
        return [self.embed_text(t) for t in (texts or [])]

    def embed_query(self, query: str) -> list[float]:
        """검색용 쿼리 임시 임베딩 (mock).

        실제 BGE-M3 에서는 query 와 document 가 동일 모델로 임베딩되지만
        역할 구분을 위해 별도 메서드로 둔다 (이후 prompt 분기·캐시 키 분리 등에 활용).
        """
        return self.embed_text(query)

    # ------------------------------------------------------------------
    # internal: deterministic mock vector
    # ------------------------------------------------------------------
    @staticmethod
    def _mock_vector(text: str, dim: int = _MOCK_VECTOR_DIM) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        # digest 의 바이트를 [-1.0, 1.0] 범위 float 로 변환
        return [(digest[i % len(digest)] / 255.0) * 2 - 1 for i in range(dim)]

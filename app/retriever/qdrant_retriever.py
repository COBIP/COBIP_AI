"""
QdrantRetriever: 향후 Qdrant + BGE-M3 + BGE-Reranker 연동용 스켈레톤.
실제 연동 시 TODO 부분만 채우면 된다.
"""

from __future__ import annotations

from app.config import settings
from app.retriever.base import BaseRetriever


class QdrantRetriever(BaseRetriever):
    def __init__(self) -> None:
        self.qdrant_url = settings.qdrant_url
        self.collection_name = settings.qdrant_collection_name
        # TODO: qdrant_client.QdrantClient 초기화
        # TODO: BGE-M3 임베딩 모델 로드

    async def retrieve(
        self,
        problem_id: int,
        user_code: str,
        question: str,
    ) -> list[str]:
        """
        실제 RAG 흐름:
        1. question + user_code를 BGE-M3로 임베딩
        2. Qdrant에서 problem_id 필터 + 벡터 유사도 검색
        3. BGE-Reranker로 결과 재정렬
        4. 상위 N개 텍스트 반환
        """
        # TODO: 아래 의사 코드를 실제 구현으로 교체
        #
        # query_vector = self.embedding_model.encode(f"{question} {user_code}")
        #
        # search_results = self.qdrant_client.search(
        #     collection_name=self.collection_name,
        #     query_vector=query_vector,
        #     query_filter={"must": [{"key": "problem_id", "match": {"value": problem_id}}]},
        #     limit=10,
        # )
        #
        # candidates = [hit.payload["text"] for hit in search_results]
        #
        # reranked = self.reranker.rerank(question, candidates, top_n=5)
        #
        # return reranked

        raise NotImplementedError(
            "QdrantRetriever는 아직 구현되지 않았습니다. "
            "USE_MOCK=true로 설정하거나 Qdrant 연동을 완성하세요."
        )

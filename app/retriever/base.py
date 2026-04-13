"""
Retriever 추상 인터페이스.
MockRetriever, QdrantRetriever 등 구현체가 이 인터페이스를 따른다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseRetriever(ABC):
    @abstractmethod
    async def retrieve(
        self,
        problem_id: int,
        user_code: str,
        question: str,
    ) -> list[str]:
        """
        문제 ID, 사용자 코드, 질문을 기반으로 관련 지식 조각을 검색한다.

        Returns:
            관련 context 문자열 리스트
        """
        ...

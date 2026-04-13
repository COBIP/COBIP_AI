"""
MockRetriever: 프로토타입용 in-memory 검색.
problem_store에서 해당 문제의 지식 조각을 반환한다.
Qdrant 없이도 RAG 파이프라인을 테스트할 수 있다.
"""

from __future__ import annotations

from app.data.problem_store import get_problem
from app.retriever.base import BaseRetriever


class MockRetriever(BaseRetriever):
    async def retrieve(
        self,
        problem_id: int,
        user_code: str,
        question: str,
    ) -> list[str]:
        problem = get_problem(problem_id)
        if problem is None:
            return ["해당 문제를 찾을 수 없습니다."]

        context_pieces: list[str] = []

        # 1) 핵심 개념
        context_pieces.append(f"[개념] {problem.concept}")

        # 2) 힌트
        context_pieces.append(f"[힌트] {problem.hint}")

        # 3) 사용자 코드와 매칭되는 wrongPattern 피드백
        user_code_stripped = user_code.strip()
        for wp in problem.wrong_patterns:
            if wp.pattern.strip() == user_code_stripped:
                context_pieces.append(
                    f"[오류-{wp.error_type}] {wp.feedback}"
                )

        # 4) explanation_chunks 전체
        for chunk in problem.explanation_chunks:
            context_pieces.append(f"[설명] {chunk}")

        # 5) 정답 코드
        context_pieces.append(f"[정답] {problem.answer_code}")

        return context_pieces

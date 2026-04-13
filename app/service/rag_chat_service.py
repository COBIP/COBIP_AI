"""
RAG Chat Service.
핵심 오케스트레이션: Retriever → PromptBuilder → LLMClient
"""

from __future__ import annotations

from app.data.problem_store import get_problem
from app.dto.schemas import ChatRequest, ChatResponse
from app.llm.base import BaseLLMClient
from app.prompt.prompt_builder import build_prompt
from app.retriever.base import BaseRetriever


class RAGChatService:
    def __init__(
        self,
        retriever: BaseRetriever,
        llm_client: BaseLLMClient,
    ) -> None:
        self.retriever = retriever
        self.llm_client = llm_client

    async def chat(self, request: ChatRequest) -> ChatResponse:
        # 1) 문제 데이터 조회
        problem = get_problem(request.problem_id)
        if problem is None:
            return ChatResponse(
                answer=f"문제 ID {request.problem_id}을(를) 찾을 수 없습니다.",
                retrieved_context=[],
            )

        # 2) RAG 검색
        retrieved_context = await self.retriever.retrieve(
            problem_id=request.problem_id,
            user_code=request.user_code,
            question=request.question,
        )

        # 3) 프롬프트 구성
        system_prompt, user_prompt = build_prompt(
            retrieved_context=retrieved_context,
            user_code=request.user_code,
            question=request.question,
            problem_title=problem.title,
            problem_description=problem.description,
        )

        # 4) LLM 호출
        answer = await self.llm_client.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

        return ChatResponse(
            answer=answer,
            retrieved_context=retrieved_context,
        )

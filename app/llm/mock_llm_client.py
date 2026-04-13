"""
MockLLMClient: 프로토타입용 mock 답변 생성.
vLLM 없이도 RAG 파이프라인을 테스트할 수 있다.
"""

from __future__ import annotations

from app.llm.base import BaseLLMClient


class MockLLMClient(BaseLLMClient):
    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        return (
            "[Mock LLM 응답]\n"
            "사용자의 코드를 분석한 결과, 제출한 코드에 오류가 있습니다.\n"
            "아래 검색된 context를 참고하여 설명드리겠습니다.\n\n"
            f"--- 시스템 프롬프트 요약 ---\n{system_prompt[:200]}...\n\n"
            f"--- 사용자 질문 ---\n{user_prompt[:200]}...\n\n"
            "위 정보를 바탕으로, 자료형을 확인하고 코드를 수정해보세요."
        )

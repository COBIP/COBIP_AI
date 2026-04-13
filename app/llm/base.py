"""
LLM Client 추상 인터페이스.
MockLLMClient, VLLMClient 등 구현체가 이 인터페이스를 따른다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseLLMClient(ABC):
    @abstractmethod
    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        """
        시스템 프롬프트와 유저 프롬프트를 받아 LLM 답변을 생성한다.

        Returns:
            LLM이 생성한 텍스트 답변
        """
        ...

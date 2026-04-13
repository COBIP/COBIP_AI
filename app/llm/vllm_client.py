"""
VLLMClient: vLLM의 OpenAI-compatible API를 호출하는 클라이언트.
config의 VLLM_BASE_URL, VLLM_MODEL_NAME을 사용한다.
"""

from __future__ import annotations

import httpx

from app.config import settings
from app.llm.base import BaseLLMClient


class VLLMClient(BaseLLMClient):
    def __init__(self) -> None:
        self.base_url = settings.vllm_base_url
        self.model_name = settings.vllm_model_name
        self.max_tokens = settings.vllm_max_tokens
        self.temperature = settings.vllm_temperature

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        return data["choices"][0]["message"]["content"]

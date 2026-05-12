"""OpenAI-호환 /chat/completions 호출 service.

이 단계에서는 호출 "구조"만 만든다.
- VLLM_BASE_URL 이 설정되어 있으면 실제 OpenAI-호환 엔드포인트로 POST.
- 설정되어 있지 않으면 임시 응답(mock)을 반환해, 다른 service 가 LLMService 를
  안전하게 의존할 수 있도록 한다.
- 오류는 RuntimeError 로 통일해 던진다 (네트워크 오류·타임아웃·파싱 실패 등).

LLM 서버 자체는 FastAPI 서버에 설치하지 않는다.
GPU 서버 또는 별도 컨테이너에서 실행되는 OpenAI-호환 HTTP API 만 호출한다.
"""

import json
import logging
import re

import httpx

from app.core.config import settings

__all__ = ["LLMService"]


logger = logging.getLogger(__name__)


class LLMService:
    """OpenAI-호환 LLM 호출 service (mock fallback 포함)."""

    # ------------------------------------------------------------------
    # public
    # ------------------------------------------------------------------
    @property
    def provider(self) -> str:
        provider = settings.LLM_PROVIDER.strip().lower()
        return "ollama" if provider == "ollama" else "vllm"

    def build_messages(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> list[dict]:
        """OpenAI-호환 messages 배열을 만든다."""
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def generate_text(self, prompt: str) -> str:
        """단일 prompt 로 텍스트 응답을 받는다.

        VLLM_BASE_URL 미설정 시 mock 텍스트를 반환한다.
        설정 시에는 build_messages 로 OpenAI-호환 messages 를 만들어
        call_vllm 을 호출하고 choices[0].message.content 를 반환한다.
        """
        if not settings.VLLM_BASE_URL:
            return self._mock_text(prompt)

        messages = self.build_messages(
            system_prompt="You are a helpful assistant.",
            user_prompt=prompt,
        )
        result = self.call_vllm(messages)
        return self._extract_content(result)

    def generate_json(self, prompt: str) -> dict:
        """단일 prompt 로 JSON 응답을 받아 dict 로 반환한다.

        VLLM_BASE_URL 미설정 시 mock dict 를 반환한다.
        설정 시 generate_text() 결과에서 첫 JSON object 를 파싱한다.
        """
        if not settings.VLLM_BASE_URL:
            return self._mock_json(prompt)

        text = self.generate_text(prompt)
        return self._parse_json_object(text)

    def call_vllm(self, messages: list[dict]) -> dict:
        """OpenAI-호환 /chat/completions 엔드포인트를 호출한다.

        VLLM_BASE_URL 미설정 시 mock OpenAI-호환 응답을 반환한다.
        네트워크 오류·HTTP 오류·타임아웃은 RuntimeError 로 감싸 던진다.
        VLLM_BASE_URL 끝의 '/' 유무와 무관하게 중복 슬래시 없이 호출한다.
        """
        if not settings.VLLM_BASE_URL:
            return self._mock_response(messages)

        url = f"{settings.VLLM_BASE_URL.rstrip('/')}/chat/completions"
        model_name = (
            settings.VLLM_MODEL
            or settings.VLLM_MODEL_NAME
            or settings.LLM_MODEL_NAME
        )
        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": settings.LLM_TEMPERATURE,
            "max_tokens": settings.LLM_MAX_TOKENS,
        }

        logger.info(
            "provider=%s mode=llm_call model=%s",
            self.provider,
            model_name,
        )
        try:
            with httpx.Client(timeout=settings.LLM_TIMEOUT_SECONDS) as client:
                response = client.post(url, json=payload)
                response.raise_for_status()
                logger.info("provider=%s mode=llm_ok", self.provider)
                return response.json()
        except httpx.TimeoutException as exc:
            raise RuntimeError(
                f"LLM 호출 타임아웃 ({settings.LLM_TIMEOUT_SECONDS}s 초과)"
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                "LLM 호출 실패: "
                f"HTTP {exc.response.status_code} {exc.response.reason_phrase}"
            ) from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"LLM 호출 네트워크 오류: {exc}") from exc

    # ------------------------------------------------------------------
    # internal: response parsing
    # ------------------------------------------------------------------
    @staticmethod
    def _extract_content(result: dict) -> str:
        """OpenAI-호환 응답에서 choices[0].message.content 를 안전하게 꺼낸다."""
        try:
            choices = result["choices"]
            if not choices:
                raise KeyError("choices is empty")
            message = choices[0]["message"]
            content = message["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(
                f"LLM 응답 형식이 OpenAI-호환 스키마가 아닙니다: {result!r}"
            ) from exc

        if not isinstance(content, str):
            raise RuntimeError(
                f"LLM 응답 content 가 문자열이 아닙니다: {type(content).__name__}"
            )
        return content

    @staticmethod
    def _parse_json_object(text: str) -> dict:
        cleaned = re.sub(r"```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        cleaned = cleaned.replace("```", "").strip()

        decoder = json.JSONDecoder()
        for index, char in enumerate(cleaned):
            if char != "{":
                continue
            try:
                parsed, _ = decoder.raw_decode(cleaned[index:])
            except json.JSONDecodeError:
                continue
            if not isinstance(parsed, dict):
                raise RuntimeError(
                    "LLM 응답 JSON 타입이 dict 가 아닙니다. "
                    f"실제 타입: {type(parsed).__name__}"
                )
            return parsed

        raise RuntimeError(
            "LLM 응답에서 JSON object 를 찾을 수 없습니다. "
            f"앞 200자: {cleaned[:200]!r}"
        )

    # ------------------------------------------------------------------
    # internal: mock fallbacks (VLLM_BASE_URL 미설정 시)
    # ------------------------------------------------------------------
    @staticmethod
    def _mock_text(prompt: str) -> str:
        return (
            "(mock) VLLM_BASE_URL 미설정 상태입니다. "
            "실제 LLM 호출 대신 임시 텍스트를 반환합니다. "
            f"prompt 길이: {len(prompt)}"
        )

    @staticmethod
    def _mock_json(prompt: str) -> dict:
        return {
            "mock": True,
            "warning": "VLLM_BASE_URL 미설정으로 인한 임시 dict 응답입니다.",
            "promptLength": len(prompt),
        }

    @staticmethod
    def _mock_response(messages: list[dict]) -> dict:
        last_user = next(
            (m.get("content", "") for m in reversed(messages) if m.get("role") == "user"),
            "",
        )
        return {
            "id": "mock-completion",
            "object": "chat.completion",
            "model": settings.LLM_MODEL_NAME,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": (
                            "(mock) VLLM_BASE_URL 미설정으로 인한 임시 응답입니다. "
                            f"마지막 user 메시지 길이: {len(last_user)}"
                        ),
                    },
                    "finish_reason": "stop",
                }
            ],
        }

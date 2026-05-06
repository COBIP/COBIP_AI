"""vLLM (OpenAI-호환 /chat/completions) 호출 service.

이 단계에서는 호출 "구조"만 만든다.
- VLLM_BASE_URL 이 설정되어 있으면 실제 OpenAI-호환 엔드포인트로 POST.
- 설정되어 있지 않으면 임시 응답(mock)을 반환해, 다른 service 가 LLMService 를
  안전하게 의존할 수 있도록 한다.
- 오류는 RuntimeError 로 통일해 던진다 (네트워크 오류·타임아웃·파싱 실패 등).
"""

import json

import httpx

from app.core.config import settings

__all__ = ["LLMService"]


class LLMService:
    """vLLM (OpenAI-호환) 호출 service (mock fallback 포함)."""

    # ------------------------------------------------------------------
    # public
    # ------------------------------------------------------------------
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
        """
        if not settings.VLLM_BASE_URL:
            return self._mock_text(prompt)

        messages = [{"role": "user", "content": prompt}]
        result = self.call_vllm(messages)
        return self._extract_content(result)

    def generate_json(self, prompt: str) -> dict:
        """단일 prompt 로 JSON 응답을 받아 dict 로 반환한다.

        VLLM_BASE_URL 미설정 시 mock dict 를 반환한다.
        실제 LLM 응답이 JSON 으로 파싱되지 않으면 RuntimeError.
        """
        if not settings.VLLM_BASE_URL:
            return self._mock_json(prompt)

        text = self.generate_text(prompt)
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "LLM 응답을 JSON 으로 파싱할 수 없습니다. "
                f"앞 200자: {text[:200]!r}"
            ) from exc

    def call_vllm(self, messages: list[dict]) -> dict:
        """vLLM /chat/completions 엔드포인트를 호출한다.

        VLLM_BASE_URL 미설정 시 mock OpenAI-호환 응답을 반환한다.
        네트워크 오류·HTTP 오류·타임아웃은 RuntimeError 로 감싸 던진다.
        """
        if not settings.VLLM_BASE_URL:
            return self._mock_response(messages)

        url = f"{settings.VLLM_BASE_URL.rstrip('/')}/chat/completions"
        payload = {
            "model": settings.LLM_MODEL_NAME,
            "messages": messages,
            "temperature": settings.LLM_TEMPERATURE,
            "max_tokens": settings.LLM_MAX_TOKENS,
        }

        try:
            with httpx.Client(timeout=settings.LLM_TIMEOUT_SECONDS) as client:
                response = client.post(url, json=payload)
                response.raise_for_status()
                return response.json()
        except httpx.TimeoutException as exc:
            raise RuntimeError(
                f"LLM 호출 타임아웃 ({settings.LLM_TIMEOUT_SECONDS}s 초과)"
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"LLM 호출 실패: HTTP {exc.response.status_code} {exc.response.reason_phrase}"
            ) from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"LLM 호출 네트워크 오류: {exc}") from exc

    # ------------------------------------------------------------------
    # internal: response parsing
    # ------------------------------------------------------------------
    @staticmethod
    def _extract_content(result: dict) -> str:
        try:
            return result["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(
                f"LLM 응답 형식이 OpenAI-호환 스키마가 아닙니다: {result!r}"
            ) from exc

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

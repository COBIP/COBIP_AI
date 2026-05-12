"""Intent별 /ai/chat 처리 핸들러 (구조 분리; 멀티스텝·LLM 분류·tool calling 없음)."""

from __future__ import annotations

import logging

from app.core.config import settings
from app.schemas.chat import AgentPayload, ChatRequest, ChatResponseData
from app.services.chat_service import ChatService

__all__ = [
    "FeatureTemplateHelpHandler",
    "GeneralChatHandler",
    "RagSearchHandler",
    "UnknownHandler",
]

logger = logging.getLogger(__name__)

_UNKNOWN_REPLY = (
    "요청 내용을 이해하지 못했습니다. 조금 더 구체적으로 입력해주세요."
)

_FEATURE_KEYWORD_LABELS: tuple[tuple[str, str], ...] = (
    ("요구사항", "요구사항"),
    ("api 명세", "API 명세"),
    ("erd", "ERD"),
    ("면접 질문", "면접 질문"),
    ("미션", "미션"),
    ("전체 코드", "전체 코드"),
)


def _feature_help_matched_topics(message: str) -> list[str]:
    """사용자 메시지에 나타난 기능템플릿 확장 주제 라벨."""
    lower = message.lower()
    lower_nospace = lower.replace(" ", "")
    matched: list[str] = []
    for needle, label in _FEATURE_KEYWORD_LABELS:
        n = needle.lower().replace(" ", "")
        if n in lower_nospace or needle in message or needle.lower() in lower:
            if label not in matched:
                matched.append(label)
    return matched


def _build_feature_template_help_answer(message: str) -> str:
    topics = _feature_help_matched_topics(message)
    topic_line = ""
    if topics:
        joined = ", ".join(topics)
        topic_line = (
            f"\n\n질문에 「{joined}」와 관련된 표현이 보입니다. "
            "이런 항목은 기능템플릿 생성 결과(산출물 구성·설명 범위 등)에 반영되거나, "
            "옵션·본문에 포함될 수 있으니 요청 JSON의 featureName·level 등과 함께 구체적으로 적어 주세요."
        )

    return f"""기능 템플릿은 HTTP **POST /ai/feature-template/generate** 로 요청합니다. (이 채널에서 API를 대신 호출하지는 않습니다.)

## 요청 시 넣을 수 있는 입력값
- **language**: 사용 언어 (예: `java`, `python`, `javascript`)
- **framework**: 프레임워크 (예: `spring-boot`, `fastapi`, `react`)
- **featureName**: 만들 기능 이름 (예: 로그인, 회원가입, 게시글 CRUD)
- **level**: 난이도 — `beginner` / `intermediate` / `advanced`
- **includeCode**: 코드 예시 포함 여부 (`true` / `false`)
- **includeMissions**: 미션 포함 여부 (`true` / `false`)
- **includeInterview**: 면접 질문 포함 여부 (`true` / `false`)

## 요청 JSON 예시
```json
{{
  "language": "java",
  "framework": "spring-boot",
  "featureName": "로그인",
  "level": "beginner",
  "includeCode": true,
  "includeMissions": true,
  "includeInterview": true
}}
```

`Content-Type: application/json` 으로 위와 같은 본문을 내면 됩니다.{topic_line}"""


class GeneralChatHandler:
    """일반 대화: useRag=true 이고 RAG_ENABLED=true일 때만 RAG."""

    async def handle(self, request: ChatRequest, agent: AgentPayload) -> ChatResponseData:
        apply_rag = settings.RAG_ENABLED and (request.useRag is True)
        query_len = len(request.message)
        logger.info(
            "agent_handler general_chat apply_rag=%s query_len=%s",
            apply_rag,
            query_len,
        )
        return ChatService().answer(
            request,
            apply_rag=apply_rag,
            variant="default",
            agent=agent,
        )


class RagSearchHandler:
    """RAG 검색 의도: RAG_ENABLED이면 Retriever 사용."""

    async def handle(self, request: ChatRequest, agent: AgentPayload) -> ChatResponseData:
        apply_rag = settings.RAG_ENABLED
        query_len = len(request.message)
        logger.info(
            "agent_handler rag_search apply_rag=%s query_len=%s",
            apply_rag,
            query_len,
        )
        return ChatService().answer(
            request,
            apply_rag=apply_rag,
            variant="default",
            agent=agent,
        )


class FeatureTemplateHelpHandler:
    """기능 템플릿: /ai/feature-template/generate 사용법·JSON 예시 고정 안내 (RAG·LLM 미사용)."""

    async def handle(self, request: ChatRequest, agent: AgentPayload) -> ChatResponseData:
        query_len = len(request.message)
        logger.info(
            "agent_handler feature_template_help apply_rag=false query_len=%s static_help=true",
            query_len,
        )
        answer = _build_feature_template_help_answer(request.message)
        return ChatResponseData(
            answer=answer,
            source="ollama",
            ragUsed=False,
            references=[],
            agent=agent,
        )


class UnknownHandler:
    """UNKNOWN: LLM 없이 고정 안내."""

    async def handle(self, request: ChatRequest, agent: AgentPayload) -> ChatResponseData:
        query_len = len(request.message)
        logger.info(
            "agent_handler unknown apply_rag=false query_len=%s unknown_reply=true",
            query_len,
        )
        return ChatResponseData(
            answer=_UNKNOWN_REPLY,
            source="ollama",
            ragUsed=False,
            references=[],
            agent=agent,
        )

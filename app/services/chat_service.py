"""보조 Q&A 챗봇 service (Ollama / LLMService, 선택 RAG context 주입)."""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import settings
from app.schemas.chat import ChatRequest, ChatResponseData
from app.schemas.rag import RetrievedReference
from app.services.llm_service import LLMService
from app.services.retriever_service import RetrieverService

__all__ = ["ChatService"]

logger = logging.getLogger(__name__)

_FALLBACK_ANSWER = (
    "현재 AI 응답 생성에 실패했습니다. 잠시 후 다시 시도해 주세요."
)

_MAX_RAG_DOC_CHARS = 800
_MAX_RAG_BLOCK_CHARS = 6000

_CHAT_SYSTEM_PROMPT = """당신은 개발 학습 플랫폼의 보조 챗봇이다.
규칙:
- 항상 한국어로 답한다.
- 초보자도 이해하도록 짧고 친절하게 설명한다.
- 코드·개념·실습·오류 해결 질문에 도움이 되게 답한다.
- 모르는 내용은 지어내지 말고 모른다고 말한다.
- 외부 문서를 검색해 확인했다는 식의 표현("문서에서 확인했다", "업로드된 자료에 따르면" 등)은 쓰지 않는다.
- 답은 과도하게 길지 않게 한다. 필요하면 짧은 예시 코드만 포함한다.
- 사용자가 제공한 참고 맥락(context)이 있으면 그것을 반영해 답하고, 없으면 일반 지식으로 답한다.
"""

_RAG_SYSTEM_APPEND = """
[검색 참고자료 사용]
아래 사용자 메시지에 포함된 [검색 참고자료] 블록이 있으면 그 내용을 우선 참고하되,
거기에 없는 사실은 확정적으로 단정하지 말고 모른다고 말한다.
"""


def _truncate(text: str, max_len: int) -> str:
    t = (text or "").strip()
    if len(t) <= max_len:
        return t
    return t[: max_len - 1] + "…"


def _format_rag_block(refs: list[RetrievedReference]) -> str:
    lines: list[str] = ["[검색 참고자료]"]
    total = 0
    for i, ref in enumerate(refs, start=1):
        body = _truncate(ref.content, _MAX_RAG_DOC_CHARS)
        title = ref.title or "(제목 없음)"
        st = ref.sourceType or ""
        score = ref.score
        chunk = (
            f"{i}. 제목: {title}\n"
            f"내용: {body}\n"
            f"출처유형: {st}\n"
            f"점수: {score}\n"
        )
        if total + len(chunk) > _MAX_RAG_BLOCK_CHARS:
            break
        lines.append(chunk)
        total += len(chunk)
    return "\n".join(lines)


class ChatService:
    """보조 Q&A 챗봇 (LLMService → Ollama). RAG_ENABLED·useRag 시 Retriever 결과를 프롬프트에 주입."""

    def answer(self, request: ChatRequest) -> ChatResponseData:
        llm = LLMService()
        msg_len = len(request.message)
        has_ctx = bool(request.context and request.context.strip())
        rag_requested = request.useRag is True
        rag_enabled = settings.RAG_ENABLED

        logger.info(
            "chat start provider=%s query_len=%s context_present=%s "
            "rag_requested=%s rag_enabled=%s",
            llm.provider,
            msg_len,
            has_ctx,
            rag_requested,
            rag_enabled,
        )

        rag_used = False
        references: list[Any] = []
        rag_block = ""

        if rag_enabled and rag_requested:
            try:
                refs = RetrieverService().retrieve(
                    request.message,
                    settings.RAG_TOP_K,
                )
                if refs:
                    rag_used = True
                    references = [r.model_dump() for r in refs]
                    rag_block = _format_rag_block(refs)
            except Exception as exc:
                logger.warning(
                    "chat rag retrieve skipped errorType=%s rag_used=false",
                    type(exc).__name__,
                )
                rag_used = False
                references = []

        user_prompt = ChatService._build_user_prompt(request, rag_block=rag_block)
        system_prompt = (
            _CHAT_SYSTEM_PROMPT + _RAG_SYSTEM_APPEND if rag_block else _CHAT_SYSTEM_PROMPT
        )

        try:
            text = llm.generate_text(
                user_prompt,
                system_prompt=system_prompt,
            )
            answer = (text or "").strip()
            if not answer:
                raise RuntimeError("empty_llm_content")

            logger.info(
                "chat complete provider=%s source=ollama rag_used=%s "
                "references_count=%s query_len=%s fallback=%s",
                llm.provider,
                rag_used,
                len(references),
                msg_len,
                False,
            )
            return ChatResponseData(
                answer=answer,
                source="ollama",
                ragUsed=rag_used,
                references=references,
            )
        except Exception as exc:
            err_type = type(exc).__name__
            logger.warning(
                "chat failed provider=%s source=fallback errorType=%s "
                "rag_used=%s references_count=%s query_len=%s fallback=%s",
                llm.provider,
                err_type,
                rag_used,
                len(references),
                msg_len,
                True,
            )
            return ChatResponseData(
                answer=_FALLBACK_ANSWER,
                source="fallback",
                ragUsed=rag_used,
                references=references,
            )

    @staticmethod
    def _build_user_prompt(request: ChatRequest, rag_block: str = "") -> str:
        parts: list[str] = [f"질문:\n{request.message}"]
        ctx = (request.context or "").strip()
        if ctx:
            parts.append(f"참고 맥락 (사용자가 직접 제공):\n{ctx}")
        if rag_block.strip():
            parts.append(rag_block.strip())
        parts.append("위 내용에 맞게 답해 주세요.")
        return "\n\n".join(parts)

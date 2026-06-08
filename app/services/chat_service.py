"""보조 Q&A 챗봇 service (Ollama / LLMService, 선택 RAG context 주입)."""

from __future__ import annotations

import logging
from typing import Any, Literal

from app.core.config import settings
from app.schemas.chat import AgentPayload, ChatRequest, ChatResponseData
from app.schemas.rag import RetrievedReference
from app.services.chat_query_policy import is_simple_concept_query
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
사용자 메시지에 [검색 참고자료] 블록이 포함되어 있다. 그 내용을 우선 참고하되,
거기에 없는 사실은 확정적으로 단정하지 말고 모른다고 말한다.
"""

_GENERAL_CONCEPT_APPEND = """
[일반 개념 설명]
이 질문은 프로그래밍·개발 일반 개념에 대한 것이다. 검색 참고자료 없이도
일반 지식으로 바로 답한다.
- "검색 참고자료가 없다", "정보를 찾을 수 없다", "다시 질문해 달라"고 말하지 않는다.
- 질문에 맞는 핵심 개념을 2~5문장으로 설명한다.
"""

_RAG_EMPTY_GENERAL_APPEND = """
[참고자료 검색 결과 없음]
프로젝트 문서 검색을 시도했지만 관련 참고자료가 없었다.
이 경우 일반 개발 지식으로 질문에 답한다.
- 참고자료 부재를 사과하거나 "검색 참고자료 블록이 제공되지 않았다"고 말하지 않는다.
- "정보를 찾을 수 없습니다", "외부 정보를 찾을 수 없습니다" 같은 실패 멘트를 쓰지 않는다.
"""

_FEATURE_HELP_APPEND = """
[기능 템플릿·산출물 안내]
사용자가 기능 명세, 요구사항, API 명세, ERD, 면접 질문 등 **구조화된 산출물**을 원하는 것으로 보일 수 있다.
- 실제 **기능 템플릿(코드/문서 골격) 생성**은 HTTP `POST /ai/feature-template/generate` 로 요청한다.
  (JSON 예: language, featureName, level 등 — 서버 스키마를 따른다.)
- 이 대화에서는 API 사용법·필드 의미만 간단히 안내하고, 긴 전체 코드 생성은 피한다.
"""

_RAG_FAILURE_PHRASES: tuple[str, ...] = (
    "검색 참고자료",
    "참고자료 블록",
    "제공되지 않았",
    "제공되지 않",
    "정보를 찾을 수 없",
    "찾을 수 없습니다",
    "외부 정보를 찾을 수 없",
    "다시 질문해",
    "다시 질문해주",
)


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
        if not body:
            continue
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
    if len(lines) <= 1:
        return ""
    return "\n".join(lines)


def _is_rag_failure_answer(answer: str) -> bool:
    low = (answer or "").lower()
    return any(p.lower() in low for p in _RAG_FAILURE_PHRASES)


def _refs_with_content(refs: list[RetrievedReference]) -> list[RetrievedReference]:
    return [r for r in refs if (r.content or "").strip()]


class ChatService:
    """보조 Q&A 챗봇 (LLMService → Ollama). apply_rag 시 Retriever 결과를 프롬프트에 주입."""

    def answer(
        self,
        request: ChatRequest,
        *,
        apply_rag: bool,
        variant: Literal["default", "feature_help"] = "default",
        agent: AgentPayload,
    ) -> ChatResponseData:
        llm = LLMService()
        msg_len = len(request.message)
        has_ctx = bool(request.context and request.context.strip())
        rag_enabled = settings.RAG_ENABLED
        concept_query = is_simple_concept_query(request.message)

        rag_attempted = False
        rag_context_found = False
        fallback_to_general_llm = concept_query or not apply_rag

        logger.info(
            "chat start provider=%s query_len=%s context_present=%s "
            "rag_enabled=%s apply_rag=%s concept_query=%s agent_intent=%s variant=%s",
            llm.provider,
            msg_len,
            has_ctx,
            rag_enabled,
            apply_rag,
            concept_query,
            agent.intent,
            variant,
        )

        rag_used = False
        references: list[Any] = []
        rag_block = ""

        if apply_rag and not concept_query:
            rag_attempted = True
            try:
                refs = _refs_with_content(
                    RetrieverService().retrieve(
                        request.message,
                        settings.RAG_TOP_K,
                    )
                )
                if refs:
                    rag_context_found = True
                    rag_used = True
                    references = [r.model_dump() for r in refs]
                    rag_block = _format_rag_block(refs)
                    if not rag_block.strip():
                        rag_context_found = False
                        rag_used = False
                        references = []
                if not rag_context_found:
                    fallback_to_general_llm = True
            except Exception as exc:
                logger.warning(
                    "chat rag retrieve skipped errorType=%s rag_used=false",
                    type(exc).__name__,
                )
                rag_used = False
                references = []
                fallback_to_general_llm = True

        system_prompt = self._build_system_prompt(
            variant=variant,
            rag_block=rag_block,
            concept_query=concept_query,
            fallback_to_general_llm=fallback_to_general_llm,
        )
        user_prompt = ChatService._build_user_prompt(request, rag_block=rag_block)

        try:
            text = llm.generate_text(
                user_prompt,
                system_prompt=system_prompt,
            )
            answer = (text or "").strip()
            if not answer:
                raise RuntimeError("empty_llm_content")

            if _is_rag_failure_answer(answer):
                logger.info(
                    "chat rag_failure_phrase_detected retrying_general query_len=%s "
                    "rag_attempted=%s rag_context_found=%s",
                    msg_len,
                    rag_attempted,
                    rag_context_found,
                )
                fallback_to_general_llm = True
                retry_system = (
                    _CHAT_SYSTEM_PROMPT
                    + _GENERAL_CONCEPT_APPEND
                    + "\n절대 참고자료 부재를 언급하지 말고 질문에 직접 답하라."
                )
                retry_text = llm.generate_text(
                    ChatService._build_user_prompt(request, rag_block=""),
                    system_prompt=retry_system,
                )
                answer = (retry_text or "").strip()
                if not answer:
                    raise RuntimeError("empty_llm_content_retry")
                rag_used = False

            logger.info(
                "chat complete provider=%s source=ollama rag_used=%s "
                "rag_attempted=%s rag_context_found=%s fallback_to_general_llm=%s "
                "references_count=%s query_len=%s fallback=%s agent_intent=%s",
                llm.provider,
                rag_used,
                rag_attempted,
                rag_context_found,
                fallback_to_general_llm,
                len(references),
                msg_len,
                False,
                agent.intent,
            )
            return ChatResponseData(
                answer=answer,
                source="ollama",
                ragUsed=rag_used,
                references=references,
                agent=agent,
            )
        except Exception as exc:
            err_type = type(exc).__name__
            logger.warning(
                "chat failed provider=%s source=fallback errorType=%s "
                "rag_used=%s rag_attempted=%s rag_context_found=%s "
                "fallback_to_general_llm=%s references_count=%s query_len=%s "
                "fallback=%s agent_intent=%s",
                llm.provider,
                err_type,
                rag_used,
                rag_attempted,
                rag_context_found,
                fallback_to_general_llm,
                len(references),
                msg_len,
                True,
                agent.intent,
            )
            return ChatResponseData(
                answer=_FALLBACK_ANSWER,
                source="fallback",
                ragUsed=rag_used,
                references=references,
                agent=agent,
            )

    @staticmethod
    def _build_system_prompt(
        *,
        variant: Literal["default", "feature_help"],
        rag_block: str,
        concept_query: bool,
        fallback_to_general_llm: bool,
    ) -> str:
        system_prompt = _CHAT_SYSTEM_PROMPT
        if variant == "feature_help":
            system_prompt = system_prompt + _FEATURE_HELP_APPEND
        if rag_block.strip():
            system_prompt = system_prompt + _RAG_SYSTEM_APPEND
        elif concept_query or fallback_to_general_llm:
            system_prompt = system_prompt + _GENERAL_CONCEPT_APPEND
            if fallback_to_general_llm and not concept_query:
                system_prompt = system_prompt + _RAG_EMPTY_GENERAL_APPEND
        return system_prompt

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

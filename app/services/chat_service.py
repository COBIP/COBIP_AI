"""보조 Q&A 챗봇 service.

⚠️ 위치 정책:
- 챗봇은 이 시스템의 "핵심 기능"이 아니다.
- 핵심 기능은 기능템플릿 생성·문법 문제 생성/채점·미션 피드백·면접 피드백이다.
- 챗봇은 그 외의 단순 질문에 답하는 "보조 Q&A" 기능으로만 동작한다.
- 따라서 우선순위·리소스 배분에서도 기능템플릿 생성 라인보다 항상 낮다.

이 단계에서는 실제 외부 LLM 호출과 Qdrant 검색 없이
임시 답변과 빈 references 만 반환한다.
"""

from app.schemas.chat import ChatRequest, ChatResponse

__all__ = ["ChatService"]


class ChatService:
    """보조 Q&A 챗봇 service (mock 단계)."""

    def answer(self, request: ChatRequest) -> ChatResponse:
        message = (request.message or "").strip()

        if not message:
            answer_text = (
                "질문 내용이 비어 있습니다. 학습 도중 궁금한 점을 한 줄로 적어 주세요."
            )
        else:
            answer_text = (
                f"(mock) 질문하신 \"{message}\" 에 대해 임시 답변을 반환합니다. "
                "실제 답변은 추후 RAG/LLM 연동 후 본문·기능템플릿 컨텍스트에서 추출됩니다. "
                "이 챗봇은 기능템플릿 생성을 보조하는 Q&A 기능으로만 동작합니다."
            )

        return ChatResponse(
            answer=answer_text,
            references=[],
        )

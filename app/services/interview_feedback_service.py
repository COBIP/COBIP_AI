"""면접 답변 평가 service.

이 단계에서는 실제 LLM(vLLM/Qwen) 없이 키워드 포함 여부 기반 rule 로 구현한다.
실제 LLM 연동은 추후 단계에서 추가한다.
"""

from pydantic import BaseModel

__all__ = [
    "InterviewFeedbackService",
    "InterviewFeedbackRequest",
    "InterviewFeedbackResponse",
]


# ---------------------------------------------------------------------------
# InterviewFeedbackRequest / InterviewFeedbackResponse
#
# NOTE: 두 모델은 임시로 service 파일에 정의한다.
#       schemas/evaluation.py 또는 schemas/interview.py 로 이동시킬지 여부는
#       이후 정리 단계에서 결정.
# ---------------------------------------------------------------------------
class InterviewFeedbackRequest(BaseModel):
    featureName: str
    topic: str | None = None
    question: str
    keyPoints: list[str]
    userAnswer: str
    modelAnswer: str | None = None


class InterviewFeedbackResponse(BaseModel):
    score: int
    feedback: str
    includedKeyPoints: list[str]
    missingKeyPoints: list[str]
    improvedAnswer: str


class InterviewFeedbackService:
    """면접 답변 평가 service (rule 기반 mock)."""

    def generate_feedback(
        self,
        request: InterviewFeedbackRequest,
    ) -> InterviewFeedbackResponse:
        user_answer_lower = (request.userAnswer or "").lower()

        included: list[str] = []
        missing: list[str] = []
        for point in request.keyPoints:
            keyword = point.strip()
            if not keyword:
                continue
            if keyword.lower() in user_answer_lower:
                included.append(point)
            else:
                missing.append(point)

        total = len(included) + len(missing)
        score = int(round(100 * len(included) / total)) if total > 0 else 0

        if total == 0:
            feedback = (
                "평가할 keyPoints 가 비어 있어 점수를 산정하기 어렵습니다. "
                "면접 질문의 핵심 키 포인트를 함께 전달해 주세요."
            )
        elif score >= 80:
            feedback = (
                "주요 포인트를 잘 짚어 답변했습니다. 핵심 흐름을 명확히 설명한 점이 좋습니다."
            )
        elif score >= 50:
            feedback = (
                "필수 포인트 일부가 누락되었습니다. 빠진 항목을 보강하면 답변이 더 탄탄해집니다."
            )
        else:
            feedback = (
                "핵심 포인트가 다수 누락되었습니다. 답변 구성 단계에서 키워드를 점검하고 "
                "각 포인트를 한 문장씩 짚어보는 연습을 권장합니다."
            )

        improved_parts: list[str] = []
        if request.modelAnswer:
            improved_parts.append(request.modelAnswer.strip())
        if missing:
            improved_parts.append("[보강 포인트] " + ", ".join(missing))
        improved_answer = "\n".join(improved_parts).strip()
        if not improved_answer:
            improved_answer = (
                f"{request.featureName} 관련 답변에는 다음 키 포인트가 포함되어야 합니다: "
                + ", ".join(request.keyPoints)
                if request.keyPoints
                else f"{request.featureName} 관련 답변의 핵심 키 포인트를 정리해 주세요."
            )

        return InterviewFeedbackResponse(
            score=score,
            feedback=feedback,
            includedKeyPoints=included,
            missingKeyPoints=missing,
            improvedAnswer=improved_answer,
        )

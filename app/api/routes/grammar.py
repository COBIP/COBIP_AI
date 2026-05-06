from fastapi import APIRouter

from app.schemas.common import ApiResponse
from app.schemas.grammar import (
    GrammarExplainWrongAnswerRequest,
    GrammarGenerateQuestionsRequest,
    GrammarGradeAnswerRequest,
)
from app.services.grammar_question_service import GrammarQuestionService

router = APIRouter(prefix="/ai/grammar", tags=["grammar"])


@router.post("/generate-questions", response_model=ApiResponse)
def generate_questions(
    request: GrammarGenerateQuestionsRequest,
) -> ApiResponse:
    result = GrammarQuestionService().generate_questions(request)
    return ApiResponse(
        success=True,
        message="문법 문제 생성이 완료되었습니다.",
        data=result.model_dump(),
    )


@router.post("/grade-answer", response_model=ApiResponse)
def grade_answer(
    request: GrammarGradeAnswerRequest,
) -> ApiResponse:
    result = GrammarQuestionService().grade_answer(request)
    return ApiResponse(
        success=True,
        message="문법 답안 채점이 완료되었습니다.",
        data=result.model_dump(),
    )


@router.post("/explain-wrong-answer", response_model=ApiResponse)
def explain_wrong_answer(
    request: GrammarExplainWrongAnswerRequest,
) -> ApiResponse:
    result = GrammarQuestionService().explain_wrong_answer(request)
    return ApiResponse(
        success=True,
        message="문법 오답 해설이 완료되었습니다.",
        data=result.model_dump(),
    )

"""기능템플릿 기본 문제 채점 + 코드 조각 분석 service.

이 단계에서는 실제 LLM(vLLM/Qwen) 호출 없이 rule 기반 임시 구현이다.
실제 LLM 연동, 정적 분석 도구 연동은 추후 단계에서 추가한다.
"""

from pydantic import BaseModel

from app.schemas.evaluation import (
    CodeIssueSchema,
    QuizGradeRequest,
    QuizGradeResponse,
    SubmittedCodeSchema,
)

__all__ = [
    "EvaluationService",
    "CodeAnalyzeRequest",
    "CodeAnalyzeResponse",
]


# ---------------------------------------------------------------------------
# CodeAnalyzeRequest / CodeAnalyzeResponse
#
# NOTE: 두 모델은 임시로 service 파일에 정의한다.
#       schemas/evaluation.py 로 이동시킬지 여부는 다음 정리 단계에서 결정.
# ---------------------------------------------------------------------------
class CodeAnalyzeRequest(BaseModel):
    language: str
    codeFiles: list[SubmittedCodeSchema]
    context: dict | None = None


class CodeAnalyzeResponse(BaseModel):
    summary: str
    explanation: str
    issues: list[CodeIssueSchema]
    suggestions: list[str]


class EvaluationService:
    """기능템플릿 기본 문제 채점 + 코드 분석 service (mock 단계)."""

    def grade_quiz(self, request: QuizGradeRequest) -> QuizGradeResponse:
        correct_answer = (request.question.answer or "").strip()
        user_answer = (request.userAnswer or "").strip()
        is_correct = correct_answer == user_answer

        score = 100 if is_correct else 0
        feedback = (
            "정답입니다. 잘 하셨어요."
            if is_correct
            else "오답입니다. 해설을 확인하고 다시 시도해 보세요."
        )

        return QuizGradeResponse(
            isCorrect=is_correct,
            score=score,
            feedback=feedback,
            correctAnswer=correct_answer,
            explanation=(
                "(mock) 정답 해설은 기능템플릿의 requirements / apiSpec / flow 를 "
                "참고해 작성되어야 합니다. 본문에 없는 새 개념은 도입하지 않습니다."
            ),
            relatedSection=None,
        )

    def analyze_code(self, request: CodeAnalyzeRequest) -> CodeAnalyzeResponse:
        file_count = len(request.codeFiles)
        first_file = request.codeFiles[0].fileName if request.codeFiles else "(없음)"

        summary = (
            f"(mock) {request.language} 코드 {file_count}개 파일을 분석한 요약입니다. "
            f"첫 번째 파일: {first_file}"
        )
        explanation = (
            "(mock) 제출된 코드의 구조·의도·계층 책임을 요약 설명합니다. "
            "실제로는 LLM 분석 결과로 대체됩니다."
        )

        issues: list[CodeIssueSchema] = []
        if request.codeFiles:
            issues.append(
                CodeIssueSchema(
                    fileName=first_file,
                    line=None,
                    severity="info",
                    message="(mock) 잠재적 이슈 예시 — 실제 분석 결과로 대체됩니다.",
                    suggestion="(mock) 개선 제안 예시 — 실제 분석 결과로 대체됩니다.",
                )
            )

        suggestions = [
            "(mock) 단일 책임 원칙 준수 여부 점검",
            "(mock) 입력값 검증 누락 여부 확인",
            "(mock) 예외 처리 및 응답 포맷 일관성 점검",
        ]

        return CodeAnalyzeResponse(
            summary=summary,
            explanation=explanation,
            issues=issues,
            suggestions=suggestions,
        )

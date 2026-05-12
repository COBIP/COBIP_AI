"""문법템플릿 문제 생성 / 채점 / 오답 설명 service.

이 단계에서는 실제 외부 LLM 없이 rule 기반 임시 구현이다.
실제 LLM 연동은 추후 단계에서 추가한다.

매우 중요한 정책:
- 문법템플릿의 본문(content)을 새로 생성·수정·재작성하지 않는다.
- 기존 JSONB content 는 참고만 하고, 추가 문제 생성·채점·오답 설명만 수행한다.
"""

from app.models.enums import QuestionType
from app.schemas.feature_template import QuestionSchema
from app.schemas.grammar import (
    GrammarExplainWrongAnswerRequest,
    GrammarExplainWrongAnswerResponse,
    GrammarGenerateQuestionsRequest,
    GrammarGenerateQuestionsResponse,
    GrammarGradeAnswerRequest,
    GrammarGradeAnswerResponse,
)

__all__ = ["GrammarQuestionService"]


class GrammarQuestionService:
    """문법템플릿 문제/채점/오답 설명 service (mock 단계)."""

    def generate_questions(
        self,
        request: GrammarGenerateQuestionsRequest,
    ) -> GrammarGenerateQuestionsResponse:
        questions: list[QuestionSchema] = []
        count = max(0, request.count)
        for i in range(count):
            idx = i + 1
            question_text, answer_text, choices = self._build_mock_question(
                question_type=request.questionType,
                title=request.title,
                idx=idx,
            )
            questions.append(
                QuestionSchema(
                    questionId=f"GQ-{idx:03d}",
                    type=request.questionType,
                    question=question_text,
                    choices=choices,
                    answer=answer_text,
                    explanation=(
                        "(mock) 기존 문법템플릿 content.sections 를 참고해 생성된 "
                        "임시 문제 해설입니다."
                    ),
                    relatedSection="sections",
                    difficulty=request.difficulty,
                )
            )
        return GrammarGenerateQuestionsResponse(questions=questions)

    def grade_answer(
        self,
        request: GrammarGradeAnswerRequest,
    ) -> GrammarGradeAnswerResponse:
        correct_answer = (request.question.answer or "").strip()
        user_answer = (request.userAnswer or "").strip()
        is_correct = correct_answer == user_answer

        score = 100 if is_correct else 0
        feedback = (
            "정답입니다. 잘 하셨어요."
            if is_correct
            else "오답입니다. 해설을 확인하고 다시 시도해 보세요."
        )

        return GrammarGradeAnswerResponse(
            isCorrect=is_correct,
            score=score,
            feedback=feedback,
            correctAnswer=correct_answer,
            explanation=(
                "(mock) 정답 해설은 본문 content.sections 를 참고하여 작성되어야 합니다. "
                "본문에 없는 새 개념은 도입하지 않습니다."
            ),
            relatedConcepts=[],
        )

    def explain_wrong_answer(
        self,
        request: GrammarExplainWrongAnswerRequest,
    ) -> GrammarExplainWrongAnswerResponse:
        correct_answer = (request.question.answer or "").strip()
        user_answer = (request.userAnswer or "").strip()

        return GrammarExplainWrongAnswerResponse(
            explanation=(
                f"제출하신 답안 '{user_answer}' 은(는) 정답과 일치하지 않습니다. "
                f"정답은 '{correct_answer}' 입니다. "
                "어떤 부분이 본문 설명과 어긋났는지 한 줄씩 비교해 보세요. (mock)"
            ),
            easyExplanation=(
                "쉽게 말하면, 본문에서 다룬 핵심 개념을 그대로 적용하면 됩니다. "
                "본문에 등장한 용어와 예시를 그대로 따라가 보면 정답에 가까워집니다."
            ),
            example=(
                "본문 sections 의 예시를 그대로 따라가 보세요. "
                "예시 패턴 → 동일한 패턴으로 답을 구성하면 됩니다. (mock)"
            ),
            retryHint=(
                "정답을 직접 보지 말고, 본문의 해당 section 한 부분만 다시 읽고 "
                "그 부분의 핵심 키워드를 답안으로 적어 보세요."
            ),
        )

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------
    def _build_mock_question(
        self,
        question_type: QuestionType,
        title: str,
        idx: int,
    ) -> tuple[str, str, list[str] | None]:
        if question_type == QuestionType.MULTIPLE_CHOICE:
            correct = f"보기{(idx - 1) % 4 + 1}"
            choices = [correct, "보기A", "보기B", "보기C"]
            return (
                f"[{title}] 객관식 문제 {idx}: 본문에 따른 올바른 설명을 고르세요.",
                correct,
                choices,
            )
        if question_type == QuestionType.FILL_BLANK:
            return (
                f"[{title}] 빈칸 문제 {idx}: 본문 sections 의 핵심 키워드로 빈칸을 채우세요. ___",
                f"answer_{idx}",
                None,
            )
        if question_type == QuestionType.OUTPUT_PREDICTION:
            return (
                f"[{title}] 출력 예측 문제 {idx}: 다음 코드의 출력 결과는 무엇인가요?",
                f"output_{idx}",
                None,
            )
        if question_type == QuestionType.CODE_ERROR_FIND:
            return (
                f"[{title}] 코드 오류 찾기 문제 {idx}: 다음 코드에서 오류가 있는 위치는?",
                f"line_{idx}",
                None,
            )
        if question_type == QuestionType.CODE_FILL:
            return (
                f"[{title}] 코드 빈칸 문제 {idx}: 빈칸에 들어갈 코드 조각을 작성하세요. ___",
                f"snippet_{idx}",
                None,
            )
        # SHORT_ANSWER (default)
        return (
            f"[{title}] 단답형 문제 {idx}: 본문에서 다룬 핵심 키워드 한 단어를 적으세요.",
            f"키워드_{idx}",
            None,
        )

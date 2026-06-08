"""기능템플릿 기본 문제 채점 + 코드 조각 분석 service."""

from __future__ import annotations

import re

from app.models.enums import QuestionType
from app.schemas.evaluation import (
    CodeAnalyzeRequest,
    CodeAnalyzeResponse,
    QuizGradeRequest,
    QuizGradeResponse,
)
from app.services.evaluation_payload_normalizer import (
    extract_answer_keywords,
    normalize_answer_text,
)

__all__ = [
    "EvaluationService",
    "CodeAnalyzeRequest",
    "CodeAnalyzeResponse",
]


class EvaluationService:
    """기능템플릿 기본 문제 채점 + 코드 분석 service."""

    def grade_quiz(self, request: QuizGradeRequest) -> QuizGradeResponse:
        correct_answer = (request.question.answer or "").strip()
        user_answer = (request.userAnswer or "").strip()
        q_type = request.question.type

        is_correct, score = self._grade_answer(
            correct_answer=correct_answer,
            user_answer=user_answer,
            question_type=q_type,
            choices=request.question.choices,
        )

        feedback = (
            "정답입니다. 잘 하셨어요."
            if is_correct
            else "오답입니다. 해설을 확인하고 다시 시도해 보세요."
        )
        if not is_correct and score >= 50:
            feedback = "핵심 키워드는 맞지만 표현이 정답과 다릅니다. 해설을 참고하세요."

        return QuizGradeResponse(
            isCorrect=is_correct,
            score=score,
            feedback=feedback,
            correctAnswer=correct_answer,
            explanation=(
                request.question.explanation
                or "(mock) 정답 해설은 기능템플릿의 requirements / apiSpec / flow 를 "
                "참고해 작성되어야 합니다. 본문에 없는 새 개념은 도입하지 않습니다."
            ),
            relatedSection=request.question.relatedSection,
        )

    def _grade_answer(
        self,
        *,
        correct_answer: str,
        user_answer: str,
        question_type: QuestionType,
        choices: list[str] | None,
    ) -> tuple[bool, int]:
        if not correct_answer:
            return False, 0
        if not user_answer:
            return False, 0

        norm_correct = normalize_answer_text(correct_answer)
        norm_user = normalize_answer_text(user_answer)

        if norm_correct == norm_user:
            return True, 100

        if question_type == QuestionType.MULTIPLE_CHOICE and choices:
            return self._grade_multiple_choice(
                correct_answer, user_answer, choices, norm_correct, norm_user
            )

        if question_type in (
            QuestionType.SHORT_ANSWER,
            QuestionType.FILL_BLANK,
            QuestionType.CODE_FILL,
        ):
            return self._grade_short_answer(norm_correct, norm_user, correct_answer, user_answer)

        if norm_correct in norm_user or norm_user in norm_correct:
            return True, 90

        overlap = self._keyword_overlap_ratio(correct_answer, user_answer)
        if overlap >= 0.8:
            return True, max(70, int(round(overlap * 100)))
        if overlap >= 0.5:
            return False, max(50, int(round(overlap * 100)))

        return False, 0

    @staticmethod
    def _grade_multiple_choice(
        correct_answer: str,
        user_answer: str,
        choices: list[str],
        norm_correct: str,
        norm_user: str,
    ) -> tuple[bool, int]:
        correct_idx = None
        user_idx = None
        for i, choice in enumerate(choices):
            nc = normalize_answer_text(choice)
            if nc == norm_correct or choice.strip() == correct_answer.strip():
                correct_idx = i
            if nc == norm_user or choice.strip() == user_answer.strip():
                user_idx = i

        if correct_idx is not None and user_idx is not None:
            return user_idx == correct_idx, 100 if user_idx == correct_idx else 0

        if norm_user == norm_correct:
            return True, 100
        return False, 0

    @staticmethod
    def _grade_short_answer(
        norm_correct: str,
        norm_user: str,
        correct_answer: str,
        user_answer: str,
    ) -> tuple[bool, int]:
        if norm_correct == norm_user:
            return True, 100

        correct_keywords = extract_answer_keywords(correct_answer)
        user_keywords = extract_answer_keywords(user_answer)
        if correct_keywords and user_keywords:
            overlap = len(correct_keywords & user_keywords) / len(correct_keywords)
            if overlap >= 0.6:
                return True, max(80, int(round(overlap * 100)))
            if overlap >= 0.5:
                return True, max(70, int(round(overlap * 100)))

        if re.sub(r"\s+", "", norm_correct) == re.sub(r"\s+", "", norm_user):
            return True, 95

        nums_correct = re.findall(r"\d+", correct_answer)
        nums_user = re.findall(r"\d+", user_answer)
        if nums_correct and nums_correct == nums_user:
            return True, 100

        return False, 0

    @staticmethod
    def _keyword_overlap_ratio(correct_answer: str, user_answer: str) -> float:
        correct_keywords = extract_answer_keywords(correct_answer)
        if not correct_keywords:
            return 0.0
        user_keywords = extract_answer_keywords(user_answer)
        return len(correct_keywords & user_keywords) / len(correct_keywords)

    def analyze_code(self, request: CodeAnalyzeRequest) -> CodeAnalyzeResponse:
        code = request.code or ""
        char_count = len(code)
        line_count = code.count("\n") + 1 if code else 0

        summary = (
            f"(mock) {request.language} 코드 약 {line_count}줄 / {char_count}자 "
            "분석 요약입니다."
        )
        explanation = (
            "(mock) 제출된 코드의 구조·의도·계층 책임을 요약 설명합니다. "
            "실제로는 LLM 분석 결과로 대체됩니다."
        )

        potential_issues: list[str] = []
        if code.strip():
            potential_issues.append(
                "(mock) 잠재적 이슈 예시 — 실제 분석 결과로 대체됩니다."
            )

        improvement_suggestions = [
            "(mock) 단일 책임 원칙 준수 여부 점검",
            "(mock) 입력값 검증 누락 여부 확인",
            "(mock) 예외 처리 및 응답 포맷 일관성 점검",
        ]

        return CodeAnalyzeResponse(
            summary=summary,
            explanation=explanation,
            potentialIssues=potential_issues,
            improvementSuggestions=improvement_suggestions,
        )

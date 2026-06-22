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

        feedback = self._build_quiz_feedback(
            is_correct=is_correct,
            score=score,
            correct_answer=correct_answer,
            user_answer=user_answer,
            related_section=request.question.relatedSection,
        )

        return QuizGradeResponse(
            isCorrect=is_correct,
            score=score,
            feedback=feedback,
            correctAnswer=correct_answer,
            explanation=(
                request.question.explanation
                or self._build_explanation_fallback(
                    correct_answer=correct_answer,
                    related_section=request.question.relatedSection,
                    question_text=(request.question.question or "").strip(),
                )
            ),
            relatedSection=request.question.relatedSection,
        )

    @staticmethod
    def _section_label(related_section: str | None) -> str:
        labels = {
            "overview": "개요(overview)",
            "requirements": "요구사항(requirements)",
            "flow": "흐름(flow)",
            "apiSpec": "API 명세(apiSpec)",
            "codeFiles": "코드(codeFiles)",
            "basicQuestions": "기본 문제(basicQuestions)",
            "missions": "미션(missions)",
            "interviewQuestions": "면접 질문(interviewQuestions)",
            "nextRecommendations": "다음 추천(nextRecommendations)",
        }
        if not related_section:
            return "기능템플릿"
        return labels.get(related_section, related_section)

    def _build_quiz_feedback(
        self,
        *,
        is_correct: bool,
        score: int,
        correct_answer: str,
        user_answer: str,
        related_section: str | None,
    ) -> str:
        section_label = self._section_label(related_section)

        if is_correct:
            if score >= 100:
                return (
                    f"정답입니다. '{correct_answer}' 핵심 개념을 정확히 짚었습니다. "
                    f"{section_label} 내용을 잘 이해하고 있습니다."
                )
            return (
                f"정답으로 인정됩니다. 핵심 표현은 맞지만, "
                f"정답 '{correct_answer}'처럼 더 명확히 정리하면 좋습니다."
            )

        if score >= 50:
            missing = self._missing_answer_keywords(correct_answer, user_answer)
            if missing:
                missing_text = ", ".join(sorted(missing)[:4])
                return (
                    f"핵심 키워드 일부는 맞지만 정답 표현이 부족합니다. "
                    f"부족한 키워드: {missing_text}. "
                    f"{section_label} 섹션과 정답 '{correct_answer}'를 다시 비교해 보세요."
                )
            return (
                f"핵심 방향은 맞지만 정답 '{correct_answer}'와 표현이 다릅니다. "
                f"{section_label} 섹션에서 용어를 다시 확인해 보세요."
            )

        if not user_answer.strip():
            return (
                f"답이 비어 있습니다. {section_label} 섹션을 참고해 "
                f"'{correct_answer}'와 연결되는 개념을 작성해 보세요."
            )

        return (
            f"오답입니다. '{user_answer}'는 정답 '{correct_answer}'와 핵심이 다릅니다. "
            f"{section_label} 섹션에서 관련 개념을 다시 정리한 뒤 재시도하세요."
        )

    @staticmethod
    def _missing_answer_keywords(correct_answer: str, user_answer: str) -> set[str]:
        correct_keywords = extract_answer_keywords(correct_answer)
        user_keywords = extract_answer_keywords(user_answer)
        return correct_keywords - user_keywords

    @staticmethod
    def _build_explanation_fallback(
        *,
        correct_answer: str,
        related_section: str | None,
        question_text: str,
    ) -> str:
        section_label = EvaluationService._section_label(related_section)
        question_hint = f"문제 '{question_text}'의 " if question_text else ""
        return (
            f"{question_hint}정답은 '{correct_answer}'입니다. "
            f"{section_label} 섹션에서 해당 개념이 왜 필요한지, "
            f"어떤 입력·처리·결과 흐름과 연결되는지 다시 읽어 보세요. "
            f"기능템플릿에 없는 새 개념은 추가하지 말고, 템플릿 근거로 이해를 정리하세요."
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

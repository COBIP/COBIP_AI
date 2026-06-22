"""POST /ai/code/analyze 전용 분석 service.

제출 전 단계의 코드리뷰 + 오답피드백을 생성한다.
- 기본 경로: 기존 LLMService.generate_json() 으로 JSON 응답을 받아 정규화한다.
- LLM 미설정/타임아웃/파싱 실패 시: 코드·언어·context·requirements 기반의 최소 분석을
  fallback 으로 반환한다.
- 어떤 경로에서도 "(mock)" 문구는 출력하지 않는다.

채점기가 아니므로 passed/score 는 다루지 않는다. (제출 후 채점은 /ai/mission/feedback)
"""

from __future__ import annotations

import logging

from app.core.config import settings
from app.prompts.code_analyze_prompts import build_code_analyze_prompt
from app.schemas.evaluation import (
    CodeAnalyzeRequest,
    CodeAnalyzeResponse,
    SubmittedCodeSchema,
)
from app.services.llm_service import LLMService

__all__ = ["CodeAnalyzeService"]

logger = logging.getLogger(__name__)

# fallback 요구사항 대조 시 무시할 너무 짧은/일반적인 토큰.
_FALLBACK_STOPWORDS: frozenset[str] = frozenset(
    {
        "한다",
        "하는",
        "구현",
        "처리",
        "기능",
        "코드",
        "경우",
        "있는",
        "통해",
        "관련",
        "모든",
        "각각",
        "또는",
        "그리고",
    }
)

_MAX_REQUIREMENT_LIST = 12


class CodeAnalyzeService:
    """코드리뷰 + 오답피드백 service (LLM 우선, 실패 시 rule fallback)."""

    def __init__(self, llm_service: LLMService | None = None) -> None:
        self._llm_service = llm_service or LLMService()

    def analyze(self, request: CodeAnalyzeRequest) -> CodeAnalyzeResponse:
        code = self._resolve_code(request)
        requirements = self._clean_list(request.requirements)
        success_criteria = self._clean_list(request.successCriteria)

        if not code.strip():
            return self._empty_code_response(requirements)

        prompt = build_code_analyze_prompt(
            code=code,
            language=request.language,
            context=request.context,
            mission_title=request.missionTitle,
            mission_description=request.missionDescription,
            requirements=requirements,
            success_criteria=success_criteria,
        )

        try:
            raw = self._llm_service.generate_json(
                prompt,
                timeout_seconds=settings.LLM_TIMEOUT_SECONDS,
            )
        except RuntimeError as exc:
            logger.warning(
                "code analyze LLM call failed; using fallback: errorType=%s",
                type(exc).__name__,
            )
            return self._fallback_response(
                code=code,
                language=request.language,
                context=request.context,
                requirements=requirements,
                success_criteria=success_criteria,
            )

        if not self._looks_like_llm_payload(raw):
            logger.info("code analyze LLM payload not usable; using fallback")
            return self._fallback_response(
                code=code,
                language=request.language,
                context=request.context,
                requirements=requirements,
                success_criteria=success_criteria,
            )

        return self._normalize_llm_response(
            raw,
            code=code,
            language=request.language,
            context=request.context,
            requirements=requirements,
            success_criteria=success_criteria,
        )

    # ------------------------------------------------------------------
    # input handling
    # ------------------------------------------------------------------
    @staticmethod
    def _resolve_code(request: CodeAnalyzeRequest) -> str:
        """code 가 비어 있고 submittedCode 가 있으면 파일 내용을 합쳐 사용한다."""
        if request.code and request.code.strip():
            return request.code
        files: list[SubmittedCodeSchema] = request.submittedCode or []
        merged = "\n\n".join(
            f"// {f.fileName}\n{f.content}" for f in files if f.content and f.content.strip()
        )
        return merged

    @staticmethod
    def _clean_list(values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for value in values or []:
            text = str(value).strip()
            if text:
                cleaned.append(text)
        return cleaned

    # ------------------------------------------------------------------
    # LLM payload normalization
    # ------------------------------------------------------------------
    @staticmethod
    def _looks_like_llm_payload(raw: object) -> bool:
        """generate_json 의 mock dict 나 빈 응답을 fallback 으로 돌리기 위한 판별."""
        if not isinstance(raw, dict):
            return False
        if raw.get("mock") is True:
            return False
        has_summary = bool(str(raw.get("summary", "")).strip())
        has_explanation = bool(str(raw.get("explanation", "")).strip())
        return has_summary or has_explanation

    def _normalize_llm_response(
        self,
        raw: dict,
        *,
        code: str,
        language: str,
        context: str | None,
        requirements: list[str],
        success_criteria: list[str],
    ) -> CodeAnalyzeResponse:
        summary = self._sanitize_text(raw.get("summary"))
        explanation = self._sanitize_text(raw.get("explanation"))

        if not summary:
            summary = self._default_summary(code, language)
        if not explanation:
            explanation = "제출한 코드를 기준으로 구조와 흐름을 검토했습니다."

        return CodeAnalyzeResponse(
            summary=summary,
            explanation=explanation,
            potentialIssues=self._sanitize_list(raw.get("potentialIssues")),
            improvementSuggestions=self._sanitize_list(raw.get("improvementSuggestions")),
            satisfiedRequirements=self._sanitize_list(raw.get("satisfiedRequirements")),
            missingRequirements=self._sanitize_list(raw.get("missingRequirements")),
            incorrectParts=self._sanitize_list(raw.get("incorrectParts")),
            wrongAnswerFeedback=self._sanitize_list(raw.get("wrongAnswerFeedback")),
        )

    @staticmethod
    def _sanitize_text(value: object) -> str:
        if not isinstance(value, str):
            return ""
        # 안전장치: 혹시 모를 "(mock)" 잔여 문구 제거.
        return value.replace("(mock)", "").strip()

    @classmethod
    def _sanitize_list(cls, value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        items: list[str] = []
        for entry in value:
            text = cls._sanitize_text(entry) if isinstance(entry, str) else ""
            if text:
                items.append(text)
        return items

    # ------------------------------------------------------------------
    # fallback (LLM 미설정/실패 시)
    # ------------------------------------------------------------------
    def _empty_code_response(self, requirements: list[str]) -> CodeAnalyzeResponse:
        return CodeAnalyzeResponse(
            summary="분석할 코드가 없습니다.",
            explanation="제출된 코드가 비어 있어 코드리뷰를 진행할 수 없습니다. 먼저 코드를 작성한 뒤 다시 분석을 요청하세요.",
            potentialIssues=[],
            improvementSuggestions=["핵심 로직을 담은 최소 코드부터 작성한 뒤 분석을 다시 실행하세요."],
            satisfiedRequirements=[],
            missingRequirements=list(requirements[:_MAX_REQUIREMENT_LIST]),
            incorrectParts=[],
            wrongAnswerFeedback=(
                ["아직 코드가 없어 요구사항 충족 여부를 판단할 수 없습니다."] if requirements else []
            ),
        )

    def _fallback_response(
        self,
        *,
        code: str,
        language: str,
        context: str | None,
        requirements: list[str],
        success_criteria: list[str],
    ) -> CodeAnalyzeResponse:
        code_lower = code.lower()
        line_count = code.count("\n") + 1

        summary = self._default_summary(code, language)
        if context and context.strip():
            summary += f" 분석 문맥: {context.strip()}."

        explanation = (
            f"AI 상세 분석을 사용할 수 없어, 코드 구조 기준의 기본 검토만 제공합니다. "
            f"현재 코드는 약 {line_count}줄이며, 책임 분리와 흐름이 명확한지 직접 점검하는 것이 좋습니다."
        )

        potential_issues = self._fallback_potential_issues(code, code_lower)
        improvement_suggestions = self._fallback_suggestions(code_lower)

        satisfied, missing = self._fallback_requirement_match(code_lower, requirements)
        wrong_answer_feedback = self._fallback_wrong_answer_feedback(
            missing, success_criteria, code_lower
        )
        incorrect_parts = self._fallback_incorrect_parts(code, code_lower)

        return CodeAnalyzeResponse(
            summary=summary,
            explanation=explanation,
            potentialIssues=potential_issues,
            improvementSuggestions=improvement_suggestions,
            satisfiedRequirements=satisfied,
            missingRequirements=missing,
            incorrectParts=incorrect_parts,
            wrongAnswerFeedback=wrong_answer_feedback,
        )

    @staticmethod
    def _default_summary(code: str, language: str) -> str:
        char_count = len(code)
        line_count = code.count("\n") + 1 if code else 0
        return f"{language} 코드 약 {line_count}줄 / {char_count}자를 검토했습니다."

    @staticmethod
    def _fallback_potential_issues(code: str, code_lower: str) -> list[str]:
        issues: list[str] = []
        has_exception = any(token in code_lower for token in ("try", "catch", "except", "throw"))
        if not has_exception:
            issues.append("예외 처리 코드가 보이지 않습니다. 실패 상황에 대한 처리를 점검하세요.")

        has_validation = any(
            token in code_lower
            for token in ("valid", "검증", "null", "isempty", "isblank", "if ", "if(")
        )
        if not has_validation:
            issues.append("입력 검증 로직이 보이지 않습니다. 잘못된 입력에 대한 방어를 점검하세요.")

        if "{ }" in code or "{}" in code or "() { }" in code:
            issues.append("메서드 본문이 비어 있어 실제 동작이 구현되지 않은 부분이 있습니다.")

        return issues

    @staticmethod
    def _fallback_suggestions(code_lower: str) -> list[str]:
        suggestions: list[str] = []
        if "return" not in code_lower:
            suggestions.append("처리 결과를 반환하는 흐름이 있는지 확인하세요.")
        suggestions.append("계층(Controller/Service/Repository 등)별 책임이 섞이지 않았는지 점검하세요.")
        return suggestions

    @classmethod
    def _fallback_requirement_match(
        cls, code_lower: str, requirements: list[str]
    ) -> tuple[list[str], list[str]]:
        satisfied: list[str] = []
        missing: list[str] = []
        for requirement in requirements[:_MAX_REQUIREMENT_LIST]:
            tokens = cls._requirement_tokens(requirement)
            hit = any(token in code_lower for token in tokens)
            if hit:
                satisfied.append(requirement)
            else:
                missing.append(requirement)
        return satisfied, missing

    @staticmethod
    def _requirement_tokens(requirement: str) -> list[str]:
        tokens: list[str] = []
        for raw in requirement.replace("/", " ").replace(",", " ").split():
            token = raw.strip().lower()
            if len(token) < 2:
                continue
            if token in _FALLBACK_STOPWORDS:
                continue
            tokens.append(token)
        return tokens

    @staticmethod
    def _fallback_wrong_answer_feedback(
        missing: list[str],
        success_criteria: list[str],
        code_lower: str,
    ) -> list[str]:
        feedback: list[str] = []
        for requirement in missing:
            feedback.append(
                f"'{requirement}' 관련 구현 근거를 현재 코드에서 찾지 못했습니다. 해당 로직이 있는지 확인하세요."
            )
        for criterion in success_criteria[:_MAX_REQUIREMENT_LIST]:
            tokens = [
                token
                for token in criterion.lower().split()
                if len(token) >= 2 and token not in _FALLBACK_STOPWORDS
            ]
            if tokens and not any(token in code_lower for token in tokens):
                feedback.append(
                    f"완료 기준 '{criterion}' 을(를) 만족하는 흐름이 코드에서 확인되지 않습니다."
                )
        return feedback

    @staticmethod
    def _fallback_incorrect_parts(code: str, code_lower: str) -> list[str]:
        parts: list[str] = []
        if "{ }" in code or "{}" in code or "() { }" in code:
            parts.append("메서드 본문이 비어 있어 요구한 동작이 수행되지 않습니다.")
        if "password" in code_lower and not any(
            token in code_lower for token in ("encode", "hash", "encrypt", "bcrypt")
        ):
            parts.append("비밀번호를 다루지만 암호화·해시 처리가 보이지 않습니다.")
        return parts

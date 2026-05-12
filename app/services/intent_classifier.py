"""Intent 분류: 룰 기본, 선택적 LLM 보조 (Hybrid)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum

from app.core.config import settings
from app.services.llm_service import LLMService

__all__ = [
    "AgentIntent",
    "HybridIntentClassifier",
    "IntentClassificationResult",
    "LLMIntentClassifier",
    "RuleBasedIntentClassifier",
]

logger = logging.getLogger(__name__)

_AGENT_MODE_RULE = "rule_based"
_AGENT_MODE_LLM = "llm_assisted"
_AGENT_MODE_HYBRID = "hybrid"


class AgentIntent(str, Enum):
    """에이전트 intent (API·handler와 동일 문자열)."""

    GENERAL_CHAT = "GENERAL_CHAT"
    RAG_SEARCH = "RAG_SEARCH"
    FEATURE_TEMPLATE_HELP = "FEATURE_TEMPLATE_HELP"
    UNKNOWN = "UNKNOWN"


_RAG_HINTS = (
    "문서",
    "검색",
    "찾아",
    "근거",
    "자료",
    "참고",
    "RAG",
    "rag",
)
_FEATURE_HINTS = (
    "기능템플릿",
    "기능 템플릿",
    "템플릿",
    "요구사항",
    "API 명세",
    "api 명세",
    "ERD",
    "erd",
    "면접 질문",
)
_GENERAL_HINTS = (
    "안녕",
    "고마워",
    "뭐해",
    "설명해줘",
    "도와줘",
)

_VALID_INTENTS = frozenset(
    {
        AgentIntent.GENERAL_CHAT.value,
        AgentIntent.RAG_SEARCH.value,
        AgentIntent.FEATURE_TEMPLATE_HELP.value,
        AgentIntent.UNKNOWN.value,
    }
)

_HYBRID_CLASSIFIER_NAME = "HybridIntentClassifier"


@dataclass(frozen=True)
class IntentClassificationResult:
    """HybridIntentClassifier.classify 결과 (intent·mode·trace용 메타)."""

    intent: str
    mode: str
    classifier_name: str
    llm_intent_used: bool
    steps: tuple[str, ...]


class RuleBasedIntentClassifier:
    """기존 AgentOrchestrator.classify_intent 와 동일한 룰 기반 분류."""

    def classify(self, message: str) -> str:
        text = (message or "").strip()
        # 1) 빈 문자열 → UNKNOWN
        if not text:
            return AgentIntent.UNKNOWN.value

        lower = text.lower()
        lower_fold = lower.replace(" ", "")

        # 2) 기능템플릿 관련 → FEATURE_TEMPLATE_HELP (RAG 키워드보다 우선)
        for hint in _FEATURE_HINTS:
            h = hint.lower().replace(" ", "")
            if h in lower_fold or hint in text or hint.lower() in lower:
                return AgentIntent.FEATURE_TEMPLATE_HELP.value

        # 3) RAG 관련 → RAG_SEARCH
        for hint in _RAG_HINTS:
            if hint in ("RAG", "rag"):
                if "rag" in lower:
                    return AgentIntent.RAG_SEARCH.value
                continue
            if hint in text:
                return AgentIntent.RAG_SEARCH.value

        # 4) 일반 대화 힌트 → GENERAL_CHAT
        for hint in _GENERAL_HINTS:
            if hint in text:
                return AgentIntent.GENERAL_CHAT.value

        # 5) 기본값 → GENERAL_CHAT
        return AgentIntent.GENERAL_CHAT.value


@dataclass(frozen=True)
class _LLMIntentOutcome:
    intent: str
    ok: bool


class LLMIntentClassifier:
    """LLM으로 intent 추출. 실패·비정상 값은 ok=False (호출부에서 룰 등으로 fallback)."""

    _SYSTEM_PROMPT = """You classify a single user message into exactly one intent label.
Reply with exactly one line containing only one of these four tokens (no punctuation, no explanation):
GENERAL_CHAT
RAG_SEARCH
FEATURE_TEMPLATE_HELP
UNKNOWN

Rules:
- GENERAL_CHAT: normal chat, coding help, greetings without other intent.
- RAG_SEARCH: user wants document search, evidence, uploaded materials, "find in docs", RAG.
- FEATURE_TEMPLATE_HELP: feature template, requirements doc, API spec, ERD, interview questions generation help.
- UNKNOWN: cannot tell."""

    def classify(self, message: str) -> _LLMIntentOutcome:
        msg_len = len(message or "")
        try:
            llm = LLMService()
            user_prompt = f"Message:\n{message}\n"
            raw = llm.generate_text(
                user_prompt,
                system_prompt=self._SYSTEM_PROMPT,
            )
            intent = self._parse_llm_intent(raw)
            if intent is None:
                logger.info(
                    "llm_intent_classifier parse_failed query_len=%s",
                    msg_len,
                )
                return _LLMIntentOutcome(AgentIntent.UNKNOWN.value, False)
            logger.info(
                "llm_intent_classifier ok intent=%s query_len=%s",
                intent,
                msg_len,
            )
            return _LLMIntentOutcome(intent, True)
        except Exception as exc:
            logger.warning(
                "llm_intent_classifier error errorType=%s query_len=%s",
                type(exc).__name__,
                msg_len,
            )
            return _LLMIntentOutcome(AgentIntent.UNKNOWN.value, False)

    @staticmethod
    def _parse_llm_intent(raw: str) -> str | None:
        if not raw or not raw.strip():
            return None
        text = raw.strip()
        # Prefer whole-line match
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            line = re.sub(r"^[`'\"]+|[`'\"]+$", "", line)
            if ":" in line and not line.startswith("{"):
                # e.g. "Intent: RAG_SEARCH"
                parts = line.split(":", 1)
                if len(parts) == 2:
                    candidate = parts[1].strip()
                else:
                    candidate = line
            else:
                candidate = line.split()[0] if line.split() else line
            candidate = candidate.strip().strip("`'\"")
            upper = candidate.upper()
            for valid in _VALID_INTENTS:
                if valid.upper() == upper:
                    return valid
        # Fallback: first occurrence of any valid token as word
        for valid in sorted(_VALID_INTENTS, key=len, reverse=True):
            if re.search(rf"\b{re.escape(valid)}\b", text, flags=re.IGNORECASE):
                return valid
        return None


class HybridIntentClassifier:
    """룰 우선. UNKNOWN이면(옵션) LLM 보조. GENERAL_CHAT은 옵션으로 LLM 재분류."""

    def __init__(
        self,
        *,
        rule: RuleBasedIntentClassifier | None = None,
        llm: LLMIntentClassifier | None = None,
    ) -> None:
        self._rule = rule or RuleBasedIntentClassifier()
        self._llm = llm or LLMIntentClassifier()

    def classify(self, message: str) -> IntentClassificationResult:
        steps: list[str] = ["rule_based_intent_classification"]
        rule_intent = self._rule.classify(message)
        llm_used = False

        if rule_intent == AgentIntent.UNKNOWN.value and settings.AGENT_LLM_INTENT_ENABLED:
            steps.append("llm_intent_classification")
            llm_used = True
            out = self._llm.classify(message)
            if out.ok and out.intent in _VALID_INTENTS:
                return IntentClassificationResult(
                    intent=out.intent,
                    mode=_AGENT_MODE_LLM,
                    classifier_name=_HYBRID_CLASSIFIER_NAME,
                    llm_intent_used=llm_used,
                    steps=tuple(steps),
                )
            return IntentClassificationResult(
                intent=AgentIntent.UNKNOWN.value,
                mode=_AGENT_MODE_RULE,
                classifier_name=_HYBRID_CLASSIFIER_NAME,
                llm_intent_used=llm_used,
                steps=tuple(steps),
            )

        if (
            rule_intent == AgentIntent.GENERAL_CHAT.value
            and settings.AGENT_LLM_INTENT_ENABLED
            and settings.AGENT_LLM_INTENT_REFINE_GENERAL
        ):
            steps.append("llm_intent_refinement")
            llm_used = True
            out = self._llm.classify(message)
            if (
                out.ok
                and out.intent in _VALID_INTENTS
                and out.intent != AgentIntent.UNKNOWN.value
            ):
                return IntentClassificationResult(
                    intent=out.intent,
                    mode=_AGENT_MODE_HYBRID,
                    classifier_name=_HYBRID_CLASSIFIER_NAME,
                    llm_intent_used=llm_used,
                    steps=tuple(steps),
                )
            return IntentClassificationResult(
                intent=rule_intent,
                mode=_AGENT_MODE_RULE,
                classifier_name=_HYBRID_CLASSIFIER_NAME,
                llm_intent_used=llm_used,
                steps=tuple(steps),
            )

        return IntentClassificationResult(
            intent=rule_intent,
            mode=_AGENT_MODE_RULE,
            classifier_name=_HYBRID_CLASSIFIER_NAME,
            llm_intent_used=False,
            steps=tuple(steps),
        )

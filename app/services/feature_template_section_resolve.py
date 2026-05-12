"""기능템플릿 섹션 재생성용 section 이름 → canonical camelCase key."""

from __future__ import annotations

__all__ = [
    "CANONICAL_FEATURE_TEMPLATE_SECTIONS",
    "resolve_canonical_feature_template_section",
]


CANONICAL_FEATURE_TEMPLATE_SECTIONS: frozenset[str] = frozenset(
    {
        "overview",
        "requirements",
        "flow",
        "apiSpec",
        "codeFiles",
        "basicQuestions",
        "missions",
        "interviewQuestions",
        "nextRecommendations",
    }
)


def resolve_canonical_feature_template_section(raw: str) -> str:
    """허용 별칭·snake_case·enum 값을 FeatureTemplateData 필드명(camelCase)으로 통일한다."""
    s = (raw or "").strip()
    if not s:
        raise ValueError("section must be a non-empty string")

    if s in CANONICAL_FEATURE_TEMPLATE_SECTIONS:
        return s

    key = s.lower().replace("-", "_")
    table: dict[str, str] = {
        "overview": "overview",
        "requirements": "requirements",
        "flow": "flow",
        "api_spec": "apiSpec",
        "apispec": "apiSpec",
        "code_view": "codeFiles",
        "code_files": "codeFiles",
        "codefiles": "codeFiles",
        "basic_questions": "basicQuestions",
        "basicquestions": "basicQuestions",
        "missions": "missions",
        "interview": "interviewQuestions",
        "interview_questions": "interviewQuestions",
        "interviewquestions": "interviewQuestions",
        "next_recommendations": "nextRecommendations",
        "nextrecommendations": "nextRecommendations",
    }
    out = table.get(key)
    if out is not None:
        return out

    raise ValueError(
        f"unsupported section: {raw!r}; "
        f"allowed: {', '.join(sorted(CANONICAL_FEATURE_TEMPLATE_SECTIONS))}"
    )


def alternate_keys_for_section(canonical: str) -> tuple[str, ...]:
    """LLM 응답에서 섹션 값을 찾을 때 시도할 보조 key."""
    extras: dict[str, tuple[str, ...]] = {
        "apiSpec": ("api_spec",),
        "codeFiles": ("code_view", "code_files"),
        "basicQuestions": ("basic_questions",),
        "interviewQuestions": ("interview", "interview_questions"),
        "nextRecommendations": ("next_recommendations",),
    }
    return extras.get(canonical, ())

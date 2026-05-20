"""LLM 호출용 프롬프트 조립기.

이 단계에서는 기능템플릿 생성 요청에 대한 최종 프롬프트 문자열만 만든다.
실제 LLM 호출은 별도 service에서 수행한다.
"""

from __future__ import annotations

import json
from typing import Any

from app.prompts.feature_template_prompts import (
    FEATURE_TEMPLATE_RAG_CONTEXT_INSTRUCTIONS,
    FEATURE_TEMPLATE_SECTION_SYSTEM_PROMPT,
    FEATURE_TEMPLATE_SECTION_USER_PROMPT_TEMPLATE,
    FEATURE_TEMPLATE_SYSTEM_PROMPT,
    FEATURE_TEMPLATE_USER_PROMPT_TEMPLATE,
)
from app.schemas.feature_template import FeatureTemplateGenerateRequest

__all__ = [
    "build_feature_template_prompt",
    "build_feature_template_section_prompt",
    "format_rag_references_for_feature_template_prompt",
]

_RAG_CONTEXT_HEADER = "[검색 근거 / RAG Context]"
_MAX_RAG_REFERENCES = 5
_MAX_RAG_CONTENT_CHARS = 1000


def format_rag_references_for_feature_template_prompt(
    references: list[Any],
    *,
    max_items: int = _MAX_RAG_REFERENCES,
    max_content_chars: int = _MAX_RAG_CONTENT_CHARS,
) -> str:
    """RAG 검색 결과를 기능템플릿 user 프롬프트용 블록으로 포맷한다.

    - 유효한 content가 있는 항목만 포함한다.
    - 최대 max_items개 (기본 5, 운영에서는 3~5 범위 권장).
    - content는 max_content_chars자로 자른다 (기본 1000).
    - title / 출처(sourceType 또는 source) / score / 내용을 선택적으로 포함한다.
    - references가 비어 있거나 유효 항목이 없으면 빈 문자열을 반환한다.
    """

    if not references or max_items < 1:
        return ""

    blocks: list[str] = []
    for raw in references:
        if len(blocks) >= max_items:
            break
        if not isinstance(raw, dict):
            continue
        content = raw.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        body = content.strip()
        if len(body) > max_content_chars:
            body = body[: max_content_chars - 1] + "…"

        title = raw.get("title")
        title_s = title.strip() if isinstance(title, str) and title.strip() else None

        source_val = raw.get("sourceType")
        if not (isinstance(source_val, str) and source_val.strip()):
            alt = raw.get("source")
            source_val = alt if isinstance(alt, str) and alt.strip() else None
        else:
            source_val = source_val.strip()

        score = raw.get("score")
        score_line: str | None = None
        if isinstance(score, (int, float)):
            score_line = str(score)

        lines: list[str] = [f"{len(blocks) + 1}."]
        if title_s:
            lines.append(f"   제목: {title_s}")
        if source_val:
            lines.append(f"   출처: {source_val}")
        if score_line is not None:
            lines.append(f"   점수: {score_line}")
        lines.append(f"   내용: {body}")
        blocks.append("\n".join(lines))

    if not blocks:
        return ""

    header = _RAG_CONTEXT_HEADER
    intro = FEATURE_TEMPLATE_RAG_CONTEXT_INSTRUCTIONS
    return f"{header}\n\n{intro}\n\n" + "\n\n".join(blocks)


def _extract_rag_references_from_reference_context(
    reference_context: dict[str, Any] | None,
) -> list[Any]:
    if not isinstance(reference_context, dict):
        return []
    raw = reference_context.get("ragReferences")
    if raw is None:
        raw = reference_context.get("rag_references")
    if not isinstance(raw, list):
        return []
    return list(raw)


def _reference_context_for_prompt_json(
    reference_context: dict[str, Any] | None,
    *,
    omit_rag_references: bool,
) -> dict[str, Any] | None:
    """프롬프트 JSON 블록용 referenceContext. RAG 포맷 블록을 쓸 때는 ragReferences 중복을 줄인다."""

    if not isinstance(reference_context, dict):
        return reference_context
    if not omit_rag_references:
        return dict(reference_context)
    out = {k: v for k, v in reference_context.items() if k not in ("ragReferences", "rag_references")}
    return out


def build_feature_template_prompt(request: FeatureTemplateGenerateRequest) -> str:
    """기능템플릿 생성용 최종 프롬프트 문자열을 조립한다.

    조립 결과는 다음을 보장한다:
    - language / framework / featureName / level 포함
    - includeCode / includeMissions / includeInterview 옵션 반영
    - overview.techStack 에 language·framework 반영 지시 (프롬프트 본문)
    - 기능템플릿 9개 섹션 순서 명시 (overview → requirements → flow
      → apiSpec → codeFiles → basicQuestions → missions
      → interviewQuestions → nextRecommendations)
    - apiSpec은 flow 다음, codeFiles 이전에 위치
    """

    framework_text = request.framework if request.framework else "(미지정)"

    rag_refs = _extract_rag_references_from_reference_context(request.referenceContext)
    rag_body = format_rag_references_for_feature_template_prompt(
        rag_refs,
        max_items=_MAX_RAG_REFERENCES,
        max_content_chars=_MAX_RAG_CONTENT_CHARS,
    )
    rag_context_section = f"\n\n{rag_body}" if rag_body else ""

    omit_rag_in_json = bool(rag_body)
    ctx_for_json = _reference_context_for_prompt_json(
        request.referenceContext,
        omit_rag_references=omit_rag_in_json,
    )

    if ctx_for_json:
        reference_context_text = json.dumps(
            ctx_for_json,
            ensure_ascii=False,
            indent=2,
        )
    else:
        reference_context_text = "(없음)"

    user_prompt = FEATURE_TEMPLATE_USER_PROMPT_TEMPLATE.format(
        language=request.language,
        framework=framework_text,
        featureName=request.featureName,
        level=request.level.value,
        includeCode=str(request.includeCode).lower(),
        includeMissions=str(request.includeMissions).lower(),
        includeInterview=str(request.includeInterview).lower(),
        ragContextSection=rag_context_section,
        referenceContext=reference_context_text,
    )

    return f"{FEATURE_TEMPLATE_SYSTEM_PROMPT}\n\n{user_prompt}"


def build_feature_template_section_prompt(
    section_key: str,
    request: FeatureTemplateGenerateRequest,
    *,
    previous_content: dict | None = None,
    current_template: dict | None = None,
    user_instruction: str | None = None,
    extra_tech_stack: list[str] | None = None,
) -> str:
    """단일 섹션 재생성용 프롬프트 (루트 JSON 에 section key 하나만 포함하도록 지시)."""

    framework_text = request.framework if request.framework else "(미지정)"
    tech_stack_text = (
        json.dumps(extra_tech_stack, ensure_ascii=False)
        if extra_tech_stack
        else "(없음)"
    )
    previous_text = (
        json.dumps(previous_content, ensure_ascii=False, indent=2)
        if previous_content
        else "(없음)"
    )
    current_text = (
        json.dumps(current_template, ensure_ascii=False, indent=2)
        if current_template
        else "(없음)"
    )
    instruction_text = (
        user_instruction.strip()
        if user_instruction and user_instruction.strip()
        else "(없음)"
    )

    user_prompt = FEATURE_TEMPLATE_SECTION_USER_PROMPT_TEMPLATE.format(
        sectionKey=section_key,
        language=request.language,
        framework=framework_text,
        featureName=request.featureName,
        level=request.level.value,
        includeCode=str(request.includeCode).lower(),
        includeMissions=str(request.includeMissions).lower(),
        includeInterview=str(request.includeInterview).lower(),
        techStackText=tech_stack_text,
        previousContentText=previous_text,
        currentTemplateText=current_text,
        userInstructionText=instruction_text,
    )

    return f"{FEATURE_TEMPLATE_SECTION_SYSTEM_PROMPT}\n\n{user_prompt}"

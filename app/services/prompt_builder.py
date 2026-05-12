"""LLM 호출용 프롬프트 조립기.

이 단계에서는 기능템플릿 생성 요청에 대한 최종 프롬프트 문자열만 만든다.
실제 LLM 호출은 별도 service에서 수행한다.
"""

import json

from app.prompts.feature_template_prompts import (
    FEATURE_TEMPLATE_SECTION_SYSTEM_PROMPT,
    FEATURE_TEMPLATE_SECTION_USER_PROMPT_TEMPLATE,
    FEATURE_TEMPLATE_SYSTEM_PROMPT,
    FEATURE_TEMPLATE_USER_PROMPT_TEMPLATE,
)
from app.schemas.feature_template import FeatureTemplateGenerateRequest

__all__ = ["build_feature_template_prompt", "build_feature_template_section_prompt"]


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

    if request.referenceContext:
        reference_context_text = json.dumps(
            request.referenceContext,
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

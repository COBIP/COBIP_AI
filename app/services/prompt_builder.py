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
    "build_applied_references_payload",
    "build_feature_template_prompt",
    "build_feature_template_prompt_with_applied_rags",
    "build_feature_template_section_prompt",
    "extract_raw_rag_references_from_reference_context",
    "format_rag_references_for_feature_template_prompt",
    "select_usable_rag_references",
]

_RAG_CONTEXT_HEADER = "[검색 근거 / RAG Context]"
_MAX_RAG_REFERENCES = 5
_MAX_RAG_CONTENT_CHARS = 1000
_CONTENT_PREVIEW_MAX_CHARS = 200  # 150~250자 권장 범위 내 기본값


def select_usable_rag_references(
    references: list[Any] | None,
    *,
    max_items: int = _MAX_RAG_REFERENCES,
) -> list[dict[str, Any]]:
    """프롬프트 주입·appliedReferences 공통: 유효한 content가 있는 항목만 최대 max_items개."""

    if not references or max_items < 1:
        return []
    out: list[dict[str, Any]] = []
    for raw in references:
        if len(out) >= max_items:
            break
        if not isinstance(raw, dict):
            continue
        content = raw.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        out.append(dict(raw))
    return out


def _format_rag_block_from_selected(
    selected: list[dict[str, Any]],
    *,
    max_content_chars: int = _MAX_RAG_CONTENT_CHARS,
) -> str:
    """select_usable_rag_references 결과만 받아 RAG Context 블록 문자열을 만든다."""

    if not selected:
        return ""

    blocks: list[str] = []
    for raw in selected:
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


def build_applied_references_payload(
    selected: list[dict[str, Any]],
    *,
    preview_max_chars: int = _CONTENT_PREVIEW_MAX_CHARS,
) -> list[dict[str, Any]]:
    """프롬프트에 실제 포함된 RAG reference와 동일 순서·동일 건으로 응답용 요약을 만든다."""

    out: list[dict[str, Any]] = []
    for raw in selected:
        content = raw.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        body = content.strip()
        limit = min(max(int(preview_max_chars), 1), 250)
        preview = body[:limit]
        if len(body) > limit:
            preview = body[: limit - 1] + "…"

        item: dict[str, Any] = {"usedInPrompt": True, "contentPreview": preview}

        title = raw.get("title")
        if isinstance(title, str) and title.strip():
            item["title"] = title.strip()

        src = raw.get("source")
        if isinstance(src, str) and src.strip():
            item["source"] = src.strip()

        st = raw.get("sourceType")
        if isinstance(st, str) and st.strip():
            item["sourceType"] = st.strip()

        sc = raw.get("score")
        if isinstance(sc, (int, float)):
            item["score"] = sc

        out.append(item)
    return out


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

    selected = select_usable_rag_references(references, max_items=max_items)
    return _format_rag_block_from_selected(selected, max_content_chars=max_content_chars)


def extract_raw_rag_references_from_reference_context(
    reference_context: dict[str, Any] | None,
) -> list[Any]:
    """referenceContext에서 ragReferences / rag_references 원본 리스트를 반환한다."""

    return _extract_rag_references_from_reference_context(reference_context)


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


def _build_initial_generation_section_instructions(
    request: FeatureTemplateGenerateRequest,
) -> str:
    """include flags에 따라 최초 generate용 섹션 지시만 짧게 조립한다."""

    lines = [
        "- 최초 generate는 skeleton-first 전략이다. 전체 구조만 빠르게 보여주고 상세 보강은 regenerate-section에서 수행한다.",
        "- overview: featureName, purpose, useCases, resultDescription, techStack, learningGoals를 짧게 채운다.",
        "- requirements: 정확히 3개. 입력, 검증, 성공/실패/보안 관점으로 나눈다.",
        "- flow: steps 정확히 5개, layers는 핵심 계층만 간결히 작성한다.",
        "- apiSpec: 핵심 API 1개만 작성한다. requestBody/responseBody는 필드 예시가 있는 JSON 객체다.",
        "- basicQuestions: 정확히 3개. type은 가능한 한 섞고 choices는 multiple_choice가 아니면 null이다.",
        "- nextRecommendations: 정확히 3개만 추천한다.",
    ]

    if request.includeCode:
        lines.append(
            "- codeFiles: includeCode=true여도 최초 generate에서는 상세 코드를 만들지 않는다. "
            "가능하면 []를 반환하고, 꼭 필요하면 최대 4개 짧은 stub만 작성한다. "
            "Spring Boot 로그인은 LoginController.java, LoginService.java, "
            "LoginRequest.java, LoginResponse.java 4개 이름만 우선하며 상세 코드는 regenerate-section에서 생성한다."
        )
    else:
        lines.append(
            "- codeFiles: includeCode=false 이므로 반드시 []만 반환한다. "
            "코드 파일 내용과 코드 예시는 생성하지 않는다."
        )

    if request.includeMissions:
        lines.append(
            "- missions: includeMissions=true여도 최초 generate에서는 []를 우선 반환한다. "
            "상세 실습 미션은 regenerate-section에서 생성한다."
        )
    else:
        lines.append(
            "- missions: includeMissions=false 이므로 반드시 []만 반환한다. "
            "실습 미션 내용과 예시는 생성하지 않는다."
        )

    if request.includeInterview:
        lines.append(
            "- interviewQuestions: includeInterview=true여도 최초 generate에서는 []를 우선 반환한다. "
            "상세 핵심점검/면접 문항은 regenerate-section에서 생성한다."
        )
    else:
        lines.append(
            "- interviewQuestions: includeInterview=false 이므로 반드시 []만 반환한다. "
            "면접 질문 내용과 예시는 생성하지 않는다."
        )

    lines.extend(
        [
            "- 모든 필드는 schema 이름을 그대로 사용한다. goal/hints/keywords/title 같은 단독 key는 금지한다.",
            '- enum: difficulty는 "beginner"|"intermediate"|"advanced", basicQuestions.type은 허용값만 사용한다.',
            '- 타입: requirements[].priority는 문자열, apiSpec[].status는 정수, flow.steps는 문자열 배열이다.',
        ]
    )
    return "\n".join(lines)


def _build_initial_generation_json_skeleton(
    request: FeatureTemplateGenerateRequest,
) -> str:
    """9개 top-level key를 유지하되 include flags에 따라 선택 섹션 예시는 제거한다."""

    skeleton: dict[str, Any] = {
        "overview": {
            "featureName": request.featureName,
            "purpose": "",
            "useCases": [],
            "resultDescription": "",
            "techStack": [request.language]
            + ([request.framework] if request.framework else []),
            "learningGoals": [],
        },
        "requirements": [
            {
                "requirementId": "R-001",
                "name": "",
                "description": "",
                "inputValue": "",
                "processCondition": "",
                "successResult": "",
                "failureResult": "",
                "priority": "HIGH",
                "relatedScreenOrApi": "",
            }
        ],
        "flow": {
            "steps": ["1) 요청 수신", "2) 입력 검증", "3) 처리 실행", "4) 결과 생성", "5) 응답 반환"],
            "layers": [{"layer": "Controller", "role": ""}],
        },
        "apiSpec": [
            {
                "apiName": "",
                "method": "POST",
                "endpoint": "/api/feature",
                "description": "",
                "requestBody": {"field": "value"},
                "responseBody": {"data": {}},
                "status": 200,
            }
        ],
        "codeFiles": [],
        "basicQuestions": [
            {
                "questionId": "Q-001",
                "type": "multiple_choice",
                "question": "",
                "choices": ["A", "B", "C", "D"],
                "answer": "",
                "explanation": "",
                "relatedSection": "requirements",
                "difficulty": request.level.value,
            }
        ],
        "missions": [],
        "interviewQuestions": [],
        "nextRecommendations": [
            {
                "featureName": "",
                "reason": "",
                "expectedLearning": "",
                "priority": 1,
            }
        ],
    }

    return json.dumps(skeleton, ensure_ascii=False, indent=2)


def build_feature_template_prompt_with_applied_rags(
    request: FeatureTemplateGenerateRequest,
) -> tuple[str, list[dict[str, Any]]]:
    """프롬프트 문자열과 프롬프트에 반영된 RAG reference 요약(appliedReferences)을 함께 반환한다."""

    framework_text = request.framework if request.framework else "(미지정)"

    rag_refs = _extract_rag_references_from_reference_context(request.referenceContext)
    selected = select_usable_rag_references(rag_refs)
    rag_body = _format_rag_block_from_selected(
        selected,
        max_content_chars=_MAX_RAG_CONTENT_CHARS,
    )
    applied = build_applied_references_payload(selected)
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
        sectionInstructions=_build_initial_generation_section_instructions(request),
        jsonSkeleton=_build_initial_generation_json_skeleton(request),
    )

    prompt = f"{FEATURE_TEMPLATE_SYSTEM_PROMPT}\n\n{user_prompt}"
    return prompt, applied


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

    prompt, _applied = build_feature_template_prompt_with_applied_rags(request)
    return prompt


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

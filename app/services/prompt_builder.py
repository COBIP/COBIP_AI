"""LLM 호출용 프롬프트 조립기.

이 단계에서는 기능템플릿 생성 요청에 대한 최종 프롬프트 문자열만 만든다.
실제 LLM 호출은 별도 service에서 수행한다.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from app.prompts.feature_template_prompts import (
    FEATURE_TEMPLATE_RAG_CONTEXT_INSTRUCTIONS,
    FEATURE_TEMPLATE_SECTION_SYSTEM_PROMPT,
    FEATURE_TEMPLATE_SECTION_USER_PROMPT_TEMPLATE,
    FEATURE_TEMPLATE_SYSTEM_PROMPT,
    FEATURE_TEMPLATE_USER_PROMPT_TEMPLATE,
)
from app.core.config import settings
from app.schemas.feature_template import FeatureTemplateGenerateRequest

InitialSkeletonProfile = Literal["legacy", "fast", "ultra_fast", "llm_full"]

__all__ = [
    "InitialSkeletonProfile",
    "build_applied_references_payload",
    "build_feature_template_prompt",
    "build_feature_template_prompt_with_applied_rags",
    "build_feature_template_section_prompt",
    "extract_raw_rag_references_from_reference_context",
    "format_rag_references_for_feature_template_prompt",
    "get_initial_generation_skeleton_metadata",
    "is_fast_skeleton_enabled_for_initial_generate",
    "is_ultra_fast_skeleton_enabled_for_initial_generate",
    "resolve_initial_generation_skeleton_profile",
    "select_usable_rag_references",
    "skeleton_rag_content_max_chars_for_initial_generate",
    "skeleton_rag_top_k_for_initial_generate",
]

_RAG_CONTEXT_HEADER = "[검색 근거 / RAG Context]"
_MAX_RAG_REFERENCES = 5  # select_usable_rag_references 기본 상한(비기능템플릿 호출용)
_CONTENT_PREVIEW_MAX_CHARS = 200  # 150~250자 권장 범위 내 기본값


def _feature_template_rag_top_k() -> int:
    return max(1, min(10, int(settings.FEATURE_TEMPLATE_RAG_TOP_K)))


def _feature_template_rag_content_max_chars() -> int:
    return max(50, int(settings.FEATURE_TEMPLATE_RAG_CONTENT_MAX_CHARS))


def resolve_initial_generation_skeleton_profile() -> InitialSkeletonProfile:
    """24차: llm_full > ultra-fast > fast > legacy 우선순위."""

    if settings.FEATURE_TEMPLATE_LLM_FULL_FIRST_ENABLED:
        return "llm_full"
    if settings.FEATURE_TEMPLATE_ULTRA_FAST_SKELETON_ENABLED:
        return "ultra_fast"
    if settings.FEATURE_TEMPLATE_FAST_SKELETON_ENABLED:
        return "fast"
    return "legacy"


def is_ultra_fast_skeleton_enabled_for_initial_generate() -> bool:
    return resolve_initial_generation_skeleton_profile() == "ultra_fast"


def is_fast_skeleton_enabled_for_initial_generate() -> bool:
    return resolve_initial_generation_skeleton_profile() in ("fast", "ultra_fast")


def skeleton_rag_top_k_for_initial_generate() -> int:
    """최초 generate 프롬프트·retrieval 공통 top_k."""

    profile = resolve_initial_generation_skeleton_profile()
    if profile == "llm_full":
        return max(1, min(10, int(settings.FEATURE_TEMPLATE_RAG_TOP_K)))
    if profile == "legacy":
        return max(1, min(10, int(settings.FEATURE_TEMPLATE_RAG_TOP_K)))
    return max(1, min(10, int(settings.FEATURE_TEMPLATE_SKELETON_RAG_TOP_K)))


def skeleton_rag_content_max_chars_for_initial_generate() -> int:
    profile = resolve_initial_generation_skeleton_profile()
    if profile in ("legacy", "llm_full"):
        return _feature_template_rag_content_max_chars()
    return max(50, int(settings.FEATURE_TEMPLATE_SKELETON_RAG_CONTENT_MAX_CHARS))


def skeleton_max_tokens_for_initial_generate() -> int | None:
    """legacy/llm_full는 상한 없음(LLM_MAX_TOKENS), fast/ultra-fast는 skeleton 전용 상한."""

    profile = resolve_initial_generation_skeleton_profile()
    if profile in ("legacy", "llm_full"):
        return None
    return max(64, int(settings.FEATURE_TEMPLATE_SKELETON_MAX_TOKENS))


def get_initial_generation_skeleton_metadata() -> dict[str, Any]:
    profile = resolve_initial_generation_skeleton_profile()
    max_tokens = skeleton_max_tokens_for_initial_generate()
    return {
        "profile": profile,
        "ultraFastSkeletonEnabled": profile == "ultra_fast",
        "fastSkeletonEnabled": profile in ("fast", "ultra_fast"),
        "skeletonMaxTokens": max_tokens,
        "skeletonRagTopK": skeleton_rag_top_k_for_initial_generate(),
        "skeletonRagContentMaxChars": skeleton_rag_content_max_chars_for_initial_generate(),
    }


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
    max_content_chars: int = _feature_template_rag_content_max_chars(),
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


def _extract_applied_reference_metadata(raw: dict[str, Any]) -> dict[str, Any]:
    """appliedReferences/trace용 optional 관측 필드 추출."""

    meta = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
    out: dict[str, Any] = {}
    for key in ("section", "docType", "path", "fileName"):
        val = raw.get(key) if key in raw else meta.get(key)
        if isinstance(val, str) and val.strip():
            out[key] = val.strip()
    if meta.get("contentTruncated") is True:
        out["contentTruncated"] = True
    orig = meta.get("originalContentLength")
    if isinstance(orig, int) and orig > 0:
        out["originalContentLength"] = orig
    return out


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

        item.update(_extract_applied_reference_metadata(raw))

        out.append(item)
    return out


def format_rag_references_for_feature_template_prompt(
    references: list[Any],
    *,
    max_items: int = _MAX_RAG_REFERENCES,
    max_content_chars: int = _feature_template_rag_content_max_chars(),
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
    *,
    profile: InitialSkeletonProfile,
) -> str:
    """include flags에 따라 최초 generate용 섹션 지시만 짧게 조립한다."""

    if profile == "llm_full":
        return _build_llm_full_section_instructions(request)
    if profile == "ultra_fast":
        return _build_ultra_fast_skeleton_section_instructions(request)
    if profile == "fast":
        return _build_fast_skeleton_section_instructions(request)
    return _build_legacy_initial_generation_section_instructions(request)


def _build_llm_full_section_instructions(
    request: FeatureTemplateGenerateRequest,
) -> str:
    lines = [
        "- LLM full-first: 9개 섹션을 한 번에 상세 생성한다. skeleton-only·stub·빈 배열 우회는 금지한다.",
        "- overview: featureName, purpose, useCases, resultDescription, techStack, learningGoals를 실무형으로 채운다.",
        "- requirements: 최소 3개. 입력, 검증, 성공/실패, 보안 관점으로 나눈다.",
        "- flow: steps 5개 이상, layers는 Controller/Service/Repository/DB 및 필요 시 외부 연동.",
        "- apiSpec: 최소 1개. requestBody/responseBody는 필드 예시가 있는 JSON 객체, status는 정수.",
        "- basicQuestions: 최소 3개. type은 가능한 한 섞고 choices는 multiple_choice가 아니면 null.",
        "- nextRecommendations: 최소 3개.",
    ]

    if request.includeCode:
        lines.append(
            "- codeFiles: includeCode=true이므로 fileName·filePath·role·language·content를 "
            "실제 동작 가능한 예시로 최소 4개 작성한다. Spring Boot 로그인은 "
            "LoginController.java, LoginService.java, LoginRequest.java, LoginResponse.java 등을 포함한다."
        )
    else:
        lines.append(
            "- codeFiles: includeCode=false 이므로 반드시 []만 반환한다."
        )

    if request.includeMissions:
        lines.append(
            "- missions: includeMissions=true이므로 최소 2개. description 앞 '미션 목표:' 한 줄, "
            "requirements·successCriteria를 포함한다."
        )
    else:
        lines.append(
            "- missions: includeMissions=false 이므로 반드시 []만 반환한다."
        )

    if request.includeInterview:
        lines.append(
            "- interviewQuestions: includeInterview=true이므로 최소 3개. keyPoints·sampleAnswer를 포함한다."
        )
    else:
        lines.append(
            "- interviewQuestions: includeInterview=false 이므로 반드시 []만 반환한다."
        )

    lines.extend(
        [
            "- RAG context가 있으면 requirements·apiSpec·flow·codeFiles에 우선 반영한다.",
            "- 모든 필드는 schema 이름을 그대로 사용한다. goal/hints/keywords/title 단독 key 금지.",
            '- enum: difficulty는 "beginner"|"intermediate"|"advanced", basicQuestions.type은 허용값만.',
            '- 타입: requirements[].priority는 문자열, apiSpec[].status는 정수, flow.steps는 문자열 배열.',
        ]
    )
    return "\n".join(lines)


def _build_ultra_fast_skeleton_section_instructions(
    request: FeatureTemplateGenerateRequest,
) -> str:
    lines = [
        "- ultra-fast skeleton: LLM은 overview·requirements·flow·apiSpec만 최소 생성한다.",
        "- overview: purpose·resultDescription 각 1문장·50자 내외. learningGoals는 [] 허용 또는 최대 2개 짧게. useCases·techStack 최소.",
        "- requirements: 정확히 3개. description/processCondition/successResult/failureResult는 각 짧게.",
        "- flow: steps 3개 이하, layers 3개 이하. 각 role은 짧게.",
        "- apiSpec: 핵심 API 1개. requestBody/responseBody는 최소 필드 JSON.",
        "- basicQuestions: 반드시 [] (서버 normalizer가 3개 채움).",
        "- nextRecommendations: 반드시 [] (서버 normalizer가 3개 채움).",
        "- codeFiles/missions/interviewQuestions: include 플래그와 무관하게 반드시 [].",
        "- RAG context는 요약·재서술하지 말고 requirements/apiSpec/flow에만 반영한다.",
        "- 장문 설명·중복 문장·코드 본문 금지.",
        "- 모든 필드는 schema 이름을 그대로 사용한다. goal/hints/keywords/title 단독 key 금지.",
        '- enum: difficulty는 "beginner"|"intermediate"|"advanced".',
        '- 타입: requirements[].priority는 문자열, apiSpec[].status는 정수, flow.steps는 문자열 배열.',
    ]
    return "\n".join(lines)


def _build_fast_skeleton_section_instructions(
    request: FeatureTemplateGenerateRequest,
) -> str:
    lines = [
        "- fast skeleton 초안 모드: 최초 generate는 짧은 초안만 생성한다. 장문 해설·상세 근거·긴 배열은 금지한다.",
        "- overview: purpose·resultDescription은 각 1~2문장, learningGoals는 최대 3개(각 20자 내외), useCases·techStack은 짧게.",
        "- requirements: 정확히 3개. 각 필드는 한 문장 수준으로 짧게 쓴다.",
        "- flow: steps 3~4개, layers 4~5개 이하로 핵심 계층만 짧게.",
        "- apiSpec: 핵심 API 1개만. requestBody/responseBody는 짧은 JSON 객체 예시.",
        "- basicQuestions: 정확히 3개. explanation은 1문장.",
        "- nextRecommendations: 정확히 3개만.",
        "- codeFiles: includeCode와 무관하게 반드시 []만 반환한다. 코드 본문·stub·파일명 나열은 금지.",
        "- missions: includeMissions와 무관하게 반드시 []만 반환한다.",
        "- interviewQuestions: includeInterview와 무관하게 반드시 []만 반환한다.",
        "- 상세 보강은 regenerate-section과 서버 normalizer가 담당한다.",
        "- 모든 필드는 schema 이름을 그대로 사용한다. goal/hints/keywords/title 같은 단독 key는 금지한다.",
        '- enum: difficulty는 "beginner"|"intermediate"|"advanced", basicQuestions.type은 허용값만 사용한다.',
        '- 타입: requirements[].priority는 문자열, apiSpec[].status는 정수, flow.steps는 문자열 배열이다.',
    ]
    return "\n".join(lines)


def _build_legacy_initial_generation_section_instructions(
    request: FeatureTemplateGenerateRequest,
) -> str:
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
    *,
    profile: InitialSkeletonProfile,
) -> str:
    """9개 top-level key를 유지하되 skeleton 프로필별 예시를 최소화한다."""

    if profile == "llm_full":
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
                "steps": [
                    "1) 요청 수신",
                    "2) 입력 검증",
                    "3) 비즈니스 처리",
                    "4) 결과 생성",
                    "5) 응답 반환",
                ],
                "layers": [
                    {"layer": "Controller", "role": "요청 수신·응답 반환"},
                    {"layer": "Service", "role": "비즈니스 로직"},
                    {"layer": "Repository", "role": "데이터 접근"},
                    {"layer": "DB", "role": "영속 저장"},
                ],
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
            "codeFiles": [] if not request.includeCode else [
                {
                    "fileName": "",
                    "filePath": "",
                    "role": "Controller",
                    "language": request.language,
                    "content": "",
                }
            ],
            "basicQuestions": [
                {
                    "questionId": "Q-001",
                    "type": "short_answer",
                    "question": "",
                    "choices": None,
                    "answer": "",
                    "explanation": "",
                    "relatedSection": "requirements",
                    "difficulty": request.level.value,
                }
            ],
            "missions": [] if not request.includeMissions else [
                {
                    "missionId": "M-001",
                    "title": "",
                    "description": "",
                    "missionType": "enhancement",
                    "requirements": [],
                    "successCriteria": [],
                    "relatedRequirements": [],
                    "difficulty": request.level.value,
                }
            ],
            "interviewQuestions": [] if not request.includeInterview else [
                {
                    "questionId": "IQ-001",
                    "question": "",
                    "keyPoints": [],
                    "sampleAnswer": "",
                    "relatedSection": "flow",
                }
            ],
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

    if profile == "ultra_fast":
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
                "steps": ["1) 요청", "2) 인증", "3) 응답"],
                "layers": [
                    {"layer": "Controller", "role": "수신"},
                    {"layer": "Service", "role": "인증"},
                    {"layer": "DB", "role": "조회"},
                ],
            },
            "apiSpec": [
                {
                    "apiName": "로그인",
                    "method": "POST",
                    "endpoint": "/api/auth/login",
                    "description": "",
                    "requestBody": {"email": "", "password": ""},
                    "responseBody": {"accessToken": ""},
                    "status": 200,
                }
            ],
            "codeFiles": [],
            "basicQuestions": [],
            "missions": [],
            "interviewQuestions": [],
            "nextRecommendations": [],
        }
        return json.dumps(skeleton, ensure_ascii=False, indent=2)

    if profile == "fast":
        skeleton = {
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
                "steps": ["1) 요청", "2) 검증", "3) 처리", "4) 응답"],
                "layers": [
                    {"layer": "Controller", "role": ""},
                    {"layer": "Service", "role": ""},
                ],
            },
            "apiSpec": [
                {
                    "apiName": "",
                    "method": "POST",
                    "endpoint": "/api/feature",
                    "description": "",
                    "requestBody": {},
                    "responseBody": {},
                    "status": 200,
                }
            ],
            "codeFiles": [],
            "basicQuestions": [
                {
                    "questionId": "Q-001",
                    "type": "short_answer",
                    "question": "",
                    "choices": None,
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

    skeleton = {
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
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    """프롬프트, appliedReferences, skeleton 메타데이터를 함께 반환한다."""

    framework_text = request.framework if request.framework else "(미지정)"
    skeleton_meta = get_initial_generation_skeleton_metadata()
    profile: InitialSkeletonProfile = skeleton_meta["profile"]

    rag_refs = _extract_rag_references_from_reference_context(request.referenceContext)
    rag_top_k = skeleton_meta["skeletonRagTopK"]
    rag_content_max = skeleton_meta["skeletonRagContentMaxChars"]
    selected = select_usable_rag_references(
        rag_refs,
        max_items=rag_top_k,
    )
    rag_body = _format_rag_block_from_selected(
        selected,
        max_content_chars=rag_content_max,
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
        sectionInstructions=_build_initial_generation_section_instructions(
            request,
            profile=profile,
        ),
        jsonSkeleton=_build_initial_generation_json_skeleton(
            request,
            profile=profile,
        ),
    )

    from app.prompts.feature_template_prompts import (
        FEATURE_TEMPLATE_LLM_FULL_SUPPLEMENT,
        FEATURE_TEMPLATE_ULTRA_FAST_SKELETON_SUPPLEMENT,
    )

    system_prompt = FEATURE_TEMPLATE_SYSTEM_PROMPT
    if profile == "llm_full":
        system_prompt = f"{system_prompt}\n\n{FEATURE_TEMPLATE_LLM_FULL_SUPPLEMENT}"
    elif profile == "ultra_fast":
        system_prompt = f"{system_prompt}\n\n{FEATURE_TEMPLATE_ULTRA_FAST_SKELETON_SUPPLEMENT}"

    prompt = f"{system_prompt}\n\n{user_prompt}"
    return prompt, applied, skeleton_meta


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

    prompt, _applied, _meta = build_feature_template_prompt_with_applied_rags(request)
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

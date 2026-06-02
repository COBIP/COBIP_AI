"""22차: quality baseline instant skeleton (deterministic, normalizer-backed)."""

from __future__ import annotations

import re
from typing import Any

from app.models.enums import DifficultyLevel, QuestionType
from app.schemas.feature_template import FeatureTemplateGenerateRequest
from app.services.feature_template_normalizer import FeatureTemplateNormalizer

__all__ = [
    "QUALITY_INSTANT_GENERATION_MODE",
    "build_quality_instant_skeleton_dict",
    "is_login_instant_skeleton_request",
]

QUALITY_INSTANT_GENERATION_MODE = "quality_instant_skeleton"
_DEFERRED_SECTIONS = ["codeFiles", "missions", "interviewQuestions"]

_FEATURE_API: dict[str, tuple[str, str, str]] = {
    "로그인": ("POST", "/api/auth/login", "로그인 API"),
    "게시글 작성": ("POST", "/api/posts", "게시글 작성 API"),
    "댓글 작성": ("POST", "/api/comments", "댓글 작성 API"),
    "상품 등록": ("POST", "/api/products", "상품 등록 API"),
    "예약 생성": ("POST", "/api/reservations", "예약 생성 API"),
    "프로필 수정": ("PATCH", "/api/profile", "프로필 수정 API"),
}


def is_login_instant_skeleton_request(request: FeatureTemplateGenerateRequest) -> bool:
    return (request.featureName or "").strip() == "로그인"


def _level_label(level: DifficultyLevel) -> str:
    return {
        DifficultyLevel.BEGINNER: "초급",
        DifficultyLevel.INTERMEDIATE: "중급",
        DifficultyLevel.ADVANCED: "고급",
    }[level]


def _slug_resource(feature_name: str) -> str:
    fn = feature_name.strip()
    if fn in _FEATURE_API:
        path = _FEATURE_API[fn][1]
        return path.rsplit("/", 1)[-1]
    ascii_slug = re.sub(r"[^a-zA-Z0-9]+", "-", fn).strip("-").lower()
    if ascii_slug:
        return ascii_slug.replace("-", "")
    return "resources"


def _api_for_feature(feature_name: str) -> tuple[str, str, str]:
    fn = feature_name.strip()
    if fn in _FEATURE_API:
        return _FEATURE_API[fn]
    slug = _slug_resource(fn)
    if fn.endswith("수정"):
        return ("PATCH", f"/api/{slug}", f"{fn} API")
    return ("POST", f"/api/{slug}", f"{fn} API")


def _tech_stack(request: FeatureTemplateGenerateRequest) -> list[str]:
    stack = [request.language]
    if request.framework:
        stack.append(request.framework)
    return stack


def _generic_requirements(
    request: FeatureTemplateGenerateRequest,
    *,
    method: str,
    endpoint: str,
) -> list[dict[str, Any]]:
    name = request.featureName.strip()
    return [
        {
            "requirementId": "R-001",
            "name": f"{name} 입력값 수집",
            "description": f"사용자는 {name}에 필요한 필수 입력값을 제공한다.",
            "inputValue": "요청 본문 JSON 필드",
            "processCondition": "필수 필드가 비어 있지 않아야 한다.",
            "successResult": "입력값이 유효하면 처리 단계로 진행한다.",
            "failureResult": "검증 실패 시 400 응답과 오류 메시지를 반환한다.",
            "priority": "HIGH",
            "relatedScreenOrApi": endpoint,
        },
        {
            "requirementId": "R-002",
            "name": f"{name} 비즈니스 처리",
            "description": f"Service 계층이 {name} 핵심 규칙을 검증하고 처리한다.",
            "inputValue": "검증된 요청 DTO",
            "processCondition": "도메인 규칙과 권한 조건을 만족해야 한다.",
            "successResult": "처리 성공 시 결과 DTO를 생성한다.",
            "failureResult": "규칙 위반 시 409 또는 422 응답을 반환한다.",
            "priority": "HIGH",
            "relatedScreenOrApi": f"{name}Service",
        },
        {
            "requirementId": "R-003",
            "name": f"{name} 응답 반환",
            "description": f"{method} {endpoint} 호출 결과를 클라이언트에 반환한다.",
            "inputValue": "처리 결과 DTO",
            "processCondition": "Controller가 표준 응답 포맷으로 직렬화한다.",
            "successResult": "200 또는 201과 함께 결과 데이터를 반환한다.",
            "failureResult": "처리 실패 시 오류 코드와 메시지를 반환한다.",
            "priority": "MEDIUM",
            "relatedScreenOrApi": endpoint,
        },
    ]


def _generic_flow(feature_name: str) -> dict[str, Any]:
    return {
        "steps": [
            f"1. Client가 {feature_name} 요청을 전송한다.",
            "2. Controller가 요청 DTO를 검증하고 Service로 전달한다.",
            "3. Service가 비즈니스 규칙을 적용하고 Repository를 호출한다.",
            "4. Repository/DB에서 필요한 데이터를 조회·저장한다.",
            "5. Controller가 표준 응답 포맷으로 결과를 반환한다.",
        ],
        "layers": [
            {"layer": "Client", "role": f"{feature_name} 화면 입력 및 API 호출"},
            {"layer": "Controller", "role": "요청 수신·입력 검증·응답 반환"},
            {"layer": "Service", "role": "비즈니스 규칙 처리"},
            {"layer": "Repository", "role": "영속 계층 데이터 접근"},
            {"layer": "DB", "role": "데이터 저장 및 조회"},
        ],
    }


def _generic_api_spec(
    *,
    api_name: str,
    method: str,
    endpoint: str,
) -> list[dict[str, Any]]:
    return [
        {
            "apiName": api_name,
            "method": method,
            "endpoint": endpoint,
            "description": f"{api_name} 처리 엔드포인트",
            "requestBody": {"title": "string", "content": "string"},
            "responseBody": {
                "success": True,
                "data": {"id": "long", "message": "string"},
            },
            "status": 201 if method == "POST" else 200,
        }
    ]


def _generic_basic_questions(feature_name: str, level: DifficultyLevel) -> list[dict[str, Any]]:
    diff = level.value
    return [
        {
            "questionId": "Q-001",
            "type": QuestionType.SHORT_ANSWER.value,
            "question": f"{feature_name} 요청에서 Controller와 Service 역할을 구분해 설명하시오.",
            "choices": None,
            "answer": "Controller는 HTTP 요청·응답, Service는 비즈니스 규칙 처리.",
            "explanation": "계층 분리로 테스트와 유지보수성을 높인다.",
            "relatedSection": "flow",
            "difficulty": diff,
        },
        {
            "questionId": "Q-002",
            "type": QuestionType.MULTIPLE_CHOICE.value,
            "question": f"{feature_name} 입력값 검증은 어느 계층에서 수행하는 것이 일반적인가?",
            "choices": [
                "Controller 또는 Service에서 Bean Validation으로 검증",
                "Repository에서만 검증",
                "DB 제약조건만 사용",
                "Client에서만 검증",
            ],
            "answer": "Controller 또는 Service에서 Bean Validation으로 검증",
            "explanation": "입력 검증은 요청 진입 지점 또는 Service 초기에 수행한다.",
            "relatedSection": "requirements",
            "difficulty": diff,
        },
        {
            "questionId": "Q-003",
            "type": QuestionType.SHORT_ANSWER.value,
            "question": f"{feature_name} API 성공 시 클라이언트가 받아야 할 최소 정보는?",
            "choices": None,
            "answer": "처리 결과 식별자와 성공 여부를 담은 표준 응답.",
            "explanation": "일관된 API 응답 포맷으로 클라이언트 처리를 단순화한다.",
            "relatedSection": "apiSpec",
            "difficulty": diff,
        },
    ]


def _generic_next_recommendations(feature_name: str) -> list[dict[str, Any]]:
    return [
        {
            "featureName": "목록 조회",
            "reason": f"{feature_name} 이후 데이터 목록을 확인하는 흐름을 학습한다.",
            "expectedLearning": "페이징·필터·정렬 API 설계",
            "priority": 1,
        },
        {
            "featureName": "상세 조회",
            "reason": "단일 리소스 상세 화면과 GET API 패턴을 익힌다.",
            "expectedLearning": "PathVariable·DTO 매핑",
            "priority": 2,
        },
        {
            "featureName": "수정",
            "reason": f"{feature_name}과 짝을 이루는 변경 API를 구현한다.",
            "expectedLearning": "PUT/PATCH와 부분 업데이트",
            "priority": 3,
        },
    ]


def _generic_seed(request: FeatureTemplateGenerateRequest) -> dict[str, Any]:
    name = request.featureName.strip()
    method, endpoint, api_name = _api_for_feature(name)
    level_l = _level_label(request.level)
    return {
        "overview": {
            "featureName": name,
            "purpose": f"{level_l} 학습용 {name} 기능을 구현한다.",
            "useCases": [f"{name} 기본 사용", f"{name} 확장 시나리오"],
            "resultDescription": f"{name} 처리 결과를 API 응답으로 반환한다.",
            "techStack": _tech_stack(request),
            "learningGoals": [
                f"{name} 요청·응답 흐름 이해",
                "Controller-Service-Repository 계층 분리",
                "REST API 설계 기본",
            ],
        },
        "requirements": _generic_requirements(request, method=method, endpoint=endpoint),
        "flow": _generic_flow(name),
        "apiSpec": _generic_api_spec(api_name=api_name, method=method, endpoint=endpoint),
        "codeFiles": [],
        "basicQuestions": _generic_basic_questions(name, request.level),
        "missions": [],
        "interviewQuestions": [],
        "nextRecommendations": _generic_next_recommendations(name),
    }


def _apply_deferred_empty_sections(normalized: dict[str, Any]) -> None:
    normalized["codeFiles"] = []
    normalized["missions"] = []
    normalized["interviewQuestions"] = []


def build_quality_instant_skeleton_dict(
    request: FeatureTemplateGenerateRequest,
) -> dict[str, Any]:
    """Deterministic quality skeleton → normalizer → deferred 섹션 비우기."""

    if is_login_instant_skeleton_request(request):
        seed: dict[str, Any] = {}
    else:
        seed = _generic_seed(request)

    normalized = FeatureTemplateNormalizer.normalize(seed, request)
    _apply_deferred_empty_sections(normalized)
    return normalized

"""22차/23차: quality baseline instant skeleton (deterministic, normalizer-backed)."""

from __future__ import annotations

import re
from typing import Any

from app.models.enums import DifficultyLevel, QuestionType
from app.schemas.feature_template import FeatureTemplateGenerateRequest
from app.services.feature_template_normalizer import (
    FeatureTemplateNormalizer,
    build_generic_api_spec_template,
)

__all__ = [
    "QUALITY_INSTANT_GENERATION_MODE",
    "QUALITY_INSTANT_FULL_GENERATION_MODE",
    "build_quality_instant_skeleton_dict",
    "compute_instant_deferred_sections",
    "is_login_instant_skeleton_request",
    "instant_full_baseline_applied",
    "resolve_instant_generation_mode",
]

QUALITY_INSTANT_GENERATION_MODE = "quality_instant_skeleton"
QUALITY_INSTANT_FULL_GENERATION_MODE = "quality_instant_full"

_FEATURE_CLASS_PREFIX: dict[str, str] = {
    "게시글 작성": "Post",
    "댓글 작성": "Comment",
    "상품 등록": "Product",
    "예약 생성": "Reservation",
    "프로필 수정": "Profile",
}


def _java_class_prefix(feature_name: str) -> str:
    fn = feature_name.strip()
    if fn in _FEATURE_CLASS_PREFIX:
        return _FEATURE_CLASS_PREFIX[fn]
    if fn == "로그인":
        return "Login"
    ascii_name = re.sub(r"[^a-zA-Z0-9]+", "", fn)
    if ascii_name and ascii_name[0].isalpha():
        return ascii_name[0].upper() + ascii_name[1:]
    return "Feature"


def _java_pkg_default() -> str:
    return "com.example.app"


def _java_file_path(package: str, file_name: str) -> str:
    return f"src/main/java/{package.replace('.', '/')}/{file_name}"


def _login_code_files_baseline() -> list[dict[str, Any]]:
    pkg = "com.example.auth"
    return [
        {
            "fileName": "LoginController.java",
            "filePath": _java_file_path(pkg, "LoginController.java"),
            "role": "Controller",
            "language": "java",
            "content": f"""package {pkg};

import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/auth")
public class LoginController {{

    private final LoginService loginService;

    public LoginController(LoginService loginService) {{
        this.loginService = loginService;
    }}

    @PostMapping("/login")
    public ResponseEntity<LoginResponse> login(@Valid @RequestBody LoginRequest request) {{
        LoginResponse response = loginService.login(request);
        return ResponseEntity.ok(response);
    }}
}}
""",
        },
        {
            "fileName": "LoginService.java",
            "filePath": _java_file_path(pkg, "LoginService.java"),
            "role": "Service",
            "language": "java",
            "content": f"""package {pkg};

import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;

@Service
public class LoginService {{

    private final UserRepository userRepository;
    private final PasswordEncoder passwordEncoder;
    private final JwtProvider jwtProvider;

    public LoginService(
            UserRepository userRepository,
            PasswordEncoder passwordEncoder,
            JwtProvider jwtProvider) {{
        this.userRepository = userRepository;
        this.passwordEncoder = passwordEncoder;
        this.jwtProvider = jwtProvider;
    }}

    public LoginResponse login(LoginRequest request) {{
        var user = userRepository.findByEmail(request.email())
                .orElseThrow(() -> new AuthException("INVALID_CREDENTIALS"));
        if (!passwordEncoder.matches(request.password(), user.getPasswordHash())) {{
            throw new AuthException("INVALID_CREDENTIALS");
        }}
        String accessToken = jwtProvider.createAccessToken(user);
        return new LoginResponse(accessToken, "Bearer", user.getEmail());
    }}
}}
""",
        },
        {
            "fileName": "LoginRequest.java",
            "filePath": _java_file_path(pkg, "LoginRequest.java"),
            "role": "Request DTO",
            "language": "java",
            "content": f"""package {pkg};

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;

public record LoginRequest(
        @Email @NotBlank String email,
        @NotBlank String password) {{
}}
""",
        },
        {
            "fileName": "LoginResponse.java",
            "filePath": _java_file_path(pkg, "LoginResponse.java"),
            "role": "Response DTO",
            "language": "java",
            "content": f"""package {pkg};

public record LoginResponse(String accessToken, String tokenType, String email) {{
}}
""",
        },
    ]


def _login_missions_baseline(level: DifficultyLevel) -> list[dict[str, Any]]:
    diff = level.value
    return [
        {
            "missionId": "M-001",
            "title": "로그인 요청 DTO와 API 연결하기",
            "description": "email/password를 받는 LoginRequest를 만들고 Controller에서 검증한다.",
            "missionType": "implementation",
            "requirements": [
                "LoginRequest에 email/password 필드를 정의한다.",
                "POST /api/auth/login 요청을 Controller에서 받는다.",
                "잘못된 입력은 400 응답으로 처리한다.",
            ],
            "successCriteria": [
                "email/password가 request body로 전달된다.",
                "Controller가 Service를 호출한다.",
            ],
            "relatedRequirements": ["R-001"],
            "difficulty": diff,
        },
        {
            "missionId": "M-002",
            "title": "로그인 검증과 토큰 응답 완성하기",
            "description": "사용자 조회, 비밀번호 검증, accessToken 응답 흐름을 구현한다.",
            "missionType": "implementation",
            "requirements": [
                "email로 사용자를 조회한다.",
                "비밀번호 불일치 시 401 응답을 반환한다.",
                "성공 시 accessToken/tokenType을 반환한다.",
            ],
            "successCriteria": [
                "잘못된 계정은 로그인 실패 처리된다.",
                "성공 응답에 accessToken이 포함된다.",
            ],
            "relatedRequirements": ["R-002", "R-003"],
            "difficulty": diff,
        },
    ]


def _login_interview_questions_baseline() -> list[dict[str, Any]]:
    return [
        {
            "questionId": "IQ-001",
            "question": "LoginRequest DTO를 따로 만드는 이유는 무엇인가?",
            "keyPoints": [
                "HTTP 요청 본문과 도메인 모델 분리",
                "Bean Validation 적용 위치",
                "Controller 계약 안정화",
            ],
            "sampleAnswer": (
                "HTTP 요청 JSON을 도메인 엔티티와 분리해 검증 규칙을 DTO에 모으고, "
                "Controller·Service 계약을 안정적으로 유지하기 위해서다."
            ),
            "relatedSection": "codeFiles",
        },
        {
            "questionId": "IQ-002",
            "question": "비밀번호 검증 로직은 Controller가 아니라 Service에 두는 이유는 무엇인가?",
            "keyPoints": [
                "비즈니스 규칙은 Service 책임",
                "Controller는 HTTP 처리",
                "테스트 용이성",
            ],
            "sampleAnswer": (
                "비밀번호 비교와 사용자 조회는 비즈니스 규칙이므로 Service에 두고, "
                "Controller는 요청·응답 변환만 담당한다."
            ),
            "relatedSection": "flow",
        },
        {
            "questionId": "IQ-003",
            "question": "로그인 성공 시 accessToken을 반환하는 이유는 무엇인가?",
            "keyPoints": [
                "상태 비저장 인증",
                "후속 API 인증",
                "세션 대비 확장성",
            ],
            "sampleAnswer": (
                "클라이언트가 이후 요청에서 Authorization 헤더로 자신을 증명할 수 있도록 "
                "무상태 인증 토큰을 발급하기 위해서다."
            ),
            "relatedSection": "apiSpec",
        },
    ]


def _service_field_name(class_name: str) -> str:
    return class_name[0].lower() + class_name[1:] if class_name else "service"


def _generic_code_files_baseline(request: FeatureTemplateGenerateRequest) -> list[dict[str, Any]]:
    prefix = _java_class_prefix(request.featureName)
    method, endpoint, _ = _api_for_feature(request.featureName)
    pkg = _java_pkg_default()
    controller = f"{prefix}Controller"
    service = f"{prefix}Service"
    req_dto = f"{prefix}CreateRequest" if method == "POST" else f"{prefix}UpdateRequest"
    resp_dto = f"{prefix}Response"
    mapping = endpoint.rsplit("/", 1)[0] if endpoint.count("/") >= 2 else "/api"
    action = "create" if method == "POST" else "update"
    http_mapping = "PostMapping" if method == "POST" else "PatchMapping"
    path_suffix = endpoint.split("/")[-1]
    service_field = _service_field_name(service)

    return [
        {
            "fileName": f"{controller}.java",
            "filePath": _java_file_path(pkg, f"{controller}.java"),
            "role": "Controller",
            "language": "java",
            "content": f"""package {pkg};

import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.{http_mapping};
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("{mapping}")
public class {controller} {{

    private final {service} {service_field};

    public {controller}({service} {service_field}) {{
        this.{service_field} = {service_field};
    }}

    @{http_mapping}("/{path_suffix}")
    public ResponseEntity<{resp_dto}> {action}(@Valid @RequestBody {req_dto} request) {{
        return ResponseEntity.ok({service_field}.{action}(request));
    }}
}}
""",
        },
        {
            "fileName": f"{service}.java",
            "filePath": _java_file_path(pkg, f"{service}.java"),
            "role": "Service",
            "language": "java",
            "content": f"""package {pkg};

import org.springframework.stereotype.Service;

@Service
public class {service} {{

    private final {prefix}Repository repository;

    public {service}({prefix}Repository repository) {{
        this.repository = repository;
    }}

    public {resp_dto} {action}({req_dto} request) {{
        var saved = repository.save(request.toEntity());
        return {resp_dto}.from(saved);
    }}
}}
""",
        },
        {
            "fileName": f"{req_dto}.java",
            "filePath": _java_file_path(pkg, f"{req_dto}.java"),
            "role": "Request DTO",
            "language": "java",
            "content": f"""package {pkg};

import jakarta.validation.constraints.NotBlank;

public record {req_dto}(@NotBlank String title, String content) {{
    public {prefix}Entity toEntity() {{
        return new {prefix}Entity(title, content);
    }}
}}
""",
        },
        {
            "fileName": f"{resp_dto}.java",
            "filePath": _java_file_path(pkg, f"{resp_dto}.java"),
            "role": "Response DTO",
            "language": "java",
            "content": f"""package {pkg};

public record {resp_dto}(Long id, String title, String message) {{
    public static {resp_dto} from({prefix}Entity entity) {{
        return new {resp_dto}(entity.getId(), entity.getTitle(), "처리 완료");
    }}
}}
""",
        },
    ]


def _generic_missions_baseline(
    request: FeatureTemplateGenerateRequest,
) -> list[dict[str, Any]]:
    name = request.featureName.strip()
    diff = request.level.value
    return [
        {
            "missionId": "M-001",
            "title": f"{name} 요청 DTO와 API 연결하기",
            "description": f"{name} 입력값을 DTO로 받고 Controller에서 Service로 전달한다.",
            "missionType": "implementation",
            "requirements": [
                "요청 DTO에 필수 필드를 정의한다.",
                f"{name} API 엔드포인트를 Controller에 연결한다.",
                "입력 검증 실패 시 400 응답을 반환한다.",
            ],
            "successCriteria": [
                "요청 본문이 DTO로 매핑된다.",
                "Controller가 Service를 호출한다.",
            ],
            "relatedRequirements": ["R-001"],
            "difficulty": diff,
        },
        {
            "missionId": "M-002",
            "title": f"{name} 비즈니스 처리와 응답 완성하기",
            "description": f"Service와 Repository를 통해 {name} 처리 결과를 반환한다.",
            "missionType": "implementation",
            "requirements": [
                "Service에서 도메인 규칙을 검증한다.",
                "Repository/DB에 데이터를 저장하거나 조회한다.",
                "표준 응답 DTO로 결과를 반환한다.",
            ],
            "successCriteria": [
                "처리 성공 시 식별자와 결과 메시지가 포함된다.",
                "실패 시 적절한 HTTP 상태 코드가 반환된다.",
            ],
            "relatedRequirements": ["R-002", "R-003"],
            "difficulty": diff,
        },
    ]


def _generic_interview_questions_baseline(feature_name: str) -> list[dict[str, Any]]:
    return [
        {
            "questionId": "IQ-001",
            "question": f"{feature_name} API에서 요청 DTO를 분리하는 이유는 무엇인가?",
            "keyPoints": ["입력 검증", "계층 분리", "API 계약 안정화"],
            "sampleAnswer": (
                "HTTP 요청 구조와 내부 도메인 모델을 분리해 검증과 변경 영향을 "
                "Controller·Service 경계에 고정하기 위해서다."
            ),
            "relatedSection": "codeFiles",
        },
        {
            "questionId": "IQ-002",
            "question": f"{feature_name} 처리에서 Service 계층의 역할은 무엇인가?",
            "keyPoints": ["비즈니스 규칙", "Repository 호출", "트랜잭션 경계"],
            "sampleAnswer": (
                "Service는 {feature_name} 규칙을 적용하고 Repository를 호출해 "
                "영속 계층과 협력한다."
            ).format(feature_name=feature_name),
            "relatedSection": "flow",
        },
        {
            "questionId": "IQ-003",
            "question": f"{feature_name} 성공 응답에 식별자와 메시지를 포함하는 이유는?",
            "keyPoints": ["클라이언트 후속 처리", "일관된 API 응답", "UX"],
            "sampleAnswer": (
                "클라이언트가 생성·수정 결과를 화면에 반영하고 "
                "후속 API 호출에 사용할 식별자를 제공하기 위해서다."
            ),
            "relatedSection": "apiSpec",
        },
    ]


def _seed_optional_baselines(request: FeatureTemplateGenerateRequest) -> dict[str, Any]:
    if is_login_instant_skeleton_request(request):
        seed: dict[str, Any] = {}
    else:
        seed = _generic_seed(request)

    if request.includeCode:
        seed["codeFiles"] = (
            _login_code_files_baseline()
            if is_login_instant_skeleton_request(request)
            else _generic_code_files_baseline(request)
        )
    if request.includeMissions:
        seed["missions"] = (
            _login_missions_baseline(request.level)
            if is_login_instant_skeleton_request(request)
            else _generic_missions_baseline(request)
        )
    if request.includeInterview:
        seed["interviewQuestions"] = (
            _login_interview_questions_baseline()
            if is_login_instant_skeleton_request(request)
            else _generic_interview_questions_baseline(request.featureName.strip())
        )
    return seed


def resolve_instant_generation_mode(request: FeatureTemplateGenerateRequest) -> str:
    if request.includeCode or request.includeMissions or request.includeInterview:
        return QUALITY_INSTANT_FULL_GENERATION_MODE
    return QUALITY_INSTANT_GENERATION_MODE


def instant_full_baseline_applied(request: FeatureTemplateGenerateRequest) -> bool:
    return resolve_instant_generation_mode(request) == QUALITY_INSTANT_FULL_GENERATION_MODE


def compute_instant_deferred_sections(
    request: FeatureTemplateGenerateRequest,
    normalized: dict[str, Any],
) -> list[str]:
    deferred: list[str] = []
    if request.includeCode and not normalized.get("codeFiles"):
        deferred.append("codeFiles")
    if request.includeMissions and not normalized.get("missions"):
        deferred.append("missions")
    if request.includeInterview and not normalized.get("interviewQuestions"):
        deferred.append("interviewQuestions")
    return deferred


def _apply_include_flag_sections(
    request: FeatureTemplateGenerateRequest,
    normalized: dict[str, Any],
) -> None:
    if not request.includeCode:
        normalized["codeFiles"] = []
    if not request.includeMissions:
        normalized["missions"] = []
    if not request.includeInterview:
        normalized["interviewQuestions"] = []


def _ensure_instant_full_guard(
    request: FeatureTemplateGenerateRequest,
    normalized: dict[str, Any],
) -> None:
    """normalizer 이후 include=true인데 비어 있으면 deterministic baseline으로 재보강."""

    if request.includeCode and not normalized.get("codeFiles"):
        normalized["codeFiles"] = (
            _login_code_files_baseline()
            if is_login_instant_skeleton_request(request)
            else _generic_code_files_baseline(request)
        )
    if request.includeMissions and not normalized.get("missions"):
        normalized["missions"] = (
            _login_missions_baseline(request.level)
            if is_login_instant_skeleton_request(request)
            else _generic_missions_baseline(request)
        )
    if request.includeInterview and not normalized.get("interviewQuestions"):
        normalized["interviewQuestions"] = (
            _login_interview_questions_baseline()
            if is_login_instant_skeleton_request(request)
            else _generic_interview_questions_baseline(request.featureName.strip())
        )


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
        build_generic_api_spec_template(
            api_name=api_name,
            method=method,
            endpoint=endpoint,
        )
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


def build_quality_instant_skeleton_dict(
    request: FeatureTemplateGenerateRequest,
) -> dict[str, Any]:
    """Deterministic quality skeleton → normalizer → include flags 반영."""

    seed = _seed_optional_baselines(request)
    normalized = FeatureTemplateNormalizer.normalize(seed, request)
    _apply_include_flag_sections(request, normalized)
    _ensure_instant_full_guard(request, normalized)
    return normalized

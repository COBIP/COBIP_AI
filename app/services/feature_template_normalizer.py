"""기능템플릿 LLM/fallback dict → FeatureTemplateData용 안전 구조 보정."""

from __future__ import annotations

import copy
import logging
import re
from typing import Any

from app.models.enums import DifficultyLevel
from app.schemas.feature_template import FeatureTemplateGenerateRequest

__all__ = [
    "FeatureTemplateNormalizer",
    "build_generic_api_spec_template",
    "get_login_api_spec_template",
    "normalize_feature_template_payload",
]

logger = logging.getLogger(__name__)

_DEFAULT_MISSION_REQUIREMENTS: tuple[str, ...] = (
    "미션 목표를 이해하고 필요한 기능을 구현한다.",
)
_DEFAULT_MISSION_SUCCESS: tuple[str, ...] = (
    "요구사항에 맞게 기능이 정상 동작한다.",
)
_DIFFICULTY_VALID: frozenset[str] = frozenset(m.value for m in DifficultyLevel)

_PRIORITY_NUMBER_MAP: dict[int, str] = {
    1: "HIGH",
    2: "MEDIUM",
    3: "LOW",
}

_TOP_LEVEL_STRING_FIELDS: dict[str, tuple[str, ...]] = {
    "overview": ("featureName", "purpose", "resultDescription"),
    "flow.layers": ("layer", "role"),
    "requirements": (
        "requirementId",
        "name",
        "description",
        "inputValue",
        "processCondition",
        "successResult",
        "failureResult",
        "priority",
        "relatedScreenOrApi",
    ),
    "apiSpec": ("apiName", "method", "endpoint", "description"),
    "codeFiles": ("fileName", "role", "language", "content"),
    "basicQuestions": (
        "questionId",
        "type",
        "question",
        "answer",
        "explanation",
        "relatedSection",
        "difficulty",
    ),
    "missions": ("missionId", "title", "description", "missionType", "difficulty"),
    "interviewQuestions": ("questionId", "question", "sampleAnswer", "relatedSection"),
    "nextRecommendations": ("featureName", "reason", "expectedLearning"),
}

_STRING_LIST_FIELDS: dict[str, tuple[str, ...]] = {
    "overview": ("useCases", "techStack", "learningGoals"),
    "flow": ("steps",),
    "basicQuestions": ("choices",),
    "missions": ("requirements", "successCriteria", "relatedRequirements"),
    "interviewQuestions": ("keyPoints",),
}

_TOP_LEVEL_ALIASES: dict[str, str] = {
    "api_spec": "apiSpec",
    "basic_questions": "basicQuestions",
    "interview": "interviewQuestions",
    "interview_questions": "interviewQuestions",
    "next_recommendations": "nextRecommendations",
}


def _coerce_to_string(value: object) -> str:
    if isinstance(value, dict):
        return " ".join(str(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    return "" if value is None else str(value)


def _normalize_string_fields(
    item: dict,
    fields: tuple[str, ...],
    path_prefix: str,
    changed_fields: list[str],
) -> dict:
    normalized_item = dict(item)
    for field in fields:
        if field not in normalized_item:
            continue
        value = normalized_item[field]
        if value is None and field in {"filePath", "relatedSection"}:
            continue
        if not isinstance(value, str):
            normalized_item[field] = _coerce_to_string(value)
            changed_fields.append(f"{path_prefix}.{field}")
    return normalized_item


def _normalize_string_list_field(
    item: dict,
    field: str,
    path_prefix: str,
    changed_fields: list[str],
) -> dict:
    if field not in item:
        return item

    normalized_item = dict(item)
    values = normalized_item[field]
    if values is None and field == "choices":
        return normalized_item
    if not isinstance(values, list):
        normalized_item[field] = [_coerce_to_string(values)]
        changed_fields.append(f"{path_prefix}.{field}")
        return normalized_item

    normalized_values = []
    changed = False
    for value in values:
        if isinstance(value, str):
            normalized_values.append(value)
        else:
            normalized_values.append(_coerce_to_string(value))
            changed = True
    if changed:
        normalized_item[field] = normalized_values
        changed_fields.append(f"{path_prefix}.{field}")
    return normalized_item


def _default_requirement_related_screen_or_api(
    request: FeatureTemplateGenerateRequest | None,
) -> str:
    if request is None:
        return "관련 화면 / API"
    name = (request.featureName or "").strip()
    if not name:
        return "관련 화면 / API"
    return f"{name} 화면 / {name} API"


def _is_missing_or_blank_str(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def _str_list_effectively_empty(value: object) -> bool:
    if value is None:
        return True
    if not isinstance(value, list):
        return True
    return not any(_coerce_to_string(item).strip() for item in value)


def _mission_hints_parts(hints_raw: object, hint_raw: object) -> list[str]:
    parts: list[str] = []
    for src in (hints_raw, hint_raw):
        if src is None:
            continue
        if isinstance(src, list):
            for x in src:
                t = _coerce_to_string(x).strip()
                if t:
                    parts.append(t)
        else:
            t = _coerce_to_string(src).strip()
            if t:
                parts.append(t)
    return parts


def _default_mission_difficulty(request: FeatureTemplateGenerateRequest | None) -> str:
    if request is not None:
        return request.level.value
    return DifficultyLevel.BEGINNER.value


def _contains_placeholder(text: str) -> bool:
    if not text:
        return False
    low = text.lower()
    if "실제 동작 가능한 코드 문자열" in text:
        return True
    if "..." in text:
        return True
    if "TODO" in text:
        return True
    if "예시 코드" in text:
        return True
    if "생략" in text:
        return True
    if "placeholder" in low:
        return True
    if "플레이스홀더" in text:
        return True
    return False


def _interview_item_has_placeholder(item: dict[str, Any]) -> bool:
    q = item.get("question")
    if isinstance(q, str) and _contains_placeholder(q):
        return True
    sa = item.get("sampleAnswer")
    if isinstance(sa, str) and _contains_placeholder(sa):
        return True
    kps = item.get("keyPoints")
    if isinstance(kps, list):
        for kp in kps:
            if isinstance(kp, str) and _contains_placeholder(kp):
                return True
    return False


def _java_class_prefix(request: FeatureTemplateGenerateRequest | None) -> str:
    if request is None:
        return "Login"
    fn = (request.featureName or "").strip()
    if fn in ("로그인", "login", "Login"):
        return "Login"
    safe = re.sub(r"[^0-9a-zA-Z_]+", "", fn.replace(" ", ""))
    if safe and safe[0].isalpha():
        return safe[0].upper() + safe[1:]
    return "App"


def _is_java_spring(request: FeatureTemplateGenerateRequest | None) -> bool:
    if request is None:
        return False
    if (request.language or "").lower() != "java":
        return False

    framework = getattr(request, "framework", "") or ""
    tech_stack = (
        getattr(request, "techStack", None)
        or getattr(request, "tech_stack", None)
        or ""
    )

    target = f"{framework} {tech_stack}".lower().replace("_", "-")
    return "spring" in target


def _is_login_feature_request(request: FeatureTemplateGenerateRequest | None) -> bool:
    if request is None:
        return False
    fn = (request.featureName or "").strip()
    return fn in ("로그인", "login", "Login")


_LOGIN_PKG_DEFAULT = "com.example.auth"
_LOGIN_CANONICAL_ENDPOINT = "/api/auth/login"
_LOGIN_CANONICAL_ENDPOINT_WITH_METHOD = "POST /api/auth/login"
_LOGIN_REQUIRED_FILES: tuple[str, ...] = (
    "LoginController.java",
    "LoginService.java",
    "LoginRequest.java",
    "LoginResponse.java",
)


def _basename_java_filename(name: str) -> str:
    s = (name or "").strip().replace("\\", "/")
    if "/" in s:
        s = s.rsplit("/", 1)[-1]
    if not s:
        return "Unknown.java"
    if not s.endswith(".java"):
        s = f"{s}.java"
    return s


def _extract_java_package(content: str) -> str | None:
    m = re.search(r"^\s*package\s+([\w.]+)\s*;", content, re.MULTILINE)
    return m.group(1) if m else None


def _java_file_path_for(package: str, basename: str) -> str:
    rel = package.replace(".", "/") + "/" + basename
    return f"src/main/java/{rel}"


def _scrub_login_endpoint_placeholders_in_text(text: str) -> str:
    """로그인 템플릿 문자열 내 generic endpoint placeholder를 canonical로 치환."""

    if not text or not isinstance(text, str):
        return text
    out = text
    replacements = (
        ("POST /api/feature", _LOGIN_CANONICAL_ENDPOINT_WITH_METHOD),
        ("post /api/feature", _LOGIN_CANONICAL_ENDPOINT_WITH_METHOD),
        ("Post /api/feature", _LOGIN_CANONICAL_ENDPOINT_WITH_METHOD),
        ("/api/feature", _LOGIN_CANONICAL_ENDPOINT),
        ("/api/example", _LOGIN_CANONICAL_ENDPOINT),
        ("POST /api/login", _LOGIN_CANONICAL_ENDPOINT_WITH_METHOD),
        ("post /api/login", _LOGIN_CANONICAL_ENDPOINT_WITH_METHOD),
    )
    for old, new in replacements:
        if old in out:
            out = out.replace(old, new)
    return out


def _scrub_login_endpoint_placeholders_in_payload(
    normalized: dict[str, Any],
    changed_fields: list[str],
) -> None:
    """requirements/flow/basicQuestions/missions/interviewQuestions 텍스트 endpoint 보정."""

    req_fields = (
        "description",
        "inputValue",
        "processCondition",
        "successResult",
        "failureResult",
        "relatedScreenOrApi",
    )
    reqs = normalized.get("requirements")
    if isinstance(reqs, list):
        for index, item in enumerate(reqs):
            if not isinstance(item, dict):
                continue
            for field in req_fields:
                val = item.get(field)
                if not isinstance(val, str):
                    continue
                fixed = _scrub_login_endpoint_placeholders_in_text(val)
                if fixed != val:
                    item[field] = fixed
                    changed_fields.append(f"requirements[{index}].{field}[endpoint-scrub]")

    flow = normalized.get("flow")
    if isinstance(flow, dict):
        steps = flow.get("steps")
        if isinstance(steps, list):
            new_steps: list[str] = []
            for index, step in enumerate(steps):
                text = _coerce_to_string(step)
                fixed = _scrub_login_endpoint_placeholders_in_text(text)
                if fixed != text:
                    changed_fields.append(f"flow.steps[{index}][endpoint-scrub]")
                new_steps.append(fixed)
            flow["steps"] = new_steps

    for section, str_fields in (
        ("basicQuestions", ("question", "answer", "explanation")),
        ("interviewQuestions", ("question", "sampleAnswer")),
    ):
        items = normalized.get(section)
        if not isinstance(items, list):
            continue
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            for field in str_fields:
                val = item.get(field)
                if not isinstance(val, str):
                    continue
                fixed = _scrub_login_endpoint_placeholders_in_text(val)
                if fixed != val:
                    item[field] = fixed
                    changed_fields.append(f"{section}[{index}].{field}[endpoint-scrub]")
            if section == "interviewQuestions":
                kps = item.get("keyPoints")
                if isinstance(kps, list):
                    fixed_kps: list[str] = []
                    for kp_index, kp in enumerate(kps):
                        text = _coerce_to_string(kp)
                        fixed = _scrub_login_endpoint_placeholders_in_text(text)
                        if fixed != text:
                            changed_fields.append(
                                f"interviewQuestions[{index}].keyPoints[{kp_index}][endpoint-scrub]"
                            )
                        fixed_kps.append(fixed)
                    item["keyPoints"] = fixed_kps

    missions = normalized.get("missions")
    if isinstance(missions, list):
        for index, item in enumerate(missions):
            if not isinstance(item, dict):
                continue
            for field in ("title", "description"):
                val = item.get(field)
                if isinstance(val, str):
                    fixed = _scrub_login_endpoint_placeholders_in_text(val)
                    if fixed != val:
                        item[field] = fixed
                        changed_fields.append(f"missions[{index}].{field}[endpoint-scrub]")
            for list_field in ("requirements", "successCriteria"):
                values = item.get(list_field)
                if not isinstance(values, list):
                    continue
                fixed_list: list[str] = []
                for li, raw in enumerate(values):
                    text = _coerce_to_string(raw)
                    fixed = _scrub_login_endpoint_placeholders_in_text(text)
                    if fixed != text:
                        changed_fields.append(
                            f"missions[{index}].{list_field}[{li}][endpoint-scrub]"
                        )
                    fixed_list.append(fixed)
                item[list_field] = fixed_list


def _infer_java_code_file_role(file_name: str) -> str | None:
    bn = _basename_java_filename(file_name)
    role_map: tuple[tuple[str, str], ...] = (
        ("Controller.java", "REST API 컨트롤러"),
        ("Service.java", "비즈니스 로직 서비스"),
        ("Request.java", "요청 DTO"),
        ("Response.java", "응답 DTO"),
        ("Repository.java", "데이터 접근 Repository"),
        ("Entity.java", "JPA Entity"),
        ("Config.java", "설정 클래스"),
        ("Filter.java", "인증/인가 필터"),
    )
    for suffix, role in role_map:
        if bn.endswith(suffix):
            return role
    return None


def _normalize_java_package_in_content(content: str, package: str) -> str:
    if not content:
        return content
    out = re.sub(
        r"^\s*package\s+[\w.]+\s*;",
        f"package {package};",
        content,
        count=1,
        flags=re.MULTILINE,
    )
    for alt_pkg in ("com.example.login", "com.example.auth"):
        if alt_pkg != package:
            out = out.replace(alt_pkg, package)
    return out


def _normalize_login_dto_accessor_consistency(content: str) -> str:
    """class DTO + record-style accessor 혼용을 getter 호출로 통일."""

    if not content:
        return content
    replacements = (
        (r"\brequest\.username\(\)", "request.getUsername()"),
        (r"\brequest\.password\(\)", "request.getPassword()"),
        (r"\bbody\.username\(\)", "body.getUsername()"),
        (r"\bbody\.password\(\)", "body.getPassword()"),
        (r"\bloginRequest\.username\(\)", "loginRequest.getUsername()"),
        (r"\bloginRequest\.password\(\)", "loginRequest.getPassword()"),
    )
    out = content
    for pattern, repl in replacements:
        out = re.sub(pattern, repl, out)
    return out


def _normalize_login_code_file_roles(
    files: list[dict[str, Any]],
    changed_fields: list[str],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for index, raw in enumerate(files):
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        fn = str(item.get("fileName", "") or "")
        inferred = _infer_java_code_file_role(fn)
        if inferred and item.get("role") != inferred:
            item["role"] = inferred
            changed_fields.append(f"codeFiles[{index}].role")
        out.append(item)
    return out


def _unify_login_java_codefiles_package(
    files: list[dict[str, Any]],
    package: str,
    changed_fields: list[str],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for index, raw in enumerate(files):
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        fn = _basename_java_filename(str(item.get("fileName", "") or ""))
        if not fn.endswith(".java"):
            out.append(item)
            continue
        content = item.get("content", "")
        cstr = content if isinstance(content, str) else _coerce_to_string(content)
        fixed = _normalize_java_package_in_content(cstr, package)
        fixed = _normalize_login_dto_accessor_consistency(fixed)
        if fixed != cstr:
            changed_fields.append(f"codeFiles[{index}].content[package-dto]")
        item["fileName"] = fn
        item["filePath"] = _java_file_path_for(package, fn)
        item["language"] = "java"
        item["content"] = fixed
        out.append(item)
    return out


def _apply_spring_boot_login_quality_guard(
    normalized: dict[str, Any],
    request: FeatureTemplateGenerateRequest | None,
    changed_fields: list[str],
) -> None:
    """로그인 + Spring Boot LLM/fallback 공통 품질 guard."""

    if request is None or not _is_java_spring(request) or not _is_login_feature_request(request):
        return

    _scrub_login_endpoint_placeholders_in_payload(normalized, changed_fields)

    if not request.includeCode:
        return

    files = normalized.get("codeFiles")
    if not isinstance(files, list):
        return

    files = _unify_login_java_codefiles_package(files, _LOGIN_PKG_DEFAULT, changed_fields)
    files = _normalize_login_code_file_roles(files, changed_fields)
    normalized["codeFiles"] = files


def _java_declares_type(content: str, type_name: str) -> bool:
    return bool(
        re.search(
            rf"\b(?:class|record|interface)\s+{re.escape(type_name)}\b",
            content,
        )
    )


def _is_controller_like_java(content: str) -> bool:
    return "@RestController" in content or "@Controller" in content


def _login_controller_content_valid(content: str) -> bool:
    if _contains_placeholder(content):
        return False
    path_ok = "/api/auth" in content
    return (
        "class LoginController" in content
        and "@RestController" in content
        and path_ok
        and "@PostMapping" in content
        and "/login" in content
        and "LoginService" in content
        and "LoginRequest" in content
        and "LoginResponse" in content
    )


def _login_service_content_valid(content: str) -> bool:
    if _contains_placeholder(content):
        return False
    if _is_controller_like_java(content):
        return False
    if "@RequestMapping" in content or "@PostMapping" in content or "@GetMapping" in content:
        return False
    has_request_access = (
        "request.getUsername()" in content
        or "request.getPassword()" in content
        or "request.username()" in content
        or "request.password()" in content
    )
    return (
        "class LoginService" in content
        and "@Service" in content
        and "LoginResponse" in content
        and "login" in content
        and "LoginRequest" in content
        and has_request_access
    )


def _login_request_content_valid(content: str) -> bool:
    if _contains_placeholder(content):
        return False
    has_type = "record LoginRequest" in content or "class LoginRequest" in content
    has_username = "username" in content
    has_password = "password" in content
    if "class LoginRequest" in content:
        return has_type and has_username and has_password and "getUsername" in content
    return has_type and has_username and has_password


def _login_response_content_valid(content: str) -> bool:
    if _contains_placeholder(content):
        return False
    has_type = "record LoginResponse" in content or "class LoginResponse" in content
    low = content.lower()
    has_field = (
        "accesstoken" in low
        or re.search(r"\btoken\b", low)
        or re.search(r"\buser\b", low)
        or "username" in low
    )
    return has_type and has_field


def _canonical_login_spring_four() -> dict[str, dict[str, Any]]:
    pkg = _LOGIN_PKG_DEFAULT
    return {
        "LoginController.java": {
            "fileName": "LoginController.java",
            "filePath": _java_file_path_for(pkg, "LoginController.java"),
            "role": "REST API 컨트롤러",
            "language": "java",
            "content": f"""package {pkg};

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
    public ResponseEntity<LoginResponse> login(@RequestBody LoginRequest request) {{
        return ResponseEntity.ok(loginService.login(request));
    }}
}}
""",
        },
        "LoginService.java": {
            "fileName": "LoginService.java",
            "filePath": _java_file_path_for(pkg, "LoginService.java"),
            "role": "비즈니스 로직 서비스",
            "language": "java",
            "content": f"""package {pkg};

import org.springframework.stereotype.Service;

@Service
public class LoginService {{

    public LoginResponse login(LoginRequest request) {{
        String username = request.getUsername();
        String password = request.getPassword();
        if (username == null || username.isBlank()) {{
            throw new IllegalArgumentException("username required");
        }}
        if (password == null || password.isBlank()) {{
            throw new IllegalArgumentException("password required");
        }}
        if (!"demo".equals(username)) {{
            throw new IllegalArgumentException("unknown user");
        }}
        if (!"demo".equals(password)) {{
            throw new IllegalArgumentException("invalid password");
        }}
        return new LoginResponse("demo-access-token", "Bearer", username);
    }}
}}
""",
        },
        "LoginRequest.java": {
            "fileName": "LoginRequest.java",
            "filePath": _java_file_path_for(pkg, "LoginRequest.java"),
            "role": "요청 DTO",
            "language": "java",
            "content": f"""package {pkg};

public class LoginRequest {{
    private String username;
    private String password;

    public String getUsername() {{
        return username;
    }}

    public void setUsername(String username) {{
        this.username = username;
    }}

    public String getPassword() {{
        return password;
    }}

    public void setPassword(String password) {{
        this.password = password;
    }}
}}
""",
        },
        "LoginResponse.java": {
            "fileName": "LoginResponse.java",
            "filePath": _java_file_path_for(pkg, "LoginResponse.java"),
            "role": "응답 DTO",
            "language": "java",
            "content": f"""package {pkg};

public class LoginResponse {{
    private String accessToken;
    private String tokenType;
    private String username;

    public LoginResponse(String accessToken, String tokenType, String username) {{
        this.accessToken = accessToken;
        this.tokenType = tokenType;
        this.username = username;
    }}

    public String getAccessToken() {{
        return accessToken;
    }}

    public String getTokenType() {{
        return tokenType;
    }}

    public String getUsername() {{
        return username;
    }}
}}
""",
        },
    }


def _default_login_requirements(
    request: FeatureTemplateGenerateRequest | None,
) -> list[dict[str, Any]]:
    return [
        {
            "requirementId": "R-001",
            "name": "로그인 요청 입력값 검증",
            "description": "사용자는 username과 password를 입력해 로그인 요청을 보낼 수 있어야 한다.",
            "inputValue": "username, password",
            "processCondition": "username/password는 비어 있으면 안 된다.",
            "successResult": "유효한 입력이면 인증 처리로 진행한다.",
            "failureResult": "입력값이 누락되면 400 응답을 반환한다.",
            "priority": "HIGH",
            "relatedScreenOrApi": "POST /api/auth/login",
        },
        {
            "requirementId": "R-002",
            "name": "사용자 인증 처리",
            "description": "서버는 입력받은 username으로 사용자를 조회하고 비밀번호를 검증한다.",
            "inputValue": "username, password",
            "processCondition": "사용자 존재 여부와 비밀번호 일치 여부를 확인한다.",
            "successResult": "인증 성공 시 토큰 발급 단계로 진행한다.",
            "failureResult": "인증 실패 시 401 응답을 반환한다.",
            "priority": "HIGH",
            "relatedScreenOrApi": "LoginService.login",
        },
        {
            "requirementId": "R-003",
            "name": "로그인 성공 응답",
            "description": "로그인 성공 시 accessToken, tokenType, username을 반환한다.",
            "inputValue": "인증된 사용자 정보",
            "processCondition": "인증이 성공해야 한다.",
            "successResult": "200 OK와 로그인 응답 DTO를 반환한다.",
            "failureResult": "인증 실패 시 성공 응답을 반환하지 않는다.",
            "priority": "MEDIUM",
            "relatedScreenOrApi": "LoginResponse",
        },
    ]


_LOGIN_GENERIC_ENDPOINTS: frozenset[str] = frozenset(
    {
        "",
        "/",
        "/feature",
        "/api/feature",
        "/api/test",
        "/api/example",
        "/api/login",
    }
)


def _is_generic_endpoint(value: object) -> bool:
    text = _coerce_to_string(value).strip()
    if not text:
        return True
    return text.lower() in _LOGIN_GENERIC_ENDPOINTS


def _login_api_spec_template() -> dict[str, Any]:
    request_body = {
        "email": "user@example.com",
        "password": "Passw0rd!",
    }
    response_body = {
        "success": True,
        "message": "로그인 성공",
        "data": {
            "accessToken": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.example.token",
            "tokenType": "Bearer",
            "user": {
                "userId": 1,
                "email": "user@example.com",
                "nickname": "코비",
            },
        },
    }
    request_fields = [
        {
            "name": "email",
            "type": "string",
            "required": True,
            "description": "등록된 사용자 이메일 (@Email Bean Validation 적용)",
            "example": "user@example.com",
        },
        {
            "name": "password",
            "type": "string",
            "required": True,
            "description": "8자 이상 비밀번호 (@NotBlank, @Size(min=8) 적용)",
            "example": "Passw0rd!",
        },
    ]
    response_fields = [
        {
            "name": "success",
            "type": "boolean",
            "required": True,
            "description": "API 처리 성공 여부",
            "example": True,
        },
        {
            "name": "message",
            "type": "string",
            "required": True,
            "description": "결과 메시지",
            "example": "로그인 성공",
        },
        {
            "name": "data.accessToken",
            "type": "string",
            "required": True,
            "description": "JWT 액세스 토큰 (후속 API Authorization 헤더에 사용)",
            "example": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.example.token",
        },
        {
            "name": "data.tokenType",
            "type": "string",
            "required": True,
            "description": "토큰 타입 (Bearer)",
            "example": "Bearer",
        },
        {
            "name": "data.user.userId",
            "type": "long",
            "required": True,
            "description": "사용자 식별자",
            "example": 1,
        },
        {
            "name": "data.user.email",
            "type": "string",
            "required": True,
            "description": "로그인한 사용자 이메일",
            "example": "user@example.com",
        },
        {
            "name": "data.user.nickname",
            "type": "string",
            "required": True,
            "description": "화면 표시용 닉네임",
            "example": "코비",
        },
    ]
    status_codes = [
        {
            "code": 200,
            "description": "로그인 성공",
            "when": "email·password 검증 및 JWT accessToken 발급 성공",
        },
        {
            "code": 400,
            "description": "입력값 오류",
            "when": "email 형식 오류, password 누락, Bean Validation 실패",
        },
        {
            "code": 401,
            "description": "인증 실패",
            "when": "존재하지 않는 계정 또는 비밀번호 불일치",
        },
    ]
    error_responses = [
        {
            "status": 400,
            "code": "VALIDATION_ERROR",
            "message": "입력값이 올바르지 않습니다.",
            "example": {
                "success": False,
                "message": "email must be a well-formed email address",
                "data": None,
            },
        },
        {
            "status": 401,
            "code": "INVALID_CREDENTIALS",
            "message": "이메일 또는 비밀번호가 올바르지 않습니다.",
            "example": {
                "success": False,
                "message": "INVALID_CREDENTIALS",
                "data": None,
            },
        },
    ]
    frontend_notes = [
        "로그인 성공 시 data.accessToken을 secure storage 정책에 맞게 저장한다.",
        "후속 API 호출 시 Authorization: Bearer {accessToken} 헤더를 추가한다.",
        "401 응답 시 로그인 화면으로 이동하고 입력 필드를 초기화한다.",
        "400 응답은 필드별 validation 메시지를 폼에 매핑해 표시한다.",
    ]
    description = (
        "이메일과 비밀번호를 입력받아 사용자를 인증하고 JWT accessToken을 발급하는 로그인 API입니다.\n\n"
        "인증 필요 여부: Bearer Token 불필요 (공개 엔드포인트)\n"
        "Request Headers: Content-Type: application/json\n\n"
        "상태 코드:\n"
        "- 200: 로그인 성공 — accessToken·tokenType·user 정보 반환\n"
        "- 400: 입력값 오류 — email 형식 오류 또는 password 누락\n"
        "- 401: 인증 실패 — 계정 없음 또는 비밀번호 불일치\n\n"
        "프론트 연동 참고:\n"
        "- 성공 시 accessToken 저장 후 Authorization: Bearer {token}으로 후속 API 호출\n"
        "- 401 시 로그인 화면 리다이렉트, 400 시 필드 오류 메시지 표시"
    )
    return {
        "apiName": "로그인 API",
        "method": "POST",
        "endpoint": "/api/auth/login",
        "description": description,
        "authenticationRequired": False,
        "requestHeaders": [
            {
                "name": "Content-Type",
                "required": True,
                "value": "application/json",
                "description": "JSON 요청 본문",
            },
            {
                "name": "Accept",
                "required": False,
                "value": "application/json",
                "description": "JSON 응답 선호",
            },
        ],
        "requestFields": request_fields,
        "responseFields": response_fields,
        "requestBody": request_body,
        "responseBody": response_body,
        "status": 200,
        "statusCodes": status_codes,
        "errorResponses": error_responses,
        "frontendNotes": frontend_notes,
    }


def get_login_api_spec_template() -> dict[str, Any]:
    """로그인 instant baseline / normalizer / fallback 공용 API 명세 템플릿."""

    return copy.deepcopy(_login_api_spec_template())


def build_generic_api_spec_template(
    *,
    api_name: str,
    method: str,
    endpoint: str,
) -> dict[str, Any]:
    """로그인 외 기능 instant baseline용 API 명세 템플릿."""

    success_status = 201 if method.upper() == "POST" else 200
    request_body = {
        "title": "샘플 제목",
        "content": "샘플 내용",
    }
    response_body = {
        "success": True,
        "message": f"{api_name} 처리 성공",
        "data": {
            "id": 1,
            "message": "처리 완료",
        },
    }
    description = (
        f"{api_name} 요청을 처리하는 REST API입니다.\n\n"
        f"인증 필요 여부: Bearer Token 필요 (Authorization: Bearer {'{token}'})\n"
        f"Request Headers: Content-Type: application/json\n\n"
        f"상태 코드:\n"
        f"- {success_status}: 처리 성공\n"
        f"- 400: 입력값 오류\n"
        f"- 401: 인증 필요 또는 토큰 만료\n"
        f"- 409: 비즈니스 규칙 충돌\n\n"
        "프론트 연동 참고:\n"
        "- Authorization 헤더에 accessToken을 포함한다.\n"
        "- 400/409 응답 message를 사용자에게 표시한다."
    )
    return {
        "apiName": api_name,
        "method": method,
        "endpoint": endpoint,
        "description": description,
        "authenticationRequired": True,
        "requestHeaders": [
            {
                "name": "Content-Type",
                "required": True,
                "value": "application/json",
                "description": "JSON 요청 본문",
            },
            {
                "name": "Authorization",
                "required": True,
                "value": "Bearer {accessToken}",
                "description": "로그인 후 발급받은 JWT",
            },
        ],
        "requestFields": [
            {
                "name": "title",
                "type": "string",
                "required": True,
                "description": "요청 제목 또는 식별용 문자열",
                "example": "샘플 제목",
            },
            {
                "name": "content",
                "type": "string",
                "required": True,
                "description": "요청 본문 또는 상세 내용",
                "example": "샘플 내용",
            },
        ],
        "responseFields": [
            {
                "name": "success",
                "type": "boolean",
                "required": True,
                "description": "처리 성공 여부",
                "example": True,
            },
            {
                "name": "message",
                "type": "string",
                "required": True,
                "description": "결과 메시지",
                "example": f"{api_name} 처리 성공",
            },
            {
                "name": "data.id",
                "type": "long",
                "required": True,
                "description": "생성·처리된 리소스 ID",
                "example": 1,
            },
        ],
        "requestBody": request_body,
        "responseBody": response_body,
        "status": success_status,
        "statusCodes": [
            {
                "code": success_status,
                "description": "처리 성공",
                "when": "입력 검증 및 비즈니스 처리 성공",
            },
            {
                "code": 400,
                "description": "입력값 오류",
                "when": "필수 필드 누락 또는 형식 오류",
            },
            {
                "code": 401,
                "description": "인증 실패",
                "when": "토큰 누락·만료·위조",
            },
            {
                "code": 409,
                "description": "비즈니스 충돌",
                "when": "중복 데이터 또는 규칙 위반",
            },
        ],
        "errorResponses": [
            {
                "status": 400,
                "code": "VALIDATION_ERROR",
                "message": "입력값이 올바르지 않습니다.",
                "example": {
                    "success": False,
                    "message": "title must not be blank",
                    "data": None,
                },
            },
            {
                "status": 401,
                "code": "UNAUTHORIZED",
                "message": "인증이 필요합니다.",
                "example": {
                    "success": False,
                    "message": "UNAUTHORIZED",
                    "data": None,
                },
            },
        ],
        "frontendNotes": [
            "API 호출 전 accessToken 유효성을 확인한다.",
            "성공 응답 data.id를 화면 상태 또는 후속 API path variable에 반영한다.",
            "오류 응답 message를 toast/alert로 사용자에게 전달한다.",
        ],
    }


_API_SPEC_DOCUMENTATION_KEYS: tuple[str, ...] = (
    "authenticationRequired",
    "requestHeaders",
    "requestFields",
    "responseFields",
    "statusCodes",
    "errorResponses",
    "frontendNotes",
)


def _is_missing_api_spec_documentation(item: dict[str, Any]) -> bool:
    for key in _API_SPEC_DOCUMENTATION_KEYS:
        value = item.get(key)
        if key == "authenticationRequired":
            continue
        if value in (None, [], {}):
            return True
    return False


def _apply_api_spec_documentation_defaults(
    item: dict[str, Any],
    template: dict[str, Any],
    *,
    index: int,
    changed_fields: list[str],
) -> None:
    prefix = f"apiSpec[{index}]"
    desc = _coerce_to_string(item.get("description")).strip()
    template_desc = _coerce_to_string(template.get("description")).strip()
    if (
        _is_missing_or_blank_str(item.get("description"))
        or len(desc) < len(template_desc) // 2
    ):
        item["description"] = template_desc
        changed_fields.append(f"{prefix}.description")
    if "authenticationRequired" not in item:
        item["authenticationRequired"] = template.get("authenticationRequired", False)
        changed_fields.append(f"{prefix}.authenticationRequired")
    for key in _API_SPEC_DOCUMENTATION_KEYS:
        if key == "authenticationRequired":
            continue
        value = item.get(key)
        if value in (None, [], {}):
            template_value = template.get(key)
            if template_value is not None:
                item[key] = copy.deepcopy(template_value)
                changed_fields.append(f"{prefix}.{key}")


def _default_login_purpose() -> str:
    return "사용자가 email과 password로 시스템에 안전하게 인증한다."


def _default_login_result_description() -> str:
    return "인증 성공 시 accessToken과 사용자 요약 정보를 반환한다."


def _default_login_learning_goals() -> list[str]:
    return [
        "Controller → Service → Repository 계층 흐름을 이해한다.",
        "LoginRequest/LoginResponse DTO 분리 이유를 이해한다.",
        "BCrypt 기반 비밀번호 해시 저장과 검증을 이해한다.",
        "JWT accessToken/tokenType/user 응답 구조와 토큰 발급 흐름을 이해한다.",
        "로그인 실패 시 400/401 응답으로 인증 결과를 일관되게 처리하는 방식을 이해한다.",
    ]


def _default_login_basic_questions() -> list[dict[str, Any]]:
    return [
        {
            "questionId": "Q-login-1",
            "type": "short_answer",
            "question": "로그인 API에서 이메일과 비밀번호를 먼저 검증해야 하는 이유를 설명하시오.",
            "choices": None,
            "answer": "잘못된 요청을 인증 로직으로 넘기지 않고 명확한 오류 응답을 반환하기 위해서다.",
            "explanation": "입력값 검증을 먼저 수행하면 불필요한 DB 조회를 줄이고 실패 원인을 안정적으로 처리할 수 있다.",
            "relatedSection": "requirements",
            "difficulty": "beginner",
        },
        {
            "questionId": "Q-login-2",
            "type": "fill_blank",
            "question": "로그인 성공 시 서버는 보통 accessToken과 tokenType을 포함한 ____를 반환한다.",
            "choices": None,
            "answer": "응답 DTO",
            "explanation": "응답 DTO는 클라이언트가 사용할 토큰과 사용자 요약 정보를 안정된 구조로 전달한다.",
            "relatedSection": "apiSpec",
            "difficulty": "beginner",
        },
        {
            "questionId": "Q-login-3",
            "type": "short_answer",
            "question": "비밀번호를 평문으로 비교하거나 저장하면 안 되는 이유를 설명하시오.",
            "choices": None,
            "answer": "유출 시 원문 비밀번호가 노출되므로 BCrypt 같은 해시로 저장하고 검증해야 한다.",
            "explanation": "단방향 해시와 솔트를 사용하면 저장소 유출 상황에서도 원문 복구 위험을 낮출 수 있다.",
            "relatedSection": "requirements",
            "difficulty": "beginner",
        },
    ]


def _is_poor_choices(value: object) -> bool:
    if value is None:
        return False
    if not isinstance(value, list):
        return True
    stripped = [_coerce_to_string(item).strip() for item in value]
    if stripped == ["A", "B", "C", "D"]:
        return True
    return bool(stripped) and all(len(item) <= 2 for item in stripped)


def _is_poor_short_text(value: object) -> bool:
    text = _coerce_to_string(value).strip()
    return text in {"", "정답", "설명"}


_LOGIN_API_NAME_KOREAN = "로그인 API"


def _looks_like_path(text: str) -> bool:
    s = text.strip()
    if not s:
        return False
    return s.startswith("/") or s.startswith("http://") or s.startswith("https://")


def _is_poor_api_request_body(value: object) -> bool:
    if not isinstance(value, dict) or not value:
        return True
    has_email_or_username = any(
        k in value for k in ("email", "username", "userId", "id")
    )
    has_password = "password" in value
    if has_password and has_email_or_username:
        return False
    keys = {str(k).lower() for k in value.keys()}
    if keys == {"field"} or keys == {"field", "type"}:
        return True
    return not (has_password and has_email_or_username)


def _is_poor_api_response_body(value: object) -> bool:
    if not isinstance(value, dict) or not value:
        return True
    data = value.get("data")
    if isinstance(data, dict):
        if "accessToken" in data or "user" in data:
            return False
    if "accessToken" in value and ("user" in value or "tokenType" in value):
        return False
    return True


def _default_login_requirements_detailed(
    request: FeatureTemplateGenerateRequest | None,
) -> list[dict[str, Any]]:
    return [
        {
            "requirementId": "R-001",
            "name": "로그인 정보 입력",
            "description": "사용자는 email과 password를 입력해 로그인 요청을 보낸다.",
            "inputValue": "email, password",
            "processCondition": "email과 password 모두 비어 있지 않다.",
            "successResult": "요청이 서버로 전달된다.",
            "failureResult": "필수값 누락 시 400 응답을 반환한다.",
            "priority": "HIGH",
            "relatedScreenOrApi": "POST /api/auth/login",
        },
        {
            "requirementId": "R-002",
            "name": "입력값 검증",
            "description": "email 형식과 password 길이를 검증한다.",
            "inputValue": "email format, password length",
            "processCondition": "email은 형식이 유효하고 password는 8자 이상이다.",
            "successResult": "검증 통과 시 사용자 조회 단계로 진행한다.",
            "failureResult": "검증 실패 시 400 응답과 사유 메시지를 반환한다.",
            "priority": "HIGH",
            "relatedScreenOrApi": "POST /api/auth/login",
        },
        {
            "requirementId": "R-003",
            "name": "인증 처리 및 토큰 발급",
            "description": "사용자 조회와 비밀번호 해시 검증을 거쳐 JWT accessToken을 발급한다.",
            "inputValue": "stored password hash, plain password",
            "processCondition": "BCrypt.matches로 해시 비교에 성공한다.",
            "successResult": "200 응답으로 accessToken/tokenType/user 정보를 반환한다.",
            "failureResult": "인증 실패 시 401 응답을 반환한다.",
            "priority": "HIGH",
            "relatedScreenOrApi": "POST /api/auth/login",
        },
    ]


def _default_login_flow_layers() -> list[dict[str, str]]:
    return [
        {"layer": "Client", "role": "로그인 폼 입력 및 API 호출"},
        {"layer": "Controller", "role": "POST /api/auth/login 요청 수신과 입력 DTO 검증"},
        {
            "layer": "Service",
            "role": "사용자 조회, 비밀번호 해시 검증, JWT accessToken 발급",
        },
        {"layer": "Repository", "role": "username/email 기준으로 사용자 정보를 조회"},
        {"layer": "DB", "role": "사용자 계정과 비밀번호 해시 저장"},
        {
            "layer": "Response",
            "role": "accessToken/tokenType/user 정보를 응답으로 반환",
        },
    ]


def _default_login_flow_layers_compact() -> list[dict[str, str]]:
    return [
        {"layer": "Client", "role": "로그인 요청 전송"},
        {"layer": "Controller", "role": "요청 수신·입력 검증"},
        {"layer": "Service", "role": "인증·JWT 발급"},
        {"layer": "DB", "role": "사용자 조회"},
    ]


def _default_login_flow_steps() -> list[str]:
    return [
        "1. 사용자가 email과 password를 입력한다.",
        "2. 클라이언트가 POST /api/auth/login 요청을 보낸다.",
        "3. Controller가 요청 DTO를 검증한다.",
        "4. Service가 사용자 조회 및 비밀번호 해시 검증을 수행한다.",
        "5. 인증 성공 시 JWT accessToken을 발급하고 응답을 반환한다.",
    ]


def _default_login_flow_steps_compact() -> list[str]:
    return [
        "1. POST /api/auth/login 요청 수신",
        "2. 입력 검증 및 사용자 인증",
        "3. JWT accessToken 응답 반환",
    ]


def _default_login_next_recommendations() -> list[dict[str, Any]]:
    return [
        {
            "featureName": "회원가입",
            "reason": "로그인과 짝을 이루는 사용자 생성 흐름을 학습한다.",
            "expectedLearning": "회원 등록 검증과 BCrypt 해시 저장을 익힌다.",
            "priority": 1,
        },
        {
            "featureName": "JWT 인증",
            "reason": "토큰 기반 무상태 인증 패턴을 확장 학습한다.",
            "expectedLearning": "accessToken 발급, 서명 검증, 만료/리프레시 정책을 이해한다.",
            "priority": 2,
        },
        {
            "featureName": "로그아웃",
            "reason": "토큰 무효화와 클라이언트 상태 정리 방식을 학습한다.",
            "expectedLearning": "서버측 블랙리스트, 클라이언트 토큰 제거 전략을 이해한다.",
            "priority": 3,
        },
        {
            "featureName": "권한 관리",
            "reason": "인증된 사용자에 대한 역할/권한 기반 인가를 학습한다.",
            "expectedLearning": "Role 모델링과 인가 필터/인터셉터 적용을 이해한다.",
            "priority": 4,
        },
        {
            "featureName": "비밀번호 재설정",
            "reason": "비밀번호 분실 대응 흐름과 보안 토큰 발급을 학습한다.",
            "expectedLearning": "재설정 토큰 발급/검증과 만료 처리를 이해한다.",
            "priority": 5,
        },
    ]


_KOREAN_SPACE_VARIANT_MAP: dict[str, str] = {
    "회원가입": "회원가입",
    "회원 가입": "회원가입",
    "로그인": "로그인",
    "로그아웃": "로그아웃",
    "로그 아웃": "로그아웃",
    "비밀번호재설정": "비밀번호 재설정",
    "비밀번호 재설정": "비밀번호 재설정",
    "권한관리": "권한 관리",
    "권한 관리": "권한 관리",
    "jwt 인증": "JWT 인증",
    "jwt인증": "JWT 인증",
}


def _next_rec_canonical_key(name: str) -> str:
    base = _coerce_to_string(name).strip()
    if not base:
        return ""
    key = _KOREAN_SPACE_VARIANT_MAP.get(base)
    if key:
        return key.lower()
    return base.replace(" ", "").lower()


def _normalize_next_rec_display_name(name: str) -> str:
    base = _coerce_to_string(name).strip()
    if not base:
        return base
    pretty = _KOREAN_SPACE_VARIANT_MAP.get(base)
    if pretty:
        return pretty
    pretty = _KOREAN_SPACE_VARIANT_MAP.get(base.lower())
    if pretty:
        return pretty
    return base


def _ensure_login_quality_baseline(
    normalized: dict[str, Any],
    request: FeatureTemplateGenerateRequest | None,
    changed_fields: list[str],
) -> None:
    if request is None or not _is_login_feature_request(request):
        return

    overview = normalized.get("overview")
    if isinstance(overview, dict):
        if _is_missing_or_blank_str(overview.get("purpose")) or _is_poor_short_text(
            overview.get("purpose")
        ):
            overview["purpose"] = _default_login_purpose()
            changed_fields.append("overview.purpose[login-default]")
        if _is_missing_or_blank_str(overview.get("resultDescription")) or _is_poor_short_text(
            overview.get("resultDescription")
        ):
            overview["resultDescription"] = _default_login_result_description()
            changed_fields.append("overview.resultDescription[login-default]")
        goals = overview.get("learningGoals")
        if _str_list_effectively_empty(goals) or (
            isinstance(goals, list) and len(goals) < 3
        ):
            overview["learningGoals"] = _default_login_learning_goals()
            changed_fields.append("overview.learningGoals[login-default]")

    login_api = _login_api_spec_template()
    api_specs = normalized.get("apiSpec")
    if not isinstance(api_specs, list) or not api_specs:
        normalized["apiSpec"] = [dict(login_api)]
        changed_fields.append("apiSpec[login-default]")
    else:
        fixed_specs: list[dict[str, Any]] = []
        for index, raw_item in enumerate(api_specs):
            if not isinstance(raw_item, dict):
                continue
            item = dict(raw_item)
            if _is_generic_endpoint(item.get("endpoint")):
                item["endpoint"] = login_api["endpoint"]
                changed_fields.append(f"apiSpec[{index}].endpoint")
            api_name_val = _coerce_to_string(item.get("apiName")).strip()
            if (
                _is_missing_or_blank_str(item.get("apiName"))
                or _looks_like_path(api_name_val)
            ):
                item["apiName"] = _LOGIN_API_NAME_KOREAN
                changed_fields.append(f"apiSpec[{index}].apiName")
            method_val = _coerce_to_string(item.get("method")).strip().upper()
            if not method_val or method_val != "POST":
                item["method"] = "POST"
                changed_fields.append(f"apiSpec[{index}].method")
            if _is_missing_or_blank_str(item.get("description")):
                item["description"] = login_api["description"]
                changed_fields.append(f"apiSpec[{index}].description")
            if _is_poor_api_request_body(item.get("requestBody")):
                item["requestBody"] = dict(login_api["requestBody"])
                changed_fields.append(f"apiSpec[{index}].requestBody")
            if _is_poor_api_response_body(item.get("responseBody")):
                item["responseBody"] = copy.deepcopy(login_api["responseBody"])
                changed_fields.append(f"apiSpec[{index}].responseBody")
            if item.get("status") in (None, "", 0):
                item["status"] = 200
                changed_fields.append(f"apiSpec[{index}].status")
            _apply_api_spec_documentation_defaults(
                item,
                login_api,
                index=index,
                changed_fields=changed_fields,
            )
            fixed_specs.append(item)
        normalized["apiSpec"] = fixed_specs or [dict(login_api)]

    reqs = normalized.get("requirements")
    if not isinstance(reqs, list):
        reqs = []
    fixed_reqs: list[dict[str, Any]] = [dict(item) for item in reqs if isinstance(item, dict)]
    defaults = _default_login_requirements_detailed(request)
    while len(fixed_reqs) < 3:
        fixed_reqs.append(dict(defaults[len(fixed_reqs)]))
        changed_fields.append("requirements[login+pad]")
    if len(fixed_reqs) > 3:
        fixed_reqs = fixed_reqs[:3]
        changed_fields.append("requirements[login-trim]")
    for index, item in enumerate(fixed_reqs):
        default = defaults[min(index, len(defaults) - 1)]
        rel = _coerce_to_string(item.get("relatedScreenOrApi")).strip()
        rel_lower = rel.lower()
        has_login_api_anchor = (
            "/api/auth/login" in rel_lower
            or "logincontroller" in rel_lower
            or "loginservice" in rel_lower
            or "loginrequest" in rel_lower
            or "loginresponse" in rel_lower
        )
        if (
            _is_generic_endpoint(item.get("relatedScreenOrApi"))
            or _is_missing_or_blank_str(item.get("relatedScreenOrApi"))
            or not has_login_api_anchor
        ):
            item["relatedScreenOrApi"] = default["relatedScreenOrApi"]
            changed_fields.append(f"requirements[{index}].relatedScreenOrApi")
        for field in (
            "inputValue",
            "processCondition",
            "successResult",
            "failureResult",
            "description",
            "name",
        ):
            if _is_missing_or_blank_str(item.get(field)):
                item[field] = default[field]
                changed_fields.append(f"requirements[{index}].{field}")
        prio = _coerce_to_string(item.get("priority")).strip().upper()
        if index < 3 and prio not in {"HIGH", "CRITICAL"}:
            item["priority"] = "HIGH"
            changed_fields.append(f"requirements[{index}].priority")
        if _is_missing_or_blank_str(item.get("requirementId")):
            item["requirementId"] = default["requirementId"]
            changed_fields.append(f"requirements[{index}].requirementId")
    normalized["requirements"] = fixed_reqs

    flow = normalized.get("flow")
    if isinstance(flow, dict):
        layers = flow.get("layers")
        if not isinstance(layers, list) or len(layers) < 3:
            flow["layers"] = list(_default_login_flow_layers_compact())
            changed_fields.append("flow.layers[login-default]")
        steps = flow.get("steps")
        if _str_list_effectively_empty(steps) or (
            isinstance(steps, list) and len(steps) < 3
        ):
            flow["steps"] = list(_default_login_flow_steps_compact())
            changed_fields.append("flow.steps[login-default]")
        normalized["flow"] = flow

    questions = normalized.get("basicQuestions")
    if not isinstance(questions, list):
        questions = []
    fixed_questions: list[dict[str, Any]] = [
        dict(item) for item in questions if isinstance(item, dict)
    ]
    question_defaults = _default_login_basic_questions()
    while len(fixed_questions) < 3:
        fixed_questions.append(dict(question_defaults[len(fixed_questions)]))
        changed_fields.append("basicQuestions[login+pad]")
    for index, item in enumerate(fixed_questions):
        default = question_defaults[min(index, len(question_defaults) - 1)]
        if _is_poor_choices(item.get("choices")):
            item["type"] = default["type"]
            item["choices"] = default["choices"]
            changed_fields.append(f"basicQuestions[{index}].choices")
        if _is_poor_short_text(item.get("answer")):
            item["answer"] = default["answer"]
            changed_fields.append(f"basicQuestions[{index}].answer")
        if _is_poor_short_text(item.get("explanation")):
            item["explanation"] = default["explanation"]
            changed_fields.append(f"basicQuestions[{index}].explanation")
        if _is_missing_or_blank_str(item.get("question")):
            item["question"] = default["question"]
            changed_fields.append(f"basicQuestions[{index}].question")
        if _is_missing_or_blank_str(item.get("type")):
            item["type"] = default["type"]
            changed_fields.append(f"basicQuestions[{index}].type")
        if _is_missing_or_blank_str(item.get("relatedSection")):
            item["relatedSection"] = default["relatedSection"]
            changed_fields.append(f"basicQuestions[{index}].relatedSection")
        if _is_missing_or_blank_str(item.get("difficulty")):
            item["difficulty"] = default["difficulty"]
            changed_fields.append(f"basicQuestions[{index}].difficulty")
    normalized["basicQuestions"] = fixed_questions

    recs = normalized.get("nextRecommendations")
    if isinstance(recs, list):
        seen_keys: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for raw_item in recs:
            if not isinstance(raw_item, dict):
                continue
            item = dict(raw_item)
            name = _coerce_to_string(item.get("featureName"))
            key = _next_rec_canonical_key(name)
            if not key or key in seen_keys:
                if key in seen_keys:
                    changed_fields.append("nextRecommendations[dedupe]")
                continue
            seen_keys.add(key)
            pretty = _normalize_next_rec_display_name(name)
            if pretty != name:
                item["featureName"] = pretty
                changed_fields.append("nextRecommendations[normalizeName]")
            deduped.append(item)

        defaults_rec = _default_login_next_recommendations()
        for default_item in defaults_rec:
            if len(deduped) >= 3:
                break
            key = _next_rec_canonical_key(default_item["featureName"])
            if key in seen_keys:
                continue
            seen_keys.add(key)
            deduped.append(dict(default_item))
            changed_fields.append("nextRecommendations[login+pad]")

        for new_priority, item in enumerate(deduped, start=1):
            if item.get("priority") != new_priority:
                item["priority"] = new_priority
                changed_fields.append("nextRecommendations[priorityReset]")
        normalized["nextRecommendations"] = deduped


def _ensure_final_login_defense(
    normalized: dict[str, Any],
    request: FeatureTemplateGenerateRequest | None,
    changed_fields: list[str],
) -> None:
    """로그인+Spring 최종 반환 직전: codeFiles 4종·requirements 최소 보장."""
    if request is None or not _is_java_spring(request) or not _is_login_feature_request(request):
        return

    req_list = normalized.get("requirements")
    if not isinstance(req_list, list) or len(req_list) == 0:
        normalized["requirements"] = _default_login_requirements(request)
        changed_fields.append("requirements[final+default]")

    include_code = getattr(request, "includeCode", None)
    if include_code is None:
        include_code = getattr(request, "include_code", True)
    if include_code is None:
        include_code = True

    if include_code is False:
        normalized["codeFiles"] = []
        return

    files = normalized.get("codeFiles")
    if not isinstance(files, list):
        return

    canon = _canonical_login_spring_four()
    merged: dict[str, dict[str, Any]] = {}
    for it in files:
        if not isinstance(it, dict):
            continue
        raw_fn = str(it.get("fileName", "") or "")
        bn = _basename_java_filename(raw_fn)
        if not bn.endswith(".java"):
            continue
        if "/" in raw_fn or "\\" in raw_fn:
            changed_fields.append("codeFiles[final-guard].fileName-basename")

        fixed = dict(it)
        content = fixed.get("content", "")
        cs = content if isinstance(content, str) else _coerce_to_string(content)
        cs = _normalize_java_package_in_content(cs, _LOGIN_PKG_DEFAULT)
        cs = _normalize_login_dto_accessor_consistency(cs)
        fixed["fileName"] = bn
        fixed["filePath"] = _java_file_path_for(_LOGIN_PKG_DEFAULT, bn)
        fixed["language"] = "java"
        fixed["content"] = cs
        inferred_role = _infer_java_code_file_role(bn)
        if inferred_role:
            fixed["role"] = inferred_role
        merged[bn] = fixed

    for req_fn in _LOGIN_REQUIRED_FILES:
        if req_fn not in merged:
            merged[req_fn] = dict(canon[req_fn])
            changed_fields.append(f"codeFiles[final+].{req_fn}")
            continue
        if req_fn == "LoginResponse.java":
            c = merged[req_fn].get("content", "")
            cs = c if isinstance(c, str) else _coerce_to_string(c)
            if not _login_response_content_valid(cs):
                merged[req_fn] = dict(canon[req_fn])
                changed_fields.append("codeFiles[final~].LoginResponse.java")

    out_list: list[dict[str, Any]] = [dict(merged[r]) for r in _LOGIN_REQUIRED_FILES if r in merged]
    for k in sorted(merged.keys()):
        if k not in _LOGIN_REQUIRED_FILES:
            out_list.append(dict(merged[k]))

    by_bn: dict[str, dict[str, Any]] = {}
    for item in out_list:
        d = dict(item)
        bn2 = _basename_java_filename(str(d.get("fileName", "") or ""))
        if not bn2.endswith(".java"):
            continue
        c2 = d.get("content", "")
        c2s = c2 if isinstance(c2, str) else _coerce_to_string(c2)
        c2s = _normalize_java_package_in_content(c2s, _LOGIN_PKG_DEFAULT)
        c2s = _normalize_login_dto_accessor_consistency(c2s)
        d["fileName"] = bn2
        d["filePath"] = _java_file_path_for(_LOGIN_PKG_DEFAULT, bn2)
        d["language"] = "java"
        d["content"] = c2s
        inferred_role = _infer_java_code_file_role(bn2)
        if inferred_role:
            d["role"] = inferred_role
        by_bn[bn2] = d

    for req_fn in _LOGIN_REQUIRED_FILES:
        if req_fn not in by_bn:
            by_bn[req_fn] = dict(canon[req_fn])
            changed_fields.append(f"codeFiles[final2+].{req_fn}")

    final_out: list[dict[str, Any]] = [dict(by_bn[r]) for r in _LOGIN_REQUIRED_FILES if r in by_bn]
    for k in sorted(by_bn.keys()):
        if k not in _LOGIN_REQUIRED_FILES:
            final_out.append(dict(by_bn[k]))

    for it in final_out:
        fn = str(it.get("fileName", "") or "")
        if "/" in fn or "\\" in fn:
            it["fileName"] = _basename_java_filename(fn)
            c3 = it.get("content", "")
            c3s = c3 if isinstance(c3, str) else _coerce_to_string(c3)
            it["filePath"] = _java_file_path_for(_LOGIN_PKG_DEFAULT, it["fileName"])
            changed_fields.append("codeFiles[final3].fileName")

    normalized["codeFiles"] = final_out


def _normalize_login_spring_boot_codefiles(
    files: list[Any],
    changed_fields: list[str],
) -> list[dict[str, Any]]:
    """로그인 + Spring Boot: fileName·package·역할 검증, 중복 제거, 필수 4파일 보장."""
    canon = _canonical_login_spring_four()
    by_bn: dict[str, dict[str, Any]] = {}
    extras: list[dict[str, Any]] = []

    for raw in files:
        if not isinstance(raw, dict):
            continue
        it = dict(raw)
        raw_fn = str(it.get("fileName", "") or "")
        bn = _basename_java_filename(raw_fn)
        if not bn.endswith(".java"):
            continue
        content = it.get("content", "")
        c = content if isinstance(content, str) else _coerce_to_string(content)
        if "/" in raw_fn.replace("\\", "/"):
            changed_fields.append("codeFiles[].fileName-basename")

        pkg = _extract_java_package(c) or _LOGIN_PKG_DEFAULT
        it["fileName"] = bn
        it["filePath"] = _java_file_path_for(pkg, bn)
        it["language"] = "java"
        it["content"] = c

        if bn == "AuthService.java":
            if _is_controller_like_java(c) or _java_declares_type(c, "LoginController"):
                changed_fields.append("codeFiles[drop].AuthService.java")
                continue
            if "LoginService.java" in by_bn:
                changed_fields.append("codeFiles[drop].AuthService.java")
                continue
            if _login_service_content_valid(c):
                it["fileName"] = "LoginService.java"
                pkg2 = _extract_java_package(c) or _LOGIN_PKG_DEFAULT
                it["filePath"] = _java_file_path_for(pkg2, "LoginService.java")
                by_bn["LoginService.java"] = it
                changed_fields.append("codeFiles[].AuthService->LoginService")
                continue
            changed_fields.append("codeFiles[drop].AuthService.java")
            continue

        if bn in _LOGIN_REQUIRED_FILES:
            if bn in by_bn:
                changed_fields.append(f"codeFiles[dedup].{bn}")
            by_bn[bn] = it
        else:
            extras.append(it)

    extras2: list[dict[str, Any]] = []
    for it in extras:
        bn = str(it.get("fileName", "") or "")
        if bn != "AuthService.java":
            extras2.append(it)
            continue
        c = it.get("content", "")
        c = c if isinstance(c, str) else _coerce_to_string(c)
        if _is_controller_like_java(c) or _java_declares_type(c, "LoginController"):
            changed_fields.append("codeFiles[drop].AuthService.java")
            continue
        if "LoginService.java" in by_bn:
            changed_fields.append("codeFiles[drop].AuthService.java")
            continue
        if _login_service_content_valid(c):
            pkg2 = _extract_java_package(c) or _LOGIN_PKG_DEFAULT
            it["fileName"] = "LoginService.java"
            it["filePath"] = _java_file_path_for(pkg2, "LoginService.java")
            it["content"] = c
            by_bn["LoginService.java"] = it
            changed_fields.append("codeFiles[].AuthService->LoginService")
        else:
            changed_fields.append("codeFiles[drop].AuthService.java")
    extras = extras2

    for bn in list(by_bn.keys()):
        it = by_bn[bn]
        c = it["content"]
        exp = bn[:-5] if bn.endswith(".java") else ""
        if exp and not _java_declares_type(c, exp):
            if bn == "LoginService.java" and _java_declares_type(c, "LoginController"):
                del by_bn[bn]
                changed_fields.append(f"codeFiles[drop].{bn}-wrong-type")
                continue
            if bn in canon:
                by_bn[bn] = dict(canon[bn])
                changed_fields.append(f"codeFiles[replace].{bn}")

    if "LoginController.java" in by_bn:
        if not _login_controller_content_valid(by_bn["LoginController.java"]["content"]):
            by_bn["LoginController.java"] = dict(canon["LoginController.java"])
            changed_fields.append("codeFiles[replace].LoginController.java")

    if "LoginService.java" in by_bn:
        if not _login_service_content_valid(by_bn["LoginService.java"]["content"]):
            by_bn["LoginService.java"] = dict(canon["LoginService.java"])
            changed_fields.append("codeFiles[replace].LoginService.java")

    if "LoginRequest.java" in by_bn:
        if not _login_request_content_valid(by_bn["LoginRequest.java"]["content"]):
            by_bn["LoginRequest.java"] = dict(canon["LoginRequest.java"])
            changed_fields.append("codeFiles[replace].LoginRequest.java")
    if "LoginResponse.java" in by_bn:
        if not _login_response_content_valid(by_bn["LoginResponse.java"]["content"]):
            by_bn["LoginResponse.java"] = dict(canon["LoginResponse.java"])
            changed_fields.append("codeFiles[replace].LoginResponse.java")

    for req in _LOGIN_REQUIRED_FILES:
        if req not in by_bn:
            by_bn[req] = dict(canon[req])
            changed_fields.append(f"codeFiles[+].{req}")

    for _bn, item in by_bn.items():
        cs = item.get("content", "")
        cs = cs if isinstance(cs, str) else _coerce_to_string(cs)
        pkgf = _extract_java_package(cs) or _LOGIN_PKG_DEFAULT
        item["filePath"] = _java_file_path_for(pkgf, str(item.get("fileName", "")))

    for it in extras:
        bn = _basename_java_filename(str(it.get("fileName", "") or ""))
        if bn in _LOGIN_REQUIRED_FILES or bn == "AuthService.java":
            continue
        if bn in by_bn:
            continue
        c2 = it.get("content", "")
        c2s = c2 if isinstance(c2, str) else _coerce_to_string(c2)
        pkg3 = _extract_java_package(c2s) or _LOGIN_PKG_DEFAULT
        it["fileName"] = bn
        it["filePath"] = _java_file_path_for(pkg3, bn)
        it["language"] = "java"
        it["content"] = c2s
        by_bn[bn] = it

    out: list[dict[str, Any]] = []
    for req in _LOGIN_REQUIRED_FILES:
        out.append(dict(by_bn[req]))
    for bn in sorted(x for x in by_bn if x not in _LOGIN_REQUIRED_FILES):
        it = dict(by_bn[bn])
        c = it.get("content", "")
        cs = c if isinstance(c, str) else _coerce_to_string(c)
        if _contains_placeholder(cs):
            changed_fields.append(f"codeFiles[drop].{bn}-placeholder")
            continue
        out.append(it)
    return out


def _java_spring_code_templates(prefix: str) -> list[dict[str, Any]]:
    p = prefix
    lc = f"{p}Controller"
    ls = f"{p}Service"
    lr = f"{p}Request"
    lresp = f"{p}Response"
    return [
        {
            "fileName": f"{lc}.java",
            "role": "REST API 엔드포인트",
            "language": "java",
            "content": f"""package com.example.auth;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/auth")
public class {lc} {{

    private final {ls} authService;

    public {lc}({ls} authService) {{
        this.authService = authService;
    }}

    @PostMapping("/login")
    public ResponseEntity<{lresp}> login(@RequestBody {lr} body) {{
        {lresp} result = authService.login(body.username(), body.password());
        return ResponseEntity.ok(result);
    }}
}}
""",
        },
        {
            "fileName": f"{ls}.java",
            "role": "비즈니스 로직",
            "language": "java",
            "content": f"""package com.example.auth;

import org.springframework.stereotype.Service;

@Service
public class {ls} {{

    private final UserRepository userRepository;

    public {ls}(UserRepository userRepository) {{
        this.userRepository = userRepository;
    }}

    public {lresp} login(String username, String password) {{
        var user = userRepository.findByUsername(username)
                .orElseThrow(() -> new IllegalArgumentException("사용자 없음"));
        if (!user.matchesPassword(password)) {{
            throw new IllegalArgumentException("비밀번호 불일치");
        }}
        return new {lresp}(user.getId(), user.getUsername(), "로그인 성공");
    }}
}}
""",
        },
        {
            "fileName": f"{lr}.java",
            "role": "요청 DTO",
            "language": "java",
            "content": f"""package com.example.auth;

public record {lr}(String username, String password) {{
}}
""",
        },
        {
            "fileName": f"{lresp}.java",
            "role": "응답 DTO",
            "language": "java",
            "content": f"""package com.example.auth;

public record {lresp}(Long userId, String username, String message) {{
}}
""",
        },
        {
            "fileName": "UserEntity.java",
            "role": "영속 엔티티",
            "language": "java",
            "content": """package com.example.auth;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "users")
public class UserEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String username;

    @Column(nullable = false)
    private String passwordHash;

    protected UserEntity() {
    }

    public Long getId() {
        return id;
    }

    public String getUsername() {
        return username;
    }

    public boolean matchesPassword(String rawPassword) {
        return passwordHash != null && rawPassword != null && passwordHash.equals(rawPassword);
    }
}
""",
        },
        {
            "fileName": "UserRepository.java",
            "role": "데이터 접근",
            "language": "java",
            "content": """package com.example.auth;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface UserRepository extends JpaRepository<UserEntity, Long> {
    Optional<UserEntity> findByUsername(String username);
}
""",
        },
    ]


def _default_interview_templates() -> list[dict[str, Any]]:
    return [
        {
            "questionId": "IQ-norm-1",
            "question": (
                "클라이언트가 로그인 요청을 보낸 뒤 서버에서 인증이 완료되기까지의 "
                "HTTP 흐름과 주요 검증 단계를 순서대로 설명하시오."
            ),
            "keyPoints": [
                "요청 본문에서 자격 증명 수신",
                "사용자 조회 및 비밀번호 검증",
                "성공 시 세션 또는 토큰 발급",
                "실패 시 상태 코드와 메시지 정책",
            ],
            "sampleAnswer": (
                "클라이언트는 보통 POST로 사용자명과 비밀번호를 전송한다. "
                "서버는 저장소에서 사용자를 찾고, 저장된 해시와 입력 비밀번호를 "
                "BCrypt 등으로 비교한다. 일치하면 인증 성공으로 간주하고 "
                "세션 쿠키나 JWT access 토큰을 응답에 실어 보낸다. "
                "실패하면 401과 함께 동일한 형태의 오류 본문으로 정보 유출을 줄인다."
            ),
            "relatedSection": "flow",
        },
        {
            "questionId": "IQ-norm-2",
            "question": (
                "동일한 로그인 유스케이스에서 Controller, Service, Repository 계층을 "
                "나눈 이유와 각 계층의 책임 경계를 설명하시오."
            ),
            "keyPoints": [
                "Controller는 HTTP 변환과 입력 검증",
                "Service는 유스케이스와 트랜잭션 경계",
                "Repository는 영속화 쿼리 캡슐화",
                "계층 간 순환 의존 방지",
            ],
            "sampleAnswer": (
                "Controller는 요청과 응답 매핑, 상태 코드 결정, 입력 형식 검증에 집중한다. "
                "Service는 비즈니스 규칙, 사용자 조회, 비밀번호 검증, 예외를 도메인 예외로 "
                "바꾸는 역할을 맡긴다. Repository는 엔티티 로딩과 쿼리를 숨겨 "
                "Service가 영속성 세부사항을 몰라도 되게 한다. 이렇게 나누면 "
                "테스트와 변경 영향 범위를 줄일 수 있다."
            ),
            "relatedSection": "codeFiles",
        },
        {
            "questionId": "IQ-norm-3",
            "question": (
                "로그인 시 비밀번호를 평문으로 저장하지 않고 BCrypt 같은 해시를 "
                "사용하는 이유와 운영 시 주의할 점을 설명하시오."
            ),
            "keyPoints": [
                "DB 유출 시에도 원문 비밀번호 복구가 어렵도록 단방향 해시",
                "솔트와 work factor로 무차별 대입 비용 증가",
                "로그와 예외 메시지에 비밀번호 노출 금지",
                "전송 구간은 TLS로 보호",
            ],
            "sampleAnswer": (
                "BCrypt는 단방향 해시와 솔트를 결합해 레인보우 테이블 공격을 어렵게 한다. "
                "work factor를 올려 연산 비용을 조절할 수 있다. 운영에서는 "
                "절대 평문을 로그에 남기지 않고, 검증 실패 시에도 "
                "사용자 존재 여부를 노출하지 않도록 메시지를 통일하는 것이 중요하다."
            ),
            "relatedSection": "requirements",
        },
    ]


def _default_next_recommendation_rows() -> list[tuple[str, str, str]]:
    return [
        (
            "회원가입",
            "로그인과 짝을 이루는 사용자 생성 흐름으로 비밀번호 해시와 중복 검증을 익힌다.",
            "엔티티 설계, BCrypt 저장, username 중복 검사, 검증 오류 응답 형식 통일.",
        ),
        (
            "JWT 인증",
            "세션 기반에서 벗어나 토큰 기반 무상태 인증 패턴을 확장 학습한다.",
            "액세스 토큰 발급, 서명 검증, 만료와 리프레시 정책, 클레임 설계.",
        ),
        (
            "권한 관리",
            "인증된 사용자에 대해 역할과 권한으로 API 접근을 제한하는 방법을 학습한다.",
            "Role 모델링, 인가 필터 또는 인터셉터, 보호 URL 정책과 테스트 전략.",
        ),
    ]


def _pad_mission_dicts(
    existing: list[dict[str, Any]],
    request: FeatureTemplateGenerateRequest | None,
    need: int,
) -> list[dict[str, Any]]:
    out = list(existing)
    diff = _default_mission_difficulty(request)
    n = len(out)
    idx = 0
    while len(out) < need:
        idx += 1
        mid = n + idx
        out.append(
            {
                "missionId": f"auto-mission-{mid}",
                "title": f"구현 미션 {idx}",
                "description": (
                    "미션 목표: 요구사항에 맞는 핵심 로직과 예외 경로를 구현하고 "
                    "단위 검증으로 동작을 확인한다."
                ),
                "missionType": "implementation",
                "requirements": list(_DEFAULT_MISSION_REQUIREMENTS),
                "successCriteria": list(_DEFAULT_MISSION_SUCCESS),
                "relatedRequirements": [],
                "difficulty": diff,
            }
        )
    return out


def _apply_post_normalize_quality(
    normalized: dict[str, Any],
    request: FeatureTemplateGenerateRequest | None,
    changed_fields: list[str],
) -> None:
    """placeholder 제거, 최소 개수 보장(include 플래그 존중)."""
    inc_code = request is None or request.includeCode
    inc_miss = request is None or request.includeMissions
    inc_iv = request is None or request.includeInterview

    if inc_code:
        files = normalized.get("codeFiles")
        if isinstance(files, list):
            if (
                request is not None
                and _is_java_spring(request)
                and _is_login_feature_request(request)
            ):
                normalized["codeFiles"] = _normalize_login_spring_boot_codefiles(
                    files,
                    changed_fields,
                )
            else:
                prefix = _java_class_prefix(request)
                use_java = request is None or request.language.lower() == "java"
                templates = _java_spring_code_templates(prefix) if use_java else []
                by_name = {str(t["fileName"]): t for t in templates}
                seen: set[str] = set()
                new_list: list[dict[str, Any]] = []
                for index, raw_item in enumerate(files):
                    if not isinstance(raw_item, dict):
                        continue
                    item = dict(raw_item)
                    fn = str(item.get("fileName", "") or f"file-{index}.java")
                    seen.add(fn)
                    content = item.get("content", "")
                    cstr = content if isinstance(content, str) else _coerce_to_string(content)
                    if _contains_placeholder(cstr):
                        tpl = by_name.get(fn) if by_name else None
                        if tpl is None and templates:
                            tpl = templates[0]
                        if tpl is not None:
                            item["content"] = tpl["content"]
                            if use_java and _is_java_spring(request) and fn not in by_name:
                                item["fileName"] = tpl["fileName"]
                                item["role"] = tpl["role"]
                                item["language"] = "java"
                        else:
                            lang = (
                                (request.language or "python").lower()
                                if request is not None
                                else "python"
                            )
                            item["content"] = (
                                f"# {fn}\n"
                                "def run() -> None:\n"
                                "    return None\n"
                            )
                            item["language"] = lang
                        changed_fields.append(f"codeFiles[{index}].content")
                    elif not isinstance(item.get("content"), str):
                        item["content"] = cstr
                    new_list.append(item)
                if len(new_list) < 3:
                    if templates:
                        for tpl in templates:
                            if len(new_list) >= 3:
                                break
                            if tpl["fileName"] not in seen:
                                new_list.append(dict(tpl))
                                seen.add(str(tpl["fileName"]))
                                changed_fields.append(f"codeFiles[+].{tpl['fileName']}")
                    else:
                        pad_i = len(new_list)
                        while len(new_list) < 3:
                            new_list.append(
                                {
                                    "fileName": f"module_{pad_i}.py",
                                    "role": "supporting module",
                                    "language": (request.language if request else "python").lower(),
                                    "content": (
                                        f"# module {pad_i}\n"
                                        f"def step_{pad_i}() -> int:\n"
                                        f"    return {pad_i}\n"
                                    ),
                                }
                            )
                            pad_i += 1
                            changed_fields.append(f"codeFiles[+].module_{pad_i - 1}.py")
                normalized["codeFiles"] = new_list

    if inc_miss:
        missions = normalized.get("missions")
        if isinstance(missions, list):
            mlist = [dict(x) for x in missions if isinstance(x, dict)]
            if len(mlist) < 2:
                normalized["missions"] = _pad_mission_dicts(mlist, request, 2)
                changed_fields.append("missions[+pad]")

    if inc_iv:
        iv = normalized.get("interviewQuestions")
        if isinstance(iv, list):
            iv_list: list[dict[str, Any]] = []
            templates_iv = _default_interview_templates()
            for index, raw_item in enumerate(iv):
                if not isinstance(raw_item, dict):
                    continue
                item = dict(raw_item)
                if _interview_item_has_placeholder(item):
                    tpl = templates_iv[min(index, len(templates_iv) - 1)]
                    item.update(
                        {
                            "questionId": tpl["questionId"],
                            "question": tpl["question"],
                            "keyPoints": list(tpl["keyPoints"]),
                            "sampleAnswer": tpl["sampleAnswer"],
                            "relatedSection": tpl["relatedSection"],
                        }
                    )
                    changed_fields.append(f"interviewQuestions[{index}]")
                iv_list.append(item)
            t_idx = 0
            while len(iv_list) < 3:
                tpl = templates_iv[t_idx % len(templates_iv)]
                t_idx += 1
                dup = dict(tpl)
                dup["questionId"] = f"{tpl['questionId']}-pad-{t_idx}"
                iv_list.append(dup)
                changed_fields.append("interviewQuestions[+pad]")
            normalized["interviewQuestions"] = iv_list

    _ensure_login_quality_baseline(normalized, request, changed_fields)

    nxt = normalized.get("nextRecommendations")
    if not isinstance(nxt, list):
        nxt = []
    rows = _default_next_recommendation_rows()
    out_next: list[dict[str, Any]] = []
    for idx, raw_item in enumerate(nxt):
        if not isinstance(raw_item, dict):
            continue
        item = dict(raw_item)
        fn0 = _coerce_to_string(item.get("featureName", "")).strip()
        rs0 = _coerce_to_string(item.get("reason", "")).strip()
        el0 = _coerce_to_string(item.get("expectedLearning", "")).strip()
        row = rows[min(idx, len(rows) - 1)]
        if not fn0 or _contains_placeholder(fn0):
            item["featureName"] = row[0]
            changed_fields.append(f"nextRecommendations[{idx}].featureName")
        else:
            item["featureName"] = fn0
        if not rs0 or _contains_placeholder(rs0):
            item["reason"] = row[1]
            changed_fields.append(f"nextRecommendations[{idx}].reason")
        else:
            item["reason"] = rs0
        if not el0 or _contains_placeholder(el0):
            item["expectedLearning"] = row[2]
            changed_fields.append(f"nextRecommendations[{idx}].expectedLearning")
        else:
            item["expectedLearning"] = el0
        pr = item.get("priority", idx + 1)
        try:
            item["priority"] = int(pr)
        except (TypeError, ValueError):
            item["priority"] = idx + 1
        out_next.append(item)

    pri = max((int(x.get("priority", 0)) for x in out_next), default=0) + 1
    r = 0
    while len(out_next) < 3:
        name, reason, learn = rows[r % len(rows)]
        r += 1
        if any(str(x.get("featureName")) == name for x in out_next):
            continue
        out_next.append(
            {
                "featureName": name,
                "reason": reason,
                "expectedLearning": learn,
                "priority": pri,
            }
        )
        pri += 1
        changed_fields.append("nextRecommendations[+pad]")
    normalized["nextRecommendations"] = out_next


def normalize_feature_template_payload(
    payload: dict,
    request: FeatureTemplateGenerateRequest | None = None,
) -> dict:
    """LLM 응답에서 자주 흔들리는 타입만 Pydantic 검증 전에 보정한다."""
    if not isinstance(payload, dict):
        return payload

    normalized = dict(payload)
    changed_fields: list[str] = []

    default_related = _default_requirement_related_screen_or_api(request)

    requirements = normalized.get("requirements")
    if isinstance(requirements, list):
        normalized_requirements = []
        for index, item in enumerate(requirements):
            if not isinstance(item, dict):
                continue

            normalized_item = _normalize_string_fields(
                item,
                _TOP_LEVEL_STRING_FIELDS["requirements"],
                f"requirements[{index}]",
                changed_fields,
            )
            priority = normalized_item.get("priority")
            if isinstance(priority, int):
                normalized_item["priority"] = _PRIORITY_NUMBER_MAP.get(
                    priority,
                    str(priority),
                )
                changed_fields.append(f"requirements[{index}].priority")
            elif isinstance(priority, str) and priority.strip().isdigit():
                normalized_item["priority"] = _PRIORITY_NUMBER_MAP.get(
                    int(priority.strip()),
                    priority,
                )
                changed_fields.append(f"requirements[{index}].priority")
            elif priority is not None and not isinstance(priority, str):
                normalized_item["priority"] = str(priority)
                changed_fields.append(f"requirements[{index}].priority")
            if _is_missing_or_blank_str(normalized_item.get("priority")):
                normalized_item["priority"] = "MEDIUM"
                changed_fields.append(f"requirements[{index}].priority")
            related = normalized_item.get("relatedScreenOrApi")
            if _is_missing_or_blank_str(related):
                normalized_item["relatedScreenOrApi"] = default_related
                changed_fields.append(f"requirements[{index}].relatedScreenOrApi")
            normalized_requirements.append(normalized_item)
        normalized["requirements"] = normalized_requirements

    api_specs = normalized.get("apiSpec")
    if isinstance(api_specs, list):
        normalized_api_specs = []
        for index, item in enumerate(api_specs):
            if not isinstance(item, dict):
                continue

            normalized_item = _normalize_string_fields(
                item,
                _TOP_LEVEL_STRING_FIELDS["apiSpec"],
                f"apiSpec[{index}]",
                changed_fields,
            )
            status = normalized_item.get("status")
            if isinstance(status, str):
                match = re.search(r"\d{3}", status)
                if match:
                    normalized_item["status"] = int(match.group())
                    changed_fields.append(f"apiSpec[{index}].status")
                else:
                    logger.warning(
                        "Feature template normalization skipped: field=apiSpec[%s].status reason=unparseable",
                        index,
                    )
            normalized_api_specs.append(normalized_item)
        normalized["apiSpec"] = normalized_api_specs

    flow = normalized.get("flow")
    if isinstance(flow, dict):
        normalized_flow = dict(flow)
        normalized_flow = _normalize_string_list_field(
            normalized_flow,
            "steps",
            "flow",
            changed_fields,
        )
        layers = normalized_flow.get("layers")
        if isinstance(layers, list):
            normalized_layers = []
            for index, item in enumerate(layers):
                if isinstance(item, dict):
                    normalized_layers.append(
                        _normalize_string_fields(
                            item,
                            _TOP_LEVEL_STRING_FIELDS["flow.layers"],
                            f"flow.layers[{index}]",
                            changed_fields,
                        )
                    )
            normalized_flow["layers"] = normalized_layers
        normalized["flow"] = normalized_flow

    missions = normalized.get("missions")
    if isinstance(missions, list):
        normalized_missions = []
        for index, item in enumerate(missions):
            if not isinstance(item, dict):
                continue

            normalized_item = _normalize_string_fields(
                item,
                _TOP_LEVEL_STRING_FIELDS["missions"],
                f"missions[{index}]",
                changed_fields,
            )
            if (
                "relatedRequirements" not in normalized_item
                or normalized_item.get("relatedRequirements") is None
            ):
                normalized_item["relatedRequirements"] = []
                changed_fields.append(f"missions[{index}].relatedRequirements")
            for field in _STRING_LIST_FIELDS["missions"]:
                normalized_item = _normalize_string_list_field(
                    normalized_item,
                    field,
                    f"missions[{index}]",
                    changed_fields,
                )

            hints_raw = normalized_item.pop("hints", None)
            goal_raw = normalized_item.pop("goal", None)
            hint_raw = normalized_item.pop("hint", None)

            goal_s = _coerce_to_string(goal_raw).strip() if goal_raw is not None else ""
            hints_parts = _mission_hints_parts(hints_raw, hint_raw)

            mission_type = normalized_item.get("missionType")
            if _is_missing_or_blank_str(mission_type):
                normalized_item["missionType"] = "implementation"
                changed_fields.append(f"missions[{index}].missionType")
            elif not isinstance(mission_type, str):
                normalized_item["missionType"] = str(mission_type)
                changed_fields.append(f"missions[{index}].missionType")

            goal_consumed = False
            if _str_list_effectively_empty(normalized_item.get("requirements")):
                merged: list[str] = []
                if goal_s:
                    merged.append(goal_s)
                    goal_consumed = True
                for h in hints_parts:
                    if h not in merged:
                        merged.append(h)
                if not merged:
                    merged = list(_DEFAULT_MISSION_REQUIREMENTS)
                normalized_item["requirements"] = merged
                changed_fields.append(f"missions[{index}].requirements")

            if _str_list_effectively_empty(normalized_item.get("successCriteria")):
                if goal_s and not goal_consumed:
                    normalized_item["successCriteria"] = [goal_s]
                else:
                    normalized_item["successCriteria"] = list(_DEFAULT_MISSION_SUCCESS)
                changed_fields.append(f"missions[{index}].successCriteria")

            default_diff = _default_mission_difficulty(request)
            normalized_item.setdefault("difficulty", default_diff)
            diff = normalized_item.get("difficulty")
            if diff is None or (isinstance(diff, str) and not diff.strip()):
                normalized_item["difficulty"] = default_diff
                changed_fields.append(f"missions[{index}].difficulty")
            elif isinstance(diff, str):
                dlow = diff.strip().lower()
                if dlow not in _DIFFICULTY_VALID:
                    normalized_item["difficulty"] = default_diff
                    changed_fields.append(f"missions[{index}].difficulty")
            else:
                normalized_item["difficulty"] = str(diff)
                if str(normalized_item["difficulty"]).lower() not in _DIFFICULTY_VALID:
                    normalized_item["difficulty"] = default_diff
                    changed_fields.append(f"missions[{index}].difficulty")

            normalized_missions.append(normalized_item)
        normalized["missions"] = normalized_missions

    overview = normalized.get("overview")
    if isinstance(overview, dict):
        normalized_overview = _normalize_string_fields(
            overview,
            _TOP_LEVEL_STRING_FIELDS["overview"],
            "overview",
            changed_fields,
        )
        for field in _STRING_LIST_FIELDS["overview"]:
            normalized_overview = _normalize_string_list_field(
                normalized_overview,
                field,
                "overview",
                changed_fields,
            )
        normalized["overview"] = normalized_overview

    for section in ("codeFiles", "basicQuestions", "interviewQuestions", "nextRecommendations"):
        items = normalized.get(section)
        if not isinstance(items, list):
            continue
        normalized_items = []
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            normalized_item = _normalize_string_fields(
                item,
                _TOP_LEVEL_STRING_FIELDS[section],
                f"{section}[{index}]",
                changed_fields,
            )
            for field in _STRING_LIST_FIELDS.get(section, ()):
                normalized_item = _normalize_string_list_field(
                    normalized_item,
                    field,
                    f"{section}[{index}]",
                    changed_fields,
                )
            normalized_items.append(normalized_item)
        normalized[section] = normalized_items

    _apply_post_normalize_quality(normalized, request, changed_fields)
    _apply_spring_boot_login_quality_guard(normalized, request, changed_fields)
    _ensure_final_login_defense(normalized, request, changed_fields)

    if changed_fields:
        logger.info(
            "Feature template LLM payload normalized: fields=%s",
            ",".join(changed_fields),
        )

    return normalized


def _default_overview(request: FeatureTemplateGenerateRequest | None) -> dict[str, Any]:
    name = ""
    if request is not None:
        name = (request.featureName or "").strip()
    return {
        "featureName": name,
        "purpose": "",
        "useCases": [],
        "resultDescription": "",
        "techStack": [],
        "learningGoals": [],
    }


def _ensure_list_of_dicts(value: object) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        return []
    return [x for x in value if isinstance(x, dict)]


def _ensure_flow(value: object) -> dict[str, Any]:
    if isinstance(value, list):
        return {"steps": [_coerce_to_string(x) for x in value], "layers": []}
    if not isinstance(value, dict):
        return {"steps": [], "layers": []}
    raw = dict(value)
    steps = raw.get("steps", [])
    if not isinstance(steps, list):
        steps = [_coerce_to_string(steps)] if steps is not None else []
    else:
        steps = [_coerce_to_string(s) for s in steps]
    layers = raw.get("layers", [])
    if not isinstance(layers, list):
        layers = []
    clean_layers: list[dict[str, Any]] = []
    for item in layers:
        if isinstance(item, dict):
            clean_layers.append(item)
    return {"steps": steps, "layers": clean_layers}


def _remap_top_level_keys(data: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, val in data.items():
        if key == "code_view":
            continue
        canon = _TOP_LEVEL_ALIASES.get(key, key)
        out[canon] = val
    if "code_view" in data and "codeFiles" not in out:
        cv = data["code_view"]
        if isinstance(cv, dict) and isinstance(cv.get("files"), list):
            out["codeFiles"] = _ensure_list_of_dicts(cv["files"])
        elif isinstance(cv, list):
            out["codeFiles"] = _ensure_list_of_dicts(cv)
        elif isinstance(cv, dict):
            out["codeFiles"] = []
    return out


class FeatureTemplateNormalizer:
    """9개 top-level 섹션을 항상 채운 뒤 타입 보정까지 수행한다."""

    @staticmethod
    def normalize(
        raw: object,
        request: FeatureTemplateGenerateRequest | None = None,
    ) -> dict[str, Any]:
        if not isinstance(raw, dict):
            raw_dict: dict[str, Any] = {}
        else:
            raw_dict = dict(raw)

        remapped = _remap_top_level_keys(raw_dict)

        overview_base = _default_overview(request)
        overview_src = remapped.get("overview")
        overview: dict[str, Any]
        if isinstance(overview_src, dict):
            overview = {**overview_base, **overview_src}
        else:
            overview = dict(overview_base)

        requirements = _ensure_list_of_dicts(remapped.get("requirements"))
        flow = _ensure_flow(remapped.get("flow"))
        api_spec = _ensure_list_of_dicts(remapped.get("apiSpec"))
        code_files = _ensure_list_of_dicts(remapped.get("codeFiles"))
        basic_questions = _ensure_list_of_dicts(remapped.get("basicQuestions"))
        missions = _ensure_list_of_dicts(remapped.get("missions"))
        interview_questions = _ensure_list_of_dicts(remapped.get("interviewQuestions"))
        next_recommendations = _ensure_list_of_dicts(remapped.get("nextRecommendations"))

        if request is not None:
            if not request.includeCode:
                code_files = []
            if not request.includeMissions:
                missions = []
            if not request.includeInterview:
                interview_questions = []

        merged: dict[str, Any] = {
            "overview": overview,
            "requirements": requirements,
            "flow": flow,
            "apiSpec": api_spec,
            "codeFiles": code_files,
            "basicQuestions": basic_questions,
            "missions": missions,
            "interviewQuestions": interview_questions,
            "nextRecommendations": next_recommendations,
        }
        once = normalize_feature_template_payload(merged, request)
        return normalize_feature_template_payload(dict(once), request)

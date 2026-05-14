"""기능템플릿 LLM/fallback dict → FeatureTemplateData용 안전 구조 보정."""

from __future__ import annotations

import logging
import re
from typing import Any

from app.models.enums import DifficultyLevel
from app.schemas.feature_template import FeatureTemplateGenerateRequest

__all__ = [
    "FeatureTemplateNormalizer",
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
    return (
        "class LoginService" in content
        and "@Service" in content
        and "LoginResponse" in content
        and "login" in content
        and "LoginRequest" in content
    )


def _login_request_content_valid(content: str) -> bool:
    if _contains_placeholder(content):
        return False
    return ("record LoginRequest" in content or "class LoginRequest" in content) and (
        "username" in content and "password" in content
    )


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
            "role": "REST API 엔드포인트",
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
            "role": "비즈니스 로직",
            "language": "java",
            "content": f"""package {pkg};

import org.springframework.stereotype.Service;

@Service
public class LoginService {{

    public LoginResponse login(LoginRequest request) {{
        String username = request.username();
        String password = request.password();
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

public record LoginRequest(String username, String password) {{
}}
""",
        },
        "LoginResponse.java": {
            "fileName": "LoginResponse.java",
            "filePath": _java_file_path_for(pkg, "LoginResponse.java"),
            "role": "응답 DTO",
            "language": "java",
            "content": f"""package {pkg};

public record LoginResponse(String accessToken, String tokenType, String username) {{
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
        pkg = _extract_java_package(cs) or _LOGIN_PKG_DEFAULT
        fixed["fileName"] = bn
        fixed["filePath"] = _java_file_path_for(pkg, bn)
        fixed["language"] = "java"
        fixed["content"] = cs
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
        pkg2 = _extract_java_package(c2s) or _LOGIN_PKG_DEFAULT
        d["fileName"] = bn2
        d["filePath"] = _java_file_path_for(pkg2, bn2)
        d["language"] = "java"
        d["content"] = c2s
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
            pkg3 = _extract_java_package(c3s) or _LOGIN_PKG_DEFAULT
            it["filePath"] = _java_file_path_for(pkg3, it["fileName"])
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

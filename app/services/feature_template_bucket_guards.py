"""기능템플릿 feature bucket별 canonical baseline 및 quality guard."""

from __future__ import annotations

import re
from typing import Any, Callable

from app.schemas.feature_template import FeatureTemplateGenerateRequest

__all__ = [
    "BUCKETS_SKIP_LEGACY_LOGIN_BASELINE",
    "apply_feature_bucket_guards",
    "build_bucket_prompt_constraints",
    "detect_feature_template_bucket",
    "should_skip_legacy_java_login_baseline",
]

LOGIN_BUCKET = "login"
SIGNUP_BUCKET = "signup"
CRUD_BUCKET = "crud"
JWT_AUTH_BUCKET = "jwt_auth"
GENERIC_BUCKET = "generic"

# login bucket 전용 legacy `_java_spring_code_templates`(AppController/login baseline) 주입을
# 건너뛰는 bucket. jwt_auth는 AuthController·POST /api/auth/login을 canonical에 포함하며,
# signup/crud/generic과 legacy login baseline을 공유하지 않는다.
BUCKETS_SKIP_LEGACY_LOGIN_BASELINE = frozenset(
    {SIGNUP_BUCKET, CRUD_BUCKET, JWT_AUTH_BUCKET, GENERIC_BUCKET}
)


def should_skip_legacy_java_login_baseline(bucket: str) -> bool:
    """login bucket이 아닌 bucket guard 대상에서 legacy login baseline 템플릿 주입을 생략."""

    return bucket in BUCKETS_SKIP_LEGACY_LOGIN_BASELINE

_SIGNUP_NAMES = frozenset(
    {"회원가입", "signup", "sign up", "sign-up", "register", "registration", "가입"}
)
_CRUD_NAMES = frozenset(
    {"게시글 crud", "게시글", "게시판", "post crud", "posts", "board", "product crud"}
)
_JWT_NAMES = frozenset({"jwt 인증", "jwt인증", "jwt authentication", "token auth"})
_LOGIN_NAMES = frozenset({"로그인", "login", "sign in", "signin"})

_AUTH_PKG = "com.example.auth"
_POST_PKG = "com.example.post"
_SECURITY_PKG = "com.example.security"


def detect_feature_template_bucket(
    feature_name: str | None,
    framework: str | None = None,
) -> str:
    raw = (feature_name or "").strip()
    if not raw:
        return "generic"
    fn = raw.lower()
    if fn in _LOGIN_NAMES or raw in ("로그인", "Login"):
        return LOGIN_BUCKET
    if fn in _SIGNUP_NAMES or "회원가입" in raw or "signup" in fn or "register" in fn:
        return SIGNUP_BUCKET
    if fn in _CRUD_NAMES or "crud" in fn or "게시글" in raw:
        return CRUD_BUCKET
    if fn in _JWT_NAMES or ("jwt" in fn and "인증" in raw) or fn == "jwt":
        return JWT_AUTH_BUCKET
    if "jwt" in fn and ("auth" in fn or "인증" in raw or "token" in fn):
        return JWT_AUTH_BUCKET
    return GENERIC_BUCKET


def _java_file_path(package: str, file_name: str) -> str:
    rel = package.replace(".", "/") + "/" + file_name
    return f"src/main/java/{rel}"


def _basename(name: str) -> str:
    s = (name or "").strip().replace("\\", "/")
    if "/" in s:
        s = s.rsplit("/", 1)[-1]
    if s and not s.endswith(".java"):
        s = f"{s}.java"
    return s


_JAVA_CLASS_FILE_PATTERN = re.compile(r"^[A-Z][A-Za-z0-9_]*\.java$")


def _is_valid_java_codefile_name(file_name: str) -> bool:
    """Java Spring Boot codeFiles fileName 규칙 검사."""

    bn = _basename(file_name)
    if not bn.endswith(".java"):
        return False
    low = bn.lower()
    if ".py" in low:
        return False
    if low.startswith("module_") and ".py" in low:
        return False
    return bool(_JAVA_CLASS_FILE_PATTERN.match(bn))


def _java_codefile_path_matches_filename(item: dict[str, Any]) -> bool:
    fn = _basename(str(item.get("fileName", "") or ""))
    fp = str(item.get("filePath") or "").replace("\\", "/")
    if not fp.strip():
        return True
    return fp.endswith(f"/{fn}") or fp.endswith(fn)


def _java_codefile_class_matches_filename(item: dict[str, Any]) -> bool:
    fn = _basename(str(item.get("fileName", "") or ""))
    if not fn.endswith(".java"):
        return True
    class_name = fn[:-5]
    content = str(item.get("content", "") or "")
    if not content.strip():
        return True
    declared = _extract_public_class(content)
    if declared is None:
        return True
    return declared == class_name


def _should_drop_java_codefile(raw: dict[str, Any], drop_patterns: tuple[str, ...]) -> bool:
    """비정상 fileName·경로·public class 불일치·bucket 무관 LLM 찌꺼기 제거."""

    bn = _basename(str(raw.get("fileName", "") or ""))
    if not bn:
        return True
    if not _is_valid_java_codefile_name(bn):
        return True
    if any(p.lower() in bn.lower() for p in drop_patterns):
        return True
    if not _java_codefile_path_matches_filename(raw):
        return True
    content = str(raw.get("content", "") or "")
    if content.strip() and not _java_codefile_class_matches_filename(raw):
        return True
    return False


def _extract_public_class(content: str) -> str | None:
    m = re.search(r"\b(?:class|record|interface)\s+(\w+)", content)
    return m.group(1) if m else None


def _extract_package(content: str) -> str | None:
    m = re.search(r"^\s*package\s+([\w.]+)\s*;", content, re.MULTILINE)
    return m.group(1) if m else None


def _set_package(content: str, package: str) -> str:
    if re.search(r"^\s*package\s+[\w.]+\s*;", content, re.MULTILINE):
        return re.sub(
            r"^\s*package\s+[\w.]+\s*;",
            f"package {package};",
            content,
            count=1,
            flags=re.MULTILINE,
        )
    return f"package {package};\n\n{content.lstrip()}"


def _set_public_class(content: str, class_name: str) -> str:
    if re.search(rf"\b(?:class|record|interface)\s+{re.escape(class_name)}\b", content):
        return content
    replaced = re.sub(
        r"\b(?:public\s+)?(?:class|record|interface)\s+\w+",
        f"public class {class_name}",
        content,
        count=1,
    )
    if replaced != content:
        return replaced
    pkg = _extract_package(content) or "com.example.app"
    return f"package {pkg};\n\npublic class {class_name} {{\n}}\n"


def align_java_codefile_entry(
    item: dict[str, Any],
    *,
    package: str,
    canonical_by_name: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """fileName/filePath/content public class/package 일치 보정."""

    out = dict(item)
    bn = _basename(str(out.get("fileName", "") or ""))
    if not bn.endswith(".java"):
        return out
    class_name = bn[:-5]
    out["fileName"] = bn
    out["filePath"] = _java_file_path(package, bn)
    out["language"] = "java"

    content = out.get("content", "")
    cstr = content if isinstance(content, str) else str(content or "")
    canon = (canonical_by_name or {}).get(bn)
    if canon and isinstance(canon.get("content"), str):
        if _content_needs_canonical_replace(cstr, class_name, bn):
            out["content"] = canon["content"]
            if canon.get("role"):
                out["role"] = canon["role"]
            pkg = _extract_package(canon["content"]) or package
            out["filePath"] = _java_file_path(pkg, bn)
            return out

    cstr = _set_package(cstr, package)
    cstr = _set_public_class(cstr, class_name)
    declared = _extract_public_class(cstr)
    if declared != class_name and canon and isinstance(canon.get("content"), str):
        out["content"] = canon["content"]
        out["filePath"] = _java_file_path(_extract_package(canon["content"]) or package, bn)
    else:
        out["content"] = cstr
    return out


def _content_needs_canonical_replace(content: str, class_name: str, file_name: str) -> bool:
    if not content or not content.strip():
        return True
    declared = _extract_public_class(content)
    if declared and declared != class_name:
        return True
    low = content.lower()
    if file_name.startswith("Signup") and any(
        x in low for x in ("/login", "login(", "loginrequest")
    ):
        return True
    if file_name.startswith("Post") and any(
        x in low for x in ("/api/auth/login", "userrepository", "login(")
    ):
        return True
    if file_name.startswith("Jwt") and "jwtcontroller" in low.replace(" ", ""):
        return True
    # AuthController / LoginRequest / LoginResponse (jwt_auth bucket)는
    # POST /api/auth/login endpoint를 canonical에 포함하므로 여기서 금지하지 않는다.
    if file_name in ("AppController.java", "CRUDController.java", "JWTController.java"):
        return True
    return False


def _text_has_any(text: str, needles: tuple[str, ...]) -> bool:
    low = text.lower()
    return any(n.lower() in low for n in needles)


def _payload_has_forbidden(normalized: dict[str, Any], needles: tuple[str, ...]) -> bool:
    parts: list[str] = []
    for key in ("requirements", "apiSpec", "basicQuestions", "missions", "interviewQuestions"):
        items = normalized.get(key)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            for field in item.values():
                if isinstance(field, str):
                    parts.append(field)
                elif isinstance(field, list):
                    parts.extend(str(x) for x in field if x is not None)
    flow = normalized.get("flow")
    if isinstance(flow, dict):
        for step in flow.get("steps") or []:
            parts.append(str(step))
        for layer in flow.get("layers") or []:
            if isinstance(layer, dict):
                parts.append(str(layer.get("role", "")))
    files = normalized.get("codeFiles")
    if isinstance(files, list):
        for f in files:
            if isinstance(f, dict):
                parts.append(str(f.get("content", "")))
                parts.append(str(f.get("fileName", "")))
    blob = "\n".join(parts)
    return _text_has_any(blob, needles)


_SIGNUP_FORBIDDEN = (
    "/api/auth/login",
    "LoginRequest",
    "LoginResponse",
    "AppController",
    "AppService",
    "AppRequest",
    "@PostMapping(\"/login\")",
    "login(",
)
_CRUD_FORBIDDEN = (
    "/api/auth/login",
    "UserRepository",
    "AppController",
    "CRUDController",
    "CRUDService",
    "CRUDRequest",
    "login(",
    "username",
    "password",
)
_JWT_FORBIDDEN = ("JWTController", "AppController")
_JWT_FORBIDDEN_API_ENDPOINTS = ("/api/auth/signup",)
_SIGNUP_FORBIDDEN_API_ENDPOINTS = (
    "/api/auth/login",
    "/api/users/me",
    "/api/posts",
)
_CRUD_FORBIDDEN_API_ENDPOINTS = (
    "/api/auth/login",
    "/api/auth/signup",
    "/api/users/me",
)
_GENERIC_FORBIDDEN_API_ENDPOINTS = (
    "/api/auth/login",
    "/api/auth/signup",
    "/api/users/me",
    "/api/posts",
)


def _api_spec_key(item: dict[str, Any]) -> tuple[str, str]:
    return (
        str(item.get("method", "GET") or "GET").upper(),
        str(item.get("endpoint", "") or "").strip(),
    )


def _endpoint_matches_forbidden(ep: str, forbidden: tuple[str, ...]) -> bool:
    ep_low = ep.lower()
    if not ep_low:
        return True
    for pattern in forbidden:
        p = pattern.lower()
        if p.startswith("/"):
            if p in ep_low or ep_low.startswith(p.rstrip("/")):
                return True
        elif p in ep_low:
            return True
    return False


def _normalize_api_spec_headers(raw: Any) -> list[dict[str, Any]]:
    """apiSpec requestHeaders — dict 입력을 schema list 형태로 변환."""

    if raw is None:
        return []
    if isinstance(raw, dict):
        return [
            {
                "name": str(name),
                "value": str(value) if value is not None else None,
                "required": True,
                "description": "",
            }
            for name, value in raw.items()
        ]
    if isinstance(raw, list):
        out: list[dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "") or "").strip()
            if not name:
                continue
            out.append(
                {
                    "name": name,
                    "value": item.get("value"),
                    "required": bool(item.get("required", True)),
                    "description": str(item.get("description", "") or ""),
                }
            )
        return out
    return []


def _normalize_api_spec_item(
    source: dict[str, Any] | None,
    canon: dict[str, Any],
) -> dict[str, Any]:
    """apiSpec item을 FeatureTemplateData ApiSpecSchema에 맞게 보정."""

    out = dict(canon)
    if source:
        for key, val in source.items():
            if key == "requestHeaders":
                continue
            if val is not None and val != "":
                out[key] = val

    headers_raw = source.get("requestHeaders") if source else None
    if headers_raw is not None:
        normalized = _normalize_api_spec_headers(headers_raw)
        if normalized:
            out["requestHeaders"] = normalized
    out["requestHeaders"] = _normalize_api_spec_headers(out.get("requestHeaders"))

    if not str(out.get("description", "")).strip():
        out["description"] = str(canon.get("description", ""))
    if not str(out.get("apiName", "")).strip():
        out["apiName"] = str(canon.get("apiName", ""))
    if not str(out.get("method", "")).strip():
        out["method"] = str(canon.get("method", "GET"))
    if not str(out.get("endpoint", "")).strip():
        out["endpoint"] = str(canon.get("endpoint", ""))
    if out.get("requestBody") is None:
        out["requestBody"] = canon.get("requestBody", {})
    if out.get("responseBody") is None:
        out["responseBody"] = canon.get("responseBody", {})
    if out.get("status") is None:
        out["status"] = canon.get("status", 200)
    if out.get("authenticationRequired") is None:
        out["authenticationRequired"] = bool(canon.get("authenticationRequired", False))
    return out


def _normalize_jwt_api_spec_item(
    source: dict[str, Any] | None,
    canon: dict[str, Any],
) -> dict[str, Any]:
    """JWT apiSpec item schema 보정 (공통 normalizer 위임)."""

    return _normalize_api_spec_item(source, canon)


def _sanitize_bucket_api_spec(
    normalized: dict[str, Any],
    canon: list[dict[str, Any]],
    *,
    forbidden_endpoint_substrings: tuple[str, ...],
    changed_fields: list[str],
    tag: str,
) -> None:
    """bucket canonical apiSpec만 deterministic하게 유지."""

    items = normalized.get("apiSpec")
    if not isinstance(items, list):
        items = []

    allowed_keys = {_api_spec_key(c) for c in canon}
    kept: dict[tuple[str, str], dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        ep = str(item.get("endpoint", "") or "").strip()
        key = _api_spec_key(item)
        if _endpoint_matches_forbidden(ep, forbidden_endpoint_substrings):
            changed_fields.append(f"apiSpec[{tag}-drop].{ep or 'unknown'}")
            continue
        if key not in allowed_keys:
            changed_fields.append(f"apiSpec[{tag}-drop-extra].{ep or 'unknown'}")
            continue
        kept[key] = item

    result: list[dict[str, Any]] = []
    for canon_item in canon:
        key = _api_spec_key(canon_item)
        source = kept.get(key)
        merged = _normalize_api_spec_item(source, canon_item)
        if source is None:
            changed_fields.append(f"apiSpec[{tag}+].{canon_item['endpoint']}")
        elif merged != source:
            changed_fields.append(f"apiSpec[{tag}~].{canon_item['endpoint']}")
        result.append(merged)

    if result != items:
        changed_fields.append(f"apiSpec[{tag}-canonical]")
    normalized["apiSpec"] = result


def _sanitize_signup_api_spec(normalized: dict[str, Any], changed_fields: list[str]) -> None:
    _sanitize_bucket_api_spec(
        normalized,
        _default_signup_api_spec(),
        forbidden_endpoint_substrings=_SIGNUP_FORBIDDEN_API_ENDPOINTS,
        changed_fields=changed_fields,
        tag="signup",
    )


def _sanitize_crud_api_spec(normalized: dict[str, Any], changed_fields: list[str]) -> None:
    _sanitize_bucket_api_spec(
        normalized,
        _default_crud_api_spec(),
        forbidden_endpoint_substrings=_CRUD_FORBIDDEN_API_ENDPOINTS,
        changed_fields=changed_fields,
        tag="crud",
    )


def _sanitize_jwt_api_spec(normalized: dict[str, Any], changed_fields: list[str]) -> None:
    _sanitize_bucket_api_spec(
        normalized,
        _default_jwt_api_spec(),
        forbidden_endpoint_substrings=_JWT_FORBIDDEN_API_ENDPOINTS + ("signup",),
        changed_fields=changed_fields,
        tag="jwt",
    )


def _default_generic_api_spec_item(feature_name: str) -> dict[str, Any]:
    fn = feature_name or "기능"
    endpoint = _generic_api_endpoint(fn)
    return {
        "apiName": fn,
        "method": "POST",
        "endpoint": endpoint,
        "description": f"{fn} 기능 API",
        "authenticationRequired": False,
        "requestHeaders": [
            {
                "name": "Content-Type",
                "value": "application/json",
                "required": True,
                "description": "JSON 요청 본문",
            }
        ],
        "requestBody": {},
        "responseBody": {},
        "status": 200,
    }


def _sanitize_generic_api_spec(
    normalized: dict[str, Any],
    request: FeatureTemplateGenerateRequest,
    changed_fields: list[str],
) -> None:
    """generic bucket: 다른 bucket endpoint 혼입 제거 + schema 보정."""

    fn = request.featureName or "기능"
    default_item = _default_generic_api_spec_item(fn)
    items = normalized.get("apiSpec")
    if not isinstance(items, list):
        items = []

    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        ep = str(item.get("endpoint", "") or "").strip()
        if _endpoint_matches_forbidden(ep, _GENERIC_FORBIDDEN_API_ENDPOINTS):
            changed_fields.append(f"apiSpec[generic-drop].{ep or 'unknown'}")
            continue
        key = _api_spec_key(item)
        if key in seen:
            changed_fields.append(f"apiSpec[generic-drop-dup].{ep or 'unknown'}")
            continue
        seen.add(key)
        result.append(_normalize_api_spec_item(item, default_item))

    if not result:
        result = [_normalize_api_spec_item(None, default_item)]
        changed_fields.append("apiSpec[generic-default]")

    normalized["apiSpec"] = result


def _canonical_signup_codefiles() -> dict[str, dict[str, Any]]:
    pkg = _AUTH_PKG
    return {
        "SignupController.java": {
            "fileName": "SignupController.java",
            "filePath": _java_file_path(pkg, "SignupController.java"),
            "role": "REST API 컨트롤러",
            "language": "java",
            "content": f"""package {pkg};

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/auth")
public class SignupController {{

    private final SignupService signupService;

    public SignupController(SignupService signupService) {{
        this.signupService = signupService;
    }}

    @PostMapping("/signup")
    public ResponseEntity<SignupResponse> signup(@RequestBody SignupRequest request) {{
        return ResponseEntity.status(HttpStatus.CREATED).body(signupService.signup(request));
    }}
}}
""",
        },
        "SignupService.java": {
            "fileName": "SignupService.java",
            "filePath": _java_file_path(pkg, "SignupService.java"),
            "role": "비즈니스 로직 서비스",
            "language": "java",
            "content": f"""package {pkg};

import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;

@Service
public class SignupService {{

    private final UserRepository userRepository;
    private final PasswordEncoder passwordEncoder;

    public SignupService(UserRepository userRepository, PasswordEncoder passwordEncoder) {{
        this.userRepository = userRepository;
        this.passwordEncoder = passwordEncoder;
    }}

    public SignupResponse signup(SignupRequest request) {{
        if (userRepository.existsByEmail(request.getEmail())) {{
            throw new IllegalStateException("duplicate email");
        }}
        String hash = passwordEncoder.encode(request.getPassword());
        User user = new User(request.getEmail(), hash, request.getNickname());
        User saved = userRepository.save(user);
        return new SignupResponse(saved.getId(), saved.getEmail(), saved.getNickname());
    }}
}}
""",
        },
        "SignupRequest.java": {
            "fileName": "SignupRequest.java",
            "filePath": _java_file_path(pkg, "SignupRequest.java"),
            "role": "요청 DTO",
            "language": "java",
            "content": f"""package {pkg};

public class SignupRequest {{
    private String email;
    private String password;
    private String nickname;

    public String getEmail() {{ return email; }}
    public void setEmail(String email) {{ this.email = email; }}
    public String getPassword() {{ return password; }}
    public void setPassword(String password) {{ this.password = password; }}
    public String getNickname() {{ return nickname; }}
    public void setNickname(String nickname) {{ this.nickname = nickname; }}
}}
""",
        },
        "SignupResponse.java": {
            "fileName": "SignupResponse.java",
            "filePath": _java_file_path(pkg, "SignupResponse.java"),
            "role": "응답 DTO",
            "language": "java",
            "content": f"""package {pkg};

public class SignupResponse {{
    private Long userId;
    private String email;
    private String nickname;

    public SignupResponse(Long userId, String email, String nickname) {{
        this.userId = userId;
        this.email = email;
        this.nickname = nickname;
    }}

    public Long getUserId() {{ return userId; }}
    public String getEmail() {{ return email; }}
    public String getNickname() {{ return nickname; }}
}}
""",
        },
        "User.java": {
            "fileName": "User.java",
            "filePath": _java_file_path(pkg, "User.java"),
            "role": "JPA Entity",
            "language": "java",
            "content": f"""package {pkg};

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "users")
public class User {{
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    private String email;
    private String passwordHash;
    private String nickname;

    protected User() {{}}

    public User(String email, String passwordHash, String nickname) {{
        this.email = email;
        this.passwordHash = passwordHash;
        this.nickname = nickname;
    }}

    public Long getId() {{ return id; }}
    public String getEmail() {{ return email; }}
    public String getNickname() {{ return nickname; }}
}}
""",
        },
        "UserRepository.java": {
            "fileName": "UserRepository.java",
            "filePath": _java_file_path(pkg, "UserRepository.java"),
            "role": "데이터 접근 Repository",
            "language": "java",
            "content": f"""package {pkg};

import org.springframework.data.jpa.repository.JpaRepository;

public interface UserRepository extends JpaRepository<User, Long> {{
    boolean existsByEmail(String email);
}}
""",
        },
    }


def _default_signup_requirements() -> list[dict[str, Any]]:
    return [
        {
            "requirementId": "R-001",
            "name": "입력값 검증",
            "description": "email/password/nickname 필수값 및 형식을 검증한다.",
            "inputValue": "email, password, nickname",
            "processCondition": "Bean Validation 적용",
            "successResult": "유효하면 가입 처리로 진행",
            "failureResult": "400 validation error",
            "priority": "HIGH",
            "relatedScreenOrApi": "POST /api/auth/signup",
        },
        {
            "requirementId": "R-002",
            "name": "이메일 중복 검사",
            "description": "UserRepository.existsByEmail로 중복을 확인한다.",
            "inputValue": "email",
            "processCondition": "동일 email 미존재",
            "successResult": "가입 계속",
            "failureResult": "409 duplicate email",
            "priority": "HIGH",
            "relatedScreenOrApi": "SignupService.signup",
        },
        {
            "requirementId": "R-003",
            "name": "비밀번호 해시 저장",
            "description": "PasswordEncoder.encode로 BCrypt 해시 후 User 저장",
            "inputValue": "raw password",
            "processCondition": "평문 password DB 저장 금지",
            "successResult": "201 + userId/email/nickname",
            "failureResult": "400/409",
            "priority": "HIGH",
            "relatedScreenOrApi": "POST /api/auth/signup",
        },
    ]


def _default_signup_flow() -> dict[str, Any]:
    return {
        "steps": [
            "1. POST /api/auth/signup 요청 수신",
            "2. SignupRequest 입력값 검증",
            "3. 이메일 중복 검사",
            "4. password BCrypt 해시 처리",
            "5. User 저장",
            "6. SignupResponse 반환",
        ],
        "layers": [
            {"layer": "Controller", "role": "SignupController — HTTP 수신/응답"},
            {"layer": "Service", "role": "SignupService — 중복 검사·해시·저장"},
            {"layer": "Repository", "role": "UserRepository — DB 접근"},
            {"layer": "DB", "role": "users 테이블"},
        ],
    }


def _default_signup_api_spec() -> list[dict[str, Any]]:
    return [
        {
            "apiName": "회원가입",
            "method": "POST",
            "endpoint": "/api/auth/signup",
            "description": "email/password/nickname으로 회원 가입",
            "authenticationRequired": False,
            "requestHeaders": [
                {
                    "name": "Content-Type",
                    "value": "application/json",
                    "required": True,
                    "description": "JSON 요청 본문",
                }
            ],
            "requestBody": {"email": "user@example.com", "password": "secret", "nickname": "nick"},
            "responseBody": {
                "success": True,
                "message": "created",
                "data": {"userId": 1, "email": "user@example.com", "nickname": "nick"},
            },
            "status": 201,
            "statusCodes": [
                {"code": 201, "description": "가입 성공"},
                {"code": 400, "description": "validation error"},
                {"code": 409, "description": "duplicate email"},
            ],
        }
    ]


def _canonical_crud_codefiles() -> dict[str, dict[str, Any]]:
    pkg = _POST_PKG
    return {
        "PostController.java": {
            "fileName": "PostController.java",
            "filePath": _java_file_path(pkg, "PostController.java"),
            "role": "REST API 컨트롤러",
            "language": "java",
            "content": f"""package {pkg};

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import java.util.List;

@RestController
@RequestMapping("/api/posts")
public class PostController {{

    private final PostService postService;

    public PostController(PostService postService) {{
        this.postService = postService;
    }}

    @PostMapping
    public ResponseEntity<PostResponse> create(@RequestBody PostCreateRequest request) {{
        return ResponseEntity.status(201).body(postService.create(request));
    }}

    @GetMapping
    public List<PostResponse> list() {{
        return postService.list();
    }}

    @GetMapping("/{{postId}}")
    public PostResponse get(@PathVariable Long postId) {{
        return postService.get(postId);
    }}

    @PutMapping("/{{postId}}")
    public PostResponse update(@PathVariable Long postId, @RequestBody PostUpdateRequest request) {{
        return postService.update(postId, request);
    }}

    @DeleteMapping("/{{postId}}")
    public ResponseEntity<Void> delete(@PathVariable Long postId) {{
        postService.delete(postId);
        return ResponseEntity.noContent().build();
    }}
}}
""",
        },
        "PostService.java": {
            "fileName": "PostService.java",
            "filePath": _java_file_path(pkg, "PostService.java"),
            "role": "비즈니스 로직 서비스",
            "language": "java",
            "content": f"""package {pkg};

import org.springframework.stereotype.Service;
import java.util.List;
import java.util.stream.Collectors;

@Service
public class PostService {{

    private final PostRepository postRepository;

    public PostService(PostRepository postRepository) {{
        this.postRepository = postRepository;
    }}

    public PostResponse create(PostCreateRequest request) {{
        Post post = new Post(request.getTitle(), request.getContent());
        return toResponse(postRepository.save(post));
    }}

    public List<PostResponse> list() {{
        return postRepository.findAll().stream().map(this::toResponse).collect(Collectors.toList());
    }}

    public PostResponse get(Long postId) {{
        return toResponse(postRepository.findById(postId).orElseThrow(() -> new IllegalArgumentException("not found")));
    }}

    public PostResponse update(Long postId, PostUpdateRequest request) {{
        Post post = postRepository.findById(postId).orElseThrow(() -> new IllegalArgumentException("not found"));
        post.update(request.getTitle(), request.getContent());
        return toResponse(postRepository.save(post));
    }}

    public void delete(Long postId) {{
        if (!postRepository.existsById(postId)) {{
            throw new IllegalArgumentException("not found");
        }}
        postRepository.deleteById(postId);
    }}

    private PostResponse toResponse(Post post) {{
        return new PostResponse(post.getId(), post.getTitle(), post.getContent());
    }}
}}
""",
        },
        "PostRepository.java": {
            "fileName": "PostRepository.java",
            "filePath": _java_file_path(pkg, "PostRepository.java"),
            "role": "데이터 접근 Repository",
            "language": "java",
            "content": f"""package {pkg};

import org.springframework.data.jpa.repository.JpaRepository;

public interface PostRepository extends JpaRepository<Post, Long> {{
}}
""",
        },
        "Post.java": {
            "fileName": "Post.java",
            "filePath": _java_file_path(pkg, "Post.java"),
            "role": "JPA Entity",
            "language": "java",
            "content": f"""package {pkg};

import jakarta.persistence.*;

@Entity
@Table(name = "posts")
public class Post {{
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    private String title;
    private String content;

    protected Post() {{}}
    public Post(String title, String content) {{ this.title = title; this.content = content; }}
    public void update(String title, String content) {{ this.title = title; this.content = content; }}
    public Long getId() {{ return id; }}
    public String getTitle() {{ return title; }}
    public String getContent() {{ return content; }}
}}
""",
        },
        "PostCreateRequest.java": {
            "fileName": "PostCreateRequest.java",
            "filePath": _java_file_path(pkg, "PostCreateRequest.java"),
            "role": "요청 DTO",
            "language": "java",
            "content": f"""package {pkg};

public class PostCreateRequest {{
    private String title;
    private String content;
    public String getTitle() {{ return title; }}
    public void setTitle(String title) {{ this.title = title; }}
    public String getContent() {{ return content; }}
    public void setContent(String content) {{ this.content = content; }}
}}
""",
        },
        "PostUpdateRequest.java": {
            "fileName": "PostUpdateRequest.java",
            "filePath": _java_file_path(pkg, "PostUpdateRequest.java"),
            "role": "요청 DTO",
            "language": "java",
            "content": f"""package {pkg};

public class PostUpdateRequest {{
    private String title;
    private String content;
    public String getTitle() {{ return title; }}
    public void setTitle(String title) {{ this.title = title; }}
    public String getContent() {{ return content; }}
    public void setContent(String content) {{ this.content = content; }}
}}
""",
        },
        "PostResponse.java": {
            "fileName": "PostResponse.java",
            "filePath": _java_file_path(pkg, "PostResponse.java"),
            "role": "응답 DTO",
            "language": "java",
            "content": f"""package {pkg};

public class PostResponse {{
    private Long id;
    private String title;
    private String content;
    public PostResponse(Long id, String title, String content) {{
        this.id = id; this.title = title; this.content = content;
    }}
    public Long getId() {{ return id; }}
    public String getTitle() {{ return title; }}
    public String getContent() {{ return content; }}
}}
""",
        },
    }


def _default_crud_requirements() -> list[dict[str, Any]]:
    specs = [
        ("R-001", "게시글 생성", "POST /api/posts", "201"),
        ("R-002", "게시글 목록 조회", "GET /api/posts", "200"),
        ("R-003", "게시글 단건 조회", "GET /api/posts/{postId}", "200/404"),
        ("R-004", "게시글 수정", "PUT /api/posts/{postId}", "200/404"),
        ("R-005", "게시글 삭제", "DELETE /api/posts/{postId}", "204/404"),
    ]
    out = []
    for rid, name, api, result in specs:
        out.append(
            {
                "requirementId": rid,
                "name": name,
                "description": f"{name} API를 제공한다.",
                "inputValue": "요청 DTO 또는 postId",
                "processCondition": "Service/Repository 계층 처리",
                "successResult": result,
                "failureResult": "400/404",
                "priority": "HIGH",
                "relatedScreenOrApi": api,
            }
        )
    return out


def _default_crud_flow() -> dict[str, Any]:
    return {
        "steps": [
            "1. POST /api/posts 생성",
            "2. GET /api/posts 목록",
            "3. GET /api/posts/{postId} 단건",
            "4. PUT /api/posts/{postId} 수정",
            "5. DELETE /api/posts/{postId} 삭제",
            "6. Service에서 postId 조회 및 예외 처리",
            "7. Repository로 저장/조회/삭제",
        ],
        "layers": [
            {"layer": "Controller", "role": "PostController"},
            {"layer": "Service", "role": "PostService"},
            {"layer": "Repository", "role": "PostRepository"},
            {"layer": "DB", "role": "posts 테이블"},
        ],
    }


def _default_crud_api_spec() -> list[dict[str, Any]]:
    endpoints = [
        ("POST", "/api/posts", 201),
        ("GET", "/api/posts", 200),
        ("GET", "/api/posts/{postId}", 200),
        ("PUT", "/api/posts/{postId}", 200),
        ("DELETE", "/api/posts/{postId}", 204),
    ]
    out = []
    for method, endpoint, status in endpoints:
        headers: list[dict[str, Any]] = []
        if method in ("POST", "PUT"):
            headers = [
                {
                    "name": "Content-Type",
                    "value": "application/json",
                    "required": True,
                    "description": "JSON 요청 본문",
                }
            ]
        out.append(
            {
                "apiName": f"게시글 {method}",
                "method": method,
                "endpoint": endpoint,
                "description": f"게시글 CRUD — {method} {endpoint}",
                "authenticationRequired": False,
                "requestHeaders": headers,
                "requestBody": {"title": "제목", "content": "내용"} if method in ("POST", "PUT") else {},
                "responseBody": {"id": 1, "title": "제목", "content": "내용"},
                "status": status,
            }
        )
    return out


def _canonical_jwt_codefiles() -> dict[str, dict[str, Any]]:
    auth = _AUTH_PKG
    sec = _SECURITY_PKG
    return {
        "JwtTokenProvider.java": {
            "fileName": "JwtTokenProvider.java",
            "filePath": _java_file_path(sec, "JwtTokenProvider.java"),
            "role": "인증/토큰 Provider",
            "language": "java",
            "content": f"""package {sec};

import org.springframework.stereotype.Component;

@Component
public class JwtTokenProvider {{

    public String createAccessToken(String subject) {{
        return "signed-jwt-token-for-" + subject;
    }}

    public boolean validateToken(String token) {{
        return token != null && !token.isBlank();
    }}

    public String getSubject(String token) {{
        return "user-subject";
    }}
}}
""",
        },
        "JwtAuthenticationFilter.java": {
            "fileName": "JwtAuthenticationFilter.java",
            "filePath": _java_file_path(sec, "JwtAuthenticationFilter.java"),
            "role": "인증/인가 필터",
            "language": "java",
            "content": f"""package {sec};

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.filter.OncePerRequestFilter;
import java.io.IOException;

public class JwtAuthenticationFilter extends OncePerRequestFilter {{

    private final JwtTokenProvider jwtTokenProvider;

    public JwtAuthenticationFilter(JwtTokenProvider jwtTokenProvider) {{
        this.jwtTokenProvider = jwtTokenProvider;
    }}

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {{
        String header = request.getHeader("Authorization");
        if (header != null && header.startsWith("Bearer ")) {{
            String token = header.substring(7);
            if (jwtTokenProvider.validateToken(token)) {{
                // SecurityContext에 Authentication 저장
            }}
        }}
        chain.doFilter(request, response);
    }}
}}
""",
        },
        "SecurityConfig.java": {
            "fileName": "SecurityConfig.java",
            "filePath": _java_file_path(sec, "SecurityConfig.java"),
            "role": "설정 클래스",
            "language": "java",
            "content": f"""package {sec};

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

@Configuration
public class SecurityConfig {{

    @Bean
    public SecurityFilterChain filterChain(HttpSecurity http, JwtAuthenticationFilter jwtFilter) throws Exception {{
        http.csrf(csrf -> csrf.disable())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/auth/login").permitAll()
                .anyRequest().authenticated())
            .addFilterBefore(jwtFilter, UsernamePasswordAuthenticationFilter.class);
        return http.build();
    }}
}}
""",
        },
        "CustomUserDetailsService.java": {
            "fileName": "CustomUserDetailsService.java",
            "filePath": _java_file_path(sec, "CustomUserDetailsService.java"),
            "role": "비즈니스 로직 서비스",
            "language": "java",
            "content": f"""package {sec};

import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.stereotype.Service;

@Service
public class CustomUserDetailsService implements UserDetailsService {{

    @Override
    public UserDetails loadUserByUsername(String username) throws UsernameNotFoundException {{
        throw new UsernameNotFoundException("user not found");
    }}
}}
""",
        },
        "AuthController.java": {
            "fileName": "AuthController.java",
            "filePath": _java_file_path(auth, "AuthController.java"),
            "role": "REST API 컨트롤러",
            "language": "java",
            "content": f"""package {auth};

import {sec}.JwtTokenProvider;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/auth")
public class AuthController {{

    private final JwtTokenProvider jwtTokenProvider;

    public AuthController(JwtTokenProvider jwtTokenProvider) {{
        this.jwtTokenProvider = jwtTokenProvider;
    }}

    @PostMapping("/login")
    public ResponseEntity<LoginResponse> login(@RequestBody LoginRequest request) {{
        String token = jwtTokenProvider.createAccessToken(request.getEmail());
        return ResponseEntity.ok(new LoginResponse(token, "Bearer", request.getEmail()));
    }}
}}
""",
        },
        "LoginRequest.java": {
            "fileName": "LoginRequest.java",
            "filePath": _java_file_path(auth, "LoginRequest.java"),
            "role": "요청 DTO",
            "language": "java",
            "content": f"""package {auth};

public class LoginRequest {{
    private String email;
    private String password;
    public String getEmail() {{ return email; }}
    public void setEmail(String email) {{ this.email = email; }}
    public String getPassword() {{ return password; }}
    public void setPassword(String password) {{ this.password = password; }}
}}
""",
        },
        "LoginResponse.java": {
            "fileName": "LoginResponse.java",
            "filePath": _java_file_path(auth, "LoginResponse.java"),
            "role": "응답 DTO",
            "language": "java",
            "content": f"""package {auth};

public class LoginResponse {{
    private String accessToken;
    private String tokenType;
    private String email;
    public LoginResponse(String accessToken, String tokenType, String email) {{
        this.accessToken = accessToken; this.tokenType = tokenType; this.email = email;
    }}
    public String getAccessToken() {{ return accessToken; }}
    public String getTokenType() {{ return tokenType; }}
    public String getEmail() {{ return email; }}
}}
""",
        },
    }


def _default_jwt_requirements() -> list[dict[str, Any]]:
    return [
        {
            "requirementId": "R-001",
            "name": "accessToken 발급",
            "description": "로그인 성공 시 JwtTokenProvider가 accessToken을 생성한다.",
            "inputValue": "email, password",
            "processCondition": "자격증명 검증 성공",
            "successResult": "200 + accessToken",
            "failureResult": "401",
            "priority": "HIGH",
            "relatedScreenOrApi": "POST /api/auth/login",
        },
        {
            "requirementId": "R-002",
            "name": "Bearer 토큰 추출",
            "description": "Authorization: Bearer 헤더에서 토큰을 추출한다.",
            "inputValue": "Authorization header",
            "processCondition": "Bearer prefix",
            "successResult": "토큰 문자열",
            "failureResult": "401",
            "priority": "HIGH",
            "relatedScreenOrApi": "JwtAuthenticationFilter",
        },
        {
            "requirementId": "R-003",
            "name": "JWT 검증",
            "description": "JwtTokenProvider.validateToken 수행",
            "inputValue": "accessToken",
            "processCondition": "서명/만료 검증",
            "successResult": "Authentication 생성",
            "failureResult": "401",
            "priority": "HIGH",
            "relatedScreenOrApi": "JwtTokenProvider",
        },
        {
            "requirementId": "R-004",
            "name": "보호 API 접근",
            "description": "SecurityContext 저장 후 GET /api/users/me 허용",
            "inputValue": "authenticated user",
            "processCondition": "authenticationRequired=true",
            "successResult": "200 user info",
            "failureResult": "401",
            "priority": "HIGH",
            "relatedScreenOrApi": "GET /api/users/me",
        },
    ]


def _default_jwt_flow() -> dict[str, Any]:
    return {
        "steps": [
            "1. 로그인 성공 시 JwtTokenProvider가 accessToken 생성",
            "2. 클라이언트 Authorization: Bearer 헤더 전송",
            "3. JwtAuthenticationFilter 토큰 추출",
            "4. JwtTokenProvider 검증",
            "5. UserDetails 로딩",
            "6. SecurityContext 저장",
            "7. 보호 API 허용 또는 401",
        ],
        "layers": [
            {"layer": "Filter", "role": "JwtAuthenticationFilter"},
            {"layer": "Provider", "role": "JwtTokenProvider"},
            {"layer": "Config", "role": "SecurityConfig"},
            {"layer": "Controller", "role": "AuthController"},
        ],
    }


def _default_jwt_api_spec() -> list[dict[str, Any]]:
    return [
        {
            "apiName": "로그인 API",
            "method": "POST",
            "endpoint": "/api/auth/login",
            "description": "이메일과 비밀번호를 검증하고 JWT access token을 발급합니다.",
            "authenticationRequired": False,
            "requestHeaders": [
                {
                    "name": "Content-Type",
                    "value": "application/json",
                    "required": True,
                    "description": "JSON 요청 본문",
                }
            ],
            "requestBody": {
                "email": "user@example.com",
                "password": "password123",
            },
            "responseBody": {
                "accessToken": "jwt-access-token",
                "tokenType": "Bearer",
            },
            "status": 200,
        },
        {
            "apiName": "내 정보 조회",
            "method": "GET",
            "endpoint": "/api/users/me",
            "description": "Bearer JWT로 인증된 사용자의 정보를 조회합니다.",
            "authenticationRequired": True,
            "requestHeaders": [
                {
                    "name": "Authorization",
                    "value": "Bearer {accessToken}",
                    "required": True,
                    "description": "JWT access token",
                }
            ],
            "requestBody": {},
            "responseBody": {
                "email": "user@example.com",
                "nickname": "nick",
            },
            "status": 200,
        },
    ]


def _generic_class_prefix(feature_name: str) -> str:
    mapping = {
        "댓글": "Comment",
        "프로필": "Profile",
        "검색": "Search",
        "알림": "Notification",
    }
    for key, val in mapping.items():
        if key in feature_name:
            return val
    safe = re.sub(r"[^0-9a-zA-Z]+", " ", feature_name).strip()
    if safe:
        return "".join(w.capitalize() for w in safe.split()[:2]) or "Feature"
    return "Feature"


def _generic_api_endpoint(feature_name: str) -> str:
    low = feature_name.lower()
    if "댓글" in feature_name:
        return "/api/comments"
    if "프로필" in feature_name:
        return "/api/profile"
    if "검색" in feature_name:
        return "/api/search"
    slug = re.sub(r"[^a-z0-9]+", "-", low).strip("-") or "feature"
    return f"/api/{slug}"


def _canonical_generic_codefiles(feature_name: str) -> dict[str, dict[str, Any]]:
    prefix = _generic_class_prefix(feature_name)
    pkg = "com.example.app"
    endpoint = _generic_api_endpoint(feature_name)
    lc, ls, lr, lresp = f"{prefix}Controller", f"{prefix}Service", f"{prefix}Request", f"{prefix}Response"
    return {
        f"{lc}.java": {
            "fileName": f"{lc}.java",
            "filePath": _java_file_path(pkg, f"{lc}.java"),
            "role": "REST API 컨트롤러",
            "language": "java",
            "content": f"""package {pkg};

import org.springframework.web.bind.annotation.*;
import org.springframework.http.ResponseEntity;

@RestController
@RequestMapping("{endpoint}")
public class {lc} {{
    private final {ls} service;
    public {lc}({ls} service) {{ this.service = service; }}
    @PostMapping
    public ResponseEntity<{lresp}> handle(@RequestBody {lr} request) {{
        return ResponseEntity.ok(service.process(request));
    }}
}}
""",
        },
        f"{ls}.java": {
            "fileName": f"{ls}.java",
            "filePath": _java_file_path(pkg, f"{ls}.java"),
            "role": "비즈니스 로직 서비스",
            "language": "java",
            "content": f"""package {pkg};

import org.springframework.stereotype.Service;

@Service
public class {ls} {{
    public {lresp} process({lr} request) {{
        return new {lresp}("ok");
    }}
}}
""",
        },
        f"{lr}.java": {
            "fileName": f"{lr}.java",
            "filePath": _java_file_path(pkg, f"{lr}.java"),
            "role": "요청 DTO",
            "language": "java",
            "content": f"""package {pkg};

public class {lr} {{
    private String payload;
    public String getPayload() {{ return payload; }}
    public void setPayload(String payload) {{ this.payload = payload; }}
}}
""",
        },
        f"{lresp}.java": {
            "fileName": f"{lresp}.java",
            "filePath": _java_file_path(pkg, f"{lresp}.java"),
            "role": "응답 DTO",
            "language": "java",
            "content": f"""package {pkg};

public class {lresp} {{
    private String result;
    public {lresp}(String result) {{ this.result = result; }}
    public String getResult() {{ return result; }}
}}
""",
        },
    }


def _ensure_list_section(
    normalized: dict[str, Any],
    key: str,
    factory: Callable[[], list[Any]],
    min_len: int,
    changed_fields: list[str],
) -> None:
    items = normalized.get(key)
    if not isinstance(items, list) or len(items) < min_len:
        normalized[key] = factory()
        changed_fields.append(f"{key}[bucket-default]")


def _ensure_flow(normalized: dict[str, Any], factory: Callable[[], dict], changed_fields: list[str]) -> None:
    flow = normalized.get("flow")
    if not isinstance(flow, dict):
        normalized["flow"] = factory()
        changed_fields.append("flow[bucket-default]")
        return
    steps = flow.get("steps")
    if not isinstance(steps, list) or len(steps) < 3:
        d = factory()
        flow["steps"] = d["steps"]
        changed_fields.append("flow.steps[bucket-default]")
    layers = flow.get("layers")
    if not isinstance(layers, list) or len(layers) < 2:
        d = factory()
        flow["layers"] = d["layers"]
        changed_fields.append("flow.layers[bucket-default]")


def _merge_required_codefiles(
    normalized: dict[str, Any],
    *,
    required_order: tuple[str, ...],
    canonical: dict[str, dict[str, Any]],
    default_pkg: str,
    changed_fields: list[str],
    drop_patterns: tuple[str, ...] = (),
    canonical_only: bool = False,
) -> None:
    from app.services.feature_template_normalizer import (
        _infer_java_code_file_role,
        _normalize_java_code_file_roles,
    )

    files = normalized.get("codeFiles")
    if not isinstance(files, list):
        files = []

    merged: dict[str, dict[str, Any]] = {}
    for raw in files:
        if not isinstance(raw, dict):
            continue
        bn = _basename(str(raw.get("fileName", "")))
        if not bn.endswith(".java"):
            changed_fields.append(f"codeFiles[drop-non-java].{bn or 'unknown'}")
            continue
        if _should_drop_java_codefile(raw, drop_patterns):
            changed_fields.append(f"codeFiles[drop].{bn}")
            continue
        pkg = _extract_package(str(raw.get("content", ""))) or default_pkg
        if bn in canonical:
            pkg = _extract_package(canonical[bn]["content"]) or default_pkg
        aligned = align_java_codefile_entry(raw, package=pkg, canonical_by_name=canonical)
        merged[bn] = aligned

    for req in required_order:
        if req not in merged:
            merged[req] = dict(canonical[req])
            changed_fields.append(f"codeFiles[bucket+].{req}")
            continue
        c = merged[req].get("content", "")
        if _content_needs_canonical_replace(str(c), req[:-5], req):
            merged[req] = dict(canonical[req])
            changed_fields.append(f"codeFiles[bucket~].{req}")

    out: list[dict[str, Any]] = []
    for req in required_order:
        out.append(merged[req])

    if not canonical_only:
        seen = set(required_order)
        for k in sorted(merged.keys()):
            if k not in seen:
                out.append(merged[k])

    for index, item in enumerate(out):
        fn = str(item.get("fileName", ""))
        if not item.get("filePath"):
            pkg = _extract_package(str(item.get("content", ""))) or default_pkg
            item["filePath"] = _java_file_path(pkg, _basename(fn))
            changed_fields.append(f"codeFiles[{index}].filePath")

    normalized["codeFiles"] = _normalize_java_code_file_roles(out, changed_fields)


def _apply_signup_guard(
    normalized: dict[str, Any],
    request: FeatureTemplateGenerateRequest,
    changed_fields: list[str],
) -> None:
    _ensure_list_section(normalized, "requirements", _default_signup_requirements, 3, changed_fields)
    _ensure_flow(normalized, _default_signup_flow, changed_fields)
    _ensure_list_section(normalized, "apiSpec", _default_signup_api_spec, 1, changed_fields)
    _sanitize_signup_api_spec(normalized, changed_fields)
    if request.includeMissions and (
        not isinstance(normalized.get("missions"), list) or len(normalized["missions"]) < 2
    ):
        normalized["missions"] = [
            {
                "missionId": "M-001",
                "title": "BCrypt 적용",
                "description": "미션 목표: PasswordEncoder로 해시 저장",
                "missionType": "implementation",
                "requirements": ["BCrypt"],
                "successCriteria": ["평문 미저장"],
                "relatedRequirements": ["R-003"],
                "difficulty": request.level.value,
            },
            {
                "missionId": "M-002",
                "title": "중복 이메일 처리",
                "description": "미션 목표: 409 응답",
                "missionType": "validation",
                "requirements": ["existsByEmail"],
                "successCriteria": ["409"],
                "relatedRequirements": ["R-002"],
                "difficulty": request.level.value,
            },
        ]
        changed_fields.append("missions[signup-default]")
    if request.includeInterview and (
        not isinstance(normalized.get("interviewQuestions"), list)
        or len(normalized["interviewQuestions"]) < 3
    ):
        normalized["interviewQuestions"] = [
            {
                "questionId": "IQ-001",
                "question": "회원가입과 로그인의 차이는?",
                "keyPoints": ["signup", "User 생성"],
                "sampleAnswer": "회원가입은 계정 생성, 로그인은 인증",
                "relatedSection": "flow",
            },
            {
                "questionId": "IQ-002",
                "question": "BCrypt를 쓰는 이유는?",
                "keyPoints": ["해시", "salt"],
                "sampleAnswer": "평문 저장 방지",
                "relatedSection": "codeFiles",
            },
            {
                "questionId": "IQ-003",
                "question": "409는 언제 반환하나?",
                "keyPoints": ["duplicate email"],
                "sampleAnswer": "이메일 중복 시",
                "relatedSection": "apiSpec",
            },
        ]
        changed_fields.append("interviewQuestions[signup-default]")
    if request.includeCode:
        canon = _canonical_signup_codefiles()
        order = tuple(canon.keys())
        force = _payload_has_forbidden(normalized, _SIGNUP_FORBIDDEN)
        if force:
            changed_fields.append("codeFiles[signup-forbidden-replace]")
        _merge_required_codefiles(
            normalized,
            required_order=order,
            canonical=canon,
            default_pkg=_AUTH_PKG,
            changed_fields=changed_fields,
            drop_patterns=("AppController", "AppService", "LoginController"),
            canonical_only=True,
        )
    if request.includeMissions is False:
        pass
    bq = normalized.get("basicQuestions")
    if not isinstance(bq, list) or len(bq) < 3:
        normalized["basicQuestions"] = [
            {
                "questionId": "Q-001",
                "type": "short_answer",
                "question": "SignupController 역할은?",
                "choices": None,
                "answer": "HTTP 수신",
                "explanation": "POST /api/auth/signup",
                "relatedSection": "flow",
                "difficulty": request.level.value,
            },
            {
                "questionId": "Q-002",
                "type": "short_answer",
                "question": "비밀번호는 어떻게 저장하나?",
                "choices": None,
                "answer": "BCrypt 해시",
                "explanation": "평문 금지",
                "relatedSection": "requirements",
                "difficulty": request.level.value,
            },
            {
                "questionId": "Q-003",
                "type": "short_answer",
                "question": "중복 이메일 HTTP status?",
                "choices": None,
                "answer": "409",
                "explanation": "Conflict",
                "relatedSection": "apiSpec",
                "difficulty": request.level.value,
            },
        ]
        changed_fields.append("basicQuestions[signup-default]")


def _apply_crud_guard(
    normalized: dict[str, Any],
    request: FeatureTemplateGenerateRequest,
    changed_fields: list[str],
) -> None:
    _ensure_list_section(normalized, "requirements", _default_crud_requirements, 5, changed_fields)
    _ensure_flow(normalized, _default_crud_flow, changed_fields)
    _ensure_list_section(normalized, "apiSpec", _default_crud_api_spec, 5, changed_fields)
    _sanitize_crud_api_spec(normalized, changed_fields)
    bq = normalized.get("basicQuestions")
    if not isinstance(bq, list) or len(bq) < 3:
        normalized["basicQuestions"] = [
            {
                "questionId": "Q-001",
                "type": "short_answer",
                "question": "CRUD란?",
                "choices": None,
                "answer": "Create Read Update Delete",
                "explanation": "4가지 기본 연산",
                "relatedSection": "requirements",
                "difficulty": request.level.value,
            },
            {
                "questionId": "Q-002",
                "type": "short_answer",
                "question": "404는 언제?",
                "choices": None,
                "answer": "postId 없음",
                "explanation": "NOT_FOUND",
                "relatedSection": "apiSpec",
                "difficulty": request.level.value,
            },
            {
                "questionId": "Q-003",
                "type": "short_answer",
                "question": "Repository 역할?",
                "choices": None,
                "answer": "DB 접근",
                "explanation": "PostRepository",
                "relatedSection": "flow",
                "difficulty": request.level.value,
            },
        ]
        changed_fields.append("basicQuestions[crud-default]")
    if request.includeMissions and (
        not isinstance(normalized.get("missions"), list) or len(normalized["missions"]) < 2
    ):
        normalized["missions"] = [
            {
                "missionId": "M-001",
                "title": "PostController CRUD 매핑",
                "description": "미션 목표: /api/posts CRUD 5종 endpoint 구현",
                "missionType": "implementation",
                "requirements": ["PostController", "PostMapping"],
                "successCriteria": ["5종 endpoint"],
                "relatedRequirements": ["R-001"],
                "difficulty": request.level.value,
            },
            {
                "missionId": "M-002",
                "title": "404 NOT_FOUND 처리",
                "description": "미션 목표: postId 미존재 시 예외",
                "missionType": "validation",
                "requirements": ["404", "findById"],
                "successCriteria": ["NOT_FOUND"],
                "relatedRequirements": ["R-003"],
                "difficulty": request.level.value,
            },
        ]
        changed_fields.append("missions[crud-default]")
    if request.includeInterview and (
        not isinstance(normalized.get("interviewQuestions"), list)
        or len(normalized["interviewQuestions"]) < 3
    ):
        normalized["interviewQuestions"] = [
            {
                "questionId": "IQ-001",
                "question": "PostController CRUD 매핑은?",
                "keyPoints": ["PostMapping", "GetMapping"],
                "sampleAnswer": "HTTP 메서드별 매핑",
                "relatedSection": "codeFiles",
            },
            {
                "questionId": "IQ-002",
                "question": "PostRepository 역할은?",
                "keyPoints": ["JPA", "Repository"],
                "sampleAnswer": "DB 접근",
                "relatedSection": "flow",
            },
            {
                "questionId": "IQ-003",
                "question": "404는 언제?",
                "keyPoints": ["NOT_FOUND", "postId"],
                "sampleAnswer": "postId 없음",
                "relatedSection": "apiSpec",
            },
        ]
        changed_fields.append("interviewQuestions[crud-default]")
    if request.includeCode:
        canon = _canonical_crud_codefiles()
        _merge_required_codefiles(
            normalized,
            required_order=tuple(canon.keys()),
            canonical=canon,
            default_pkg=_POST_PKG,
            changed_fields=changed_fields,
            drop_patterns=("CRUDController", "CRUDService", "AppController", "LoginController"),
            canonical_only=True,
        )


def _apply_jwt_guard(
    normalized: dict[str, Any],
    request: FeatureTemplateGenerateRequest,
    changed_fields: list[str],
) -> None:
    _ensure_list_section(normalized, "requirements", _default_jwt_requirements, 4, changed_fields)
    _ensure_flow(normalized, _default_jwt_flow, changed_fields)
    _ensure_list_section(normalized, "apiSpec", _default_jwt_api_spec, 2, changed_fields)
    _sanitize_jwt_api_spec(normalized, changed_fields)
    bq = normalized.get("basicQuestions")
    if not isinstance(bq, list) or len(bq) < 3:
        normalized["basicQuestions"] = [
            {
                "questionId": "Q-001",
                "type": "short_answer",
                "question": "JwtAuthenticationFilter 역할?",
                "choices": None,
                "answer": "토큰 추출·검증",
                "explanation": "Filter chain",
                "relatedSection": "flow",
                "difficulty": request.level.value,
            },
            {
                "questionId": "Q-002",
                "type": "short_answer",
                "question": "Bearer 헤더 형식?",
                "choices": None,
                "answer": "Authorization: Bearer {token}",
                "explanation": "RFC 6750",
                "relatedSection": "apiSpec",
                "difficulty": request.level.value,
            },
            {
                "questionId": "Q-003",
                "type": "short_answer",
                "question": "토큰 검증 실패 status?",
                "choices": None,
                "answer": "401",
                "explanation": "Unauthorized",
                "relatedSection": "requirements",
                "difficulty": request.level.value,
            },
        ]
        changed_fields.append("basicQuestions[jwt-default]")
    if request.includeMissions and (
        not isinstance(normalized.get("missions"), list) or len(normalized["missions"]) < 2
    ):
        normalized["missions"] = [
            {
                "missionId": "M-001",
                "title": "JWT 토큰 발급",
                "description": "미션 목표: login 성공 시 access token 반환",
                "missionType": "implementation",
                "requirements": ["JwtTokenProvider", "login"],
                "successCriteria": ["Bearer token"],
                "relatedRequirements": ["R-001"],
                "difficulty": request.level.value,
            },
            {
                "missionId": "M-002",
                "title": "인증 필터 적용",
                "description": "미션 목표: JwtAuthenticationFilter로 보호 API 인증",
                "missionType": "security",
                "requirements": ["JwtAuthenticationFilter", "SecurityConfig"],
                "successCriteria": ["GET /api/users/me"],
                "relatedRequirements": ["R-002"],
                "difficulty": request.level.value,
            },
        ]
        changed_fields.append("missions[jwt-default]")
    if request.includeInterview and (
        not isinstance(normalized.get("interviewQuestions"), list)
        or len(normalized["interviewQuestions"]) < 3
    ):
        normalized["interviewQuestions"] = [
            {
                "questionId": "IQ-001",
                "question": "JwtTokenProvider 역할은?",
                "keyPoints": ["token", "sign"],
                "sampleAnswer": "JWT 생성·검증",
                "relatedSection": "codeFiles",
            },
            {
                "questionId": "IQ-002",
                "question": "Bearer 헤더 형식은?",
                "keyPoints": ["Authorization", "Bearer"],
                "sampleAnswer": "Authorization: Bearer {token}",
                "relatedSection": "apiSpec",
            },
            {
                "questionId": "IQ-003",
                "question": "인증 실패 HTTP status?",
                "keyPoints": ["401", "Unauthorized"],
                "sampleAnswer": "401",
                "relatedSection": "requirements",
            },
        ]
        changed_fields.append("interviewQuestions[jwt-default]")
    if request.includeCode:
        canon = _canonical_jwt_codefiles()
        _merge_required_codefiles(
            normalized,
            required_order=tuple(canon.keys()),
            canonical=canon,
            default_pkg=_SECURITY_PKG,
            changed_fields=changed_fields,
            drop_patterns=("JWTController", "AppController"),
            canonical_only=True,
        )


def _apply_generic_guard(
    normalized: dict[str, Any],
    request: FeatureTemplateGenerateRequest,
    changed_fields: list[str],
) -> None:
    fn = request.featureName or "기능"
    overview = normalized.get("overview")
    if isinstance(overview, dict) and not str(overview.get("purpose", "")).strip():
        overview["purpose"] = f"{fn} 기능의 목적과 사용자 가치를 설명한다."
        changed_fields.append("overview.purpose[generic]")
    _ensure_list_section(
        normalized,
        "requirements",
        lambda: [
            {
                "requirementId": "R-001",
                "name": f"{fn} 요청",
                "description": f"{fn} 핵심 요구",
                "inputValue": "입력",
                "processCondition": "검증",
                "successResult": "200",
                "failureResult": "400",
                "priority": "HIGH",
                "relatedScreenOrApi": _generic_api_endpoint(fn),
            },
            {
                "requirementId": "R-002",
                "name": f"{fn} 처리",
                "description": "Service 처리",
                "inputValue": "DTO",
                "processCondition": "비즈니스 규칙",
                "successResult": "성공",
                "failureResult": "실패",
                "priority": "HIGH",
                "relatedScreenOrApi": "Service",
            },
            {
                "requirementId": "R-003",
                "name": f"{fn} 응답",
                "description": "응답 반환",
                "inputValue": "결과",
                "processCondition": "완료",
                "successResult": "Response DTO",
                "failureResult": "에러",
                "priority": "MEDIUM",
                "relatedScreenOrApi": _generic_api_endpoint(fn),
            },
        ],
        3,
        changed_fields,
    )
    _ensure_flow(
        normalized,
        lambda: {
            "steps": ["1) 요청", "2) 처리", "3) 응답"],
            "layers": [
                {"layer": "Controller", "role": "수신"},
                {"layer": "Service", "role": "로직"},
                {"layer": "Repository", "role": "저장"},
            ],
        },
        changed_fields,
    )
    _ensure_list_section(
        normalized,
        "apiSpec",
        lambda: [_default_generic_api_spec_item(fn)],
        1,
        changed_fields,
    )
    _sanitize_generic_api_spec(normalized, request, changed_fields)
    if request.includeCode:
        canon = _canonical_generic_codefiles(fn)
        _merge_required_codefiles(
            normalized,
            required_order=tuple(canon.keys()),
            canonical=canon,
            default_pkg="com.example.app",
            changed_fields=changed_fields,
            drop_patterns=("AppController", "CRUDController", "JWTController", "LoginController"),
            canonical_only=True,
        )


_BUCKET_NEXT_RECOMMENDATIONS: dict[str, list[dict[str, Any]]] = {
    SIGNUP_BUCKET: [
        {
            "featureName": "로그인",
            "reason": "회원가입 후 인증 흐름 학습",
            "expectedLearning": "JWT/세션 기반 로그인",
            "priority": 1,
        },
        {
            "featureName": "JWT 인증",
            "reason": "인증 토큰 심화",
            "expectedLearning": "Bearer 토큰·필터 체인",
            "priority": 2,
        },
        {
            "featureName": "프로필 수정",
            "reason": "회원 정보 관리 확장",
            "expectedLearning": "인증 사용자 API",
            "priority": 3,
        },
    ],
    CRUD_BUCKET: [
        {
            "featureName": "댓글 CRUD",
            "reason": "연관 엔티티 확장",
            "expectedLearning": "1:N 관계·FK",
            "priority": 1,
        },
        {
            "featureName": "JWT 인증",
            "reason": "작성자 인증 연동",
            "expectedLearning": "보호 API",
            "priority": 2,
        },
        {
            "featureName": "페이징 조회",
            "reason": "목록 API 고도화",
            "expectedLearning": "Pageable·정렬",
            "priority": 3,
        },
    ],
    JWT_AUTH_BUCKET: [
        {
            "featureName": "회원가입",
            "reason": "인증 전 사용자 등록",
            "expectedLearning": "User 저장·중복 검사",
            "priority": 1,
        },
        {
            "featureName": "프로필 조회",
            "reason": "인증 사용자 정보 API",
            "expectedLearning": "GET /api/users/me 활용",
            "priority": 2,
        },
        {
            "featureName": "토큰 갱신",
            "reason": "Refresh token 패턴",
            "expectedLearning": "만료·재발급",
            "priority": 3,
        },
    ],
}


def _section_text_blob(items: object) -> str:
    if not isinstance(items, list):
        return ""
    parts: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        for val in item.values():
            if isinstance(val, str):
                parts.append(val)
            elif isinstance(val, list):
                parts.extend(str(x) for x in val if x is not None)
    return "\n".join(parts)


def _replace_off_topic_section_items(
    normalized: dict[str, Any],
    *,
    section: str,
    forbidden: tuple[str, ...],
    replacement_factory: Callable[[], list[dict[str, Any]]],
    changed_fields: list[str],
    tag: str,
) -> None:
    items = normalized.get(section)
    if not isinstance(items, list) or not items:
        return
    blob = _section_text_blob(items).lower()
    if not _text_has_any(blob, forbidden):
        return
    normalized[section] = replacement_factory()
    changed_fields.append(f"{section}[cross-section-{tag}]")


def _apply_cross_section_consistency(
    normalized: dict[str, Any],
    request: FeatureTemplateGenerateRequest,
    bucket: str,
    changed_fields: list[str],
) -> None:
    """apiSpec·codeFiles·missions·questions 간 bucket 주제 일치 보정."""

    if bucket == SIGNUP_BUCKET:
        if request.includeMissions:
            _replace_off_topic_section_items(
                normalized,
                section="missions",
                forbidden=("/api/auth/login", "jwt", "postcontroller", "/api/posts"),
                replacement_factory=lambda: [
                    {
                        "missionId": "M-001",
                        "title": "SignupService 구현",
                        "description": "미션 목표: SignupRequest 검증 후 User 저장",
                        "missionType": "implementation",
                        "requirements": ["SignupService", "UserRepository"],
                        "successCriteria": ["POST /api/auth/signup 동작"],
                        "relatedRequirements": ["R-001"],
                        "difficulty": request.level.value,
                    },
                    {
                        "missionId": "M-002",
                        "title": "비밀번호 BCrypt 적용",
                        "description": "미션 목표: PasswordEncoder로 해시 저장",
                        "missionType": "security",
                        "requirements": ["PasswordEncoder", "BCrypt"],
                        "successCriteria": ["평문 미저장"],
                        "relatedRequirements": ["R-003"],
                        "difficulty": request.level.value,
                    },
                ],
                changed_fields=changed_fields,
                tag="signup",
            )
        if request.includeInterview:
            _replace_off_topic_section_items(
                normalized,
                section="interviewQuestions",
                forbidden=("jwt filter", "postcontroller", "게시글 삭제"),
                replacement_factory=lambda: [
                    {
                        "questionId": "IQ-001",
                        "question": "SignupController와 SignupService 역할 차이는?",
                        "keyPoints": ["Controller", "Service", "signup"],
                        "sampleAnswer": "Controller는 HTTP, Service는 비즈니스 로직",
                        "relatedSection": "flow",
                    },
                    {
                        "questionId": "IQ-002",
                        "question": "회원가입 시 비밀번호를 해시하는 이유는?",
                        "keyPoints": ["BCrypt", "PasswordEncoder"],
                        "sampleAnswer": "평문 저장 방지",
                        "relatedSection": "codeFiles",
                    },
                    {
                        "questionId": "IQ-003",
                        "question": "이메일 중복 시 어떤 HTTP status를 반환하나?",
                        "keyPoints": ["409", "existsByEmail"],
                        "sampleAnswer": "409 Conflict",
                        "relatedSection": "apiSpec",
                    },
                ],
                changed_fields=changed_fields,
                tag="signup",
            )
    elif bucket == CRUD_BUCKET:
        if request.includeMissions:
            _replace_off_topic_section_items(
                normalized,
                section="missions",
                forbidden=("/api/auth/login", "/api/auth/signup", "signup", "jwt"),
                replacement_factory=lambda: [
                    {
                        "missionId": "M-001",
                        "title": "PostController CRUD 매핑",
                        "description": "미션 목표: /api/posts CRUD 5종 endpoint 구현",
                        "missionType": "implementation",
                        "requirements": ["PostController", "PostService"],
                        "successCriteria": ["POST/GET/PUT/DELETE 매핑"],
                        "relatedRequirements": ["R-001"],
                        "difficulty": request.level.value,
                    },
                    {
                        "missionId": "M-002",
                        "title": "postId 없음 404 처리",
                        "description": "미션 목표: 단건 조회·수정·삭제 시 NOT_FOUND",
                        "missionType": "validation",
                        "requirements": ["404", "findById"],
                        "successCriteria": ["존재하지 않는 postId 예외"],
                        "relatedRequirements": ["R-003"],
                        "difficulty": request.level.value,
                    },
                ],
                changed_fields=changed_fields,
                tag="crud",
            )
        if request.includeInterview:
            _replace_off_topic_section_items(
                normalized,
                section="interviewQuestions",
                forbidden=("회원가입", "signup", "bcrypt", "jwt filter"),
                replacement_factory=lambda: [
                    {
                        "questionId": "IQ-001",
                        "question": "PostController에서 CRUD 메서드 매핑은?",
                        "keyPoints": ["PostMapping", "GetMapping", "PutMapping", "DeleteMapping"],
                        "sampleAnswer": "HTTP 메서드별 @Mapping",
                        "relatedSection": "codeFiles",
                    },
                    {
                        "questionId": "IQ-002",
                        "question": "PostService와 PostRepository 책임은?",
                        "keyPoints": ["Service", "Repository", "JPA"],
                        "sampleAnswer": "Service는 로직, Repository는 DB",
                        "relatedSection": "flow",
                    },
                    {
                        "questionId": "IQ-003",
                        "question": "존재하지 않는 postId 조회 시 status?",
                        "keyPoints": ["404", "NOT_FOUND"],
                        "sampleAnswer": "404 Not Found",
                        "relatedSection": "apiSpec",
                    },
                ],
                changed_fields=changed_fields,
                tag="crud",
            )

    elif bucket == JWT_AUTH_BUCKET:
        if request.includeMissions:
            _replace_off_topic_section_items(
                normalized,
                section="missions",
                forbidden=("/api/auth/signup", "signup", "postcontroller", "/api/posts"),
                replacement_factory=lambda: [
                    {
                        "missionId": "M-001",
                        "title": "JwtTokenProvider 구현",
                        "description": "미션 목표: login 시 access token 발급",
                        "missionType": "implementation",
                        "requirements": ["JwtTokenProvider", "createAccessToken"],
                        "successCriteria": ["POST /api/auth/login 응답에 token"],
                        "relatedRequirements": ["R-001"],
                        "difficulty": request.level.value,
                    },
                    {
                        "missionId": "M-002",
                        "title": "JwtAuthenticationFilter 연동",
                        "description": "미션 목표: Bearer 토큰 검증 후 SecurityContext 설정",
                        "missionType": "security",
                        "requirements": ["JwtAuthenticationFilter", "Bearer"],
                        "successCriteria": ["GET /api/users/me 인증 통과"],
                        "relatedRequirements": ["R-002"],
                        "difficulty": request.level.value,
                    },
                ],
                changed_fields=changed_fields,
                tag="jwt",
            )
        if request.includeInterview:
            _replace_off_topic_section_items(
                normalized,
                section="interviewQuestions",
                forbidden=("회원가입", "signup", "postrepository", "게시글"),
                replacement_factory=lambda: [
                    {
                        "questionId": "IQ-001",
                        "question": "JwtAuthenticationFilter는 어디서 동작하나?",
                        "keyPoints": ["Filter chain", "Bearer"],
                        "sampleAnswer": "요청마다 Authorization 헤더 검증",
                        "relatedSection": "flow",
                    },
                    {
                        "questionId": "IQ-002",
                        "question": "SecurityConfig에서 login endpoint는?",
                        "keyPoints": ["permitAll", "/api/auth/login"],
                        "sampleAnswer": "인증 없이 허용",
                        "relatedSection": "codeFiles",
                    },
                    {
                        "questionId": "IQ-003",
                        "question": "보호 API 호출 시 필요한 헤더는?",
                        "keyPoints": ["Authorization", "Bearer"],
                        "sampleAnswer": "Authorization: Bearer {token}",
                        "relatedSection": "apiSpec",
                    },
                ],
                changed_fields=changed_fields,
                tag="jwt",
            )

    recs = _BUCKET_NEXT_RECOMMENDATIONS.get(bucket)
    if recs:
        nxt = normalized.get("nextRecommendations")
        if not isinstance(nxt, list) or len(nxt) < 3:
            normalized["nextRecommendations"] = [dict(r) for r in recs]
            changed_fields.append(f"nextRecommendations[{bucket}-default]")
        else:
            blob = _section_text_blob(nxt).lower()
            wrong = (
                (bucket == SIGNUP_BUCKET and "postcontroller" in blob)
                or (bucket == CRUD_BUCKET and "/api/auth/login" in blob)
                or (bucket == JWT_AUTH_BUCKET and "/api/posts" in blob)
            )
            if wrong:
                normalized["nextRecommendations"] = [dict(r) for r in recs]
                changed_fields.append(f"nextRecommendations[{bucket}-cross-section]")


def apply_feature_bucket_guards(
    normalized: dict[str, Any],
    request: FeatureTemplateGenerateRequest | None,
    changed_fields: list[str],
) -> None:
    if request is None:
        return
    lang = (request.language or "").lower()
    fw = (request.framework or "").lower()
    if lang != "java" or "spring" not in fw.replace("_", "-"):
        return

    bucket = detect_feature_template_bucket(request.featureName, request.framework)
    if bucket == LOGIN_BUCKET:
        return

    if bucket == SIGNUP_BUCKET:
        _apply_signup_guard(normalized, request, changed_fields)
    elif bucket == CRUD_BUCKET:
        _apply_crud_guard(normalized, request, changed_fields)
    elif bucket == JWT_AUTH_BUCKET:
        _apply_jwt_guard(normalized, request, changed_fields)
    else:
        _apply_generic_guard(normalized, request, changed_fields)

    _apply_cross_section_consistency(normalized, request, bucket, changed_fields)


_BUCKET_PROMPTS: dict[str, str] = {
    "signup": (
        "현재 기능 bucket은 signup입니다.\n"
        "로그인 코드(login method, /api/auth/login, LoginRequest/LoginResponse)를 생성하지 마세요.\n"
        "반드시 SignupController, SignupService, SignupRequest, SignupResponse, User, UserRepository 중심으로 작성하세요.\n"
        "endpoint는 POST /api/auth/signup입니다. signup 메서드를 사용하세요."
    ),
    "crud": (
        "현재 기능 bucket은 crud입니다.\n"
        "인증/로그인 코드(/api/auth/login, username/password, UserRepository)를 생성하지 마세요.\n"
        "반드시 PostController, PostService, PostRepository, Post, PostCreateRequest, PostUpdateRequest, PostResponse 중심으로 작성하세요.\n"
        "endpoint는 /api/posts 계열입니다. CRUDController 같은 generic 이름을 쓰지 마세요."
    ),
    "jwt_auth": (
        "현재 기능 bucket은 jwt_auth입니다.\n"
        "중복 Controller 파일(JWTController 등)을 만들지 마세요.\n"
        "반드시 JwtTokenProvider, JwtAuthenticationFilter, SecurityConfig, CustomUserDetailsService, "
        "AuthController, LoginRequest, LoginResponse를 분리하세요.\n"
        "AuthController는 POST /api/auth/login endpoint를 제공하고, 보호 API 예시는 GET /api/users/me 입니다.\n"
        "POST /api/auth/signup endpoint는 jwt_auth bucket에 포함하지 마세요.\n"
        "fileName, filePath, public class명을 일치시키세요."
    ),
    "generic": (
        "현재 기능 bucket은 generic입니다.\n"
        "로그인 전용 /api/auth/login 코드를 무조건 생성하지 마세요.\n"
        "featureName에 맞는 Controller/Service/Request/Response와 endpoint를 작성하세요."
    ),
}


def build_bucket_prompt_constraints(request: FeatureTemplateGenerateRequest) -> str:
    bucket = detect_feature_template_bucket(request.featureName, request.framework)
    if bucket == LOGIN_BUCKET:
        return ""
    return _BUCKET_PROMPTS.get(bucket, _BUCKET_PROMPTS["generic"])

"""실습 미션 rule 기반 evidence 채점기."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.schemas.evaluation import (
    CodeIssueSchema,
    MissionFeedbackRequest,
    MissionFeedbackResponse,
    SubmittedCodeSchema,
)
from app.schemas.feature_template import RequirementSchema
from app.services.feature_template_bucket_guards import detect_feature_template_bucket
__all__ = ["MissionFeedbackGrader"]

_PASS_SCORE_THRESHOLD = 70

_SECURE_PASSWORD_KEYWORDS: tuple[str, ...] = (
    "encrypt",
    "hash",
    "bcrypt",
    "argon2",
    "scrypt",
    "pbkdf2",
    "passwordencoder",
    "encode(",
)


@dataclass(frozen=True)
class _EvidenceRule:
    key: str
    weight: int
    patterns: tuple[str, ...]
    critical: bool = False


_BUCKET_RULES: dict[str, tuple[_EvidenceRule, ...]] = {
    "signup": (
        _EvidenceRule("endpoint_signup", 20, (r"/api/auth/signup", r'@PostMapping\s*\(\s*"/signup"', r'mapping\s*\(\s*"/signup"'), critical=True),
        _EvidenceRule("controller", 15, (r"@RestController", r"@Controller", r"SignupController", r"AuthController"), critical=True),
        _EvidenceRule("post_mapping", 10, (r"@PostMapping", r"PostMapping")),
        _EvidenceRule("signup_request", 10, (r"SignupRequest", r"signup\s*\(", r"@RequestBody")),
        _EvidenceRule("service", 10, (r"SignupService", r"UserService")),
        _EvidenceRule("repository", 10, (r"UserRepository", r"JpaRepository")),
        _EvidenceRule("password_hash", 10, (r"PasswordEncoder", r"bcrypt", r"encode\s*\(")),
        _EvidenceRule("duplicate_check", 5, (r"existsByEmail", r"duplicate", r"409")),
    ),
    "crud": (
        _EvidenceRule("endpoint_posts", 15, (r"/api/posts", r'RequestMapping\s*\(\s*"/api/posts"'), critical=True),
        _EvidenceRule("controller", 15, (r"PostController", r"@RestController"), critical=True),
        _EvidenceRule("post_mapping", 8, (r"@PostMapping")),
        _EvidenceRule("get_mapping", 8, (r"@GetMapping")),
        _EvidenceRule("put_mapping", 8, (r"@PutMapping")),
        _EvidenceRule("delete_mapping", 8, (r"@DeleteMapping")),
        _EvidenceRule("service", 10, (r"PostService")),
        _EvidenceRule("repository", 10, (r"PostRepository")),
        _EvidenceRule("dto", 8, (r"PostCreateRequest", r"PostUpdateRequest", r"PostResponse", r"PostRequest")),
        _EvidenceRule("entity", 5, (r"class\s+Post\b", r"@Entity")),
    ),
    "jwt_auth": (
        _EvidenceRule("endpoint_login", 15, (r"/api/auth/login", r'@PostMapping\s*\(\s*"/login"'), critical=True),
        _EvidenceRule("endpoint_me", 10, (r"/api/users/me", r'@GetMapping\s*\(\s*"/me"'), critical=False),
        _EvidenceRule("controller", 15, (r"AuthController", r"@RestController"), critical=True),
        _EvidenceRule("jwt_provider", 12, (r"JwtTokenProvider", r"createAccessToken", r"generateToken")),
        _EvidenceRule("jwt_filter", 12, (r"JwtAuthenticationFilter", r"OncePerRequestFilter", r"Bearer")),
        _EvidenceRule("security_config", 10, (r"SecurityConfig", r"SecurityFilterChain", r"authorizeHttpRequests")),
        _EvidenceRule("user_details", 8, (r"UserDetailsService", r"CustomUserDetailsService", r"loadUserByUsername")),
        _EvidenceRule("login_dto", 8, (r"LoginRequest", r"LoginResponse")),
        _EvidenceRule("token_validation", 5, (r"validateToken", r"parseClaims", r"verify")),
    ),
}

_REQUIREMENT_HINTS: dict[str, tuple[str, ...]] = {
    "signup": (
        "email",
        "password",
        "nickname",
        "validation",
        "existsbyemail",
        "duplicate",
        "bcrypt",
        "hash",
        "signup",
        "repository",
    ),
    "crud": (
        "post",
        "create",
        "list",
        "update",
        "delete",
        "repository",
        "controller",
        "postid",
        "404",
    ),
    "jwt_auth": (
        "jwt",
        "token",
        "bearer",
        "login",
        "filter",
        "security",
        "authenticate",
        "authorization",
    ),
}


class MissionFeedbackGrader:
    """Evidence 기반 mission feedback 채점."""

    def grade(self, request: MissionFeedbackRequest) -> MissionFeedbackResponse:
        if not request.submittedCode or not any(f.content.strip() for f in request.submittedCode):
            return self._empty_submission_response(request)

        merged_code = "\n".join(f.content for f in request.submittedCode)
        merged_lower = merged_code.lower()
        bucket = detect_feature_template_bucket(request.featureName)

        satisfied, missing_reqs, req_score = self._grade_requirements(request, merged_lower, bucket)
        evidence_score, evidence_hits = self._grade_evidence(
            merged_code, merged_lower, bucket
        )
        api_issues, api_score = self._grade_api_specs(request, merged_code, merged_lower)
        code_issues = self._detect_code_issues(request.submittedCode, merged_lower)
        missing_requirements = [
            self._format_missing_requirement(req) for req in missing_reqs
        ]

        score = min(100, int(round(req_score * 0.35 + evidence_score * 0.45 + api_score * 0.20)))

        has_controller = self._has_controller_evidence(merged_code)
        has_critical_endpoint = self._has_critical_endpoint_evidence(
            request, merged_code, merged_lower, bucket
        )

        critical_issues = self._collect_critical_issues(
            missing=[req.name for req in missing_reqs],
            total_requirements=len(request.requirements),
            has_controller=has_controller,
            has_critical_endpoint=has_critical_endpoint,
            api_issues=api_issues,
            api_specs_count=len(request.apiSpecs),
            code_issues=code_issues,
        )

        passed = score >= _PASS_SCORE_THRESHOLD and not critical_issues

        summary = self._build_summary(
            passed=passed,
            score=score,
            satisfied_count=len(satisfied),
            total_requirements=len(request.requirements),
            evidence_hits=evidence_hits,
            api_issues=api_issues,
            code_issues=code_issues,
            critical_issues=critical_issues,
            missing_reqs=missing_reqs,
            bucket=bucket,
        )

        improvement_suggestions = self._build_suggestions(
            missing_reqs, api_issues, code_issues, evidence_hits, bucket, request
        )
        next_action = self._build_next_action(
            passed=passed,
            missing_reqs=missing_reqs,
            api_issues=api_issues,
            code_issues=code_issues,
            critical_issues=critical_issues,
            bucket=bucket,
            mission_title=(request.mission.title or "").strip(),
        )

        return MissionFeedbackResponse(
            passed=passed,
            score=score,
            summary=summary,
            satisfiedRequirements=satisfied,
            missingRequirements=missing_requirements,
            apiSpecIssues=api_issues,
            codeIssues=code_issues,
            improvementSuggestions=improvement_suggestions,
            nextAction=next_action,
        )

    def _empty_submission_response(
        self, request: MissionFeedbackRequest
    ) -> MissionFeedbackResponse:
        missing_requirements = [
            self._format_missing_requirement(req) for req in request.requirements
        ]
        return MissionFeedbackResponse(
            passed=False,
            score=0,
            summary=(
                "제출된 코드가 없어 미션을 평가할 수 없습니다. "
                "Controller·Service·Repository 흐름이 포함된 파일을 먼저 작성해야 합니다."
            ),
            satisfiedRequirements=[],
            missingRequirements=missing_requirements,
            apiSpecIssues=[
                self._format_api_spec_issue(spec.method or "GET", spec.endpoint or "/")
                for spec in request.apiSpecs
            ],
            codeIssues=[],
            improvementSuggestions=[
                "Controller에서 요청 DTO를 받고 Service로 비즈니스 로직을 분리하는 "
                "최소 구조부터 작성하세요.",
            ],
            nextAction="미션에 맞는 Controller·Service 파일을 작성한 뒤 다시 제출하세요.",
        )

    def _grade_requirements(
        self,
        request: MissionFeedbackRequest,
        merged_lower: str,
        bucket: str,
    ) -> tuple[list[str], list[RequirementSchema], float]:
        satisfied: list[str] = []
        missing: list[RequirementSchema] = []
        hints = _REQUIREMENT_HINTS.get(bucket, ())

        for req in request.requirements:
            name = (req.name or "").strip()
            if not name:
                continue
            desc = (req.description or "").lower()
            related = (req.relatedScreenOrApi or "").lower()
            tokens = self._requirement_tokens(name, desc, related, hints)

            hit = any(token in merged_lower for token in tokens if len(token) >= 2)
            if not hit and name.lower() in merged_lower:
                hit = True
            if hit:
                satisfied.append(req.name)
            else:
                missing.append(req)

        total = len(request.requirements)
        if total == 0:
            return satisfied, missing, 50.0
        ratio = len(satisfied) / total
        return satisfied, missing, ratio * 100

    @staticmethod
    def _format_missing_requirement(req: RequirementSchema) -> str:
        name = (req.name or "요구사항").strip()
        related = (req.relatedScreenOrApi or "").strip()
        description = (req.description or "").strip()

        if related.upper().startswith(("POST", "GET", "PUT", "DELETE", "PATCH")):
            return (
                f"'{name}' 요구사항이 코드에서 확인되지 않습니다. "
                f"기능 검증을 위해 {related} 구현이 필요합니다."
            )
        if related:
            return (
                f"'{name}' 요구사항이 코드에서 확인되지 않습니다. "
                f"{related} 계층/화면에 관련 로직이 반영되어야 합니다."
            )
        if description:
            short_desc = description[:80] + ("..." if len(description) > 80 else "")
            return (
                f"'{name}' 요구사항이 코드에서 확인되지 않습니다. "
                f"({short_desc})"
            )
        return f"'{name}' 요구사항이 제출 코드에서 확인되지 않습니다."

    @staticmethod
    def _format_api_spec_issue(method: str, endpoint: str) -> str:
        return (
            f"{method.upper()} {endpoint} API가 코드에서 확인되지 않습니다. "
            f"Controller에 해당 method/endpoint 매핑을 추가하세요."
        )

    def _build_summary(
        self,
        *,
        passed: bool,
        score: int,
        satisfied_count: int,
        total_requirements: int,
        evidence_hits: list[str],
        api_issues: list[str],
        code_issues: list[CodeIssueSchema],
        critical_issues: list[str],
        missing_reqs: list[RequirementSchema],
        bucket: str,
    ) -> str:
        fulfillment = (
            f"요구사항 {satisfied_count}/{total_requirements} 충족, "
            f"구현 근거(evidence) {len(evidence_hits)}건 확인"
        )

        top_problems: list[str] = []
        if critical_issues:
            top_problems.extend(critical_issues[:2])
        elif api_issues:
            top_problems.append(api_issues[0])
        elif missing_reqs:
            top_problems.append(self._format_missing_requirement(missing_reqs[0]))
        elif code_issues:
            top_problems.append(code_issues[0].message)

        if passed:
            next_hint = "다음 미션으로 넘어가도 됩니다."
            if bucket == "signup" and "password_hash" not in evidence_hits:
                next_hint = "비밀번호 해시 저장 여부를 한 번 더 점검한 뒤 다음 미션으로 진행하세요."
            return (
                f"{fulfillment}. score={score}. "
                f"핵심 Controller·API·Service 구조가 확인됩니다. {next_hint}"
            )

        problem_text = " / ".join(top_problems[:2]) if top_problems else "핵심 구현 요소가 부족합니다."
        first_fix = self._primary_fix_hint(
            missing_reqs=missing_reqs,
            api_issues=api_issues,
            code_issues=code_issues,
            critical_issues=critical_issues,
            bucket=bucket,
        )
        return (
            f"{fulfillment}, apiSpec 이슈 {len(api_issues)}건, "
            f"코드 이슈 {len(code_issues)}건. score={score}. "
            f"가장 큰 문제: {problem_text}. "
            f"우선 수정: {first_fix}"
        )

    @staticmethod
    def _primary_fix_hint(
        *,
        missing_reqs: list[RequirementSchema],
        api_issues: list[str],
        code_issues: list[CodeIssueSchema],
        critical_issues: list[str],
        bucket: str,
    ) -> str:
        if any("Controller" in issue for issue in critical_issues):
            return "Controller 클래스(@RestController)를 추가하고 API endpoint를 매핑하세요."
        if any("endpoint" in issue.lower() for issue in critical_issues):
            defaults = {
                "signup": "POST /api/auth/signup endpoint를 Controller에 추가하세요.",
                "crud": "GET /api/posts endpoint를 Controller에 추가하세요.",
                "jwt_auth": "POST /api/auth/login endpoint를 Controller에 추가하세요.",
            }
            return defaults.get(bucket, "핵심 API endpoint를 Controller에 매핑하세요.")
        if api_issues:
            return api_issues[0]
        if code_issues:
            return code_issues[0].suggestion or code_issues[0].message
        if missing_reqs:
            req = missing_reqs[0]
            related = (req.relatedScreenOrApi or "").strip()
            if related:
                return f"'{req.name}' 요구사항을 충족하도록 {related} 관련 코드를 추가하세요."
            return f"'{req.name}' 요구사항을 코드에 반영하세요."
        return "Controller → Service → Repository 흐름부터 다시 정리하세요."

    @staticmethod
    def _requirement_tokens(
        name: str,
        desc: str,
        related: str,
        bucket_hints: tuple[str, ...],
    ) -> list[str]:
        raw = f"{name} {desc} {related}".lower()
        tokens = re.findall(r"[a-z0-9가-힣]{2,}", raw)
        extra = [h for h in bucket_hints if h in desc or h in related.lower()]
        return list(dict.fromkeys(tokens + extra))

    def _grade_evidence(
        self,
        merged_code: str,
        merged_lower: str,
        bucket: str,
    ) -> tuple[float, list[str]]:
        """evidence는 점수 가중치에만 반영. 개수 부족만으로 passed를 막지 않는다."""

        rules = _BUCKET_RULES.get(bucket)
        if not rules:
            rules = self._generic_rules(merged_lower)

        hits: list[str] = []
        earned = 0
        max_score = sum(r.weight for r in rules)

        for rule in rules:
            matched = any(re.search(p, merged_code, re.IGNORECASE) for p in rule.patterns)
            if matched:
                earned += rule.weight
                hits.append(rule.key)

        if max_score == 0:
            return 0.0, hits
        return (earned / max_score) * 100, hits

    @staticmethod
    def _has_controller_evidence(merged_code: str) -> bool:
        return bool(re.search(r"@RestController|@Controller", merged_code, re.IGNORECASE))

    @staticmethod
    def _collect_critical_issues(
        *,
        missing: list[str],
        total_requirements: int,
        has_controller: bool,
        has_critical_endpoint: bool,
        api_issues: list[str],
        api_specs_count: int,
        code_issues: list[CodeIssueSchema],
    ) -> list[str]:
        """passed=false를 유발하는 명확한 critical issue만 수집."""

        critical: list[str] = []
        if not has_controller:
            critical.append("핵심 Controller가 제출 코드에서 발견되지 않습니다.")
        if not has_critical_endpoint:
            critical.append("핵심 API endpoint가 제출 코드에서 발견되지 않습니다.")
        if total_requirements >= 3 and len(missing) / total_requirements > 0.7:
            critical.append("요구사항 대부분이 코드 근거로 확인되지 않습니다.")
        if api_specs_count > 0 and len(api_issues) >= api_specs_count:
            critical.append("apiSpec과 코드가 완전히 불일치합니다.")
        for issue in code_issues:
            if (issue.severity or "").lower() in {"critical", "error"}:
                critical.append(issue.message)
        return critical

    @staticmethod
    def _generic_rules(merged_lower: str) -> tuple[_EvidenceRule, ...]:
        rules: list[_EvidenceRule] = [
            _EvidenceRule("controller", 20, (r"@RestController", r"@Controller"), critical=True),
            _EvidenceRule("service", 15, (r"Service", r"@Service")),
            _EvidenceRule("mapping", 15, (r"@PostMapping", r"@GetMapping", r"@PutMapping", r"@DeleteMapping")),
        ]
        if "repository" in merged_lower or "jpa" in merged_lower:
            rules.append(_EvidenceRule("repository", 10, (r"Repository", r"JpaRepository")))
        return tuple(rules)

    def _grade_api_specs(
        self,
        request: MissionFeedbackRequest,
        merged_code: str,
        merged_lower: str,
    ) -> tuple[list[str], float]:
        if not request.apiSpecs:
            return [], 80.0

        issues: list[str] = []
        matched = 0
        for spec in request.apiSpecs:
            endpoint = (spec.endpoint or "").strip()
            method = (spec.method or "GET").upper()
            if not endpoint:
                continue
            if self._endpoint_in_code(endpoint, method, merged_code, merged_lower):
                matched += 1
            else:
                issues.append(
                    self._format_api_spec_issue(method, endpoint)
                )

        total = len(request.apiSpecs)
        score = (matched / total) * 100 if total else 80.0
        return issues, score

    @staticmethod
    def _endpoint_in_code(
        endpoint: str,
        method: str,
        merged_code: str,
        merged_lower: str,
    ) -> bool:
        if endpoint in merged_code:
            return True

        ep_low = endpoint.lower()
        if ep_low in merged_lower:
            return True

        segments = [s for s in re.split(r"[/{}\s]+", endpoint) if s and s not in ("api", "{id}")]
        if segments and all(seg.lower() in merged_lower for seg in segments if len(seg) > 2):
            mapping_hints = {
                "POST": ("postmapping", "post"),
                "GET": ("getmapping", "get"),
                "PUT": ("putmapping", "put"),
                "DELETE": ("deletemapping", "delete"),
            }
            hints = mapping_hints.get(method, ())
            if any(h in merged_lower for h in hints):
                return True

        tail = endpoint.rstrip("/").rsplit("/", 1)[-1]
        if tail and len(tail) >= 3 and tail.lower() in merged_lower:
            return True
        return False

    def _has_critical_endpoint_evidence(
        self,
        request: MissionFeedbackRequest,
        merged_code: str,
        merged_lower: str,
        bucket: str,
    ) -> bool:
        if request.apiSpecs:
            for spec in request.apiSpecs[:2]:
                if self._endpoint_in_code(
                    spec.endpoint or "",
                    (spec.method or "GET").upper(),
                    merged_code,
                    merged_lower,
                ):
                    return True

        defaults = {
            "signup": ("/api/auth/signup", "POST"),
            "crud": ("/api/posts", "GET"),
            "jwt_auth": ("/api/auth/login", "POST"),
        }
        ep, method = defaults.get(bucket, ("", ""))
        if ep:
            return self._endpoint_in_code(ep, method, merged_code, merged_lower)
        return bool(re.search(r"@(?:Post|Get|Put|Delete)Mapping", merged_code, re.IGNORECASE))

    @staticmethod
    def _detect_code_issues(
        files: list[SubmittedCodeSchema],
        merged_lower: str,
    ) -> list[CodeIssueSchema]:
        issues: list[CodeIssueSchema] = []
        if "password" in merged_lower and not any(
            keyword in merged_lower for keyword in _SECURE_PASSWORD_KEYWORDS
        ):
            offending = next(
                (f.fileName for f in files if "password" in f.content.lower()),
                None,
            )
            issues.append(
                CodeIssueSchema(
                    fileName=offending,
                    line=None,
                    severity="warning",
                    message=(
                        "비밀번호 처리 코드에 해시/암호화 키워드가 없습니다. "
                        "평문 저장·로그 노출 위험이 있습니다."
                    ),
                    suggestion=(
                        "PasswordEncoder(BCrypt 등)로 encode() 후 저장하고, "
                        "응답·로그에 비밀번호를 노출하지 마세요."
                    ),
                )
            )
        return issues

    @staticmethod
    def _build_suggestions(
        missing_reqs: list[RequirementSchema],
        api_issues: list[str],
        code_issues: list[CodeIssueSchema],
        evidence_hits: list[str],
        bucket: str,
        request: MissionFeedbackRequest,
    ) -> list[str]:
        suggestions: list[str] = []
        if missing_reqs:
            first = missing_reqs[0]
            related = (first.relatedScreenOrApi or "").strip()
            if related.upper().startswith(("POST", "GET", "PUT", "DELETE", "PATCH")):
                suggestions.append(
                    f"'{first.name}' 요구사항을 충족하도록 {related} endpoint와 "
                    f"연결된 Service 로직을 추가하세요."
                )
            else:
                suggestions.append(
                    f"'{first.name}' 요구사항을 코드에 반영하세요. "
                    f"관련 위치: {related or 'Controller/Service'}"
                )
            if len(missing_reqs) > 1:
                others = ", ".join(req.name for req in missing_reqs[1:4])
                suggestions.append(f"이어서 다음 요구사항도 확인하세요: {others}")
        if api_issues:
            suggestions.append(
                "Controller의 @PostMapping/@GetMapping 등 HTTP method 매핑이 "
                "apiSpec endpoint와 일치하는지 대조하세요."
            )
        if code_issues:
            for issue in code_issues[:2]:
                suggestions.append(issue.suggestion or issue.message)
        if not suggestions:
            mission_title = (request.mission.title or "현재 미션").strip()
            suggestions.append(
                f"'{mission_title}' 핵심 요구사항을 충족했습니다. "
                f"다음 미션에서 예외 처리·검증 강화를 연습해 보세요."
            )
        if bucket == "signup" and "password_hash" not in evidence_hits:
            suggestions.append(
                "SignupService에서 PasswordEncoder.encode()로 비밀번호를 해시 저장하는지 확인하세요."
            )
        return suggestions

    @staticmethod
    def _build_next_action(
        *,
        passed: bool,
        missing_reqs: list[RequirementSchema],
        api_issues: list[str],
        code_issues: list[CodeIssueSchema],
        critical_issues: list[str],
        bucket: str,
        mission_title: str,
    ) -> str:
        if passed:
            if bucket == "jwt_auth":
                return "토큰 만료·리프레시 정책을 추가해 JWT 인증 흐름을 심화 학습하세요."
            if bucket == "crud":
                return "404/400 예외 응답을 추가해 CRUD API 완성도를 높여 보세요."
            if bucket == "signup":
                return "입력값 검증(@Valid)과 중복 이메일(409) 처리를 점검한 뒤 다음 미션으로 진행하세요."
            return f"'{mission_title or '현재 미션'}'을 충족했습니다. 다음 미션으로 진행하세요."

        if any("Controller" in issue for issue in critical_issues):
            return "가장 먼저 @RestController 클래스를 만들고 API endpoint를 매핑하세요."
        if any("endpoint" in issue.lower() for issue in critical_issues):
            defaults = {
                "signup": "가장 먼저 POST /api/auth/signup endpoint를 Controller에 추가하세요.",
                "crud": "가장 먼저 GET /api/posts endpoint를 Controller에 추가하세요.",
                "jwt_auth": "가장 먼저 POST /api/auth/login endpoint를 Controller에 추가하세요.",
            }
            return defaults.get(bucket, "가장 먼저 핵심 API endpoint를 Controller에 매핑하세요.")
        if api_issues:
            return f"가장 먼저 {api_issues[0].split(' API')[0]} 구현부터 맞추세요."
        if code_issues:
            return f"가장 먼저 {code_issues[0].suggestion or code_issues[0].message}"
        if missing_reqs:
            req = missing_reqs[0]
            related = (req.relatedScreenOrApi or "").strip()
            if related:
                return f"가장 먼저 '{req.name}' 요구사항을 충족하도록 {related} 관련 코드를 추가하세요."
            return f"가장 먼저 '{req.name}' 요구사항을 코드에 반영하세요."
        return "Controller → Service → Repository 순서로 최소 동작 흐름을 완성한 뒤 재제출하세요."

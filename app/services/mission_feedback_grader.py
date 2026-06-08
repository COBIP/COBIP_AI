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
from app.services.feature_template_bucket_guards import detect_feature_template_bucket
__all__ = ["MissionFeedbackGrader"]

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

        satisfied, missing, req_score = self._grade_requirements(request, merged_lower, bucket)
        evidence_score, evidence_hits, critical_misses = self._grade_evidence(
            merged_code, merged_lower, bucket
        )
        api_issues, api_score = self._grade_api_specs(request, merged_code, merged_lower)
        code_issues = self._detect_code_issues(request.submittedCode, merged_lower)

        score = min(100, int(round(req_score * 0.35 + evidence_score * 0.45 + api_score * 0.20)))

        has_controller = bool(
            re.search(r"@RestController|@Controller", merged_code, re.IGNORECASE)
        )
        has_critical_endpoint = self._has_critical_endpoint_evidence(
            request, merged_code, merged_lower, bucket
        )

        critical_issues: list[str] = []
        if not has_controller:
            critical_issues.append("핵심 Controller가 제출 코드에서 발견되지 않습니다.")
        if not has_critical_endpoint:
            critical_issues.append("핵심 API endpoint가 제출 코드에서 발견되지 않습니다.")
        if critical_misses:
            critical_issues.extend(critical_misses)
        total_req = len(request.requirements)
        if total_req >= 3 and len(missing) / total_req > 0.7:
            critical_issues.append("요구사항 대부분이 코드 근거로 확인되지 않습니다.")

        passed = score >= 70 and not critical_issues

        summary = (
            f"요구사항 {len(satisfied)}/{len(request.requirements)} 만족, "
            f"evidence {len(evidence_hits)}건, "
            f"apiSpec 이슈 {len(api_issues)}건, "
            f"코드 이슈 {len(code_issues)}건. score={score}"
        )

        improvement_suggestions = self._build_suggestions(
            missing, api_issues, code_issues, evidence_hits, bucket
        )
        next_action = (
            "다음 미션을 진행해도 됩니다."
            if passed
            else "지적된 부분을 보완한 후 재제출하세요."
        )

        return MissionFeedbackResponse(
            passed=passed,
            score=score,
            summary=summary,
            satisfiedRequirements=satisfied,
            missingRequirements=missing,
            apiSpecIssues=api_issues,
            codeIssues=code_issues,
            improvementSuggestions=improvement_suggestions,
            nextAction=next_action,
        )

    def _empty_submission_response(
        self, request: MissionFeedbackRequest
    ) -> MissionFeedbackResponse:
        return MissionFeedbackResponse(
            passed=False,
            score=0,
            summary="제출된 코드가 없습니다.",
            satisfiedRequirements=[],
            missingRequirements=[req.name for req in request.requirements],
            apiSpecIssues=[
                f"{spec.method} {spec.endpoint} 미구현"
                for spec in request.apiSpecs
            ],
            codeIssues=[],
            improvementSuggestions=[
                "제출한 코드 파일이 비어 있지 않은지 확인하세요.",
            ],
            nextAction="코드를 작성한 뒤 다시 제출해 주세요.",
        )

    def _grade_requirements(
        self,
        request: MissionFeedbackRequest,
        merged_lower: str,
        bucket: str,
    ) -> tuple[list[str], list[str], float]:
        satisfied: list[str] = []
        missing: list[str] = []
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
                missing.append(req.name)

        total = len(request.requirements)
        if total == 0:
            return satisfied, missing, 50.0
        ratio = len(satisfied) / total
        return satisfied, missing, ratio * 100

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
    ) -> tuple[float, list[str], list[str]]:
        rules = _BUCKET_RULES.get(bucket)
        if not rules:
            rules = self._generic_rules(merged_lower)

        hits: list[str] = []
        critical_misses: list[str] = []
        earned = 0
        max_score = sum(r.weight for r in rules)

        for rule in rules:
            matched = any(re.search(p, merged_code, re.IGNORECASE) for p in rule.patterns)
            if matched:
                earned += rule.weight
                hits.append(rule.key)
            elif rule.critical:
                critical_misses.append(f"핵심 evidence 누락: {rule.key}")

        if max_score == 0:
            return 0.0, hits, critical_misses
        return (earned / max_score) * 100, hits, critical_misses

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
                    f"{method} {endpoint} endpoint 가 제출 코드에서 발견되지 않습니다."
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
                        "코드에 'password' 가 등장하지만 해시/암호화 관련 키워드"
                        "(encrypt, hash, bcrypt, PasswordEncoder 등) 가 발견되지 않았습니다."
                    ),
                    suggestion=(
                        "BCrypt 등 단방향 해시 알고리즘을 사용하고 비밀번호 평문 저장·노출"
                        "을 피하세요."
                    ),
                )
            )
        return issues

    @staticmethod
    def _build_suggestions(
        missing: list[str],
        api_issues: list[str],
        code_issues: list[CodeIssueSchema],
        evidence_hits: list[str],
        bucket: str,
    ) -> list[str]:
        suggestions: list[str] = []
        if missing:
            suggestions.append(
                "다음 요구사항을 코드에 반영하세요: " + ", ".join(missing[:5])
            )
        if api_issues:
            suggestions.append(
                "API 명세서의 method/endpoint 와 코드 구현을 일치시키세요."
            )
        if code_issues:
            suggestions.append(
                "보안·예외 처리 등 코드 이슈를 우선 해결하세요."
            )
        if not suggestions:
            suggestions.append(
                "기본 요구사항을 충족했습니다. 다음 미션으로 도전해 보세요."
            )
        if bucket == "signup" and "password_hash" not in evidence_hits:
            suggestions.append("PasswordEncoder로 비밀번호를 해시 저장하는지 확인하세요.")
        return suggestions

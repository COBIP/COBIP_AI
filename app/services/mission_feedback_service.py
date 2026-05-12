"""실습 미션 피드백 service.

이 단계에서는 실제 외부 LLM 없이 단순 키워드/문자열 매칭 rule 로 구현한다.
복잡한 정적 분석 도구 연동은 추후 단계에서 추가한다.
"""

from app.schemas.evaluation import (
    CodeIssueSchema,
    MissionFeedbackRequest,
    MissionFeedbackResponse,
    SubmittedCodeSchema,
)

__all__ = ["MissionFeedbackService"]


_SECURE_PASSWORD_KEYWORDS: tuple[str, ...] = (
    "encrypt",
    "hash",
    "bcrypt",
    "argon2",
    "scrypt",
    "pbkdf2",
    "passwordencoder",
)


class MissionFeedbackService:
    """실습 미션 코드 피드백 service (rule 기반 mock 단계)."""

    def generate_feedback(
        self,
        request: MissionFeedbackRequest,
    ) -> MissionFeedbackResponse:
        # ------------------------------------------------------------------
        # rule 1: submittedCode 가 비어 있으면 즉시 실패 처리
        # ------------------------------------------------------------------
        if not request.submittedCode:
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

        merged_code = "\n".join(f.content for f in request.submittedCode)
        merged_lower = merged_code.lower()

        # ------------------------------------------------------------------
        # rule 2: requirements 키워드 매칭
        #   각 requirement.name 의 소문자 토큰이 코드에 등장하면 만족으로 판정
        # ------------------------------------------------------------------
        satisfied: list[str] = []
        missing: list[str] = []
        for req in request.requirements:
            keyword = req.name.strip()
            if not keyword:
                continue
            if keyword.lower() in merged_lower:
                satisfied.append(req.name)
            else:
                missing.append(req.name)

        # ------------------------------------------------------------------
        # rule 3: apiSpec endpoint 문자열이 코드에 없으면 이슈 추가
        # ------------------------------------------------------------------
        api_spec_issues: list[str] = []
        for spec in request.apiSpecs:
            endpoint = (spec.endpoint or "").strip()
            if endpoint and endpoint not in merged_code:
                api_spec_issues.append(
                    f"{spec.method} {endpoint} endpoint 가 제출 코드에서 발견되지 않습니다."
                )

        # ------------------------------------------------------------------
        # rule 4: password 가 있는데 encrypt/hash/bcrypt 등이 없으면 보안 이슈
        # ------------------------------------------------------------------
        code_issues: list[CodeIssueSchema] = []
        if "password" in merged_lower and not any(
            keyword in merged_lower for keyword in _SECURE_PASSWORD_KEYWORDS
        ):
            offending_file = self._find_first_file_containing(
                request.submittedCode,
                "password",
            )
            code_issues.append(
                CodeIssueSchema(
                    fileName=offending_file,
                    line=None,
                    severity="warning",
                    message=(
                        "코드에 'password' 가 등장하지만 해시/암호화 관련 키워드"
                        "(encrypt, hash, bcrypt 등) 가 발견되지 않았습니다."
                    ),
                    suggestion=(
                        "BCrypt 등 단방향 해시 알고리즘을 사용하고 비밀번호 평문 저장·노출"
                        "을 피하세요."
                    ),
                )
            )

        # ------------------------------------------------------------------
        # 점수·통과 여부 산정
        # ------------------------------------------------------------------
        total_requirements = len(request.requirements)
        satisfied_count = len(satisfied)
        if total_requirements > 0:
            score = int(round(100 * satisfied_count / total_requirements))
        else:
            score = 0

        passed = (
            total_requirements > 0
            and satisfied_count == total_requirements
            and not api_spec_issues
            and not code_issues
        )

        summary = (
            f"요구사항 {satisfied_count}/{total_requirements} 만족, "
            f"apiSpec 이슈 {len(api_spec_issues)}건, "
            f"코드 이슈 {len(code_issues)}건."
        )

        improvement_suggestions: list[str] = []
        if missing:
            improvement_suggestions.append(
                "다음 요구사항을 코드에 반영하세요: " + ", ".join(missing)
            )
        if api_spec_issues:
            improvement_suggestions.append(
                "API 명세서의 method/endpoint 와 코드 구현을 일치시키세요."
            )
        if code_issues:
            improvement_suggestions.append(
                "보안·예외 처리 등 코드 이슈를 우선 해결하세요."
            )
        if not improvement_suggestions:
            improvement_suggestions.append(
                "기본 요구사항을 충족했습니다. 다음 미션으로 도전해 보세요."
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
            apiSpecIssues=api_spec_issues,
            codeIssues=code_issues,
            improvementSuggestions=improvement_suggestions,
            nextAction=next_action,
        )

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _find_first_file_containing(
        files: list[SubmittedCodeSchema],
        keyword: str,
    ) -> str | None:
        keyword_lower = keyword.lower()
        for file in files:
            if keyword_lower in file.content.lower():
                return file.fileName
        return None

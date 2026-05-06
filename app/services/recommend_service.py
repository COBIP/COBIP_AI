"""다음 기능템플릿 추천 service.

이 단계에서는 실제 RAG/Qdrant 검색 없이 키워드 매칭 rule 로 구현한다.
실제 RAG 연동은 추후 단계에서 추가한다.
"""

from app.schemas.recommend import (
    RecommendNextTemplateRequest,
    RecommendNextTemplateResponse,
)

__all__ = ["RecommendService"]


_LOGIN_RELATED_KEYWORDS: tuple[str, ...] = (
    "로그인",
    "login",
    "signin",
    "auth",
    "인증",
)


class RecommendService:
    """다음 기능템플릿 추천 service (rule 기반 mock 단계)."""

    def recommend(
        self,
        request: RecommendNextTemplateRequest,
    ) -> RecommendNextTemplateResponse:
        current_lower = (request.currentFeatureName or "").lower()
        is_login_related = any(
            keyword in current_lower for keyword in _LOGIN_RELATED_KEYWORDS
        )

        if is_login_related:
            recommendations = self._login_recommendations()
        else:
            recommendations = self._generic_recommendations()

        return RecommendNextTemplateResponse(recommendations=recommendations)

    # ------------------------------------------------------------------
    # internal recommendation builders
    # ------------------------------------------------------------------
    def _login_recommendations(self) -> list[dict]:
        # 로그인을 학습한 사용자에게 "다음 단계로 넘어가는" 추천만 제공한다.
        # JWT 로그인·로그아웃처럼 로그인의 변형/구성요소는 의도적으로 제외한다.
        return [
            {
                "featureName": "회원가입",
                "reason": (
                    "로그인을 학습했다면 그 짝이 되는 사용자 생성 흐름이 자연스러운 다음 단계입니다. "
                    "비밀번호 해시 저장·중복 검증 등 새 패턴을 추가로 익힙니다."
                ),
            },
            {
                "featureName": "마이페이지",
                "reason": (
                    "로그인된 사용자에게만 노출되는 화면을 구현하면서, "
                    "인증 토큰을 활용해 사용자 정보를 조회·표시하는 흐름으로 한 단계 확장합니다."
                ),
            },
            {
                "featureName": "게시판 CRUD",
                "reason": (
                    "로그인 사용자가 실제로 무엇을 할 수 있는지를 만드는 단계입니다. "
                    "인증된 사용자의 글 작성·수정·삭제 권한 처리까지 종합 학습합니다."
                ),
            },
            {
                "featureName": "권한 관리",
                "reason": (
                    "인증(누구인가)을 끝낸 다음 단계인 인가(무엇을 할 수 있는가)로 넘어갑니다. "
                    "역할(Role) 기반 접근 제어를 도입해 시스템을 본격 운영형으로 확장합니다."
                ),
            },
        ]

    def _generic_recommendations(self) -> list[dict]:
        return [
            {
                "featureName": "CRUD",
                "reason": (
                    "백엔드의 기본 데이터 처리 흐름(Controller → Service → Repository → DB)을 "
                    "종합적으로 학습합니다."
                ),
            },
            {
                "featureName": "검색",
                "reason": (
                    "쿼리 파라미터·페이지네이션·정렬을 다루며 실무형 조회 패턴을 익힙니다."
                ),
            },
            {
                "featureName": "파일 업로드",
                "reason": (
                    "Multipart 처리·파일 저장소 설계·확장자/용량 검증 등 별도 도메인 지식을 "
                    "학습합니다."
                ),
            },
            {
                "featureName": "댓글 기능",
                "reason": (
                    "1:N 관계 모델링과 사용자 권한 검증, CRUD 응용을 함께 학습할 수 있습니다."
                ),
            },
        ]

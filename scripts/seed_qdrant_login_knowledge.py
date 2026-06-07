"""Spring Boot 로그인 기능 지식 seed script (Agentic RAG 14차).

Qdrant 컬렉션에 로그인 기능 기준 초기 지식 문서를 upsert한다.
기본 동작은 **dry-run** — 외부 서비스(Qdrant/Embedding 모델)에 접근하지 않고
문서 목록·payload preview·deterministic id만 출력한다.

실제 upsert를 수행하려면 ``--apply`` 플래그를 명시적으로 지정해야 한다.

운영 안전 원칙(14차):

- 기본 동작은 항상 dry-run. ``--apply``가 없으면 외부 import도 일어나지 않는다.
- 기존 Qdrant collection을 drop / recreate 하지 않는다.
- ``ensure_collection``으로 없을 때만 Cosine 거리로 새로 만든다.
- vector size는 embedding 결과 길이로 동적으로 결정한다.
- point id는 ``uuid.uuid5``로 deterministic 하게 부여하여 재실행 시 중복 생성되지 않는다.

사용 예:

    # 안전 점검 (외부 서비스 호출 없음)
    python scripts/seed_qdrant_login_knowledge.py --dry-run

    # 실제 upsert (사용자가 명시한 경우에만)
    python scripts/seed_qdrant_login_knowledge.py --apply --collection cobip_knowledge

    # docs/rag/feature-template 마크다운 원본도 함께 upsert
    python scripts/seed_qdrant_login_knowledge.py --apply --include-feature-template-docs
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import uuid
from dataclasses import dataclass
from typing import Any

__all__ = [
    "SEED_NAMESPACE",
    "SeedDocument",
    "apply_seed_upsert",
    "build_login_seed_documents",
    "build_payload",
    "build_point_id",
    "describe_documents",
    "main",
]

logger = logging.getLogger(__name__)

# 안정적인 namespace UUID (랜덤 1회 생성 후 고정)
SEED_NAMESPACE = uuid.UUID("d7c1f3fd-1bcf-4e0e-9b53-2bbb6e8a1e10")

_PREVIEW_CHARS = 140


@dataclass(frozen=True)
class SeedDocument:
    """seed 지식 문서 1건. 모든 필드는 Qdrant payload + 변환 단계에 그대로 쓰인다."""

    title: str
    content: str
    doc_type: str
    section: str
    framework: str
    language: str
    feature_name: str
    level: str
    path: str
    tags: tuple[str, ...]


def build_login_seed_documents() -> list[SeedDocument]:
    """Spring Boot 로그인 기능 학습용 초기 지식 문서 세트.

    13차 ``rag_service._hit_to_reference``가 사용하는 metadata 키
    (``docType``/``section``/``fileName``/``path``/``url``)와 호환되도록 작성한다.
    """

    framework = "Spring Boot"
    language = "Java"
    feature_name = "로그인"
    level = "beginner"
    doc_type = "feature_template_reference"

    return [
        SeedDocument(
            title="Spring Boot 로그인 요구사항 개요",
            content=(
                "Spring Boot 기반 로그인 기능은 사용자가 이메일과 비밀번호를 입력하면 "
                "서버가 자격증명을 검증하고 JWT accessToken을 발급해 인증 상태를 유지하도록 한다. "
                "학습 목표는 Spring Security 필터 체인, 비밀번호 해시 검증, JWT 발급/검증 흐름을 "
                "Controller-Service-Repository 계층 구조로 구현하면서 익히는 것이다. "
                "필수 요구사항은 이메일/비밀번호 입력 검증, BCrypt 비교, 성공 시 200과 토큰 응답, "
                "실패 시 401 응답, 토큰 만료 처리, 비밀번호 평문 저장 금지를 포함한다."
            ),
            doc_type=doc_type,
            section="requirements",
            framework=framework,
            language=language,
            feature_name=feature_name,
            level=level,
            path="seed/spring-boot-login/requirements",
            tags=("login", "spring-boot", "requirements", "jwt", "spring-security"),
        ),
        SeedDocument(
            title="POST /api/auth/login API 명세",
            content=(
                "로그인 API는 POST /api/auth/login 경로로 제공된다. "
                "요청 본문은 application/json이며 email(string)과 password(string) 두 필드를 받는다. "
                "성공 응답은 200 OK이며 본문은 accessToken(string), tokenType(\"Bearer\"), expiresIn(int seconds), "
                "user 객체(id, email, nickname)를 포함한다. "
                "실패 응답은 400(요청 본문 검증 실패), 401(자격증명 불일치), 500(서버 오류)을 사용한다. "
                "응답 헤더 Content-Type은 application/json이며 토큰은 Authorization: Bearer <accessToken> 헤더로 후속 요청에 사용한다."
            ),
            doc_type=doc_type,
            section="apiSpec",
            framework=framework,
            language=language,
            feature_name=feature_name,
            level=level,
            path="seed/spring-boot-login/api-spec",
            tags=("login", "api", "rest", "jwt", "http"),
        ),
        SeedDocument(
            title="LoginRequest / LoginResponse DTO 구조",
            content=(
                "LoginRequest DTO는 email(@Email, @NotBlank)과 password(@NotBlank, @Size(min=8)) 두 필드를 "
                "가지며 Jakarta Validation으로 입력 검증을 수행한다. "
                "LoginResponse DTO는 accessToken, tokenType, expiresIn, UserSummary user를 갖는다. "
                "UserSummary는 id(Long), email(String), nickname(String)을 노출하고 비밀번호 해시 등 민감 정보는 절대 포함하지 않는다. "
                "Lombok @Getter @Builder를 활용하면 보일러플레이트를 줄이고 불변성을 유지할 수 있다. "
                "DTO와 Entity는 별도로 두고 서비스 레이어에서 매핑한다."
            ),
            doc_type=doc_type,
            section="codeFiles",
            framework=framework,
            language=language,
            feature_name=feature_name,
            level=level,
            path="seed/spring-boot-login/dto",
            tags=("login", "dto", "validation", "lombok", "jakarta-validation"),
        ),
        SeedDocument(
            title="Controller-Service-Repository 계층 흐름",
            content=(
                "로그인 요청은 LoginController가 받아 LoginService.login(LoginRequest)에 위임한다. "
                "LoginService는 UserRepository.findByEmail로 사용자 조회 후 PasswordEncoder.matches로 BCrypt 검증을 수행한다. "
                "검증 통과 시 JwtTokenProvider.createAccessToken으로 토큰을 만들고 LoginResponse로 변환해 반환한다. "
                "Controller는 ResponseEntity<ApiResponse<LoginResponse>>로 응답하며, "
                "Service는 비즈니스 예외(InvalidCredentialsException 등)를 던지고 GlobalExceptionHandler가 HTTP 상태 코드로 매핑한다. "
                "Repository는 Spring Data JPA UserRepository extends JpaRepository<User, Long> 구조를 사용한다."
            ),
            doc_type=doc_type,
            section="flow",
            framework=framework,
            language=language,
            feature_name=feature_name,
            level=level,
            path="seed/spring-boot-login/layers",
            tags=("login", "controller", "service", "repository", "layered-architecture"),
        ),
        SeedDocument(
            title="BCrypt 비밀번호 해시 검증",
            content=(
                "사용자 비밀번호는 평문으로 절대 저장하지 않고 BCrypt 해시로 저장한다. "
                "회원가입 시 PasswordEncoder.encode(rawPassword)로 해시화한 결과를 User.password 컬럼에 저장한다. "
                "로그인 시에는 PasswordEncoder.matches(rawPassword, storedHash)로 비교하며, BCrypt는 내부적으로 salt를 포함해 매번 다른 해시를 만든다. "
                "Spring Security BCryptPasswordEncoder를 @Bean으로 등록해 DI로 주입받는 패턴이 권장된다. "
                "BCrypt strength(work factor)는 기본 10 정도가 일반적이며, 너무 높이면 응답 지연이 커지므로 운영 환경에 맞춰 조정한다."
            ),
            doc_type=doc_type,
            section="codeFiles",
            framework=framework,
            language=language,
            feature_name=feature_name,
            level=level,
            path="seed/spring-boot-login/bcrypt",
            tags=("login", "bcrypt", "password", "spring-security", "security"),
        ),
        SeedDocument(
            title="JWT accessToken / tokenType / user 응답 구조",
            content=(
                "로그인 성공 응답은 JWT 기반으로 구성한다. accessToken은 HS256 또는 RS256 서명 알고리즘으로 발급되며 "
                "subject(sub)에는 userId, claims에는 email/role 등을 담는다. "
                "tokenType은 항상 \"Bearer\"로 고정하고, expiresIn은 초 단위로 토큰 만료 시간을 표현한다(예: 3600). "
                "user 객체는 클라이언트가 화면 표시에 사용할 최소 정보(id, email, nickname)만 포함한다. "
                "refreshToken은 필요 시 별도 응답 필드와 Set-Cookie HttpOnly로 전달하며 accessToken과 만료 정책을 분리한다. "
                "JWT secret/private key는 환경변수로 관리하고 소스에 하드코딩하지 않는다."
            ),
            doc_type=doc_type,
            section="apiSpec",
            framework=framework,
            language=language,
            feature_name=feature_name,
            level=level,
            path="seed/spring-boot-login/jwt-response",
            tags=("login", "jwt", "token", "auth", "bearer"),
        ),
        SeedDocument(
            title="로그인 실패 400 / 401 에러 처리",
            content=(
                "로그인 실패는 HTTP 상태 코드로 명확히 구분한다. 요청 본문이 검증 규칙(@Email, @NotBlank, @Size)을 위반하면 400 Bad Request이며 "
                "GlobalExceptionHandler가 MethodArgumentNotValidException을 잡아 필드별 오류 메시지를 표준 ApiResponse 형식으로 반환한다. "
                "사용자 없음 또는 비밀번호 불일치는 보안상 둘을 구분하지 않고 401 Unauthorized로 동일한 InvalidCredentialsException을 던진다. "
                "에러 응답 본문은 success=false, message, errorCode, fieldErrors(필요 시)로 일관된 구조를 유지한다. "
                "예상치 못한 예외는 500 Internal Server Error로 매핑하되 상세 스택트레이스는 응답에 노출하지 않고 서버 로그에만 남긴다."
            ),
            doc_type=doc_type,
            section="requirements",
            framework=framework,
            language=language,
            feature_name=feature_name,
            level=level,
            path="seed/spring-boot-login/error-handling",
            tags=("login", "error-handling", "exception", "http-status", "validation"),
        ),
        SeedDocument(
            title="regenerate-section codeFiles 생성 기준",
            content=(
                "COBIP_AI 기능템플릿의 codeFiles 섹션은 skeleton-first 정책에 따라 최초 generate에서는 빈 배열로 두고 "
                "/ai/feature-template/regenerate-section 요청으로 별도 생성한다. "
                "로그인 기능에서 권장되는 codeFiles 목록은 LoginController.java, LoginService.java, LoginRequest.java, LoginResponse.java, "
                "JwtTokenProvider.java, SecurityConfig.java, PasswordEncoderConfig.java, GlobalExceptionHandler.java 정도이며 "
                "각 파일은 패키지 경로, import 문, 핵심 메서드 시그니처, 주요 로직 주석을 포함하는 학습용 코드여야 한다. "
                "regenerate-section은 dryRun 옵션 없이 한 섹션씩 보강하며 source 표시와 함께 응답한다."
            ),
            doc_type=doc_type,
            section="codeFiles",
            framework=framework,
            language=language,
            feature_name=feature_name,
            level=level,
            path="seed/spring-boot-login/regenerate-section",
            tags=("login", "code-files", "regenerate-section", "skeleton-first"),
        ),
        SeedDocument(
            title="기능템플릿 skeleton-first 정책",
            content=(
                "12차부터 기능템플릿 generate는 skeleton-first 전략으로 동작한다. "
                "최초 generate 응답에서는 overview, requirements, flow, apiSpec, basicQuestions, nextRecommendations 중심의 가벼운 기본 구조만 반환하고 "
                "codeFiles, missions, interviewQuestions는 빈 배열로 둔다(includeCode/Missions/Interview 플래그가 true여도 마찬가지). "
                "trace.generationMode=skeleton, skeletonFirst=true, deferredSections=[\"codeFiles\",\"missions\",\"interviewQuestions\"] 메타가 함께 응답된다. "
                "상세 산출물은 POST /ai/feature-template/regenerate-section 호출로 섹션별 보강하며 LLM 부하/타임아웃을 분산한다."
            ),
            doc_type=doc_type,
            section="policy",
            framework=framework,
            language=language,
            feature_name=feature_name,
            level=level,
            path="seed/spring-boot-login/skeleton-first",
            tags=("login", "skeleton-first", "policy", "generation-mode"),
        ),
    ]


def build_payload(doc: SeedDocument) -> dict[str, Any]:
    """Qdrant payload — retriever_service / rag_service 변환 흐름과 직접 호환."""

    return {
        "title": doc.title,
        "content": doc.content,
        "sourceType": "document",
        "docType": doc.doc_type,
        "section": doc.section,
        "framework": doc.framework,
        "language": doc.language,
        "featureName": doc.feature_name,
        "level": doc.level,
        "path": doc.path,
        "tags": list(doc.tags),
    }


def build_point_id(doc: SeedDocument) -> str:
    """deterministic UUIDv5 point id. 동일 입력 → 동일 id."""

    key = f"{doc.feature_name}|{doc.section}|{doc.title}|{doc.path}"
    return str(uuid.uuid5(SEED_NAMESPACE, key))


def describe_documents(docs: list[SeedDocument]) -> list[dict[str, Any]]:
    """dry-run/테스트에서 사용할 안전한 preview 표현."""

    out: list[dict[str, Any]] = []
    for doc in docs:
        payload = build_payload(doc)
        content_preview = doc.content[:_PREVIEW_CHARS]
        if len(doc.content) > _PREVIEW_CHARS:
            content_preview = content_preview + "…"
        out.append(
            {
                "id": build_point_id(doc),
                "title": doc.title,
                "docType": doc.doc_type,
                "section": doc.section,
                "framework": doc.framework,
                "language": doc.language,
                "featureName": doc.feature_name,
                "level": doc.level,
                "path": doc.path,
                "tags": list(doc.tags),
                "contentChars": len(doc.content),
                "contentPreview": content_preview,
                "payloadKeys": sorted(payload.keys()),
            }
        )
    return out


def apply_seed_upsert(
    docs: list[SeedDocument],
    *,
    collection_name: str | None = None,
) -> dict[str, Any]:
    """실제 Qdrant upsert. dry-run 경로에서는 호출되지 않는다.

    기존 collection이 있으면 그대로 사용하고, 없으면 ``ensure_collection``으로 생성한다.
    drop/recreate는 절대 수행하지 않는다.
    """

    from app.core.config import settings
    from app.services.embedding_service import EmbeddingService
    from app.services.qdrant_service import QdrantService

    if not docs:
        return {
            "ok": True,
            "upsertedCount": 0,
            "collection": collection_name or settings.QDRANT_COLLECTION,
            "vectorSize": 0,
            "reason": "no_documents",
        }

    emb = EmbeddingService()
    qd = QdrantService()

    target_collection = collection_name or settings.QDRANT_COLLECTION
    vectors: list[list[float]] = []
    for doc in docs:
        vec = emb.embed_text(doc.content)
        vectors.append(vec)

    vector_size = len(vectors[0]) if vectors else 0
    ensured = qd.ensure_collection(
        vector_size=vector_size, collection_name=target_collection
    )
    if not ensured:
        logger.warning(
            "seed upsert aborted reason=ensure_collection_failed collection=%s",
            target_collection,
        )
        return {
            "ok": False,
            "upsertedCount": 0,
            "collection": target_collection,
            "vectorSize": vector_size,
            "reason": "ensure_collection_failed",
        }

    points: list[dict[str, Any]] = []
    for doc, vec in zip(docs, vectors):
        points.append(
            {
                "id": build_point_id(doc),
                "vector": vec,
                "payload": build_payload(doc),
            }
        )

    ok = qd.upsert(points, collection_name=target_collection)
    return {
        "ok": bool(ok),
        "upsertedCount": len(points) if ok else 0,
        "collection": target_collection,
        "vectorSize": vector_size,
    }


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Spring Boot 로그인 기능 지식 seed (Qdrant). 기본은 dry-run이며 "
            "--apply를 명시했을 때만 실제 upsert가 수행된다."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="실제 Qdrant에 upsert. 기본 동작은 dry-run.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="외부 서비스 호출 없이 문서 목록/payload preview만 출력 (기본 동작).",
    )
    parser.add_argument(
        "--collection",
        default=None,
        help="대상 Qdrant collection 이름 (미지정 시 settings.QDRANT_COLLECTION).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="결과를 JSON 형태로 출력 (자동화/검증용).",
    )
    parser.add_argument(
        "--include-feature-template-docs",
        action="store_true",
        help=(
            "docs/rag/feature-template/*.md COBIP 표준 문서도 함께 upsert "
            "(scripts/seed_qdrant_feature_template_docs.py와 동일 소스)."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s - %(message)s")
    args = _parse_args(argv)

    docs = build_login_seed_documents()
    previews = describe_documents(docs)
    is_dry_run = not args.apply

    summary: dict[str, Any] = {
        "mode": "dry-run" if is_dry_run else "apply",
        "documentCount": len(docs),
        "titles": [p["title"] for p in previews],
        "previews": previews,
    }

    if is_dry_run:
        summary["upsert"] = None
        summary["note"] = (
            "dry-run: 외부 Qdrant/embedding 호출이 발생하지 않았습니다. "
            "실제 upsert는 --apply 플래그가 필요합니다."
        )
    else:
        try:
            result = apply_seed_upsert(docs, collection_name=args.collection)
            if args.include_feature_template_docs:
                from scripts.seed_qdrant_feature_template_docs import (
                    apply_feature_template_docs_seed,
                    build_feature_template_docs_seed_documents,
                )

                ft_docs = build_feature_template_docs_seed_documents()
                ft_result = apply_feature_template_docs_seed(
                    ft_docs, collection_name=args.collection
                )
                summary["featureTemplateDocsUpsert"] = ft_result
                summary["featureTemplateDocsCount"] = len(ft_docs)
                if result.get("ok") and ft_result.get("ok"):
                    result = {
                        **result,
                        "upsertedCount": int(result.get("upsertedCount") or 0)
                        + int(ft_result.get("upsertedCount") or 0),
                    }
                elif not ft_result.get("ok"):
                    result = {**result, "ok": False, "featureTemplateDocsFailed": True}
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(
                "seed upsert failed errorType=%s message=%s",
                type(exc).__name__,
                exc,
            )
            summary["upsert"] = {
                "ok": False,
                "errorType": type(exc).__name__,
                "message": str(exc),
            }
            _emit(summary, as_json=args.json)
            return 1
        summary["upsert"] = result

    _emit(summary, as_json=args.json)
    return 0


def _emit(summary: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    print(f"[seed] mode={summary['mode']} documentCount={summary['documentCount']}")
    for p in summary["previews"]:
        print(
            f"  - id={p['id']} section={p['section']} title={p['title']} "
            f"contentChars={p['contentChars']}"
        )
        print(f"      preview: {p['contentPreview']}")
    if summary.get("upsert") is None:
        print(f"[seed] {summary['note']}")
    else:
        print(f"[seed] upsert result={summary['upsert']}")


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    sys.exit(main())

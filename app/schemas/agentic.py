from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.models.enums import IntentType
from app.schemas.feature_template import FeatureTemplateGenerateRequest

__all__ = [
    "AgenticRagRequest",
    "AgenticRagResponseData",
    "AgenticRagTrace",
]


class AgenticRagRequest(BaseModel):
    """최상위 Agentic RAG 진입점 요청."""

    message: str = Field(..., description="사용자의 자연어 요청")
    context: str | None = Field(
        default=None,
        description="선택 참고 맥락. 챗봇 답변 또는 기능템플릿 referenceContext에 반영된다.",
    )
    useRag: bool | None = Field(
        default=None,
        description="true이면 가능한 경우 Retriever 검색 결과를 도구 실행에 주입한다.",
    )
    featureTemplate: FeatureTemplateGenerateRequest | None = Field(
        default=None,
        description=(
            "기능템플릿 생성 의도일 때 사용할 명시 입력값. 없으면 message에서 최소 필드를 추출한다."
        ),
    )

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("message는 비어 있을 수 없습니다.")
        return stripped


class AgenticRagTrace(BaseModel):
    """Agentic RAG 처리 흐름 관측용 trace."""

    classifier: str
    intent: IntentType
    serviceName: str
    handler: str
    steps: list[str] = Field(default_factory=list)
    ragUsed: bool = False
    references: list[Any] = Field(default_factory=list)
    inferredFields: dict[str, Any] = Field(default_factory=dict)
    latencyMs: int = Field(default=0, ge=0)
    toolCandidates: list[str] = Field(
        default_factory=list,
        description="라우팅된 서비스·도구 후보 식별자",
    )
    intentReason: str = Field(
        default="",
        description="최상위 intent 분류 근거 (룰 기반 설명)",
    )
    handlerReason: str = Field(
        default="",
        description="선택된 실행 경로(handler) 근거",
    )
    ragContextAvailable: bool = Field(
        default=False,
        description="referenceContext.ragReferences 중 content 유효 항목 존재 여부(기능템플릿) 또는 챗 응답 RAG 근거 사용 여부",
    )
    ragReferenceCount: int = Field(
        default=0,
        ge=0,
        description="select_usable_rag_references 기준 사용 가능 reference 개수(프롬프트 상한 적용 전·동일 필터)",
    )
    appliedReferenceCount: int = Field(
        default=0,
        ge=0,
        description="기능템플릿 응답 appliedReferences 길이(챗 경로는 0)",
    )
    fallbackUsed: bool = Field(
        default=False,
        description="결과 source가 fallback이면 true",
    )
    source: str | None = Field(
        default=None,
        description="결과 LLM provider 요약(ollama, fallback 등)",
    )
    resultType: Literal["chat", "feature_template"] | None = Field(
        default=None,
        description="응답 resultType과 동일(추적 편의)",
    )
    routeDecision: str = Field(
        default="",
        description="intent → service 한 줄 요약",
    )
    executionMode: str = Field(
        default="rule_based",
        description="최상위 분류는 rule_based; 챗 하위는 result.agent.mode 반영 시 hybrid 등",
    )
    generationMode: str | None = Field(
        default=None,
        description="기능템플릿 생성 전략(skeleton, fallback, section_regenerated 등)",
    )
    skeletonFirst: bool = Field(
        default=False,
        description="최초 generate가 skeleton-first 전략으로 실행되었는지 여부",
    )
    deferredSections: list[str] = Field(
        default_factory=list,
        description="최초 generate에서 상세 생성을 regenerate-section으로 미룬 섹션",
    )
    fastSkeletonEnabled: bool = Field(
        default=False,
        description="17차: fast skeleton 초안 프로필 적용 여부",
    )
    # Agentic RAG 13차 — Qdrant 자동 retrieval 관측 필드
    ragRetrievalAttempted: bool = Field(
        default=False,
        description="13차: feature_template_generate 경로에서 자동 RAG retrieval을 시도했는지",
    )
    ragRetrievalStatus: Literal["success", "empty", "skipped", "failed"] | None = Field(
        default=None,
        description="자동 RAG retrieval 결과 상태 (success|empty|skipped|failed)",
    )
    ragRetrievedCount: int = Field(
        default=0,
        ge=0,
        description="Qdrant 등 retriever가 반환한 raw hit 수 (필터/정규화 전)",
    )
    ragInjectedCount: int = Field(
        default=0,
        ge=0,
        description="manual+auto dedupe 후 prompt에 실제 주입된 reference 수",
    )
    ragQuery: str | None = Field(
        default=None,
        description="자동 retrieval에 사용된 query 문자열 (없으면 None)",
    )
    ragSource: Literal["manual", "qdrant", "manual+qdrant", "none"] | None = Field(
        default=None,
        description="prompt에 반영된 RAG reference 출처 요약",
    )
    ragFailureReason: str | None = Field(
        default=None,
        description="자동 retrieval 실패 사유 (실패 시에만)",
    )
    ragRetrievalSkippedReason: str | None = Field(
        default=None,
        description="자동 retrieval을 시도하지 않은 사유 (예: rag_disabled, empty_query)",
    )
    # Agentic RAG 15차 — RAG/LLM 시간 분리 관측
    ragRetrievalMs: int | None = Field(
        default=None,
        ge=0,
        description="Qdrant 검색+embedding 포함 자동 RAG retrieval 소요(ms). 스킵/실패 시 0",
    )
    featureTemplateGenerationMs: int | None = Field(
        default=None,
        ge=0,
        description="FeatureTemplateGenerator.generate 실행 소요(ms)",
    )
    totalLatencyMs: int | None = Field(
        default=None,
        ge=0,
        description="run_agentic_rag feature_template 경로 전체 소요(ms). latencyMs와 동일",
    )
    # Agentic RAG 16차 — retrieval 세부 timing / cache 관측
    embeddingMs: int | None = Field(
        default=None,
        ge=0,
        description="RAG retrieval 중 임베딩 생성 소요(ms)",
    )
    qdrantSearchMs: int | None = Field(
        default=None,
        ge=0,
        description="RAG retrieval 중 Qdrant search 소요(ms)",
    )
    referenceBuildMs: int | None = Field(
        default=None,
        ge=0,
        description="Qdrant hit을 ragReferences로 정리한 소요(ms)",
    )
    ragCacheHit: bool = Field(
        default=False,
        description="RAG retrieval cache hit 여부",
    )
    ragCacheKey: str | None = Field(
        default=None,
        description="RAG retrieval cache key (hash 기반)",
    )
    featureTemplateCacheHit: bool = Field(
        default=False,
        description="feature_template skeleton cache hit 여부",
    )
    featureTemplateCacheKey: str | None = Field(
        default=None,
        description="feature_template skeleton cache key (hash 기반)",
    )


class AgenticRagResponseData(BaseModel):
    intent: IntentType
    resultType: Literal["chat", "feature_template"]
    result: dict[str, Any]
    trace: AgenticRagTrace

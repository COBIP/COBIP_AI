from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from app.models.enums import DifficultyLevel, QuestionType

__all__ = [
    "FeatureTemplateGenerateRequest",
    "FeatureTemplateRegenerateSectionRequest",
    "FeatureTemplateRegenerateSectionResult",
    "OverviewSchema",
    "RequirementSchema",
    "LayerRoleSchema",
    "FlowSchema",
    "ApiSpecSchema",
    "CodeFileSchema",
    "QuestionSchema",
    "MissionSchema",
    "InterviewQuestionSchema",
    "NextRecommendationSchema",
    "FeatureTemplateData",
    "FeatureTemplateGenerateResult",
    "FeatureTemplateGenerateResponse",
    "FeatureTemplateRegenerateSectionResponse",
]


class FeatureTemplateGenerateRequest(BaseModel):
    language: str = Field(..., description="대상 언어 (예: java, python)")
    framework: str | None = Field(default=None, description="프레임워크 (예: spring-boot)")
    featureName: str = Field(..., description="기능 이름")
    level: DifficultyLevel
    includeCode: bool = True
    includeMissions: bool = True
    includeInterview: bool = True
    referenceContext: dict | None = Field(
        default=None,
        description="RAG 또는 외부에서 주입되는 참고 컨텍스트",
    )


class FeatureTemplateRegenerateSectionRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    templateId: int | None = Field(default=None, description="기존 템플릿 ID (Spring Boot 측)")
    section: str = Field(
        ...,
        validation_alias=AliasChoices("section", "sectionName"),
        description=(
            "재생성할 섹션. overview, requirements, flow, apiSpec, codeFiles, "
            "basicQuestions, missions, interviewQuestions, nextRecommendations 및 snake_case 별칭 허용. "
            "`sectionName`으로내도 동일하게 처리된다."
        ),
    )
    language: str
    framework: str | None = None
    featureName: str
    level: DifficultyLevel
    previousContent: dict[str, Any] | None = Field(
        default=None,
        description="재생성 시 참고할 이전 섹션 내용",
    )
    userInstruction: str | None = Field(
        default=None,
        description="사용자가 추가로 제공한 재생성 지시사항",
    )
    includeCode: bool = True
    includeMissions: bool = True
    includeInterview: bool = True
    techStack: list[str] | None = Field(
        default=None,
        description="overview/맥락에 반영할 추가 기술 스택 힌트",
    )
    currentTemplate: dict[str, Any] | None = Field(
        default=None,
        validation_alias=AliasChoices("currentTemplate", "context"),
        description="전체 템플릿 맥락 (context 로도 전달 가능)",
    )

    @field_validator("section", mode="before")
    @classmethod
    def _coerce_section_to_canonical(cls, value: object) -> str:
        from app.models.enums import FeatureTemplateSection
        from app.services.feature_template_section_resolve import (
            resolve_canonical_feature_template_section,
        )

        if isinstance(value, FeatureTemplateSection):
            value = value.value
        if not isinstance(value, str):
            raise TypeError("section must be a string")
        return resolve_canonical_feature_template_section(value)


class OverviewSchema(BaseModel):
    featureName: str
    purpose: str
    useCases: list[str]
    resultDescription: str
    techStack: list[str]
    learningGoals: list[str]


class RequirementSchema(BaseModel):
    requirementId: str
    name: str
    description: str
    inputValue: str
    processCondition: str
    successResult: str
    failureResult: str
    priority: str
    relatedScreenOrApi: str


class LayerRoleSchema(BaseModel):
    layer: str
    role: str


class FlowSchema(BaseModel):
    steps: list[str]
    layers: list[LayerRoleSchema]


class ApiSpecSchema(BaseModel):
    apiName: str
    method: str
    endpoint: str
    description: str
    requestBody: dict | str
    responseBody: dict | str
    status: int


class CodeFileSchema(BaseModel):
    fileName: str
    filePath: str | None = None
    role: str
    language: str
    content: str


class QuestionSchema(BaseModel):
    questionId: str
    type: QuestionType
    question: str
    choices: list[str] | None = None
    answer: str
    explanation: str
    relatedSection: str | None = None
    difficulty: DifficultyLevel


class MissionSchema(BaseModel):
    missionId: str
    title: str
    description: str
    missionType: str
    requirements: list[str]
    successCriteria: list[str]
    relatedRequirements: list[str]
    difficulty: DifficultyLevel


class InterviewQuestionSchema(BaseModel):
    questionId: str
    question: str
    keyPoints: list[str]
    sampleAnswer: str
    relatedSection: str | None = None


class NextRecommendationSchema(BaseModel):
    featureName: str
    reason: str
    expectedLearning: str
    priority: int


class FeatureTemplateData(BaseModel):
    overview: OverviewSchema
    requirements: list[RequirementSchema]
    flow: FlowSchema
    apiSpec: list[ApiSpecSchema]
    codeFiles: list[CodeFileSchema]
    basicQuestions: list[QuestionSchema]
    missions: list[MissionSchema]
    interviewQuestions: list[InterviewQuestionSchema]
    nextRecommendations: list[NextRecommendationSchema]


class FeatureTemplateGenerateResult(BaseModel):
    template: FeatureTemplateData
    source: Literal["ollama", "fallback", "instant"]
    appliedReferences: list[dict[str, Any]] = Field(
        default_factory=list,
        description="프롬프트에 주입된 RAG reference 요약(실제 LLM 인용 여부와 무관)",
    )
    generationMode: Literal[
        "skeleton",
        "llm_full",
        "fallback",
        "section_regenerated",
        "quality_instant_skeleton",
    ] = Field(
        default="skeleton",
        description="최초 generate 생성 전략. 12차부터 기본값은 skeleton-first",
    )
    skeletonFirst: bool = Field(
        default=True,
        description="최초 generate가 빠른 기본 구조를 먼저 반환하는 전략인지 여부",
    )
    deferredSections: list[str] = Field(
        default_factory=lambda: ["codeFiles", "missions", "interviewQuestions"],
        description="최초 generate에서 상세 생성을 regenerate-section으로 미루는 섹션",
    )
    fastSkeletonEnabled: bool = Field(
        default=False,
        description="17차: fast skeleton 초안 프로필 적용 여부",
    )
    ultraFastSkeletonEnabled: bool = Field(
        default=False,
        description="18차: ultra-fast skeleton 초안 프로필 적용 여부",
    )
    skeletonMaxTokens: int | None = Field(
        default=None,
        description="18차: 최초 skeleton LLM 출력 상한(max_tokens). legacy는 None",
    )
    skeletonRagTopK: int | None = Field(
        default=None,
        description="18차: 최초 skeleton generate에 사용한 RAG top_k",
    )
    skeletonRagContentMaxChars: int | None = Field(
        default=None,
        description="18차: 최초 skeleton generate에 사용한 RAG content 최대 길이",
    )
    instantSkeletonUsed: bool = Field(
        default=False,
        description="22차: quality instant skeleton 경로 사용 여부",
    )
    qualityBaselineApplied: bool = Field(
        default=False,
        description="22차: deterministic quality baseline 적용 여부",
    )
    initialLlmEnhancementAttempted: bool = Field(
        default=False,
        description="22차: 최초 generate optional LLM enhancement 시도 여부",
    )
    initialLlmEnhancementSucceeded: bool = Field(
        default=False,
        description="22차: optional LLM enhancement 성공 여부",
    )
    initialLlmEnhancementMs: int | None = Field(
        default=None,
        ge=0,
        description="22차: optional LLM enhancement 소요(ms)",
    )


class FeatureTemplateGenerateResponse(BaseModel):
    template: FeatureTemplateData
    source: Literal["ollama", "fallback", "instant"]
    appliedReferences: list[dict[str, Any]] = Field(
        default_factory=list,
        description="프롬프트에 주입된 RAG reference 요약",
    )
    generationMode: Literal[
        "skeleton",
        "llm_full",
        "fallback",
        "section_regenerated",
        "quality_instant_skeleton",
    ] = "skeleton"
    skeletonFirst: bool = True
    deferredSections: list[str] = Field(
        default_factory=lambda: ["codeFiles", "missions", "interviewQuestions"]
    )
    fastSkeletonEnabled: bool = False
    ultraFastSkeletonEnabled: bool = False
    skeletonMaxTokens: int | None = None
    skeletonRagTopK: int | None = None
    skeletonRagContentMaxChars: int | None = None
    instantSkeletonUsed: bool = False
    qualityBaselineApplied: bool = False
    initialLlmEnhancementAttempted: bool = False
    initialLlmEnhancementSucceeded: bool = False
    initialLlmEnhancementMs: int | None = None


class FeatureTemplateRegenerateSectionResult(BaseModel):
    section: str
    content: dict[str, Any] | list[Any]
    source: Literal["ollama", "fallback"]
    generationMode: Literal["skeleton", "llm_full", "fallback", "section_regenerated"] = "section_regenerated"


class FeatureTemplateRegenerateSectionResponse(BaseModel):
    section: str
    content: dict[str, Any] | list[Any]
    source: Literal["ollama", "fallback"]
    generationMode: Literal["skeleton", "llm_full", "fallback", "section_regenerated"] = "section_regenerated"

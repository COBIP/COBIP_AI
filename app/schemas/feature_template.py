from typing import Literal

from pydantic import BaseModel, Field

from app.models.enums import DifficultyLevel, FeatureTemplateSection, QuestionType

__all__ = [
    "FeatureTemplateGenerateRequest",
    "FeatureTemplateRegenerateSectionRequest",
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
    templateId: int | None = Field(default=None, description="기존 템플릿 ID (Spring Boot 측)")
    section: FeatureTemplateSection
    language: str
    framework: str | None = None
    featureName: str
    level: DifficultyLevel
    previousContent: dict | None = Field(
        default=None,
        description="재생성 시 참고할 이전 섹션 내용",
    )
    userInstruction: str | None = Field(
        default=None,
        description="사용자가 추가로 제공한 재생성 지시사항",
    )


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
    source: Literal["vllm", "ollama", "fallback"]


class FeatureTemplateGenerateResponse(BaseModel):
    template: FeatureTemplateData
    source: Literal["vllm", "ollama", "fallback"]


class FeatureTemplateRegenerateSectionResponse(BaseModel):
    section: FeatureTemplateSection
    content: dict

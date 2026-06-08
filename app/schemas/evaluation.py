from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.feature_template import (
    ApiSpecSchema,
    MissionSchema,
    QuestionSchema,
    RequirementSchema,
)
from app.services.evaluation_payload_normalizer import (
    normalize_mission_feedback_payload,
    normalize_quiz_grade_payload,
)

__all__ = [
    "SubmittedCodeSchema",
    "CodeIssueSchema",
    "QuizGradeRequest",
    "QuizGradeResponse",
    "MissionFeedbackRequest",
    "MissionFeedbackResponse",
    "CodeAnalyzeRequest",
    "CodeAnalyzeResponse",
    "InterviewFeedbackRequest",
    "InterviewFeedbackResponse",
]


class SubmittedCodeSchema(BaseModel):
    fileName: str
    filePath: str | None = None
    language: str
    content: str


class CodeIssueSchema(BaseModel):
    fileName: str | None = None
    line: int | None = None
    severity: str
    message: str
    suggestion: str


class QuizGradeRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    templateId: int | None = None
    featureName: str
    question: QuestionSchema
    userAnswer: str
    relatedRequirements: list[RequirementSchema] | None = None
    relatedApiSpecs: list[ApiSpecSchema] | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_fe_payload(cls, data: Any) -> Any:
        return normalize_quiz_grade_payload(data)


class QuizGradeResponse(BaseModel):
    isCorrect: bool
    score: int
    feedback: str
    correctAnswer: str
    explanation: str
    relatedSection: str | None = None


class MissionFeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    templateId: int | None = None
    featureName: str
    mission: MissionSchema
    submittedCode: list[SubmittedCodeSchema]
    requirements: list[RequirementSchema]
    apiSpecs: list[ApiSpecSchema] = Field(
        default_factory=list,
        validation_alias="apiSpecs",
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_fe_payload(cls, data: Any) -> Any:
        return normalize_mission_feedback_payload(data)


class MissionFeedbackResponse(BaseModel):
    passed: bool
    score: int
    summary: str
    satisfiedRequirements: list[str]
    missingRequirements: list[str]
    apiSpecIssues: list[str]
    codeIssues: list[CodeIssueSchema]
    improvementSuggestions: list[str]
    nextAction: str


class CodeAnalyzeRequest(BaseModel):
    code: str
    language: str
    context: str | None = None


class CodeAnalyzeResponse(BaseModel):
    summary: str
    explanation: str
    potentialIssues: list[str]
    improvementSuggestions: list[str]


class InterviewFeedbackRequest(BaseModel):
    question: str
    keyPoints: list[str]
    userAnswer: str


class InterviewFeedbackResponse(BaseModel):
    score: int
    includedKeyPoints: list[str]
    missingKeyPoints: list[str]
    feedback: str
    improvedAnswer: str

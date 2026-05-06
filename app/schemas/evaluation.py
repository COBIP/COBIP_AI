from pydantic import BaseModel

from app.schemas.feature_template import (
    ApiSpecSchema,
    MissionSchema,
    QuestionSchema,
    RequirementSchema,
)

__all__ = [
    "SubmittedCodeSchema",
    "CodeIssueSchema",
    "QuizGradeRequest",
    "QuizGradeResponse",
    "MissionFeedbackRequest",
    "MissionFeedbackResponse",
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
    templateId: int | None = None
    featureName: str
    question: QuestionSchema
    userAnswer: str
    relatedRequirements: list[RequirementSchema] | None = None
    relatedApiSpecs: list[ApiSpecSchema] | None = None


class QuizGradeResponse(BaseModel):
    isCorrect: bool
    score: int
    feedback: str
    correctAnswer: str
    explanation: str
    relatedSection: str | None = None


class MissionFeedbackRequest(BaseModel):
    templateId: int | None = None
    featureName: str
    mission: MissionSchema
    submittedCode: list[SubmittedCodeSchema]
    requirements: list[RequirementSchema]
    apiSpecs: list[ApiSpecSchema]


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

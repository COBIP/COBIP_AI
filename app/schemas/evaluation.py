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

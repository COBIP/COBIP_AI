from pydantic import BaseModel

from app.models.enums import DifficultyLevel, QuestionType
from app.schemas.feature_template import QuestionSchema

__all__ = [
    "GrammarSectionSchema",
    "GrammarContentSchema",
    "GrammarGenerateQuestionsRequest",
    "GrammarGenerateQuestionsResponse",
    "GrammarGradeAnswerRequest",
    "GrammarGradeAnswerResponse",
    "GrammarExplainWrongAnswerRequest",
    "GrammarExplainWrongAnswerResponse",
]


class GrammarSectionSchema(BaseModel):
    type: str
    level: int | None = None
    text: str | None = None
    title: str | None = None
    language: str | None = None
    content: str | None = None
    question: str | None = None
    answer: str | None = None


class GrammarContentSchema(BaseModel):
    summary: str
    learningGoals: list[str]
    sections: list[GrammarSectionSchema]


class GrammarGenerateQuestionsRequest(BaseModel):
    grammarTemplateId: int
    language: str
    title: str
    content: GrammarContentSchema
    questionType: QuestionType
    difficulty: DifficultyLevel
    count: int


class GrammarGenerateQuestionsResponse(BaseModel):
    questions: list[QuestionSchema]


class GrammarGradeAnswerRequest(BaseModel):
    question: QuestionSchema
    userAnswer: str
    content: GrammarContentSchema | None = None


class GrammarGradeAnswerResponse(BaseModel):
    isCorrect: bool
    score: int
    feedback: str
    correctAnswer: str
    explanation: str
    relatedConcepts: list[str] = []


class GrammarExplainWrongAnswerRequest(BaseModel):
    question: QuestionSchema
    userAnswer: str
    previousFeedback: str | None = None
    content: GrammarContentSchema | None = None


class GrammarExplainWrongAnswerResponse(BaseModel):
    explanation: str
    easyExplanation: str
    example: str
    retryHint: str

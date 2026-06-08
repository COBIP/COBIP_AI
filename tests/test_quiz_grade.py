"""Quiz grade normalizer + grader + API contract tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.models.enums import DifficultyLevel, QuestionType
from app.schemas.evaluation import QuizGradeRequest
from app.services.evaluation_service import EvaluationService

_RESPONSE_FIELDS = frozenset(
    {
        "isCorrect",
        "score",
        "feedback",
        "correctAnswer",
        "explanation",
        "relatedSection",
    }
)


def _quiz_payload(**overrides: object) -> dict:
    base = {
        "featureName": "회원가입",
        "question": {
            "questionId": "Q-001",
            "type": QuestionType.SHORT_ANSWER.value,
            "question": "비밀번호는 어떻게 저장하나?",
            "choices": None,
            "answer": "BCrypt 해시",
            "explanation": "평문 금지",
            "relatedSection": "requirements",
            "difficulty": DifficultyLevel.BEGINNER.value,
        },
        "userAnswer": "BCrypt 해시",
        "relatedApiSpecs": [
            {
                "apiName": "회원가입",
                "method": "POST",
                "endpoint": "/api/auth/signup",
                "description": "signup",
                "requestBody": {},
                "responseBody": {},
                "status": 201,
                "requestHeaders": {"Content-Type": "application/json"},
                "requestFields": [{"fieldName": "email", "type": "string", "required": True}],
                "responseFields": [{"fieldName": "userId", "type": "number", "required": True}],
                "errorResponses": [
                    {"statusCode": 409, "errorCode": "DUPLICATE_EMAIL", "message": "duplicate"}
                ],
            }
        ],
    }
    base.update(overrides)
    return base


class TestQuizGradeService:
    def test_exact_match_correct(self) -> None:
        req = QuizGradeRequest(**_quiz_payload())
        result = EvaluationService().grade_quiz(req)
        assert result.isCorrect is True
        assert result.score == 100

    def test_case_and_space_insensitive(self) -> None:
        req = QuizGradeRequest(**_quiz_payload(userAnswer="  bcrypt   HASH "))
        result = EvaluationService().grade_quiz(req)
        assert result.isCorrect is True

    def test_keyword_partial_credit(self) -> None:
        req = QuizGradeRequest(**_quiz_payload(userAnswer="BCrypt로 해시 저장"))
        result = EvaluationService().grade_quiz(req)
        assert result.isCorrect is True
        assert result.score >= 70

    def test_wrong_answer_fails(self) -> None:
        req = QuizGradeRequest(**_quiz_payload(userAnswer="평문 저장"))
        result = EvaluationService().grade_quiz(req)
        assert result.isCorrect is False

    def test_fe_related_api_specs_shape_no_422(self) -> None:
        QuizGradeRequest(**_quiz_payload())


class TestQuizGradeApi:
    def test_endpoint_contract(self) -> None:
        client = TestClient(app)
        resp = client.post("/ai/quiz/grade", json=_quiz_payload(userAnswer="bcrypt hash"))
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("success") is True
        data = body["data"]
        assert set(data.keys()) == _RESPONSE_FIELDS
        assert data["isCorrect"] is True

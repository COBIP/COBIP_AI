from app.models.enums import IntentType

__all__ = ["AgentRouter"]


_INTENT_TO_SERVICE: dict[IntentType, str] = {
    IntentType.FEATURE_TEMPLATE_GENERATE: "feature_template_generator.generate",
    IntentType.FEATURE_TEMPLATE_REGENERATE_SECTION: "section_regenerator.regenerate",
    IntentType.GRAMMAR_GENERATE_QUESTIONS: "grammar_question_service.generate_questions",
    IntentType.GRAMMAR_GRADE_ANSWER: "grammar_question_service.grade_answer",
    IntentType.GRAMMAR_EXPLAIN_WRONG_ANSWER: "grammar_question_service.explain_wrong_answer",
    IntentType.QUIZ_GRADE: "evaluation_service.grade_quiz",
    IntentType.MISSION_FEEDBACK: "mission_feedback_service.generate_feedback",
    IntentType.INTERVIEW_FEEDBACK: "interview_feedback_service.generate_feedback",
    IntentType.CODE_ANALYZE: "evaluation_service.analyze_code",
    IntentType.RECOMMEND_NEXT_TEMPLATE: "recommend_service.recommend",
    IntentType.CHAT: "chat_service.answer",
}


class AgentRouter:
    """Agentic RAG Router 최상위 분기 구조.

    intent 값을 받아 처리할 service 식별 문자열을 반환한다.
    실제 서비스 호출은 다음 단계에서 연결한다.
    """

    def route(self, intent: IntentType, payload: dict) -> dict:
        service_name = _INTENT_TO_SERVICE.get(intent)
        if service_name is None:
            raise ValueError(f"Unsupported intent: {intent}")

        return {"service_name": service_name}

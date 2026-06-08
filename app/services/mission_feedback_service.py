"""실습 미션 피드백 service — evidence 기반 rule 채점."""

from app.schemas.evaluation import MissionFeedbackRequest, MissionFeedbackResponse
from app.services.mission_feedback_grader import MissionFeedbackGrader

__all__ = ["MissionFeedbackService"]


class MissionFeedbackService:
    """실습 미션 코드 피드백 service."""

    def generate_feedback(
        self,
        request: MissionFeedbackRequest,
    ) -> MissionFeedbackResponse:
        return MissionFeedbackGrader().grade(request)

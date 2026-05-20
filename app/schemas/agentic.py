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


class AgenticRagResponseData(BaseModel):
    intent: IntentType
    resultType: Literal["chat", "feature_template"]
    result: dict[str, Any]
    trace: AgenticRagTrace

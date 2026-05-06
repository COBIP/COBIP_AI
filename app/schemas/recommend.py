from pydantic import BaseModel

__all__ = [
    "RecommendNextTemplateRequest",
    "RecommendNextTemplateResponse",
]


class RecommendNextTemplateRequest(BaseModel):
    currentFeatureName: str
    language: str
    framework: str | None = None
    level: str
    completedSections: list[str] = []


class RecommendNextTemplateResponse(BaseModel):
    recommendations: list[dict]

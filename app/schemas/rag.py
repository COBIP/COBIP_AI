"""RAG Retriever·인덱싱 스키마 (/ai/chat 미연동)."""

from pydantic import BaseModel, Field, field_validator

from app.core.config import settings

__all__ = [
    "RetrieveRequest",
    "RetrievedReference",
    "RetrieveResponseData",
    "RagIndexDocument",
    "RagIndexRequest",
    "RagIndexResponseData",
]


class RetrieveRequest(BaseModel):
    query: str = Field(..., description="검색 질의")
    topK: int | None = Field(
        default=None,
        description=f"상위 k개 (미지정 시 서버 기본 {settings.RAG_TOP_K}, 1~10)",
    )

    @field_validator("query")
    @classmethod
    def query_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("query는 비어 있을 수 없습니다.")
        return stripped

    @field_validator("topK")
    @classmethod
    def top_k_range(cls, value: int | None) -> int | None:
        if value is None:
            return None
        if value < 1 or value > 10:
            raise ValueError("topK는 1 이상 10 이하여야 합니다.")
        return value


class RetrievedReference(BaseModel):
    id: str | None = None
    title: str | None = None
    content: str
    score: float | None = None
    sourceType: str | None = None
    metadata: dict = Field(default_factory=dict)


class RetrieveResponseData(BaseModel):
    query: str
    references: list[RetrievedReference]
    count: int


class RagIndexDocument(BaseModel):
    id: str | None = None
    title: str | None = None
    content: str
    sourceType: str | None = None
    metadata: dict = Field(default_factory=dict)

    @field_validator("content")
    @classmethod
    def content_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("content는 비어 있을 수 없습니다.")
        return stripped


class RagIndexRequest(BaseModel):
    documents: list[RagIndexDocument]

    @field_validator("documents")
    @classmethod
    def documents_count(cls, value: list[RagIndexDocument]) -> list[RagIndexDocument]:
        if len(value) < 1:
            raise ValueError("documents는 최소 1개 이상이어야 합니다.")
        if len(value) > 50:
            raise ValueError("documents는 최대 50개까지 가능합니다.")
        return value


class RagIndexResponseData(BaseModel):
    indexedCount: int
    collection: str
    ids: list[str]

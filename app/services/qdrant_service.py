"""Qdrant 검색/저장 service 구조 (mock 단계).

이 단계에서는 실제 qdrant-client 를 사용하지 않는다.
- search 는 빈 리스트, upsert 는 True 를 반환해 호출자가 안전하게 의존할 수 있게 한다.
- build_filter 는 실제 Qdrant 호환 형식(must AND)으로 미리 만들어두어
  추후 실제 연결 단계에서 그대로 재활용 가능하다.
- 실제 연결·컬렉션 생성·실 데이터 인덱싱은 추후 단계에서 추가한다.
"""

__all__ = ["QdrantService"]


_DEFAULT_COLLECTION = "learning_resources"

# 추후 실제 Qdrant 연결 단계에서 확장한다.
# 예: "feature_template" -> "feature_templates", "grammar" -> "grammar_templates"
_COLLECTION_MAP: dict[str, str] = {}


class QdrantService:
    """Qdrant 검색/저장 service (mock 단계, 실제 연결 없음)."""

    def search(
        self,
        collection_name: str,
        query_vector: list[float],
        filters: dict | None = None,
        limit: int = 5,
    ) -> list[dict]:
        # mock 단계: 항상 빈 결과 반환.
        return []

    def upsert(self, collection_name: str, points: list[dict]) -> bool:
        # mock 단계: 항상 성공으로 간주.
        return True

    def build_filter(self, payload: dict) -> dict:
        """Qdrant 호환 filter (must AND) 구조를 만든다.

        예: {"language": "java", "level": "beginner"} →
        {
            "must": [
                {"key": "language", "match": {"value": "java"}},
                {"key": "level",    "match": {"value": "beginner"}}
            ]
        }
        list 값은 match.any 로, None 은 무시한다.
        """
        if not payload:
            return {}

        conditions: list[dict] = []
        for key, value in payload.items():
            if value is None:
                continue
            if isinstance(value, list):
                conditions.append({"key": key, "match": {"any": value}})
            else:
                conditions.append({"key": key, "match": {"value": value}})

        if not conditions:
            return {}
        return {"must": conditions}

    def get_collection_name(self, resource_type: str) -> str:
        """resource_type 별 컬렉션 이름. 기본값은 'learning_resources'."""
        return _COLLECTION_MAP.get(resource_type, _DEFAULT_COLLECTION)

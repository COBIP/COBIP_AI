from fastapi import APIRouter

from app.services.embedding_warmup_state import embedding_warmup_status_dict
from app.services.qdrant_service import QdrantService

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    qdrant = QdrantService().health_check()
    return {
        "success": True,
        "message": "AI server is running",
        "data": {
            "status": "ok",
            "qdrant": qdrant,
            **embedding_warmup_status_dict(),
        },
    }

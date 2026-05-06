from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    return {
        "success": True,
        "message": "AI server is running",
        "data": {
            "status": "ok",
        },
    }

"""공통 응답 dict 빌더.

라우터/예외 핸들러가 일관된 응답 포맷을 만들 때 사용한다.
이 단계에서는 dict 만 반환하며, FastAPI 의 JSONResponse 변환은 호출자가 담당한다.
"""

from typing import Any

__all__ = ["success_response", "error_response"]


def success_response(message: str, data: Any = None) -> dict:
    return {
        "success": True,
        "message": message,
        "data": data,
    }


def error_response(
    message: str,
    error_code: str = "AI_SERVER_ERROR",
    details: Any = None,
) -> dict:
    return {
        "success": False,
        "message": message,
        "errorCode": error_code,
        "details": details,
    }

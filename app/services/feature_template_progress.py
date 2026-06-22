"""Feature template generation progress step definitions."""

from collections.abc import Callable

__all__ = [
    "FEATURE_TEMPLATE_PROGRESS_STEPS",
    "ProgressCallback",
    "emit_feature_template_progress",
]

ProgressCallback = Callable[[str, str, int], None]

FEATURE_TEMPLATE_PROGRESS_STEPS: dict[str, tuple[str, int]] = {
    "analyze": ("요청 분석 중", 5),
    "requirements": ("요구사항 생성 중", 20),
    "flow": ("흐름/구조 설계 중", 35),
    "apiSpec": ("API 명세 작성 중", 50),
    "codeFiles": ("코드 파일 생성 중", 65),
    "questionsMissions": ("문제/미션 생성 중", 80),
    "interviewNext": ("핵심 질문/다음 추천 생성 중", 90),
    "finalize": ("최종 템플릿 정리 중", 98),
}


def emit_feature_template_progress(
    callback: ProgressCallback | None,
    step: str,
) -> None:
    if callback is None:
        return
    label, progress = FEATURE_TEMPLATE_PROGRESS_STEPS[step]
    callback(step, label, progress)

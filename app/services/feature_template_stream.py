"""SSE streaming for feature template generation."""

import asyncio
import logging
from collections.abc import AsyncIterator

from app.schemas.feature_template import FeatureTemplateGenerateRequest
from app.services.feature_template_generator import FeatureTemplateGenerator
from app.services.feature_template_progress import ProgressCallback
from app.utils.sse import format_sse

__all__ = ["stream_feature_template_generation"]

logger = logging.getLogger(__name__)


async def stream_feature_template_generation(
    request: FeatureTemplateGenerateRequest,
) -> AsyncIterator[str]:
    queue: asyncio.Queue[str | None] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def enqueue_progress(step: str, label: str, progress: int) -> None:
        payload = format_sse(
            "progress",
            {
                "status": "RUNNING",
                "step": step,
                "label": label,
                "progress": progress,
            },
        )
        loop.call_soon_threadsafe(queue.put_nowait, payload)

    progress_callback: ProgressCallback = enqueue_progress

    async def run_generation() -> None:
        try:
            result = await asyncio.to_thread(
                FeatureTemplateGenerator().generate,
                request,
                progress_callback,
            )
            await queue.put(
                format_sse(
                    "complete",
                    {
                        "status": "COMPLETED",
                        "step": "completed",
                        "label": "완료",
                        "progress": 100,
                        "template": result.template.model_dump(),
                    },
                )
            )
        except Exception as exc:
            logger.exception(
                "Feature template stream generation failed: featureName=%s",
                request.featureName,
            )
            await queue.put(
                format_sse(
                    "error",
                    {
                        "status": "FAILED",
                        "step": "failed",
                        "label": "생성 실패",
                        "progress": 0,
                        "errorMessage": str(exc),
                    },
                )
            )
        finally:
            await queue.put(None)

    task = asyncio.create_task(run_generation())

    while True:
        item = await queue.get()
        if item is None:
            break
        yield item

    await task

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.schemas.common import ApiResponse
from app.schemas.feature_template import (
    FeatureTemplateGenerateRequest,
    FeatureTemplateRegenerateSectionRequest,
)
from app.services.feature_template_generator import FeatureTemplateGenerator
from app.services.feature_template_stream import stream_feature_template_generation
from app.utils.sse import SSE_RESPONSE_HEADERS

router = APIRouter(prefix="/ai/feature-template", tags=["feature-template"])


@router.post("/generate", response_model=ApiResponse)
def generate_feature_template(
    request: FeatureTemplateGenerateRequest,
) -> ApiResponse:
    result = FeatureTemplateGenerator().generate(request)
    metadata = FeatureTemplateGenerator.result_metadata_payload(result)
    return ApiResponse(
        success=True,
        message="기능템플릿 생성이 완료되었습니다.",
        data={
            "template": result.template.model_dump(),
            "source": result.source,
            "appliedReferences": result.appliedReferences,
            **metadata,
            "fallbackUsed": result.fallbackUsed,
        },
    )


@router.post("/generate/stream")
async def generate_feature_template_stream(
    request: FeatureTemplateGenerateRequest,
) -> StreamingResponse:
    return StreamingResponse(
        stream_feature_template_generation(request),
        media_type="text/event-stream",
        headers=SSE_RESPONSE_HEADERS,
    )


@router.post("/regenerate-section", response_model=ApiResponse)
def regenerate_feature_template_section(
    request: FeatureTemplateRegenerateSectionRequest,
) -> ApiResponse:
    result = FeatureTemplateGenerator().regenerate_section(request)
    return ApiResponse(
        success=True,
        message="기능템플릿 섹션 재생성이 완료되었습니다.",
        data={
            "section": result.section,
            "content": result.content,
            "source": result.source,
            "generationMode": result.generationMode,
        },
    )

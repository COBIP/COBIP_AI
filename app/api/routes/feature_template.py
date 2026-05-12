from fastapi import APIRouter

from app.schemas.common import ApiResponse
from app.schemas.feature_template import (
    FeatureTemplateGenerateRequest,
    FeatureTemplateRegenerateSectionRequest,
)
from app.services.feature_template_generator import FeatureTemplateGenerator

router = APIRouter(prefix="/ai/feature-template", tags=["feature-template"])


@router.post("/generate", response_model=ApiResponse)
def generate_feature_template(
    request: FeatureTemplateGenerateRequest,
) -> ApiResponse:
    result = FeatureTemplateGenerator().generate(request)
    return ApiResponse(
        success=True,
        message="기능템플릿 생성이 완료되었습니다.",
        data={
            "template": result.template.model_dump(),
            "source": result.source,
        },
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
        },
    )

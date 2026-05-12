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
    # 실제 LLM 호출 없이 임시 content dict 만 반환한다.
    # 실제 재생성 로직은 추후 별도 service 단계에서 추가한다.
    content: dict = {
        "regenerated": True,
        "section": request.section.value,
        "language": request.language,
        "framework": request.framework,
        "featureName": request.featureName,
        "level": request.level.value,
        "userInstruction": request.userInstruction,
        "previousContent": request.previousContent,
        "note": "(mock) 실제 LLM 재생성 결과로 대체 예정",
    }

    return ApiResponse(
        success=True,
        message="기능템플릿 섹션 재생성이 완료되었습니다.",
        data={
            "section": request.section.value,
            "content": content,
        },
    )

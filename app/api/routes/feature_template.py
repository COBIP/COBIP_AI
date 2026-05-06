from fastapi import APIRouter

from app.schemas.common import ApiResponse
from app.schemas.feature_template import (
    FeatureTemplateData,
    FeatureTemplateGenerateRequest,
    FeatureTemplateRegenerateSectionRequest,
)
from app.services.feature_template_generator import FeatureTemplateGenerator

router = APIRouter(prefix="/ai/feature-template", tags=["feature-template"])


def _template_to_dict(template: FeatureTemplateData) -> dict:
    """FeatureTemplateData 를 응답 dict 로 변환한다.

    NOTE: basicQuestions / missions / interviewQuestions / nextRecommendations
          필드는 forward reference 미해소 상태(QuestionSchema 등 미정의)이므로
          FeatureTemplateData 자체에 model_dump() 을 호출하면 schema 빌드 단계에서
          PydanticUndefinedAnnotation 이 발생할 수 있다.
          → concrete 스키마는 개별 model_dump() 으로, 미해소 필드는 원본 list 그대로
            전달해 안전하게 직렬화한다. 4개 스키마가 정의되면 단순화 예정.
    """
    return {
        "overview": template.overview.model_dump(),
        "requirements": [r.model_dump() for r in template.requirements],
        "flow": template.flow.model_dump(),
        "apiSpec": [a.model_dump() for a in template.apiSpec],
        "codeFiles": [c.model_dump() for c in template.codeFiles],
        "basicQuestions": list(template.basicQuestions),
        "missions": list(template.missions),
        "interviewQuestions": list(template.interviewQuestions),
        "nextRecommendations": list(template.nextRecommendations),
    }


@router.post("/generate", response_model=ApiResponse)
def generate_feature_template(
    request: FeatureTemplateGenerateRequest,
) -> ApiResponse:
    template = FeatureTemplateGenerator().generate(request)
    return ApiResponse(
        success=True,
        message="기능템플릿 생성이 완료되었습니다.",
        data={"template": _template_to_dict(template)},
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

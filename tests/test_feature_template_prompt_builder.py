"""기능템플릿 프롬프트 빌더 — RAG referenceContext 주입 (Agentic RAG 2차)."""

from app.models.enums import DifficultyLevel
from app.schemas.feature_template import FeatureTemplateGenerateRequest
from app.services.prompt_builder import (
    build_feature_template_prompt,
    format_rag_references_for_feature_template_prompt,
)


def _base_request(**kwargs: object) -> FeatureTemplateGenerateRequest:
    data = dict(
        language="java",
        featureName="로그인",
        level=DifficultyLevel.BEGINNER,
        includeCode=True,
        includeMissions=True,
        includeInterview=True,
    )
    data.update(kwargs)
    return FeatureTemplateGenerateRequest(**data)


def test_prompt_includes_rag_context_section_when_rag_references_present() -> None:
    mock_ref = {
        "title": "Spring Boot 로그인 API 가이드",
        "content": (
            "로그인 API는 POST /api/auth/login 형태로 구성하고, "
            "요청 본문에는 email과 password를 포함한다. "
            "비밀번호는 평문 저장하지 않고 BCrypt로 검증한다."
        ),
        "source": "internal-docs",
        "score": 0.91,
    }
    req = _base_request(
        referenceContext={
            "agenticUserMessage": "로그인 템플릿",
            "ragReferences": [mock_ref],
        },
    )
    text = build_feature_template_prompt(req)
    assert "[검색 근거 / RAG Context]" in text
    assert "Spring Boot 로그인 API 가이드" in text
    assert "POST /api/auth/login" in text
    assert "BCrypt" in text
    assert "internal-docs" in text
    assert "0.91" in text
    # JSON 블록에는 ragReferences 중복을 넣지 않는다.
    assert '"ragReferences"' not in text
    assert "agenticUserMessage" in text


def test_prompt_omits_rag_section_when_no_usable_rag_references() -> None:
    req = _base_request(
        referenceContext={
            "note": "context only",
        },
    )
    text = build_feature_template_prompt(req)
    assert "[검색 근거 / RAG Context]" not in text


def test_prompt_omits_rag_section_when_rag_references_empty_list() -> None:
    req = _base_request(referenceContext={"ragReferences": []})
    text = build_feature_template_prompt(req)
    assert "[검색 근거 / RAG Context]" not in text


def test_format_rag_uses_source_type_when_present() -> None:
    body = format_rag_references_for_feature_template_prompt(
        [
            {
                "title": "T",
                "content": "x" * 50,
                "sourceType": "doc",
                "score": 0.5,
            }
        ],
    )
    assert "출처: doc" in body


def test_format_rag_returns_empty_for_non_dict_items() -> None:
    assert format_rag_references_for_feature_template_prompt([None, "x", 1]) == ""


def test_format_rag_truncates_long_content() -> None:
    long_content = "a" * 2000
    out = format_rag_references_for_feature_template_prompt(
        [{"title": "Long", "content": long_content}],
        max_content_chars=1000,
    )
    assert "…" in out or len(out) < len(long_content) + 500

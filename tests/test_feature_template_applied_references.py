"""기능템플릿 appliedReferences — 프롬프트 주입 RAG와 동일 기준 (Agentic RAG 3차)."""

import pytest

from app.models.enums import DifficultyLevel
from app.schemas.feature_template import FeatureTemplateGenerateRequest
from app.services.feature_template_generator import FeatureTemplateGenerator
from app.services.prompt_builder import (
    build_applied_references_payload,
    build_feature_template_prompt_with_applied_rags,
    select_usable_rag_references,
)

_MOCK_REF = {
    "title": "Spring Boot 로그인 API 가이드",
    "content": (
        "로그인 API는 POST /api/auth/login 형태로 구성하고, "
        "요청 본문에는 email과 password를 포함한다. "
        "비밀번호는 평문 저장하지 않고 BCrypt로 검증한다."
    ),
    "source": "internal-docs",
    "score": 0.91,
}


def _minimal_llm_json(feature_name: str = "로그인") -> dict:
    return {
        "overview": {
            "featureName": feature_name,
            "purpose": "p",
            "useCases": [],
            "resultDescription": "r",
            "techStack": [],
            "learningGoals": [],
        },
        "requirements": [],
        "flow": {"steps": [], "layers": []},
        "apiSpec": [],
        "codeFiles": [],
        "basicQuestions": [],
        "missions": [],
        "interviewQuestions": [],
        "nextRecommendations": [],
    }


def test_applied_references_populated_when_rag_present(monkeypatch: pytest.MonkeyPatch) -> None:
    req = FeatureTemplateGenerateRequest(
        language="java",
        featureName="로그인",
        level=DifficultyLevel.BEGINNER,
        includeCode=False,
        includeMissions=False,
        includeInterview=False,
        referenceContext={"ragReferences": [_MOCK_REF]},
    )
    gen = FeatureTemplateGenerator()
    monkeypatch.setattr(gen._llm_service, "generate_json", lambda _p: _minimal_llm_json())

    result = gen.generate(req)
    assert len(result.appliedReferences) == 1
    ar = result.appliedReferences[0]
    assert ar["title"] == "Spring Boot 로그인 API 가이드"
    assert ar["source"] == "internal-docs"
    assert ar["score"] == 0.91
    assert ar["usedInPrompt"] is True
    assert "POST /api/auth/login" in ar["contentPreview"]
    assert "BCrypt" in ar["contentPreview"]


def test_applied_references_empty_without_rag(monkeypatch: pytest.MonkeyPatch) -> None:
    req = FeatureTemplateGenerateRequest(
        language="java",
        featureName="smoke",
        level=DifficultyLevel.BEGINNER,
        includeCode=False,
        includeMissions=False,
        includeInterview=False,
    )
    gen = FeatureTemplateGenerator()
    monkeypatch.setattr(gen._llm_service, "generate_json", lambda _p: _minimal_llm_json("smoke"))

    result = gen.generate(req)
    assert result.appliedReferences == []


def test_empty_content_reference_excluded_from_prompt_and_applied() -> None:
    refs = [
        {"title": "빈 문서", "source": "internal-docs"},
        _MOCK_REF,
    ]
    selected = select_usable_rag_references(refs)
    assert len(selected) == 1
    assert selected[0]["title"] == "Spring Boot 로그인 API 가이드"
    prompt, applied = build_feature_template_prompt_with_applied_rags(
        FeatureTemplateGenerateRequest(
            language="java",
            featureName="x",
            level=DifficultyLevel.BEGINNER,
            referenceContext={"ragReferences": refs},
        ),
    )
    assert "빈 문서" not in prompt
    assert len(applied) == 1


def test_max_five_references_applied_and_in_prompt() -> None:
    refs = [
        {"title": f"T{i}", "content": f"body{i} " * 5, "source": "s"}
        for i in range(6)
    ]
    selected = select_usable_rag_references(refs)
    assert len(selected) == 5
    applied = build_applied_references_payload(selected)
    assert len(applied) == 5
    req = FeatureTemplateGenerateRequest(
        language="java",
        featureName="x",
        level=DifficultyLevel.BEGINNER,
        referenceContext={"ragReferences": refs},
    )
    prompt, applied2 = build_feature_template_prompt_with_applied_rags(req)
    assert len(applied2) == 5
    assert prompt.count("   제목:") == 5


def test_content_preview_respects_max_length() -> None:
    long = "Z" * 500
    selected = select_usable_rag_references([{"title": "L", "content": long}])
    applied = build_applied_references_payload(selected, preview_max_chars=200)
    assert len(applied) == 1
    assert len(applied[0]["contentPreview"]) <= 200


def test_prompt_and_applied_share_same_selection() -> None:
    req = FeatureTemplateGenerateRequest(
        language="java",
        featureName="로그인",
        level=DifficultyLevel.BEGINNER,
        referenceContext={"ragReferences": [_MOCK_REF]},
    )
    prompt, applied = build_feature_template_prompt_with_applied_rags(req)
    assert "[검색 근거 / RAG Context]" in prompt
    assert applied[0]["title"] in prompt

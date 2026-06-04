"""22차: quality instant skeleton 경로 검증."""

import re
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.models.enums import DifficultyLevel
from app.schemas.feature_template import FeatureTemplateGenerateRequest, FeatureTemplateData
from app.services.agent_orchestrator import AgentOrchestrator
from app.services.cache_service import CacheService
from app.services.feature_template_generator import FeatureTemplateGenerator
from app.services.feature_template_instant_skeleton import (
    QUALITY_INSTANT_FULL_GENERATION_MODE,
    QUALITY_INSTANT_GENERATION_MODE,
    build_quality_instant_skeleton_dict,
)

_FORBIDDEN_VALUE_PATTERNS = (
    re.compile(r"\bTODO\b", re.I),
    re.compile(r"\bplaceholder\b", re.I),
    re.compile(r"예시\s*코드"),
    re.compile(r"\(mock\)"),
    re.compile(r"생략"),
)


def _login_request(**kwargs: object) -> FeatureTemplateGenerateRequest:
    base = dict(
        language="java",
        framework="spring-boot",
        featureName="로그인",
        level=DifficultyLevel.BEGINNER,
        includeCode=True,
        includeMissions=True,
        includeInterview=True,
    )
    base.update(kwargs)
    return FeatureTemplateGenerateRequest(**base)


def _assert_no_weak_placeholders(payload: object) -> None:
    if isinstance(payload, dict):
        for value in payload.values():
            _assert_no_weak_placeholders(value)
    elif isinstance(payload, list):
        for item in payload:
            _assert_no_weak_placeholders(item)
    elif isinstance(payload, str):
        for pattern in _FORBIDDEN_VALUE_PATTERNS:
            assert not pattern.search(payload), f"weak placeholder found: {payload!r}"


def test_instant_skeleton_enabled_skips_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "FEATURE_TEMPLATE_INSTANT_SKELETON_ENABLED", True)
    llm = MagicMock()
    llm.generate_json.side_effect = AssertionError("LLM must not be called")
    gen = FeatureTemplateGenerator(llm_service=llm)
    result = gen.generate(
        _login_request(includeCode=False, includeMissions=False, includeInterview=False)
    )
    assert result.source == "instant"
    assert result.generationMode == QUALITY_INSTANT_GENERATION_MODE
    llm.generate_json.assert_not_called()


def test_instant_skeleton_fills_quality_sections() -> None:
    normalized = build_quality_instant_skeleton_dict(
        FeatureTemplateGenerateRequest(
            language="java",
            framework="spring-boot",
            featureName="게시글 작성",
            level=DifficultyLevel.BEGINNER,
            includeCode=True,
            includeMissions=True,
            includeInterview=True,
        )
    )
    assert len(normalized["requirements"]) >= 3
    assert len(normalized["flow"]["steps"]) >= 3
    assert len(normalized["apiSpec"]) >= 1
    assert len(normalized["basicQuestions"]) >= 3
    assert len(normalized["nextRecommendations"]) >= 3
    assert len(normalized["codeFiles"]) >= 4
    assert len(normalized["missions"]) >= 2
    assert len(normalized["interviewQuestions"]) >= 3
    _assert_no_weak_placeholders(normalized)


def test_login_instant_skeleton_uses_auth_login_endpoint() -> None:
    normalized = build_quality_instant_skeleton_dict(_login_request(includeCode=False))
    endpoints = [item["endpoint"] for item in normalized["apiSpec"]]
    assert "/api/auth/login" in endpoints
    login_api = next(item for item in normalized["apiSpec"] if item["endpoint"] == "/api/auth/login")
    assert login_api["method"] == "POST"
    assert "email" in str(login_api["requestBody"]).lower() or "password" in str(
        login_api["requestBody"]
    ).lower() or "username" in str(login_api["requestBody"]).lower()


def test_login_instant_skeleton_api_spec_includes_documentation_fields() -> None:
    normalized = build_quality_instant_skeleton_dict(_login_request())
    login_api = next(
        item for item in normalized["apiSpec"] if item["endpoint"] == "/api/auth/login"
    )
    assert login_api["authenticationRequired"] is False
    assert len(login_api["requestHeaders"]) >= 1
    assert len(login_api["requestFields"]) >= 2
    assert len(login_api["responseFields"]) >= 5
    assert len(login_api["statusCodes"]) >= 3
    assert len(login_api["errorResponses"]) >= 2
    assert len(login_api["frontendNotes"]) >= 2
    assert len(login_api["description"]) >= 120
    assert "401" in login_api["description"]
    assert login_api["requestBody"]["email"]
    assert login_api["responseBody"]["data"]["accessToken"]
    FeatureTemplateData(**normalized)


def test_login_instant_skeleton_minimum_counts() -> None:
    normalized = build_quality_instant_skeleton_dict(_login_request(includeCode=False))
    assert len(normalized["requirements"]) >= 3
    assert len(normalized["basicQuestions"]) >= 3
    assert len(normalized["nextRecommendations"]) >= 3


def test_deferred_sections_empty_when_full_baseline_filled() -> None:
    result = FeatureTemplateGenerator().generate(_login_request())
    data = result.template.model_dump()
    assert len(data["codeFiles"]) >= 4
    assert len(data["missions"]) >= 2
    assert len(data["interviewQuestions"]) >= 3
    assert result.deferredSections == []
    assert result.generationMode == QUALITY_INSTANT_FULL_GENERATION_MODE


def test_agentic_rag_path_uses_instant_skeleton(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "FEATURE_TEMPLATE_INSTANT_SKELETON_ENABLED", True)
    monkeypatch.setattr(settings, "RAG_ENABLED", False)
    monkeypatch.setattr(settings, "FEATURE_TEMPLATE_CACHE_ENABLED", False)

    client = TestClient(app)
    resp = client.post(
        "/ai/agentic-rag/run",
        json={
            "message": "로그인 기능템플릿 생성",
            "featureTemplate": {
                "language": "java",
                "framework": "spring-boot",
                "featureName": "로그인",
                "level": "beginner",
                "includeCode": False,
                "includeMissions": False,
                "includeInterview": False,
            },
        },
    )
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["result"]["source"] == "instant"
    assert body["result"]["generationMode"] == QUALITY_INSTANT_GENERATION_MODE
    tr = body["trace"]
    assert tr["instantSkeletonUsed"] is True
    assert tr["qualityBaselineApplied"] is True
    assert tr["fallbackUsed"] is False


def test_rag_failure_still_returns_instant_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "FEATURE_TEMPLATE_INSTANT_SKELETON_ENABLED", True)
    monkeypatch.setattr(settings, "RAG_ENABLED", True)
    monkeypatch.setattr(settings, "FEATURE_TEMPLATE_CACHE_ENABLED", False)

    def fail_retrieval(**kwargs: object):
        from app.services.rag_service import FeatureTemplateRagRetrieval

        return FeatureTemplateRagRetrieval(
            attempted=True,
            status="failed",
            references=[],
            retrieved_count=0,
            query=str(kwargs.get("query") or ""),
            failure_reason="qdrant unavailable",
            cache_hit=False,
            cache_key=None,
            embedding_ms=0,
            qdrant_search_ms=0,
            reference_build_ms=0,
        )

    monkeypatch.setattr(
        "app.services.rag_service.retrieve_feature_template_rag_references",
        fail_retrieval,
    )

    client = TestClient(app)
    resp = client.post(
        "/ai/agentic-rag/run",
        json={
            "message": "로그인 기능템플릿 생성",
            "featureTemplate": {
                "language": "java",
                "featureName": "로그인",
                "level": "beginner",
                "includeCode": False,
                "includeMissions": False,
                "includeInterview": False,
            },
        },
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert resp.json()["data"]["result"]["source"] == "instant"


def test_instant_metadata_fields() -> None:
    result = FeatureTemplateGenerator().generate(
        _login_request(includeCode=False, includeMissions=False, includeInterview=False)
    )
    assert result.instantSkeletonUsed is True
    assert result.qualityBaselineApplied is True
    assert result.skeletonFirst is True
    assert result.deferredSections == []
    assert result.generationMode == QUALITY_INSTANT_GENERATION_MODE
    assert result.initialLlmEnhancementAttempted is False


def test_instant_skeleton_is_cacheable(monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.test_rag_performance_cache import _clear_cache

    _clear_cache()
    monkeypatch.setattr(settings, "FEATURE_TEMPLATE_CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "FEATURE_TEMPLATE_CACHE_INSTANT_SKELETON_ENABLED", True)
    monkeypatch.setattr(settings, "RAG_ENABLED", False)

    req = _login_request(includeCode=False, includeMissions=False, includeInterview=False)
    result = FeatureTemplateGenerator().generate(req)
    assert FeatureTemplateGenerator.is_cacheable_generate_result(result) is True

    key = AgentOrchestrator._build_feature_template_cache_key(
        feature_request=req,
        rag_references=[],
    )
    CacheService().set_json(
        key,
        FeatureTemplateGenerator.serialize_cache_entry(result),
        60,
    )
    cached = CacheService().get_json(key)
    assert cached["source"] == "instant"
    assert cached["instantSkeletonUsed"] is True


def test_second_request_can_hit_feature_template_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.test_rag_performance_cache import _clear_cache

    _clear_cache()
    monkeypatch.setattr(settings, "FEATURE_TEMPLATE_CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "FEATURE_TEMPLATE_CACHE_INSTANT_SKELETON_ENABLED", True)
    monkeypatch.setattr(settings, "RAG_ENABLED", False)

    call_count = {"n": 0}
    original_generate = FeatureTemplateGenerator.generate

    def counting_generate(self, request):
        call_count["n"] += 1
        return original_generate(self, request)

    monkeypatch.setattr(FeatureTemplateGenerator, "generate", counting_generate)

    client = TestClient(app)
    payload = {
        "message": "로그인 기능템플릿 생성",
        "featureTemplate": {
            "language": "java",
            "framework": "spring-boot",
            "featureName": "로그인",
            "level": "beginner",
            "includeCode": False,
            "includeMissions": False,
            "includeInterview": False,
        },
    }
    first = client.post("/ai/agentic-rag/run", json=payload)
    second = client.post("/ai/agentic-rag/run", json=payload)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["data"]["trace"]["featureTemplateCacheHit"] is False
    assert second.json()["data"]["trace"]["featureTemplateCacheHit"] is True
    assert call_count["n"] == 1


def test_regenerate_section_still_uses_llm_path(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.schemas.feature_template import FeatureTemplateRegenerateSectionRequest

    monkeypatch.setattr(settings, "FEATURE_TEMPLATE_INSTANT_SKELETON_ENABLED", True)
    gen = FeatureTemplateGenerator()
    called = {"n": 0}

    def fake_json(_prompt: str, **_kwargs: object) -> dict:
        called["n"] += 1
        return {
            "codeFiles": [
                {
                    "fileName": "LoginController.java",
                    "filePath": "src/main/java/LoginController.java",
                    "role": "Controller",
                    "language": "java",
                    "content": "public class LoginController {}",
                }
            ]
        }

    monkeypatch.setattr(gen._llm_service, "generate_json", fake_json)
    result = gen.regenerate_section(
        FeatureTemplateRegenerateSectionRequest(
            section="codeFiles",
            language="java",
            featureName="로그인",
            level=DifficultyLevel.BEGINNER,
            includeCode=True,
        )
    )
    assert called["n"] == 1
    assert result.generationMode == "section_regenerated"
    assert result.section == "codeFiles"
    assert len(result.content) >= 1


def test_direct_generate_route_returns_instant_skeleton() -> None:
    client = TestClient(app)
    resp = client.post(
        "/ai/feature-template/generate",
        json={
            "language": "java",
            "framework": "spring-boot",
            "featureName": "로그인",
            "level": "beginner",
            "includeCode": False,
            "includeMissions": False,
            "includeInterview": False,
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["source"] == "instant"
    assert data["instantSkeletonUsed"] is True
    assert data["qualityBaselineApplied"] is True
    _assert_no_weak_placeholders(data["template"])

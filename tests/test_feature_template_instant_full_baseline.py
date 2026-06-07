"""23차: instant full baseline (codeFiles/missions/interviewQuestions)."""

import re
import time
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.models.enums import DifficultyLevel
from app.schemas.feature_template import FeatureTemplateGenerateRequest
from app.services.agent_orchestrator import AgentOrchestrator
from app.services.feature_template_generator import FeatureTemplateGenerator
from app.services.feature_template_instant_skeleton import (
    QUALITY_INSTANT_FULL_GENERATION_MODE,
    QUALITY_INSTANT_GENERATION_MODE,
    build_quality_instant_skeleton_dict,
)

_FORBIDDEN = (
    re.compile(r"\bTODO\b", re.I),
    re.compile(r"\bplaceholder\b", re.I),
    re.compile(r"생략"),
)


def _login_request(**kwargs: object) -> FeatureTemplateGenerateRequest:
    base = dict(
        language="java",
        framework="Spring Boot",
        featureName="로그인",
        level=DifficultyLevel.BEGINNER,
        includeCode=True,
        includeMissions=True,
        includeInterview=True,
    )
    base.update(kwargs)
    return FeatureTemplateGenerateRequest(**base)


def _file_names(code_files: list[dict]) -> set[str]:
    return {str(item.get("fileName", "")) for item in code_files}


def _assert_no_forbidden(payload: object) -> None:
    if isinstance(payload, dict):
        for value in payload.values():
            _assert_no_forbidden(value)
    elif isinstance(payload, list):
        for item in payload:
            _assert_no_forbidden(item)
    elif isinstance(payload, str):
        for pattern in _FORBIDDEN:
            assert not pattern.search(payload), payload


def test_direct_generate_include_code_returns_code_files() -> None:
    client = TestClient(app)
    resp = client.post(
        "/ai/feature-template/generate",
        json={
            "language": "java",
            "framework": "Spring Boot",
            "featureName": "로그인",
            "level": "beginner",
            "includeCode": True,
            "includeMissions": True,
            "includeInterview": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    template = data["template"]
    assert len(template["codeFiles"]) >= 4
    assert data["source"] == "instant"
    assert data["generationMode"] == QUALITY_INSTANT_FULL_GENERATION_MODE
    assert data["instantFullBaselineApplied"] is True


def test_login_code_files_contain_required_java_files() -> None:
    normalized = build_quality_instant_skeleton_dict(_login_request())
    names = _file_names(normalized["codeFiles"])
    assert "LoginController.java" in names
    assert "LoginService.java" in names
    assert "LoginRequest.java" in names
    assert "LoginResponse.java" in names
    _assert_no_forbidden(normalized["codeFiles"])


def test_include_missions_returns_at_least_two() -> None:
    normalized = build_quality_instant_skeleton_dict(_login_request())
    assert len(normalized["missions"]) >= 2
    assert normalized["missions"][0]["title"]
    assert normalized["missions"][0]["requirements"]
    assert normalized["missions"][0]["successCriteria"]


def test_include_interview_returns_at_least_three() -> None:
    normalized = build_quality_instant_skeleton_dict(_login_request())
    assert len(normalized["interviewQuestions"]) >= 3
    assert normalized["interviewQuestions"][0]["question"]
    assert normalized["interviewQuestions"][0]["sampleAnswer"]


def test_include_code_false_clears_code_files() -> None:
    normalized = build_quality_instant_skeleton_dict(_login_request(includeCode=False))
    assert normalized["codeFiles"] == []


def test_include_missions_false_clears_missions() -> None:
    normalized = build_quality_instant_skeleton_dict(_login_request(includeMissions=False))
    assert normalized["missions"] == []


def test_include_interview_false_clears_interview_questions() -> None:
    normalized = build_quality_instant_skeleton_dict(
        _login_request(includeInterview=False)
    )
    assert normalized["interviewQuestions"] == []


def test_instant_full_path_stays_fast_on_llm_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "FEATURE_TEMPLATE_INSTANT_SKELETON_ENABLED", True)
    llm = MagicMock()
    llm.generate_json.side_effect = RuntimeError("timeout")
    gen = FeatureTemplateGenerator(llm_service=llm)

    t0 = time.perf_counter()
    result = gen.generate(_login_request())
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert result.source == "instant"
    assert result.generationMode == QUALITY_INSTANT_FULL_GENERATION_MODE
    assert result.fallbackUsed is True
    assert len(result.template.codeFiles) >= 4
    assert len(result.template.missions) >= 2
    assert len(result.template.interviewQuestions) >= 3
    assert elapsed_ms < 2000
    llm.generate_json.assert_called_once()


def test_all_flags_false_uses_instant_skeleton_on_llm_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gen = FeatureTemplateGenerator(llm_service=MagicMock())
    gen._llm_service.generate_json.side_effect = RuntimeError("timeout")
    result = gen.generate(
        _login_request(
            includeCode=False,
            includeMissions=False,
            includeInterview=False,
        )
    )
    assert result.generationMode == QUALITY_INSTANT_GENERATION_MODE
    assert result.instantFullBaselineApplied is False
    assert result.deferredSections == []
    assert result.fallbackUsed is True


def test_cache_key_uses_v5_prefix() -> None:
    key = AgentOrchestrator._build_feature_template_cache_key(
        feature_request=_login_request(),
        rag_references=[],
    )
    assert key.startswith("feature-template:instant-full:v5:")


def test_generic_feature_has_code_missions_interview_without_placeholders() -> None:
    normalized = build_quality_instant_skeleton_dict(
        FeatureTemplateGenerateRequest(
            language="java",
            framework="Spring Boot",
            featureName="게시글 작성",
            level=DifficultyLevel.BEGINNER,
            includeCode=True,
            includeMissions=True,
            includeInterview=True,
        )
    )
    assert len(normalized["codeFiles"]) >= 4
    assert len(normalized["missions"]) >= 2
    assert len(normalized["interviewQuestions"]) >= 3
    assert normalized["apiSpec"][0]["endpoint"] == "/api/posts"
    _assert_no_forbidden(normalized)

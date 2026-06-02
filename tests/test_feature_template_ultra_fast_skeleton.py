"""18차 ultra-fast skeleton 프로필 검증."""

from unittest.mock import MagicMock

import pytest

from app.core.config import settings
from app.models.enums import DifficultyLevel
from app.schemas.feature_template import FeatureTemplateGenerateRequest
from app.services.agent_orchestrator import AgentOrchestrator
from app.services.feature_template_generator import FeatureTemplateGenerator
from app.services.feature_template_normalizer import FeatureTemplateNormalizer
from app.services.prompt_builder import (
    build_feature_template_prompt,
    get_initial_generation_skeleton_metadata,
    is_ultra_fast_skeleton_enabled_for_initial_generate,
    resolve_initial_generation_skeleton_profile,
    skeleton_max_tokens_for_initial_generate,
    skeleton_rag_content_max_chars_for_initial_generate,
    skeleton_rag_top_k_for_initial_generate,
)


def _req(**kwargs: object) -> FeatureTemplateGenerateRequest:
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


def test_ultra_fast_skeleton_defaults_enabled() -> None:
    assert settings.FEATURE_TEMPLATE_ULTRA_FAST_SKELETON_ENABLED is True
    assert settings.FEATURE_TEMPLATE_SKELETON_RAG_TOP_K == 2
    assert settings.FEATURE_TEMPLATE_SKELETON_RAG_CONTENT_MAX_CHARS == 300
    assert settings.FEATURE_TEMPLATE_SKELETON_MAX_TOKENS == 800


def test_ultra_fast_takes_priority_over_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "FEATURE_TEMPLATE_ULTRA_FAST_SKELETON_ENABLED", True)
    monkeypatch.setattr(settings, "FEATURE_TEMPLATE_FAST_SKELETON_ENABLED", True)
    assert resolve_initial_generation_skeleton_profile() == "ultra_fast"
    assert is_ultra_fast_skeleton_enabled_for_initial_generate() is True


def test_fast_used_when_ultra_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "FEATURE_TEMPLATE_ULTRA_FAST_SKELETON_ENABLED", False)
    monkeypatch.setattr(settings, "FEATURE_TEMPLATE_FAST_SKELETON_ENABLED", True)
    assert resolve_initial_generation_skeleton_profile() == "fast"


def test_ultra_fast_prompt_defers_questions_and_recommendations() -> None:
    text = build_feature_template_prompt(_req())
    assert "basicQuestions: 반드시 []" in text
    assert "nextRecommendations: 반드시 []" in text
    assert '"basicQuestions": []' in text
    assert '"nextRecommendations": []' in text
    assert "missionId" not in text
    assert "LoginController.java" not in text


def test_ultra_fast_prompt_more_restrictive_than_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    ultra_text = build_feature_template_prompt(_req())
    monkeypatch.setattr(settings, "FEATURE_TEMPLATE_ULTRA_FAST_SKELETON_ENABLED", False)
    monkeypatch.setattr(settings, "FEATURE_TEMPLATE_FAST_SKELETON_ENABLED", True)
    fast_text = build_feature_template_prompt(_req())
    assert "50자 내외" in ultra_text
    assert "basicQuestions: 반드시 []" in ultra_text
    assert "basicQuestions: 정확히 3개" in fast_text


def test_include_code_true_still_empty_codefiles_in_ultra_fast() -> None:
    text = build_feature_template_prompt(_req(includeCode=True))
    assert "codeFiles/missions/interviewQuestions" in text or "codeFiles" in text
    assert '"codeFiles": []' in text


def test_skeleton_rag_params_for_ultra_fast() -> None:
    assert skeleton_rag_top_k_for_initial_generate() == 2
    assert skeleton_rag_content_max_chars_for_initial_generate() == 300


def test_skeleton_max_tokens_only_for_non_legacy(monkeypatch: pytest.MonkeyPatch) -> None:
    assert skeleton_max_tokens_for_initial_generate() == 800
    monkeypatch.setattr(settings, "FEATURE_TEMPLATE_ULTRA_FAST_SKELETON_ENABLED", False)
    monkeypatch.setattr(settings, "FEATURE_TEMPLATE_FAST_SKELETON_ENABLED", False)
    assert skeleton_max_tokens_for_initial_generate() is None


def test_normalizer_fills_empty_basic_questions_and_next_recs() -> None:
    request = _req(includeCode=False, includeMissions=False, includeInterview=False)
    minimal = {
        "overview": {
            "featureName": "로그인",
            "purpose": "짧은 목적",
            "useCases": [],
            "resultDescription": "짧은 결과",
            "techStack": ["java"],
            "learningGoals": [],
        },
        "requirements": [],
        "flow": {"steps": ["1) a", "2) b", "3) c"], "layers": []},
        "apiSpec": [],
        "codeFiles": [],
        "basicQuestions": [],
        "missions": [],
        "interviewQuestions": [],
        "nextRecommendations": [],
    }
    normalized = FeatureTemplateNormalizer.normalize(minimal, request)
    assert len(normalized["basicQuestions"]) == 3
    assert len(normalized["nextRecommendations"]) == 3
    assert normalized["codeFiles"] == []


def test_generate_passes_skeleton_max_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "FEATURE_TEMPLATE_INSTANT_SKELETON_ENABLED", False)
    llm = MagicMock()
    llm.provider = "ollama"
    gen = FeatureTemplateGenerator(llm_service=llm)
    seen: dict[str, object] = {}

    def fake_json(_prompt: str, **kwargs: object) -> dict:
        seen.update(kwargs)
        return {
            "overview": {
                "featureName": "로그인",
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

    monkeypatch.setattr(gen._llm_service, "generate_json", fake_json)
    result = gen.generate(_req())
    assert seen.get("max_tokens") == 800
    assert result.ultraFastSkeletonEnabled is True
    assert result.skeletonMaxTokens == 800
    assert result.skeletonRagTopK == 2
    assert result.skeletonRagContentMaxChars == 300


def test_regenerate_section_does_not_pass_skeleton_max_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.schemas.feature_template import FeatureTemplateRegenerateSectionRequest

    llm = MagicMock()
    llm.provider = "ollama"
    gen = FeatureTemplateGenerator(llm_service=llm)
    seen: dict[str, object] = {}

    def fake_json(_prompt: str, **kwargs: object) -> dict:
        seen.update(kwargs)
        return {
            "requirements": [
                {
                    "requirementId": "R-001",
                    "name": "n",
                    "description": "d",
                    "inputValue": "i",
                    "processCondition": "p",
                    "successResult": "s",
                    "failureResult": "f",
                    "priority": "HIGH",
                    "relatedScreenOrApi": "a",
                }
            ]
        }

    monkeypatch.setattr(gen._llm_service, "generate_json", fake_json)
    gen.regenerate_section(
        FeatureTemplateRegenerateSectionRequest(
            section="requirements",
            language="java",
            featureName="로그인",
            level=DifficultyLevel.BEGINNER,
        )
    )
    assert "max_tokens" not in seen


def test_feature_template_cache_key_includes_ultra_fast_settings() -> None:
    req = _req()
    key = AgentOrchestrator._build_feature_template_cache_key(
        feature_request=req,
        rag_references=[],
    )
    assert "feature-template:instant-full:v5:" in key


def test_skeleton_metadata_serializable() -> None:
    meta = get_initial_generation_skeleton_metadata()
    assert meta["ultraFastSkeletonEnabled"] is True
    assert meta["fastSkeletonEnabled"] is True
    assert meta["skeletonMaxTokens"] == 800
    assert meta["skeletonRagTopK"] == 2
    assert meta["skeletonRagContentMaxChars"] == 300


def test_ultra_fast_prompt_tighter_flow_and_rag_guidance() -> None:
    text = build_feature_template_prompt(_req())
    assert "steps 3개 이하" in text
    assert "layers 3개 이하" in text
    assert "50자 내외" in text
    assert "요약·재서술하지 말고" in text or "요약·재서술하지" in text


def test_normalizer_fills_short_login_overview_and_flow() -> None:
    request = _req(includeCode=False, includeMissions=False, includeInterview=False)
    minimal = {
        "overview": {
            "featureName": "로그인",
            "purpose": "",
            "useCases": [],
            "resultDescription": "x",
            "techStack": ["java"],
            "learningGoals": [],
        },
        "requirements": [],
        "flow": {"steps": ["1) a"], "layers": [{"layer": "X", "role": ""}]},
        "apiSpec": [
            {
                "method": "POST",
                "endpoint": "/api/feature",
                "requestBody": {},
                "responseBody": {},
            }
        ],
        "codeFiles": [],
        "basicQuestions": [],
        "missions": [],
        "interviewQuestions": [],
        "nextRecommendations": [],
    }
    normalized = FeatureTemplateNormalizer.normalize(minimal, request)
    assert len(normalized["overview"]["purpose"]) > 10
    assert len(normalized["flow"]["steps"]) >= 3
    assert len(normalized["flow"]["layers"]) >= 3
    assert normalized["apiSpec"][0]["endpoint"] == "/api/auth/login"


def test_cache_key_changes_when_skeleton_tuning_settings_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    req = _req()
    key_default = AgentOrchestrator._build_feature_template_cache_key(
        feature_request=req,
        rag_references=[],
    )
    monkeypatch.setattr(settings, "FEATURE_TEMPLATE_SKELETON_MAX_TOKENS", 750)
    key_tuned = AgentOrchestrator._build_feature_template_cache_key(
        feature_request=req,
        rag_references=[],
    )
    assert key_default != key_tuned

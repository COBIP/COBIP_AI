"""21차: embedding warm-up startup 검증."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, settings
from app.main import app
from app.services.embedding_service import EmbeddingService
from app.services.embedding_warmup_state import (
    get_embedding_warmup_state,
    run_startup_embedding_warmup,
)


def test_embedding_warmup_default_off_in_settings() -> None:
    s = Settings(_env_file=None)
    assert s.EMBEDDING_WARMUP_ENABLED is False
    assert "Spring Boot" in s.EMBEDDING_WARMUP_TEXT


def test_run_startup_skips_when_rag_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "EMBEDDING_WARMUP_ENABLED", True)
    monkeypatch.setattr(settings, "RAG_ENABLED", False)
    calls = {"n": 0}

    def fake_detail(self, text=None):
        calls["n"] += 1
        return True, None

    monkeypatch.setattr(EmbeddingService, "warm_up_with_detail", fake_detail)
    run_startup_embedding_warmup()
    state = get_embedding_warmup_state()
    assert state.embeddingWarmupSkippedReason == "rag_disabled"
    assert state.embeddingWarmupAttempted is False
    assert calls["n"] == 0


def test_run_startup_skips_when_warmup_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "EMBEDDING_WARMUP_ENABLED", False)
    monkeypatch.setattr(settings, "RAG_ENABLED", True)
    calls = {"n": 0}

    def fake_detail(self, text=None):
        calls["n"] += 1
        return True, None

    monkeypatch.setattr(EmbeddingService, "warm_up_with_detail", fake_detail)
    run_startup_embedding_warmup()
    state = get_embedding_warmup_state()
    assert state.embeddingWarmupSkippedReason == "warmup_disabled"
    assert calls["n"] == 0


def test_run_startup_warmup_failure_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "EMBEDDING_WARMUP_ENABLED", True)
    monkeypatch.setattr(settings, "RAG_ENABLED", True)

    def fake_detail(self, text=None):
        return False, "RuntimeError"

    monkeypatch.setattr(EmbeddingService, "warm_up_with_detail", fake_detail)
    run_startup_embedding_warmup()
    state = get_embedding_warmup_state()
    assert state.embeddingWarmupAttempted is True
    assert state.embeddingWarmupSucceeded is False
    assert state.embeddingWarmupErrorType == "RuntimeError"


def test_warm_up_with_detail_uses_embed_query_path(monkeypatch: pytest.MonkeyPatch) -> None:
    EmbeddingService._shared_model = None
    calls = {"embed": 0}

    class _FakeModel:
        def encode(self, text, convert_to_numpy=True, show_progress_bar=False):
            import numpy as np

            return np.zeros((1, 4), dtype=np.float32)

    def fake_get_model(self):
        EmbeddingService._shared_model = _FakeModel()
        return EmbeddingService._shared_model

    def fake_embed_query(self, query: str):
        calls["embed"] += 1
        fake_get_model(self)
        return [0.0, 0.0, 0.0, 0.0]

    monkeypatch.setattr(EmbeddingService, "embed_query", fake_embed_query)

    svc = EmbeddingService()
    ok, err = svc.warm_up_with_detail("로그인 warm up")
    assert ok is True
    assert err is None
    assert calls["embed"] == 1
    assert EmbeddingService.is_shared_model_loaded() is True


def test_lifespan_calls_warmup_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def fake_run(logger=None):
        calls["n"] += 1

    monkeypatch.setattr(
        "app.main.run_startup_embedding_warmup",
        fake_run,
    )
    with TestClient(app):
        pass
    assert calls["n"] >= 1


def test_health_includes_embedding_warmup_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "EMBEDDING_WARMUP_ENABLED", True)
    monkeypatch.setattr(settings, "RAG_ENABLED", False)
    run_startup_embedding_warmup()

    with patch("app.api.routes.health.QdrantService") as mock_qdrant:
        mock_qdrant.return_value.health_check.return_value = {"ok": True}
        client = TestClient(app)
        body = client.get("/health").json()

    data = body["data"]
    assert "embeddingWarmupEnabled" in data
    assert "embeddingWarmupAttempted" in data
    assert data["embeddingWarmupSkippedReason"] == "rag_disabled"

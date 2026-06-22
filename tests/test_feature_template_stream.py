"""POST /ai/feature-template/generate/stream SSE 응답 테스트."""

import json
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.feature_template import FeatureTemplateGenerateRequest
from app.services.feature_template_generator import FeatureTemplateGenerator

_CANONICAL_KEYS = frozenset(
    {
        "overview",
        "requirements",
        "flow",
        "apiSpec",
        "codeFiles",
        "basicQuestions",
        "missions",
        "interviewQuestions",
        "nextRecommendations",
    }
)

_STREAM_REQUEST = {
    "language": "Java",
    "featureName": "회원가입",
    "framework": "Spring Boot",
    "level": "beginner",
    "includeCode": False,
    "includeMissions": False,
    "includeInterview": False,
}


def _parse_sse_events(raw: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for block in raw.strip().split("\n\n"):
        if not block.strip():
            continue
        event_type: str | None = None
        data: dict | None = None
        for line in block.split("\n"):
            if line.startswith("event: "):
                event_type = line[len("event: ") :]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: ") :])
        if event_type is not None and data is not None:
            events.append((event_type, data))
    return events


def test_generate_stream_returns_sse_events() -> None:
    client = TestClient(app)
    with client.stream(
        "POST",
        "/ai/feature-template/generate/stream",
        json=_STREAM_REQUEST,
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        body = resp.read().decode("utf-8")

    events = _parse_sse_events(body)
    event_types = [event_type for event_type, _ in events]

    assert event_types.count("progress") >= 3
    assert event_types[-1] == "complete"

    progress_events = [data for event_type, data in events if event_type == "progress"]
    assert progress_events[0]["step"] == "analyze"
    assert progress_events[0]["status"] == "RUNNING"
    assert progress_events[0]["label"] == "요청 분석 중"
    assert progress_events[0]["progress"] == 5

    complete = events[-1][1]
    assert complete["status"] == "COMPLETED"
    assert complete["step"] == "completed"
    assert complete["label"] == "완료"
    assert complete["progress"] == 100
    assert set(complete["template"].keys()) == _CANONICAL_KEYS


def test_generate_stream_complete_template_matches_generate_api() -> None:
    client = TestClient(app)
    request = dict(_STREAM_REQUEST)

    generate_resp = client.post("/ai/feature-template/generate", json=request)
    assert generate_resp.status_code == 200
    expected_template = generate_resp.json()["data"]["template"]

    with client.stream(
        "POST",
        "/ai/feature-template/generate/stream",
        json=request,
    ) as stream_resp:
        assert stream_resp.status_code == 200
        body = stream_resp.read().decode("utf-8")

    events = _parse_sse_events(body)
    complete = events[-1][1]
    assert complete["template"] == expected_template


def test_generate_stream_error_event_on_failure() -> None:
    client = TestClient(app)

    def _raise(_request: FeatureTemplateGenerateRequest, _progress_callback=None):
        raise RuntimeError("stream generation failed")

    with patch.object(FeatureTemplateGenerator, "generate", side_effect=_raise):
        with client.stream(
            "POST",
            "/ai/feature-template/generate/stream",
            json=_STREAM_REQUEST,
        ) as resp:
            assert resp.status_code == 200
            body = resp.read().decode("utf-8")

    events = _parse_sse_events(body)
    assert len(events) == 1
    event_type, data = events[0]
    assert event_type == "error"
    assert data["status"] == "FAILED"
    assert data["step"] == "failed"
    assert data["label"] == "생성 실패"
    assert data["progress"] == 0
    assert "stream generation failed" in data["errorMessage"]

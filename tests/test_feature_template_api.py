"""POST /ai/feature-template/generate 응답 스키마 스모크."""

from fastapi.testclient import TestClient

from app.main import app

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


def test_generate_endpoint_template_has_all_sections() -> None:
    client = TestClient(app)
    resp = client.post(
        "/ai/feature-template/generate",
        json={
            "language": "Java",
            "featureName": "api_smoke",
            "level": "beginner",
            "includeCode": False,
            "includeMissions": False,
            "includeInterview": False,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("success") is True
    template = body["data"]["template"]
    assert set(template.keys()) == _CANONICAL_KEYS
    assert body["data"].get("appliedReferences") == []
    assert body["data"]["generationMode"] in {
        "skeleton",
        "fallback",
        "quality_instant_skeleton",
    }
    assert body["data"]["source"] in {"ollama", "fallback", "instant"}
    assert body["data"]["instantSkeletonUsed"] is True
    assert body["data"]["skeletonFirst"] is True
    assert body["data"]["deferredSections"] == [
        "codeFiles",
        "missions",
        "interviewQuestions",
    ]

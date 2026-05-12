"""POST /ai/feature-template/regenerate-section (7-5)."""

from fastapi.testclient import TestClient

from app.main import app


def _base_body(**overrides: object) -> dict:
    body: dict = {
        "language": "java",
        "featureName": "로그인",
        "level": "beginner",
        "section": "requirements",
    }
    body.update(overrides)
    return body


def test_regenerate_section_code_view_alias_maps_to_code_files() -> None:
    client = TestClient(app)
    resp = client.post(
        "/ai/feature-template/regenerate-section",
        json=_base_body(section="code_view", includeCode=True),
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["section"] == "codeFiles"
    assert isinstance(resp.json()["data"]["content"], list)


def test_regenerate_section_snake_case_api_spec_maps_to_camel() -> None:
    client = TestClient(app)
    resp = client.post(
        "/ai/feature-template/regenerate-section",
        json=_base_body(section="api_spec"),
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["section"] == "apiSpec"
    assert isinstance(data["content"], list)
    assert len(data["content"]) >= 1
    assert "apiName" in data["content"][0]


def test_regenerate_section_invalid_section_422() -> None:
    client = TestClient(app)
    resp = client.post(
        "/ai/feature-template/regenerate-section",
        json=_base_body(section="not_a_real_section"),
    )
    assert resp.status_code == 422


def test_regenerate_section_requirements_is_list() -> None:
    client = TestClient(app)
    resp = client.post(
        "/ai/feature-template/regenerate-section",
        json=_base_body(section="requirements"),
    )
    assert resp.status_code == 200
    content = resp.json()["data"]["content"]
    assert isinstance(content, list)
    if content:
        assert "requirementId" in content[0]


def test_regenerate_section_flow_is_dict() -> None:
    client = TestClient(app)
    resp = client.post(
        "/ai/feature-template/regenerate-section",
        json=_base_body(section="flow"),
    )
    assert resp.status_code == 200
    content = resp.json()["data"]["content"]
    assert isinstance(content, dict)
    assert "steps" in content and "layers" in content


def test_regenerate_section_include_code_false_code_files_empty() -> None:
    client = TestClient(app)
    resp = client.post(
        "/ai/feature-template/regenerate-section",
        json=_base_body(section="codeFiles", includeCode=False),
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["content"] == []


def test_regenerate_section_include_missions_false_missions_empty() -> None:
    client = TestClient(app)
    resp = client.post(
        "/ai/feature-template/regenerate-section",
        json=_base_body(section="missions", includeMissions=False),
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["content"] == []


def test_regenerate_section_include_interview_false_interview_empty() -> None:
    client = TestClient(app)
    resp = client.post(
        "/ai/feature-template/regenerate-section",
        json=_base_body(section="interviewQuestions", includeInterview=False),
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["content"] == []


def test_regenerate_section_accepts_context_alias() -> None:
    client = TestClient(app)
    resp = client.post(
        "/ai/feature-template/regenerate-section",
        json=_base_body(
            section="overview",
            context={"overview": {"featureName": "x"}},
        ),
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["section"] == "overview"
    assert isinstance(resp.json()["data"]["content"], dict)

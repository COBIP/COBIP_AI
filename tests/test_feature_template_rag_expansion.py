"""기능템플릿 RAG 문서 확장 · 검색 편향 · Java role 범용 보정 테스트."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.models.enums import DifficultyLevel
from app.schemas.feature_template import FeatureTemplateGenerateRequest
from app.services.feature_template_normalizer import FeatureTemplateNormalizer
from app.services import rag_service
from scripts.seed_qdrant_feature_template_docs import (
    build_feature_template_docs_seed_documents,
    build_payload,
    build_point_id,
    main as seed_main,
)


def _java_request(feature_name: str, **kwargs: object) -> FeatureTemplateGenerateRequest:
    base = dict(
        language="Java",
        framework="Spring Boot",
        featureName=feature_name,
        level=DifficultyLevel.BEGINNER,
        includeCode=True,
        includeMissions=False,
        includeInterview=False,
    )
    base.update(kwargs)
    return FeatureTemplateGenerateRequest(**base)


def _code_files_payload(entries: list[tuple[str, str]]) -> dict:
    return {
        "codeFiles": [
            {
                "fileName": fn,
                "filePath": f"src/main/java/com/example/{fn}",
                "role": role,
                "language": "java",
                "content": f"// {fn}",
            }
            for fn, role in entries
        ]
    }


# --- RAG docs / seed ---


def test_new_rag_docs_included_in_dry_run(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        "scripts.seed_qdrant_feature_template_docs.apply_feature_template_docs_seed",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no upsert")),
    )
    rc = seed_main(["--dry-run", "--json"])
    assert rc == 0
    import json

    summary = json.loads(capsys.readouterr().out.strip())
    titles = " | ".join(summary["titles"])
    assert summary["documentCount"] >= 8
    assert "회원가입" in titles
    assert "CRUD" in titles or "게시글" in titles
    assert "JWT" in titles


@pytest.mark.parametrize(
    "filename,expected_feature",
    [
        ("spring-boot-signup-standard.md", "회원가입"),
        ("spring-boot-crud-standard.md", "게시글 CRUD"),
        ("spring-boot-jwt-auth-standard.md", "JWT 인증"),
    ],
)
def test_new_docs_seed_payload_feature_names(filename: str, expected_feature: str) -> None:
    docs = build_feature_template_docs_seed_documents()
    by_path = {d.relative_path.rsplit("/", 1)[-1]: d for d in docs}
    doc = by_path[filename]
    payload = build_payload(doc)
    assert payload["source"] == "cobip_feature_template_standard"
    assert payload["category"] == "feature_template"
    assert payload["framework"] == "Spring Boot"
    assert payload["featureName"] == expected_feature
    assert payload["title"]
    assert payload["contentPreview"]


def test_seed_deterministic_ids_stable_for_new_docs() -> None:
    docs = build_feature_template_docs_seed_documents()
    new_names = {
        "spring-boot-signup-standard.md",
        "spring-boot-crud-standard.md",
        "spring-boot-jwt-auth-standard.md",
    }
    filtered = [d for d in docs if d.relative_path.rsplit("/", 1)[-1] in new_names]
    assert len(filtered) == 3
    ids1 = [build_point_id(d) for d in filtered]
    ids2 = [build_point_id(d) for d in filtered]
    assert ids1 == ids2
    for pid in ids1:
        assert uuid.UUID(pid).version == 5


# --- RAG query / rerank ---


@pytest.mark.parametrize(
    "feature_name,expected_tokens",
    [
        ("회원가입", ("회원가입", "SignupController", "POST /api/auth/signup")),
        ("게시글 CRUD", ("게시글", "PostController", "CRUD")),
        ("JWT 인증", ("JWT", "JwtTokenProvider", "Bearer")),
    ],
)
def test_retrieval_query_includes_feature_specific_keywords(
    feature_name: str, expected_tokens: tuple[str, ...]
) -> None:
    query = rag_service.build_feature_template_retrieval_query(
        message=None,
        feature_name=feature_name,
        framework="Spring Boot",
        language="Java",
        level="beginner",
    )
    for token in expected_tokens:
        assert token in query
    assert feature_name in query


def test_rerank_prefers_matching_feature_over_login() -> None:
    refs = [
        {
            "title": "로그인 표준",
            "content": "login",
            "score": 0.95,
            "featureName": "로그인",
            "category": "feature_template",
            "framework": "Spring Boot",
        },
        {
            "title": "회원가입 표준",
            "content": "signup",
            "score": 0.80,
            "featureName": "회원가입",
            "category": "feature_template",
            "framework": "Spring Boot",
        },
    ]
    ranked = rag_service.rerank_feature_template_rag_references(
        refs,
        feature_name="회원가입",
        framework="Spring Boot",
        top_k=1,
    )
    assert len(ranked) == 1
    assert ranked[0]["featureName"] == "회원가입"


def test_rerank_crud_doc_wins_for_crud_request() -> None:
    refs = [
        {
            "title": "로그인",
            "content": "a",
            "score": 0.9,
            "featureName": "로그인",
        },
        {
            "title": "CRUD",
            "content": "b",
            "score": 0.75,
            "featureName": "게시글 CRUD",
        },
    ]
    ranked = rag_service.rerank_feature_template_rag_references(
        refs,
        feature_name="게시글 CRUD",
        framework="Spring Boot",
        top_k=1,
    )
    assert ranked[0]["featureName"] == "게시글 CRUD"


# --- Java role inference ---


@pytest.mark.parametrize(
    "file_name,expected_role",
    [
        ("PostController.java", "REST API 컨트롤러"),
        ("PostService.java", "비즈니스 로직 서비스"),
        ("PostRepository.java", "데이터 접근 Repository"),
        ("PostCreateRequest.java", "요청 DTO"),
        ("PostUpdateRequest.java", "요청 DTO"),
        ("PostResponse.java", "응답 DTO"),
        ("SignupRequest.java", "요청 DTO"),
        ("SignupResponse.java", "응답 DTO"),
        ("JwtAuthenticationFilter.java", "인증/인가 필터"),
        ("JwtTokenProvider.java", "인증/토큰 Provider"),
    ],
)
def test_java_codefile_role_inference(file_name: str, expected_role: str) -> None:
    from app.services.feature_template_normalizer import _infer_java_code_file_role

    assert _infer_java_code_file_role(file_name) == expected_role


def test_crud_codefiles_roles_not_data_access_generic() -> None:
    raw = _code_files_payload(
        [
            ("PostController.java", "데이터 접근"),
            ("PostService.java", "데이터 접근"),
            ("PostRepository.java", "데이터 접근"),
            ("PostCreateRequest.java", "데이터 접근"),
            ("PostUpdateRequest.java", "데이터 접근"),
            ("PostResponse.java", "데이터 접근"),
        ]
    )
    out = FeatureTemplateNormalizer.normalize(
        raw,
        _java_request("게시글 CRUD"),
    )
    by_name = {f["fileName"]: f["role"] for f in out["codeFiles"]}
    assert by_name["PostController.java"] == "REST API 컨트롤러"
    assert by_name["PostService.java"] == "비즈니스 로직 서비스"
    assert by_name["PostRepository.java"] == "데이터 접근 Repository"
    assert by_name["PostCreateRequest.java"] == "요청 DTO"
    assert by_name["PostUpdateRequest.java"] == "요청 DTO"
    assert by_name["PostResponse.java"] == "응답 DTO"
    for fn, role in by_name.items():
        if fn != "PostRepository.java":
            assert role != "데이터 접근", fn


def test_signup_codefiles_roles_normalized() -> None:
    raw = _code_files_payload(
        [
            ("SignupRequest.java", "데이터 접근"),
            ("SignupResponse.java", "데이터 접근"),
        ]
    )
    out = FeatureTemplateNormalizer.normalize(raw, _java_request("회원가입"))
    by_name = {f["fileName"]: f["role"] for f in out["codeFiles"]}
    assert by_name["SignupRequest.java"] == "요청 DTO"
    assert by_name["SignupResponse.java"] == "응답 DTO"

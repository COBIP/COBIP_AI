"""Agentic RAG 14차: Qdrant 로그인 지식 seed script 테스트.

실제 Qdrant/Embedding 모델을 호출하지 않고, seed 문서 구조·id 안정성·
13차 ``rag_service`` 변환 흐름과의 호환성만 검증한다.
"""

from __future__ import annotations

import json
import re
import sys
import uuid
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.seed_qdrant_login_knowledge import (  # noqa: E402
    SEED_NAMESPACE,
    SeedDocument,
    build_login_seed_documents,
    build_payload,
    build_point_id,
    describe_documents,
    main,
)
from app.schemas.rag import RetrievedReference  # noqa: E402
from app.services import rag_service  # noqa: E402

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
_REQUIRED_PAYLOAD_KEYS = {
    "title",
    "content",
    "sourceType",
    "docType",
    "section",
    "framework",
    "language",
    "featureName",
    "level",
    "path",
    "tags",
}


def test_seed_documents_have_minimum_count_and_login_focus() -> None:
    docs = build_login_seed_documents()
    assert len(docs) >= 9
    titles = " | ".join(d.title for d in docs).lower()
    # 로그인 / JWT / BCrypt / API / DTO / 계층 / skeleton-first 핵심 컨셉이 포함되어야 함
    assert "로그인" in titles
    assert "api" in titles
    assert "dto" in titles
    assert "jwt" in titles
    assert "bcrypt" in titles
    assert "계층" in titles or "controller" in titles
    assert "skeleton" in titles


def test_each_document_has_required_fields_and_nontrivial_content() -> None:
    docs = build_login_seed_documents()
    for doc in docs:
        assert isinstance(doc, SeedDocument)
        assert doc.title.strip()
        assert doc.feature_name == "로그인"
        assert doc.framework == "Spring Boot"
        assert doc.language == "Java"
        assert doc.level == "beginner"
        assert doc.section
        assert doc.doc_type == "feature_template_reference"
        assert doc.path.startswith("seed/spring-boot-login/")
        assert isinstance(doc.tags, tuple) and len(doc.tags) >= 2
        # 내용이 빈약하지 않아야 함
        assert len(doc.content) >= 120, f"too short content for {doc.title}"


def test_payload_has_required_keys_and_matches_rag_service_metadata_contract() -> None:
    docs = build_login_seed_documents()
    for doc in docs:
        payload = build_payload(doc)
        assert _REQUIRED_PAYLOAD_KEYS.issubset(payload.keys())
        assert isinstance(payload["title"], str) and payload["title"]
        assert isinstance(payload["content"], str) and payload["content"]
        assert isinstance(payload["tags"], list)
        # 13차 변환이 metadata에서 보존하는 키들은 payload에 flat으로 들어가 있어야 한다
        for k in ("docType", "section", "path"):
            assert k in payload


def test_point_id_is_deterministic_uuid5_and_stable_across_runs() -> None:
    docs = build_login_seed_documents()
    ids_first = [build_point_id(d) for d in docs]
    ids_second = [build_point_id(d) for d in docs]
    assert ids_first == ids_second
    assert len(set(ids_first)) == len(ids_first), "ids must be unique across documents"
    for pid in ids_first:
        assert _UUID_RE.match(pid), f"not a UUID string: {pid}"
        # UUIDv5 로 정확히 생성되었는지 검증
        parsed = uuid.UUID(pid)
        assert parsed.version == 5


def test_point_id_changes_when_section_or_path_changes() -> None:
    base = SeedDocument(
        title="동일 제목",
        content="동일 내용",
        doc_type="feature_template_reference",
        section="apiSpec",
        framework="Spring Boot",
        language="Java",
        feature_name="로그인",
        level="beginner",
        path="seed/spring-boot-login/a",
        tags=("login",),
    )
    other_section = SeedDocument(**{**base.__dict__, "section": "requirements"})
    other_path = SeedDocument(**{**base.__dict__, "path": "seed/spring-boot-login/b"})
    assert build_point_id(base) != build_point_id(other_section)
    assert build_point_id(base) != build_point_id(other_path)


def test_payload_is_compatible_with_rag_service_hit_to_reference() -> None:
    """seed payload → RetrievedReference → ragReference 변환이 정상 동작해야 한다.

    이는 13차 ``rag_service._hit_to_reference`` 변환 흐름과 직접 맞물린다.
    """

    docs = build_login_seed_documents()
    sample = docs[0]
    payload = build_payload(sample)

    # retriever_service._payload_text가 content를 잘 뽑는지 (간접 검증)
    assert "content" in payload
    # retriever_service는 title/content/text/body/description/sourceType 외 키를 metadata로 모은다.
    expected_metadata_keys = {
        "docType",
        "section",
        "framework",
        "language",
        "featureName",
        "level",
        "path",
        "tags",
    }
    metadata = {
        k: v
        for k, v in payload.items()
        if k
        not in ("title", "content", "text", "body", "description", "sourceType")
    }
    assert expected_metadata_keys.issubset(metadata.keys())

    retrieved = RetrievedReference(
        id=build_point_id(sample),
        title=payload["title"],
        content=payload["content"],
        score=0.91,
        sourceType=payload["sourceType"],
        metadata=metadata,
    )

    out = rag_service._hit_to_reference(retrieved.model_dump())
    assert out is not None
    assert out["source"] == "qdrant"
    assert out["title"] == sample.title
    assert sample.content[:40] in out["content"]
    assert out["sourceType"] == "document"
    assert out["score"] == 0.91
    # 13차에서 보존되는 metadata 키 (docType/section/path)는 그대로 노출된다.
    assert out["metadata"]["docType"] == "feature_template_reference"
    assert out["metadata"]["section"] == sample.section
    assert out["metadata"]["path"] == sample.path


def test_describe_documents_produces_safe_preview_only() -> None:
    docs = build_login_seed_documents()
    previews = describe_documents(docs)
    assert len(previews) == len(docs)
    for p in previews:
        assert _UUID_RE.match(p["id"])
        assert p["title"]
        assert p["contentChars"] > 0
        assert isinstance(p["payloadKeys"], list)
        assert "content" in p["payloadKeys"]
        assert "title" in p["payloadKeys"]


def test_main_dry_run_does_not_touch_external_services(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """dry-run에서는 EmbeddingService / QdrantService import / 초기화가 일어나지 않아야 한다."""

    def _boom(*_a, **_kw):  # pragma: no cover - 호출되면 안 됨
        raise AssertionError("apply_seed_upsert must not run in dry-run mode")

    monkeypatch.setattr(
        "scripts.seed_qdrant_login_knowledge.apply_seed_upsert",
        _boom,
    )

    rc = main(["--dry-run", "--json"])
    assert rc == 0
    captured = capsys.readouterr().out.strip()
    summary = json.loads(captured)
    assert summary["mode"] == "dry-run"
    assert summary["documentCount"] >= 9
    assert summary["upsert"] is None
    assert any("로그인" in t for t in summary["titles"])
    # preview에 deterministic id가 그대로 노출되어야 한다.
    sample_id = summary["previews"][0]["id"]
    assert _UUID_RE.match(sample_id)


def test_main_default_mode_is_dry_run(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def _boom(*_a, **_kw):  # pragma: no cover - 호출되면 안 됨
        raise AssertionError("default mode must be dry-run")

    monkeypatch.setattr(
        "scripts.seed_qdrant_login_knowledge.apply_seed_upsert",
        _boom,
    )

    rc = main([])
    assert rc == 0
    out = capsys.readouterr().out
    assert "mode=dry-run" in out


def test_main_apply_invokes_upsert_helper(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """--apply 시 apply_seed_upsert가 호출되며, 모킹된 결과가 출력에 반영된다."""

    calls: dict[str, object] = {}

    def fake_apply(docs, *, collection_name=None):
        calls["docs_count"] = len(docs)
        calls["collection_name"] = collection_name
        return {
            "ok": True,
            "upsertedCount": len(docs),
            "collection": collection_name or "test_collection",
            "vectorSize": 1024,
        }

    monkeypatch.setattr(
        "scripts.seed_qdrant_login_knowledge.apply_seed_upsert",
        fake_apply,
    )

    rc = main(["--apply", "--collection", "test_collection", "--json"])
    assert rc == 0
    summary = json.loads(capsys.readouterr().out.strip())
    assert summary["mode"] == "apply"
    assert summary["upsert"]["ok"] is True
    assert summary["upsert"]["upsertedCount"] == summary["documentCount"]
    assert summary["upsert"]["collection"] == "test_collection"
    assert summary["upsert"]["vectorSize"] == 1024
    assert calls["docs_count"] == summary["documentCount"]
    assert calls["collection_name"] == "test_collection"


def test_seed_namespace_is_stable() -> None:
    """SEED_NAMESPACE는 외부 명시 없이 절대 바뀌면 안 된다 (id 안정성의 핵심)."""

    assert isinstance(SEED_NAMESPACE, uuid.UUID)
    assert str(SEED_NAMESPACE) == "d7c1f3fd-1bcf-4e0e-9b53-2bbb6e8a1e10"

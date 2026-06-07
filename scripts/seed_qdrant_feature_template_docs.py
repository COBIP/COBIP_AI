"""COBIP 기능템플릿 RAG 원본 문서 → Qdrant seed script.

``docs/rag/feature-template/*.md`` 파일을 읽어 ``cobip_knowledge`` 컬렉션에 upsert한다.
기본 동작은 **dry-run** — ``--apply`` 없이는 외부 Qdrant/Embedding 호출 없음.

Idempotency: point id는 ``uuid.uuid5(SEED_NAMESPACE, relative_path)`` 로 deterministic.

사용 예::

    python scripts/seed_qdrant_feature_template_docs.py --dry-run --json
    python scripts/seed_qdrant_feature_template_docs.py --apply
    python scripts/seed_qdrant_login_knowledge.py --apply --include-feature-template-docs
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "DOCS_DIR",
    "FEATURE_TEMPLATE_SEED_NAMESPACE",
    "FeatureTemplateSeedDocument",
    "apply_feature_template_docs_seed",
    "build_feature_template_docs_seed_documents",
    "build_payload",
    "build_point_id",
    "describe_documents",
    "main",
]

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = _REPO_ROOT / "docs" / "rag" / "feature-template"

FEATURE_TEMPLATE_SEED_NAMESPACE = uuid.UUID("a3e8b2c1-4f5d-6e7a-8b9c-0d1e2f3a4b5c")

_PREVIEW_CHARS = 200
_SOURCE = "cobip_feature_template_standard"
_CATEGORY = "feature_template"

_FILE_META: dict[str, tuple[str, str, str]] = {
    "spring-boot-login-standard.md": ("Spring Boot", "로그인", "login-standard"),
    "spring-boot-auth-jwt-bcrypt.md": ("Spring Boot", "로그인", "auth-jwt-bcrypt"),
    "spring-boot-signup-standard.md": ("Spring Boot", "회원가입", "signup-standard"),
    "spring-boot-crud-standard.md": ("Spring Boot", "게시글 CRUD", "crud-standard"),
    "spring-boot-jwt-auth-standard.md": ("Spring Boot", "JWT 인증", "jwt-auth-standard"),
    "cobip-feature-template-section-rules.md": ("Spring Boot", "공통", "section-rules"),
    "cobip-api-spec-rules.md": ("Spring Boot", "공통", "api-spec-rules"),
    "feature-template-quality-anti-patterns.md": ("Spring Boot", "공통", "anti-patterns"),
}


def _tags_for_document(feature_name: str, section: str) -> tuple[str, ...]:
    slug = feature_name.replace(" ", "-").lower() if feature_name else "common"
    return ("feature-template", "cobip", section, "spring-boot", slug)


@dataclass(frozen=True)
class FeatureTemplateSeedDocument:
    """docs/rag/feature-template 마크다운 1건."""

    title: str
    content: str
    relative_path: str
    framework: str
    feature_name: str
    section: str
    tags: tuple[str, ...]


def _extract_title(markdown: str, fallback: str) -> str:
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return fallback


def build_feature_template_docs_seed_documents(
    docs_dir: Path | None = None,
) -> list[FeatureTemplateSeedDocument]:
    """``docs/rag/feature-template/*.md`` 를 읽어 seed 문서 목록을 만든다."""

    root = docs_dir or DOCS_DIR
    if not root.is_dir():
        return []

    docs: list[FeatureTemplateSeedDocument] = []
    for path in sorted(root.glob("*.md")):
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            continue
        rel = str(path.relative_to(_REPO_ROOT)).replace("\\", "/")
        meta = _FILE_META.get(path.name, ("Spring Boot", "공통", path.stem))
        framework, feature_name, section = meta
        title = _extract_title(text, path.stem.replace("-", " "))
        tags = _tags_for_document(feature_name, section)
        docs.append(
            FeatureTemplateSeedDocument(
                title=title,
                content=text,
                relative_path=rel,
                framework=framework,
                feature_name=feature_name,
                section=section,
                tags=tags,
            )
        )
    return docs


def build_payload(doc: FeatureTemplateSeedDocument) -> dict[str, Any]:
    """Qdrant payload — retriever/rag_service/appliedReferences와 호환."""

    preview = doc.content[:_PREVIEW_CHARS]
    if len(doc.content) > _PREVIEW_CHARS:
        preview = preview + "…"

    return {
        "title": doc.title,
        "content": doc.content,
        "contentPreview": preview,
        "source": _SOURCE,
        "category": _CATEGORY,
        "sourceType": "document",
        "docType": "feature_template_standard",
        "section": doc.section,
        "framework": doc.framework,
        "language": "Java",
        "featureName": doc.feature_name,
        "level": "beginner",
        "path": doc.relative_path,
        "tags": list(doc.tags),
    }


def build_point_id(doc: FeatureTemplateSeedDocument) -> str:
    """deterministic UUIDv5 — 동일 md 경로 → 동일 id."""

    return str(uuid.uuid5(FEATURE_TEMPLATE_SEED_NAMESPACE, doc.relative_path))


def describe_documents(docs: list[FeatureTemplateSeedDocument]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for doc in docs:
        payload = build_payload(doc)
        out.append(
            {
                "id": build_point_id(doc),
                "title": doc.title,
                "relativePath": doc.relative_path,
                "framework": doc.framework,
                "featureName": doc.feature_name,
                "section": doc.section,
                "contentChars": len(doc.content),
                "contentPreview": payload["contentPreview"],
                "payloadKeys": sorted(payload.keys()),
                "source": payload["source"],
                "category": payload["category"],
            }
        )
    return out


def apply_feature_template_docs_seed(
    docs: list[FeatureTemplateSeedDocument],
    *,
    collection_name: str | None = None,
) -> dict[str, Any]:
    """실제 Qdrant upsert. dry-run에서는 호출되지 않는다."""

    from app.core.config import settings
    from app.services.embedding_service import EmbeddingService
    from app.services.qdrant_service import QdrantService

    if not docs:
        return {
            "ok": True,
            "upsertedCount": 0,
            "collection": collection_name or settings.QDRANT_COLLECTION,
            "vectorSize": 0,
            "reason": "no_documents",
        }

    emb = EmbeddingService()
    qd = QdrantService()
    target = collection_name or settings.QDRANT_COLLECTION

    vectors: list[list[float]] = []
    for doc in docs:
        vectors.append(emb.embed_text(doc.content))

    vector_size = len(vectors[0]) if vectors else 0
    ensured = qd.ensure_collection(vector_size=vector_size, collection_name=target)
    if not ensured:
        logger.warning(
            "feature-template docs seed aborted reason=ensure_collection_failed collection=%s",
            target,
        )
        return {
            "ok": False,
            "upsertedCount": 0,
            "collection": target,
            "vectorSize": vector_size,
            "reason": "ensure_collection_failed",
        }

    points: list[dict[str, Any]] = []
    for doc, vec in zip(docs, vectors):
        points.append(
            {
                "id": build_point_id(doc),
                "vector": vec,
                "payload": build_payload(doc),
            }
        )

    ok = qd.upsert(points, collection_name=target)
    return {
        "ok": bool(ok),
        "upsertedCount": len(points) if ok else 0,
        "collection": target,
        "vectorSize": vector_size,
    }


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "COBIP 기능템플릿 RAG 원본 문서(docs/rag/feature-template) seed. "
            "기본은 dry-run."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="실제 Qdrant upsert.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="외부 호출 없이 preview만 출력 (기본).",
    )
    parser.add_argument(
        "--collection",
        default=None,
        help="대상 collection (미지정 시 settings.QDRANT_COLLECTION).",
    )
    parser.add_argument(
        "--docs-dir",
        default=None,
        help="마크다운 원본 디렉터리 (기본: docs/rag/feature-template).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON 출력.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s - %(message)s")
    args = _parse_args(argv)

    docs_dir = Path(args.docs_dir) if args.docs_dir else DOCS_DIR
    docs = build_feature_template_docs_seed_documents(docs_dir)
    previews = describe_documents(docs)
    is_dry_run = not args.apply

    summary: dict[str, Any] = {
        "mode": "dry-run" if is_dry_run else "apply",
        "documentCount": len(docs),
        "docsDir": str(docs_dir),
        "titles": [p["title"] for p in previews],
        "previews": previews,
    }

    if is_dry_run:
        summary["upsert"] = None
        summary["note"] = (
            "dry-run: Qdrant/embedding 호출 없음. 실제 upsert는 --apply 필요."
        )
    else:
        try:
            result = apply_feature_template_docs_seed(
                docs, collection_name=args.collection
            )
        except Exception as exc:  # pragma: no cover
            logger.error(
                "feature-template docs seed failed errorType=%s message=%s",
                type(exc).__name__,
                exc,
            )
            summary["upsert"] = {
                "ok": False,
                "errorType": type(exc).__name__,
                "message": str(exc),
            }
            _emit(summary, as_json=args.json)
            return 1
        summary["upsert"] = result

    _emit(summary, as_json=args.json)
    return 0


def _emit(summary: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    print(
        f"[seed-feature-template] mode={summary['mode']} "
        f"documentCount={summary['documentCount']} docsDir={summary['docsDir']}"
    )
    for p in summary["previews"]:
        print(
            f"  - id={p['id']} section={p['section']} title={p['title']} "
            f"source={p['source']} category={p['category']}"
        )
        preview = p["contentPreview"]
        short = preview[:120] + ("…" if len(preview) > 120 else "")
        print(f"      preview: {short}")
    if summary.get("upsert") is None:
        print(f"[seed-feature-template] {summary['note']}")
    else:
        print(f"[seed-feature-template] upsert result={summary['upsert']}")


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

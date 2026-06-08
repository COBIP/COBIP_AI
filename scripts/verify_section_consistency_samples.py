#!/usr/bin/env python3
"""signup/crud/jwt section consistency 샘플 검증."""

from __future__ import annotations

import sys

from fastapi.testclient import TestClient

from app.main import app

_BAD_SIGNUP_REQUIREMENTS = [
    {"requirementId": "R-001", "name": "사용자 등록", "description": "d", "inputValue": "x", "processCondition": "x", "successResult": "ok", "failureResult": "f", "priority": "HIGH", "relatedScreenOrApi": "a"},
    {"requirementId": "R-002", "name": "사용자 정보 수정", "description": "d", "inputValue": "x", "processCondition": "x", "successResult": "ok", "failureResult": "f", "priority": "HIGH", "relatedScreenOrApi": "a"},
    {"requirementId": "R-003", "name": "사용자 정보 삭제", "description": "d", "inputValue": "x", "processCondition": "x", "successResult": "ok", "failureResult": "f", "priority": "HIGH", "relatedScreenOrApi": "a"},
]


def _check_signup_via_normalize(client: TestClient) -> tuple[bool, str]:
    """LLM 없이 normalizer 경유 재현 — 운영에서 발견된 bad requirements 케이스."""

    from app.services.feature_template_normalizer import FeatureTemplateNormalizer
    from tests.test_feature_template_bucket_guards import _req

    raw = {
        "overview": {"featureName": "회원가입", "purpose": "", "useCases": [], "resultDescription": "", "techStack": [], "learningGoals": []},
        "requirements": _BAD_SIGNUP_REQUIREMENTS,
        "flow": {"steps": ["1"], "layers": []},
        "apiSpec": [{"method": "POST", "endpoint": "/api/auth/signup", "apiName": "signup", "description": "d", "requestBody": {}, "responseBody": {}, "status": 201}],
        "codeFiles": [],
        "basicQuestions": [],
        "missions": [{"missionId": "M-1", "title": "구현 미션 1", "description": "d", "missionType": "impl", "requirements": [], "successCriteria": [], "relatedRequirements": [], "difficulty": "beginner"}],
        "interviewQuestions": [],
        "nextRecommendations": [],
    }
    out = FeatureTemplateNormalizer.normalize(raw, _req("회원가입"))
    blob = str(out)
    ok = (
        "사용자 정보 수정" not in blob
        and "사용자 정보 삭제" not in blob
        and "구현 미션 1" not in [m["title"] for m in out["missions"]]
        and any(s.get("endpoint") == "/api/auth/signup" for s in out["apiSpec"])
    )
    req_names = [r["name"] for r in out["requirements"]]
    return ok, f"requirements={req_names}, missions={[m['title'] for m in out['missions']]}"


def main() -> int:
    client = TestClient(app)
    rows: list[tuple[str, bool, str]] = []

    ok, detail = _check_signup_via_normalize(client)
    rows.append(("signup bad-requirements normalize", ok, detail))

    for feature, forbidden in (
        ("회원가입", ("사용자 정보 수정", "구현 미션 1")),
        ("게시글 CRUD", ("회원가입", "이메일 중복")),
        ("JWT 인증", ("회원가입", "게시글 CRUD")),
    ):
        resp = client.post(
            "/ai/feature-template/generate",
            json={
                "language": "Java",
                "framework": "Spring Boot",
                "featureName": feature,
                "level": "beginner",
                "includeCode": True,
                "includeMissions": True,
                "includeInterview": True,
            },
        )
        passed = resp.status_code == 200 and resp.json().get("success")
        detail = resp.text[:120]
        if passed:
            t = resp.json()["data"]["template"]
            blob = str(t)
            req_names = [r.get("name", "") for r in t.get("requirements", [])]
            mission_titles = [m.get("title", "") for m in t.get("missions", [])]
            bad = any(f in blob for f in forbidden) or any(
                title.startswith("구현 미션") for title in mission_titles
            )
            passed = passed and not bad
            detail = f"req={req_names[:3]} missions={mission_titles[:2]}"
        rows.append((f"{feature} generate", bool(passed), detail))

    print("| 샘플 | PASS | 상세 |")
    print("|---|---|---|")
    for name, ok, detail in rows:
        print(f"| {name} | {'PASS' if ok else 'FAIL'} | {detail[:100]} |")
    return 0 if all(r[1] for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())

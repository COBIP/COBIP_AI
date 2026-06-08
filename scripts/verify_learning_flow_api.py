#!/usr/bin/env python3
"""학습 플로우 API 수동 검증 스크립트."""

from __future__ import annotations

import json
import sys

from fastapi.testclient import TestClient

from app.main import app
from app.services.feature_template_bucket_guards import (
    _canonical_crud_codefiles,
    _canonical_jwt_codefiles,
    _canonical_signup_codefiles,
)


def _print_row(scenario: str, status: int, success: bool | None, detail: str, verdict: str) -> None:
    print(f"| {scenario} | {status} | {success} | {detail} | {verdict} |")


def main() -> int:
    client = TestClient(app)
    rows: list[tuple[str, int, bool | None, str, str]] = []

    health = client.get("/health")
    rows.append(
        (
            "health",
            health.status_code,
            None,
            health.text[:80],
            "PASS" if health.status_code == 200 else "FAIL",
        )
    )

    buckets = [
        ("signup generate", {"language": "Java", "framework": "Spring Boot", "featureName": "회원가입", "level": "beginner", "includeCode": True, "includeMissions": True, "includeInterview": True}),
        ("crud generate", {"language": "Java", "framework": "Spring Boot", "featureName": "게시글 CRUD", "level": "beginner", "includeCode": True, "includeMissions": True, "includeInterview": True}),
        ("jwt generate", {"language": "Java", "framework": "Spring Boot", "featureName": "JWT 로그인 인증 기능", "level": "beginner", "includeCode": True, "includeMissions": True, "includeInterview": True}),
    ]

    for name, payload in buckets:
        resp = client.post("/ai/feature-template/generate", json=payload)
        ok = resp.status_code == 200 and resp.json().get("success") is True
        detail = "error"
        if ok:
            t = resp.json()["data"]["template"]
            eps = [f"{s.get('method')} {s.get('endpoint')}" for s in t.get("apiSpec", [])]
            detail = f"apiSpec={eps[:3]} codeFiles={len(t.get('codeFiles', []))}"
        rows.append((name, resp.status_code, resp.json().get("success") if resp.status_code == 200 else None, detail, "PASS" if ok else "FAIL"))

    def _mission_payload(feature_name: str, files: dict, api_specs: list[dict]) -> dict:
        return {
            "featureName": feature_name,
            "mission": {
                "missionId": "M-001",
                "title": "구현",
                "description": "구현",
                "missionType": "implementation",
                "requirements": ["구현"],
                "successCriteria": ["ok"],
                "relatedRequirements": ["R-001"],
                "difficulty": "beginner",
            },
            "submittedCode": [
                {"fileName": k, "filePath": v["filePath"], "language": "java", "content": v["content"]}
                for k, v in files.items()
            ],
            "requirements": [
                {
                    "requirementId": "R-001",
                    "name": "핵심 기능",
                    "description": "controller service repository endpoint",
                    "inputValue": "dto",
                    "processCondition": "ok",
                    "successResult": "200",
                    "failureResult": "400",
                    "priority": "HIGH",
                    "relatedScreenOrApi": api_specs[0]["endpoint"],
                }
            ],
            "apiSpecs": api_specs,
        }

    mission_cases = [
        ("signup mission feedback", "회원가입", _canonical_signup_codefiles(), [{"apiName": "signup", "method": "POST", "endpoint": "/api/auth/signup", "description": "d", "requestBody": {}, "responseBody": {}, "status": 201}]),
        ("crud mission feedback", "게시글 CRUD", _canonical_crud_codefiles(), [{"apiName": "list", "method": "GET", "endpoint": "/api/posts", "description": "d", "requestBody": {}, "responseBody": {}, "status": 200}]),
        ("jwt mission feedback", "JWT 인증", _canonical_jwt_codefiles(), [{"apiName": "login", "method": "POST", "endpoint": "/api/auth/login", "description": "d", "requestBody": {}, "responseBody": {}, "status": 200}]),
    ]

    for name, feature, files, specs in mission_cases:
        resp = client.post("/ai/mission/feedback", json=_mission_payload(feature, files, specs))
        ok = resp.status_code == 200 and resp.json().get("success") is True
        detail = resp.text[:80]
        if ok:
            d = resp.json()["data"]
            detail = f"score={d.get('score')} passed={d.get('passed')}"
        rows.append((name, resp.status_code, resp.json().get("success") if resp.status_code == 200 else None, detail, "PASS" if ok and resp.json()["data"].get("passed") else ("PARTIAL" if ok else "FAIL")))

    quiz = client.post(
        "/ai/quiz/grade",
        json={
            "featureName": "회원가입",
            "question": {
                "questionId": "Q-001",
                "type": "short_answer",
                "question": "비밀번호 저장?",
                "answer": "BCrypt 해시",
                "explanation": "평문 금지",
                "difficulty": "beginner",
            },
            "userAnswer": "bcrypt hash",
            "relatedApiSpecs": [
                {
                    "method": "POST",
                    "endpoint": "/api/auth/signup",
                    "requestHeaders": {"Content-Type": "application/json"},
                    "requestFields": [{"fieldName": "email"}],
                    "errorResponses": [{"statusCode": 409, "errorCode": "DUP", "message": "dup"}],
                }
            ],
        },
    )
    ok = quiz.status_code == 200 and quiz.json().get("success") is True
    detail = quiz.text[:80]
    if ok:
        detail = f"isCorrect={quiz.json()['data'].get('isCorrect')} score={quiz.json()['data'].get('score')}"
    rows.append(("quiz grade", quiz.status_code, quiz.json().get("success") if quiz.status_code == 200 else None, detail, "PASS" if ok and quiz.json()["data"].get("isCorrect") else ("PARTIAL" if ok else "FAIL")))

    print("| 시나리오 | HTTP | success | 핵심 결과 | 판정 |")
    print("|---|---:|---|---|---|")
    for row in rows:
        _print_row(*row)

    failed = sum(1 for *_, verdict in rows if verdict == "FAIL")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

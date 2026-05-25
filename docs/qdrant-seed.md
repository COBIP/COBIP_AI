# Qdrant 지식 데이터 Seed (Agentic RAG 14차)

`POST /ai/agentic-rag/run`의 `feature_template_generate` 경로가 13차부터 Qdrant 검색 결과를 자동으로 `referenceContext.ragReferences`에 주입합니다(자세한 정책은 [agentic-rag-unified-api.md](./agentic-rag-unified-api.md#기능템플릿-qdrant-자동-rag-주입-정책-13차) 참고). 14차에서는 그 동작을 실제로 확인할 수 있도록 **Spring Boot 로그인 기능 기준 초기 지식 문서**를 Qdrant에 적재할 수 있는 seed 스크립트를 추가했습니다.

## 목적

- 자동 RAG 주입 검증용 **최소 지식 코퍼스**(로그인 요구사항/API/DTO/계층/BCrypt/JWT/에러/regenerate-section/skeleton-first) 9건을 안전하게 적재한다.
- 운영 RAG_ENABLED 토글을 켜기 전, dry-run으로 문서·payload·deterministic id를 사전 점검한다.
- 기존 collection을 절대 drop / recreate 하지 않는다. 없을 때만 Cosine 거리 collection을 새로 만든다.

## 안전 원칙

| 원칙 | 동작 |
| --- | --- |
| 기본 동작은 dry-run | `--apply`가 없으면 외부 import도 일어나지 않는다. |
| collection drop 금지 | `QdrantService.ensure_collection`만 사용. 기존 collection은 그대로 둔다. |
| 중복 upsert 방지 | point id는 `uuid.uuid5(SEED_NAMESPACE, "{feature}|{section}|{title}|{path}")` 로 deterministic. |
| vector size 자동 결정 | embedding 결과 길이로 `vector_size`를 정해 `ensure_collection`에 전달. |
| graceful 실패 | embedding/upsert 실패는 호출자에 raise하지 않고 `{ "ok": false, "reason": ... }` 으로 보고. |

## Seed 문서 구성

`scripts/seed_qdrant_login_knowledge.py::build_login_seed_documents()`가 다음 9건을 반환합니다.

| section | title |
| --- | --- |
| requirements | Spring Boot 로그인 요구사항 개요 |
| apiSpec | POST /api/auth/login API 명세 |
| codeFiles | LoginRequest / LoginResponse DTO 구조 |
| flow | Controller-Service-Repository 계층 흐름 |
| codeFiles | BCrypt 비밀번호 해시 검증 |
| apiSpec | JWT accessToken / tokenType / user 응답 구조 |
| requirements | 로그인 실패 400 / 401 에러 처리 |
| codeFiles | regenerate-section codeFiles 생성 기준 |
| policy | 기능템플릿 skeleton-first 정책 |

각 문서의 Qdrant payload 키:

```
title, content, sourceType="document",
docType="feature_template_reference",
section, framework="Spring Boot", language="Java",
featureName="로그인", level="beginner",
path, tags[]
```

13차 `rag_service._hit_to_reference`가 사용하는 metadata 키(`docType` / `section` / `fileName` / `path` / `url`)와 직접 호환됩니다.

## 사용 방법

### 1) dry-run (외부 서비스 호출 없음 — 기본 동작)

```bash
# 사람이 읽기 좋은 출력
python scripts/seed_qdrant_login_knowledge.py --dry-run

# 자동화·검증용 JSON 출력
python scripts/seed_qdrant_login_knowledge.py --dry-run --json
```

확인 포인트:

- `mode=dry-run`
- `documentCount=9` (또는 그 이상)
- 각 문서에 deterministic UUIDv5 id, payload key 리스트, content preview가 표시됨
- Qdrant/embedding 모델 import가 일어나지 않음 (네트워크·모델 로드 부담 없음)

### 2) 실제 upsert (사용자가 명시한 경우에만)

> **운영 안전:** RAG_ENABLED를 켜기 전에 항상 dry-run을 먼저 돌려 문서 목록과 id가 의도대로 나오는지 확인할 것. 기존 collection이 이미 있으면 그대로 사용되며, 동일 id에 대해서는 Qdrant가 upsert로 안전하게 덮어씁니다.

```bash
# 기본 collection (settings.QDRANT_COLLECTION) 사용
python scripts/seed_qdrant_login_knowledge.py --apply

# collection 명시
python scripts/seed_qdrant_login_knowledge.py --apply --collection cobip_knowledge

# JSON 결과
python scripts/seed_qdrant_login_knowledge.py --apply --json
```

성공 시 결과 예:

```json
{
  "mode": "apply",
  "documentCount": 9,
  "upsert": {
    "ok": true,
    "upsertedCount": 9,
    "collection": "cobip_knowledge",
    "vectorSize": 1024
  }
}
```

## RAG_ENABLED 활성화 전 체크리스트

> ⚠️ `.env` 또는 `docker-compose.deploy.yml`의 운영 설정은 본 가이드의 범위가 아닙니다. 운영 변경은 항상 운영자가 직접 수행하세요.

1. **Qdrant 컨테이너 상태 확인**
   ```bash
   curl -s http://<qdrant-host>:6333/healthz
   ```
2. **collection 존재 확인**
   ```bash
   curl -s http://<qdrant-host>:6333/collections \
     | python -m json.tool
   ```
3. **seed dry-run으로 문서/id 사전 점검**
   ```bash
   python scripts/seed_qdrant_login_knowledge.py --dry-run --json
   ```
4. **seed 실제 upsert (사용자 명시 필요)**
   ```bash
   python scripts/seed_qdrant_login_knowledge.py --apply
   ```
5. **`RAG_ENABLED=true` 적용 후 ai-server 프로세스 재기동**
   - 환경변수 반영을 위해 ai-server 프로세스를 재기동해야 합니다(`pydantic-settings`가 시작 시 한 번 로드).
   - 운영 docker 재기동/배포는 본 14차 작업 범위가 아닙니다. 운영자가 별도 절차로 수행하세요.

## 자동 RAG 주입 검증 (`/ai/agentic-rag/run`)

```bash
curl -s -X POST http://<ai-server>/ai/agentic-rag/run \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Spring Boot 로그인 기능템플릿 만들어줘",
    "featureTemplate": {
      "language": "Java",
      "framework": "Spring Boot",
      "featureName": "로그인",
      "level": "beginner",
      "includeCode": false,
      "includeMissions": false,
      "includeInterview": false
    }
  }' | python -m json.tool
```

응답의 `data.trace`에서 다음 필드를 확인합니다.

| 필드 | 기대값 |
| --- | --- |
| `ragRetrievalAttempted` | `true` |
| `ragRetrievalStatus` | `success` (seed가 들어 있으면) / `empty` (collection은 있지만 hit 0) |
| `ragRetrievedCount` | Qdrant 반환 raw hit 수 |
| `ragInjectedCount` | manual+auto dedupe 후 prompt 실 주입 수 |
| `ragSource` | `qdrant` 또는 `manual+qdrant` |
| `ragQuery` | `"Spring Boot 로그인 Java beginner 기능템플릿 요구사항 API 코드 학습 ..."` |
| `ragFailureReason` | `null` |
| `ragRetrievalSkippedReason` | `null` |

`RAG_ENABLED=false` 상태에서는 `ragRetrievalAttempted=false`, `ragRetrievalStatus="skipped"`, `ragRetrievalSkippedReason="rag_disabled"`로 표시됩니다.

## Graceful Fallback 검증

다음 상황에서도 `/ai/agentic-rag/run` 응답 자체는 200으로 정상 반환되어야 합니다.

- Qdrant 컨테이너 다운 → `ragRetrievalStatus="failed"`, `ragFailureReason="retrieve_failed:..."`, 수동 reference가 있으면 그대로 prompt에 들어감
- collection 미생성 → `ragRetrievalStatus="empty"`, `ragRetrievedCount=0`
- embedding 모델 로드 실패 → `ragRetrievalStatus="failed"`, `ragFailureReason="retriever_init_failed:..."` 또는 `retrieve_failed:...`
- 검색 결과 0건 → `ragRetrievalStatus="empty"`

어떤 경우에도 기능템플릿 생성 자체는 계속되며 `data.result.source`(`ollama`/`fallback`)는 LLM 흐름 기준으로 결정됩니다.

## 운영 주의 사항

- **실제 운영 Qdrant에 대한 upsert는 운영자 명시가 있어야만 수행합니다.** 본 가이드와 스크립트는 dry-run을 기본값으로 두고 있습니다.
- **collection drop/recreate를 절대 자동화하지 않습니다.** 스키마 변경이 필요한 경우 새 collection 이름으로 옮기는 방식을 권장합니다.
- 동일 id에 대한 upsert는 Qdrant가 안전하게 덮어씁니다. seed를 재실행해도 문서 수가 비대하게 늘어나지 않습니다.
- `.env` 또는 `docker-compose.deploy.yml`의 `RAG_ENABLED`/`QDRANT_URL`/`QDRANT_COLLECTION`/`EMBEDDING_MODEL` 운영 값을 변경할 때는 운영자가 별도 절차로 수행하세요. 본 14차 작업에서는 기본값(`RAG_ENABLED=false`)을 유지합니다.

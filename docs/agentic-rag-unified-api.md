# Agentic RAG 통합 API

기능템플릿 API와 챗봇 API 위에 **최상위 Agentic RAG 진입점**을 제공합니다. 기존 엔드포인트는 그대로 두고, 자연어 요청 하나로 intent에 따라 하위 서비스로 라우팅합니다.

## 엔드포인트

| Method | Path | 설명 |
| --- | --- | --- |
| POST | `/ai/agentic-rag/run` | 자연어 요청 → intent 분류 → 서비스 실행 → trace 포함 응답 |

## 기존 API (유지)

다음 API는 **동작·경로 변경 없이** 그대로 사용할 수 있습니다.

| Method | Path |
| --- | --- |
| POST | `/ai/chat` |
| POST | `/ai/feature-template/generate` |
| POST | `/ai/feature-template/regenerate-section` |

통합 API는 위 API를 **대체하지 않습니다**. 내부적으로는 chat intent일 때 `AgentOrchestrator.run_chat` → `ChatService`, feature template intent일 때 `FeatureTemplateGenerator.generate`를 **재사용**합니다.

---

## 단순 RAG vs Agentic RAG

### 단순 RAG

```
질문 → 검색 → 답변
```

질의에 대해 Retriever로 문서를 찾고, 검색 결과를 프롬프트에 넣어 LLM이 답변하는 **단일 경로**입니다. (`POST /ai/chat`에서 `useRag` + `RAG_ENABLED`로 동작하는 패턴과 유사합니다.)

### 현재 Agentic RAG (`POST /ai/agentic-rag/run`)

```
질문
  → 자연어 의도 분류
  → AgentRouter 서비스 선택 (service_name)
  → 필요 시 RAG 검색
  → ChatService 또는 FeatureTemplateGenerator 실행
  → trace 포함 응답
```

의도에 따라 **챗봇 답변**과 **기능템플릿 생성**을 분기하고, 처리 단계를 `data.trace`로 반환합니다.

---

## 처리 흐름

1. **Intent 분류** (`AgenticRuleClassifier` 룰 기반)  
   - `chat` 또는 `feature_template_generate`
2. **AgentRouter**  
   - `chat` → `chat_service.answer`  
   - `feature_template_generate` → `feature_template_generator.generate`
3. **RAG 분기** (`RAG_ENABLED` + `useRag` 또는 메시지 키워드)  
   - **chat**: 오케스트레이터는 직접 검색하지 않고, `run_chat` → handler → `ChatService` 쪽에 위임 (`rag_retrieval_delegated_to_chat_handler`)  
   - **feature_template_generate** (13차부터):  
     · `featureName` / `framework` / `language` / `level` / `message`로 합성된 query를 `RetrieverService.retrieve`에 전달  
     · Qdrant hit은 `{ "title", "source": "qdrant", "content", "metadata"? }` 형태로 변환되어 `referenceContext.ragReferences`에 자동 주입  
     · 수동 `featureTemplate.referenceContext.ragReferences`는 절대 덮어쓰지 않고 우선 보존된다  
     · 수동 + 자동은 `title + content 앞 100자` 기준 dedupe 후 병합 (출처가 달라도 같은 문서면 한 번만 주입)  
     · Qdrant/embedding 실패, 컬렉션 없음, 결과 0개, payload 이상 등 모든 실패는 graceful: 기존 흐름이 그대로 계속 진행되며 실패 사유는 `trace.ragFailureReason` / `trace.ragRetrievalSkippedReason`에 기록된다
4. **실행**  
   - chat → `AgentOrchestrator.run_chat` → `HybridIntentClassifier` + handler → `ChatService`  
   - feature_template_generate → `FeatureTemplateGenerator.generate`
5. **응답**  
   - `ApiResponse` 래퍼 + `data.intent`, `data.resultType`, `data.result`, `data.trace`

### Intent 분류 기준 (요약)

| 결과 | 조건 |
| --- | --- |
| `feature_template_generate` | 요청에 `featureTemplate` 객체가 있음 **또는** 메시지에 기능 힌트(기능템플릿, 기능 명세 등) **와** 행동 힌트(생성, 만들, 작성 등)가 **둘 다** 포함 |
| `chat` | 그 외 (예: `"안녕"`) |

### RAG 사용 조건

- 서버 **`RAG_ENABLED=true`** 이어야 함 (기본 `false`)
- **`useRag: true`** 이거나 메시지에 `문서`, `검색`, `근거`, `자료`, `참고`, `rag` 등 키워드 포함

---

## 요청 예시

### Chat

```http
POST /ai/agentic-rag/run
Content-Type: application/json
```

```json
{
  "message": "안녕",
  "useRag": false
}
```

### Feature template

```http
POST /ai/agentic-rag/run
Content-Type: application/json
```

```json
{
  "message": "로그인 기능템플릿 만들어줘",
  "featureTemplate": {
    "language": "java",
    "framework": "Spring Boot",
    "featureName": "로그인",
    "level": "beginner",
    "includeCode": true,
    "includeMissions": true,
    "includeInterview": true,
    "referenceContext": {
      "ragReferences": [
        {
          "title": "로그인 요구사항",
          "source": "manual",
          "content": "로그인은 이메일과 비밀번호를 입력받고 JWT를 발급한다."
        }
      ]
    }
  },
  "useRag": false
}
```

`featureTemplate`을 생략하면 메시지에서 `language`, `featureName`, `level` 등을 **추론**합니다. 명시 필드를 쓰는 편이 안정적입니다.

기능템플릿 생성용 `referenceContext`의 공식 입력 위치는 root-level이 아니라 **`featureTemplate.referenceContext`** 입니다. RAG 근거를 직접 전달할 때는 `featureTemplate.referenceContext.ragReferences` 배열에 넣습니다. root-level `referenceContext`는 API 계약에 포함하지 않습니다. `context` 필드는 기존처럼 `referenceContext.userContext` 성격의 보조 맥락으로 병합됩니다.

선택 필드:

| 필드 | 설명 |
| --- | --- |
| `message` | 필수. 자연어 요청 |
| `context` | 선택. 챗봇 맥락 또는 `referenceContext.userContext` |
| `useRag` | 선택. `true`이면 RAG 사용 시도 (서버 `RAG_ENABLED` 필요) |
| `featureTemplate` | 선택. 기능템플릿 생성 시 구조화 입력. 기능템플릿용 `referenceContext`는 이 객체 내부에 둔다. |

---

## 응답 구조

공통 래퍼 (`ApiResponse`):

```json
{
  "success": true,
  "message": "Agentic RAG 처리가 완료되었습니다.",
  "data": { }
}
```

### `data.intent`

| 값 | 의미 |
| --- | --- |
| `chat` | 챗봇 경로 |
| `feature_template_generate` | 기능템플릿 생성 경로 |

### `data.resultType`

| 값 | 의미 |
| --- | --- |
| `chat` | `data.result`가 챗봇 응답 (`answer`, `source`, `ragUsed`, `references`, `agent` 등) |
| `feature_template` | `data.result`가 템플릿 (`template`, `source`, `request`, `generationMode`, `skeletonFirst`, `deferredSections`) |

### `data.trace`

통합 API 최상위 관측 필드입니다.

| 필드 | 설명 |
| --- | --- |
| `classifier` | 오케스트레이터 레벨 분류기 이름 (고정: `AgenticRuleClassifier`) |
| `intent` | `chat` 또는 `feature_template_generate` |
| `serviceName` | `AgentRouter`가 선택한 서비스 식별자 (예: `chat_service.answer`, `feature_template_generator.generate`) |
| `handler` | 실제 실행 경로 (예: `AgentOrchestrator.run_chat`, `FeatureTemplateGenerator.generate`) |
| `steps` | 처리 단계 ID 목록 (예: `natural_language_intent_classification`, `tool_handler_selection`, `rag_retrieval_skipped`, `chat_handler_execution`, `result_serialization`) |
| `ragUsed` | RAG 검색 결과가 실제로 사용된 경우 `true` |
| `references` | RAG 검색 근거 배열 (미사용 시 `[]`) |
| `inferredFields` | 메시지에서 추론한 기능템플릿 필드 (`featureTemplate`을 명시한 경우 `{}`) |
| `latencyMs` | `run_agentic_rag` 전체 처리 시간(ms) |
| `toolCandidates` | 라우팅된 서비스·도구 후보 |
| `intentReason` | intent 분류 근거 |
| `handlerReason` | handler 선택 근거 |
| `ragContextAvailable` | 프롬프트에 쓸 수 있는 RAG reference 존재 여부 |
| `ragReferenceCount` | content가 유효하고 프롬프트 상한이 적용된 RAG reference 수 |
| `appliedReferenceCount` | `data.result.appliedReferences` 길이 |
| `fallbackUsed` | 결과 `source`가 `fallback`이면 `true` |
| `source` | 결과 source (`ollama` 또는 `fallback`) |
| `resultType` | 응답 `data.resultType`과 동일 |
| `routeDecision` | intent → service 라우팅 요약 |
| `executionMode` | 최상위 실행 모드 또는 하위 chat agent mode |
| `generationMode` | 기능템플릿 생성 전략 (`skeleton`, `fallback` 등) |
| `skeletonFirst` | 최초 generate가 skeleton-first 전략이면 `true` |
| `deferredSections` | 상세 생성을 `regenerate-section`으로 미루는 섹션 목록 |
| `ragRetrievalAttempted` | 13차: feature_template_generate 경로에서 자동 Qdrant retrieval을 시도했는지 |
| `ragRetrievalStatus` | `success` \| `empty` \| `skipped` \| `failed` |
| `ragRetrievedCount` | Qdrant 등 retriever가 반환한 raw hit 수 (필터 전) |
| `ragInjectedCount` | manual+auto dedupe 후 prompt에 실제 주입된 reference 수 |
| `ragQuery` | 자동 retrieval에 사용된 query 문자열 |
| `ragSource` | `manual` \| `qdrant` \| `manual+qdrant` \| `none` |
| `ragFailureReason` | 자동 retrieval 실패 사유 요약 (실패 시) |
| `ragRetrievalSkippedReason` | 자동 retrieval을 시도하지 않은 사유 (예: `rag_disabled`, `empty_query`) |
| `ragRetrievalMs` | Qdrant 검색+embedding 포함 retrieval 소요(ms) |
| `featureTemplateGenerationMs` | FeatureTemplateGenerator.generate 소요(ms) |
| `totalLatencyMs` | feature_template 경로 전체 소요(ms). `latencyMs`와 동일 |
| `ragRetrievalMs` | 15차: Qdrant 검색+embedding 포함 자동 RAG retrieval 소요(ms). 스킵/실패 시 0 |
| `featureTemplateGenerationMs` | 15차: `FeatureTemplateGenerator.generate` 실행 소요(ms) |
| `totalLatencyMs` | 15차: feature_template 경로 전체 소요(ms). `latencyMs`와 동일 |

chat 경로일 때 `data.result.agent.trace`에는 `/ai/chat`과 동일한 **하위** trace(`HybridIntentClassifier`, handler명, `toolCandidates` 등)가 추가로 포함될 수 있습니다.

### 기능템플릿 RAG 관측성·시연 안정성 (15차)

교수 시연/발표에서 **병목이 RAG 검색인지 LLM 생성인지** 구분할 수 있도록 trace에 시간을 분리했습니다. Qdrant 검색은 `FEATURE_TEMPLATE_RAG_TOP_K`와 `FEATURE_TEMPLATE_RAG_CONTENT_MAX_CHARS`로 prompt가 과도하게 커지지 않도록 제어합니다.

| 설정 | 기본값 | 설명 |
| --- | --- | --- |
| `FEATURE_TEMPLATE_RAG_TOP_K` | `3` | 기능템플릿 Qdrant top_k 및 프롬프트 주입 reference 상한 |
| `FEATURE_TEMPLATE_RAG_CONTENT_MAX_CHARS` | `1000` | ragReference content 최대 길이. 초과 시 잘림 + `contentTruncated` metadata |

**RAG ON/OFF 비교 시 확인 필드**

| 상황 | 확인 필드 |
| --- | --- |
| RAG 비활성 (`RAG_ENABLED=false`) | `ragRetrievalAttempted=false`, `ragRetrievalStatus=skipped`, `ragRetrievalSkippedReason=rag_disabled`, `ragRetrievalMs=0` |
| RAG 활성 + seed 적재 완료 | `ragRetrievalAttempted=true`, `ragRetrievalStatus=success`, `ragSource=qdrant`, `ragRetrievedCount`/`ragInjectedCount`/`appliedReferenceCount` > 0 |
| RAG 활성 + collection 비어 있음 | `ragRetrievalStatus=empty`, `ragInjectedCount=0`, 기능템플릿 생성은 계속 성공 |
| RAG 실패 (Qdrant/embedding) | `ragRetrievalStatus=failed`, `ragFailureReason` 확인, `featureTemplateGenerationMs`로 LLM 구간은 별도 측정 |

**교수 시연 체크 포인트 (짧게)**

1. `trace.ragRetrievalMs` — RAG 검색+embedding 구간 (보통 수백 ms 이하)
2. `trace.featureTemplateGenerationMs` — LLM skeleton 생성 구간 (대부분의 전체 시간)
3. `trace.totalLatencyMs` (= `latencyMs`) — 전체 요청 시간
4. `trace.ragSource` / `ragInjectedCount` / `appliedReferenceCount` — 어떤 reference가 몇 건 주입됐는지
5. `result.appliedReferences[]` — `title`, `source`, `score`, `section`, `docType`, `path`, `contentPreview`(≤200자)

> 시연 설명 예: "현재 병목이 RAG 검색인지 LLM 생성인지 구분하기 위해 trace에 `ragRetrievalMs`와 `featureTemplateGenerationMs`를 분리했습니다. Qdrant 검색은 top_k와 content 길이를 제한해서 prompt가 과도하게 커지지 않도록 했고, 기능템플릿은 skeleton-first 방식으로 먼저 핵심 구조를 빠르게 생성한 뒤 코드/미션/면접은 regenerate-section으로 분리합니다."

### 성능 개선 1차 (16차)

16차부터는 **retrieval 세부 timing**, **embedding warm-up**, **Redis cache(선택적)** 를 추가해 반복 요청 체감 성능과 관측성을 강화합니다.

추가 env 설정 (기본값은 모두 안전 모드):

| 설정 | 기본값 | 설명 |
| --- | --- | --- |
| `EMBEDDING_WARMUP_ENABLED` | `false` | 서버 시작 시 임베딩 warm-up 시도 여부 |
| `EMBEDDING_WARMUP_TEXT` | `"Spring Boot 로그인 기능템플릿 RAG warm up"` | warm-up 임베딩 텍스트 |
| `RAG_RETRIEVAL_CACHE_ENABLED` | `false` | feature_template_generate 경로의 자동 RAG retrieval 결과 캐시 |
| `RAG_RETRIEVAL_CACHE_TTL_SECONDS` | `3600` | retrieval cache TTL |
| `FEATURE_TEMPLATE_CACHE_ENABLED` | `false` | skeleton-first 최초 generate 결과 캐시 |
| `FEATURE_TEMPLATE_CACHE_TTL_SECONDS` | `3600` | feature template cache TTL |

동작 원칙:

- Redis가 없거나 연결 실패해도 요청은 실패하지 않으며 기존 흐름으로 계속 동작합니다 (graceful fallback).
- retrieval cache key: `rag:feature-template:v1:{sha256...}`
- feature template cache key: `feature-template:skeleton:v3:{sha256...}` (18차부터 ultra-fast·skeleton RAG·max_tokens 포함)
- fallback 결과(`source=fallback`)는 feature template cache에 저장하지 않습니다.

16차 추가 trace 필드:

| 필드 | 설명 |
| --- | --- |
| `embeddingMs` | 임베딩 생성 소요(ms) |
| `qdrantSearchMs` | Qdrant 검색 소요(ms) |
| `referenceBuildMs` | hit → ragReferences 변환/정리 소요(ms) |
| `ragCacheHit` | retrieval cache hit 여부 |
| `ragCacheKey` | retrieval cache key |
| `featureTemplateCacheHit` | skeleton cache hit 여부 |
| `featureTemplateCacheKey` | skeleton cache key |

cache hit 예시:

- `ragCacheHit=true` 이면 `embeddingMs=0`, `qdrantSearchMs=0`, `referenceBuildMs=0`
- `featureTemplateCacheHit=true` 이면 `featureTemplateGenerationMs=0` (LLM generate 생략)

### fast skeleton 초안 (17차)

16차까지 Redis 캐시 hit 시에는 매우 빠르지만, **cache miss·첫 요청**에서는 `featureTemplateGenerationMs`가 LLM skeleton 생성 때문에 대부분의 시간을 차지합니다. 17차는 캐시에만 의존하지 않고 **최초 generate prompt·출력량을 줄여** uncached 응답을 1분 이내에 가깝게 만드는 것을 목표로 합니다.

| 설정 | 기본값 | 설명 |
| --- | --- | --- |
| `FEATURE_TEMPLATE_FAST_SKELETON_ENABLED` | `true` | 최초 generate fast skeleton 프로필 (짧은 overview/requirements/flow, deferred 섹션은 `[]` 우선) |

동작 원칙:

- `generationMode=skeleton`, `skeletonFirst=true`, `deferredSections=["codeFiles","missions","interviewQuestions"]` 는 12차 정책 그대로 유지합니다.
- `codeFiles` / `missions` / `interviewQuestions` 는 include 플래그와 무관하게 최초 generate에서 `[]` 우선입니다. 상세는 `regenerate-section` + normalizer 로그인 baseline 보정으로 보강합니다.
- feature template cache key: `feature-template:skeleton:v2:{sha256...}` (`fastSkeletonEnabled` 설정값 포함, 18차 이후 v3)

17차 추가 trace/result 필드:

| 필드 | 설명 |
| --- | --- |
| `fastSkeletonEnabled` | fast skeleton 프로필 적용 여부 |

### ultra-fast skeleton (18차)

17차 운영 검증(cache OFF) 기준 `featureTemplateGenerationMs`는 약 75초까지 줄었으나 60초 목표에는 미달했습니다. RAG/embedding(`ragRetrievalMs` ~700ms)은 병목이 아니며, **cache miss·uncached 첫 생성**의 병목은 Ollama LLM skeleton 생성 시간입니다. 18차는 **캐시 hit 최적화가 아니라** uncached 첫 생성 자체를 줄이는 작업입니다.

| 설정 | 기본값 | 설명 |
| --- | --- | --- |
| `FEATURE_TEMPLATE_ULTRA_FAST_SKELETON_ENABLED` | `true` | ultra-fast skeleton (fast보다 우선) |
| `FEATURE_TEMPLATE_SKELETON_RAG_TOP_K` | `2` | 최초 skeleton generate 전용 RAG top_k |
| `FEATURE_TEMPLATE_SKELETON_RAG_CONTENT_MAX_CHARS` | `300` | 최초 skeleton generate 전용 RAG content 상한 (19차: 400→300) |
| `FEATURE_TEMPLATE_SKELETON_MAX_TOKENS` | `800` | 최초 skeleton LLM 출력 상한 (19차: 900→800, `regenerate-section`·chat 미적용) |

프로필 우선순위: `ultra-fast` → `fast` → `legacy`.

전략:

- LLM은 `overview`·`requirements`(3)·`flow`·`apiSpec`(1)만 최소 생성합니다.
- `basicQuestions`·`nextRecommendations`는 최초 generate에서 `[]`를 반환하고, **normalizer**가 로그인/Spring Boot baseline으로 3개씩 deterministic 보정합니다.
- skeleton 전용 RAG context 축소(top_k=2, content 300자)로 prompt 부담을 줄입니다.
- skeleton 전용 `max_tokens=800`으로 LLM 출력 상한을 둡니다.

feature template cache key: `feature-template:skeleton:v3:{sha256...}` (`ultraFastSkeletonEnabled`, `skeletonMaxTokens`, skeleton RAG 파라미터 포함).

18차 추가 trace/result 필드:

| 필드 | 설명 |
| --- | --- |
| `ultraFastSkeletonEnabled` | ultra-fast skeleton 적용 여부 |
| `skeletonMaxTokens` | skeleton generate에 적용한 max_tokens (legacy는 null) |
| `skeletonRagTopK` | skeleton generate에 사용한 RAG top_k |
| `skeletonRagContentMaxChars` | skeleton generate에 사용한 RAG content 상한 |

### ultra-fast 60초 진입 튜닝 (19차)

18차 운영 검증(cache OFF 2회차) 기준 `featureTemplateGenerationMs`는 **63730ms**까지 줄었고, 60초 목표까지 약 **3.7초** 남았습니다. 19차는 **캐시가 아니라** uncached skeleton 생성 60초 이하 진입을 위한 미세 튜닝입니다.

| 항목 | 18차 | 19차 |
| --- | --- | --- |
| `skeletonMaxTokens` | 900 | **800** |
| `skeletonRagContentMaxChars` | 400 | **300** |
| `skeletonRagTopK` | 2 | 2 (유지) |

추가 전략:

- ultra-fast prompt에서 `basicQuestions`·`nextRecommendations`·deferred 섹션은 최초 skeleton에서 `[]` 고정, **normalizer**가 로그인 baseline으로 보정합니다.
- `overview`·`flow`·`apiSpec`도 더 짧게 생성하도록 지시하고, 빈약한 값은 normalizer가 보정합니다.
- trace 기대값: `skeletonMaxTokens=800`, `skeletonRagTopK=2`, `skeletonRagContentMaxChars=300`

### Redis cache 운영 compose 정식 반영 (20차)

19차까지 skeleton 튜닝·Redis cache 코드는 검증됐으나, EC2에서는 임시 `/tmp/docker-compose.19-cache-on.yml` override 로만 cache ON 이 유지되고 있었다. 20차부터 **`docker-compose.rag.yml`** 에 cache ON·19차 skeleton 설정을 정식 반영한다.

**환경 우선순위:** `docker-compose` 의 `ai-server.environment` > 호스트 `.env` > `app/core/config.py` 기본값.

| 파일 | 역할 |
| --- | --- |
| `docker-compose.deploy.yml` | ECR `ai-server`, Ollama, Qdrant, Redis 서비스 (기본 `RAG_ENABLED=false`) |
| `docker-compose.rag.yml` | RAG ON, Redis cache ON, 19차 ultra-fast skeleton env (deploy 와 merge) |

`docker-compose.rag.yml` 이 설정하는 값:

| 변수 | 운영 값 |
| --- | --- |
| `REDIS_URL` | `redis://redis:6379/0` |
| `RAG_RETRIEVAL_CACHE_ENABLED` | `true` |
| `RAG_RETRIEVAL_CACHE_TTL_SECONDS` | `3600` |
| `FEATURE_TEMPLATE_CACHE_ENABLED` | `true` |
| `FEATURE_TEMPLATE_CACHE_TTL_SECONDS` | `3600` |
| `FEATURE_TEMPLATE_ULTRA_FAST_SKELETON_ENABLED` | `true` |
| `FEATURE_TEMPLATE_FAST_SKELETON_ENABLED` | `true` |
| `FEATURE_TEMPLATE_SKELETON_MAX_TOKENS` | `800` |
| `FEATURE_TEMPLATE_SKELETON_RAG_TOP_K` | `2` |
| `FEATURE_TEMPLATE_SKELETON_RAG_CONTENT_MAX_CHARS` | `300` |

**기본 운영 실행 (임시 override 불필요):**

```bash
docker compose -f docker-compose.deploy.yml -f docker-compose.rag.yml \
  up -d --no-build --pull never --no-deps ai-server
```

**운영 검증 절차 (EC2·운영 담당자):**

1. Redis 컨테이너 확인: `docker compose -f docker-compose.deploy.yml ps redis`
2. ai-server cache/RAG env 확인:

```bash
docker compose -f docker-compose.deploy.yml -f docker-compose.rag.yml \
  exec ai-server env | grep -E 'REDIS_URL|RAG_RETRIEVAL_CACHE|FEATURE_TEMPLATE_CACHE|FEATURE_TEMPLATE_SKELETON'
```

기대: `REDIS_URL=redis://redis:6379/0`, `RAG_RETRIEVAL_CACHE_ENABLED=true`, `FEATURE_TEMPLATE_CACHE_ENABLED=true`, `FEATURE_TEMPLATE_SKELETON_MAX_TOKENS=800`, `FEATURE_TEMPLATE_SKELETON_RAG_CONTENT_MAX_CHARS=300`.

3. Redis ping: `docker compose -f docker-compose.deploy.yml exec redis redis-cli ping` → `PONG`

4. compose merge 확인 (로컬/CI):

```bash
docker compose -f docker-compose.deploy.yml -f docker-compose.rag.yml config \
  | grep -E 'REDIS_URL|RAG_RETRIEVAL_CACHE|FEATURE_TEMPLATE_CACHE|FEATURE_TEMPLATE_SKELETON'
```

5. Agentic RAG 기능템플릿 동일 요청 2회 (`POST /ai/agentic-rag/run`, `RAG_ENABLED` 경로):

| 회차 | 기대 trace |
| --- | --- |
| 1회차 | `ragCacheHit=false`, `featureTemplateCacheHit=false`, `ragCacheKey`·`featureTemplateCacheKey` 존재 |
| 2회차 | `ragCacheHit=true`, `featureTemplateCacheHit=true`, `embeddingMs=0`, `ragRetrievalMs=0`, `featureTemplateGenerationMs=0`, `totalLatencyMs` 수 ms 대 |

6. TTL 확인 (양수):

```bash
docker compose -f docker-compose.deploy.yml exec redis redis-cli TTL '<ragCacheKey>'
docker compose -f docker-compose.deploy.yml exec redis redis-cli TTL '<featureTemplateCacheKey>'
```

기대: 각각 약 3600초 이하의 양수 TTL (저장 직후 `RAG_RETRIEVAL_CACHE_TTL_SECONDS` / `FEATURE_TEMPLATE_CACHE_TTL_SECONDS` 기준).

코드 정책 유지: fallback 결과는 feature template cache 에 저장하지 않음. Redis 연결 실패 시 in-memory graceful fallback.

### embedding warm-up 운영 기본화 (21차)

20차에서 Redis cache ON 은 정식 compose 에 반영됐지만, **첫 기능템플릿 요청**은 embedding cold start 로 `embeddingMs`·`ragRetrievalMs` 가 60초 이상 튈 수 있어 `totalLatencyMs` 가 90초를 넘을 수 있다. 반복 요청은 cache hit 으로 수 ms 수준이다.

21차는 **서버 startup 시** RAG 와 동일한 `EmbeddingService` shared model 경로로 warm-up 을 수행해, 사용자 첫 요청에서 모델 로딩 지연을 제거하는 것이 목표다.

| 설정 | 로컬 기본 | 운영 (`docker-compose.rag.yml`) |
| --- | --- | --- |
| `EMBEDDING_WARMUP_ENABLED` | `false` | `true` |
| `EMBEDDING_WARMUP_TEXT` | Spring Boot 로그인… | 동일 |

동작:

- `RAG_ENABLED=true` 이고 `EMBEDDING_WARMUP_ENABLED=true` 일 때만 startup warm-up 수행
- `embed_query` → `_get_model()` 로 **process-level shared** `SentenceTransformer` 로드 (RAG retrieval 과 동일 인스턴스)
- warm-up 실패 시 warning 로그만 남기고 **앱 기동은 계속**
- `GET /ai/health` 의 `data` 에 warm-up 관측 필드 추가 (기존 `status`·`qdrant` 유지)

startup 로그 예:

- `Embedding warm-up started ...`
- `Embedding warm-up completed in XXXX ms (shared model loaded for RAG retrieval)`
- `Embedding warm-up skipped because RAG_ENABLED=false`
- `Embedding warm-up failed but startup continues: ...`

**운영 검증 기대:**

1. 컨테이너 재기동 후 `docker logs` 에 warm-up completed 확인
2. **첫** `POST /ai/agentic-rag/run` (cache miss): `embeddingMs` 가 60초 이상이 아니어야 함 (수백 ms~수 초 수준)
3. **두 번째** 동일 요청: `ragCacheHit=true`, `featureTemplateCacheHit=true`, `embeddingMs=0`, `featureTemplateGenerationMs=0`
4. `GET /ai/health` → `embeddingWarmupAttempted=true`, `embeddingWarmupSucceeded=true` (warm-up 성공 시)

```bash
docker compose -f docker-compose.deploy.yml -f docker-compose.rag.yml config \
  | grep -E 'EMBEDDING_WARMUP|REDIS_URL|RAG_RETRIEVAL_CACHE|FEATURE_TEMPLATE_CACHE|FEATURE_TEMPLATE_SKELETON'
```

### `source` 위치

LLM/폴백 출처는 결과 본문과 trace에 함께 제공됩니다.

- chat: `data.result.source` (`ollama` \| `fallback`)
- feature_template: `data.result.source` (`ollama` \| `fallback`)
- trace: `data.trace.source`

### 기능템플릿 skeleton-first 정책

12차부터 최초 `generate`는 전체 상세 산출물을 한 번에 만들기보다 `overview`, `requirements`, `flow`, `apiSpec`, `basicQuestions`, `nextRecommendations` 중심의 가벼운 기본 구조를 우선 반환합니다. `codeFiles`, `missions`, `interviewQuestions` 상세 생성은 `POST /ai/feature-template/regenerate-section` 경로에서 섹션별로 보강하는 것을 기본 전략으로 둡니다.

### 기능템플릿 Qdrant 자동 RAG 주입 정책 (13차)

13차부터 `POST /ai/agentic-rag/run`의 `feature_template_generate` 경로는 Qdrant 검색 결과를 자동으로 `referenceContext.ragReferences`로 변환·주입합니다. 사용자가 보내는 `featureTemplate.referenceContext.ragReferences`(수동 입력)와 자동 결과는 **수동 우선 + dedupe 병합** 정책으로 결합됩니다.

- **Retriever**: `app/services/retriever_service.py`의 `RetrieverService`를 그대로 재사용합니다(`QdrantService` + `EmbeddingService`). 본 13차에서는 RetrieverService를 새로 만들지 않고 기존 구현을 그대로 활용합니다.
- **활성 조건**: 서버 `RAG_ENABLED=true`. `RAG_ENABLED=false`인 경우 retrieval을 시도하지 않고 `trace.ragRetrievalSkippedReason="rag_disabled"`로 기록합니다.
- **Query 구성**: `{framework} {featureName} {language} {level} 기능템플릿 요구사항 API 코드 학습` 뒤에 `message`의 앞 160자를 붙입니다. 전체 길이는 256자로 제한합니다.
- **Hit → ragReference 변환**: `{ "title", "source": "qdrant", "content", "sourceType?", "score?", "metadata?" }`. `title`이 없으면 metadata의 `docType` / `section` / `fileName` / `path` / `url` 순으로 채웁니다. `content`는 `FEATURE_TEMPLATE_RAG_CONTENT_MAX_CHARS`(기본 1000)로 제한하며, 잘린 경우 metadata에 `contentTruncated` / `originalContentLength`를 남깁니다.
- **검색 개수**: `FEATURE_TEMPLATE_RAG_TOP_K`(기본 3)로 Qdrant top_k와 프롬프트 주입 상한을 제어합니다.
- **수동 reference 우선**: 수동 `ragReferences`는 절대 덮어쓰지 않고 그대로 prompt에 들어갑니다.
- **Dedupe**: `title + content 앞 100자`(공백 정규화·소문자) 기준으로 중복 제거합니다. 출처(`source`)는 키에 포함하지 않아서, 같은 문서가 manual/qdrant 두 채널로 들어와도 한 번만 주입됩니다.
- **Graceful fallback**: Qdrant 미기동, 컬렉션 없음, embedding 실패, 결과 0개, payload 이상 등 어떤 단계 실패도 호출자에게 예외를 던지지 않습니다. 기능템플릿 생성은 그대로 계속 진행되고 실패/스킵 사유는 `trace.ragFailureReason` / `trace.ragRetrievalSkippedReason`에 기록됩니다.
- **skeleton-first 유지**: 자동 주입이 들어가도 12차 `generationMode=skeleton`, `skeletonFirst=true`, `deferredSections=["codeFiles","missions","interviewQuestions"]` 정책은 그대로 유지됩니다.
- **Seed 데이터 (14차)**: Spring Boot 로그인 기능 기준 초기 지식 문서를 Qdrant에 적재할 수 있는 dry-run 안전 seed 스크립트가 `scripts/seed_qdrant_login_knowledge.py`로 제공됩니다. 운영 적용 절차와 자동 RAG 검증 방법은 [qdrant-seed.md](./qdrant-seed.md)를 참고하세요.

trace metadata 필드 (`data.trace`):

| 필드 | 의미 |
| --- | --- |
| `ragRetrievalAttempted` | 자동 retrieval 시도 여부 |
| `ragRetrievalStatus` | `success` \| `empty` \| `skipped` \| `failed` |
| `ragRetrievedCount` | Qdrant raw hit 수 |
| `ragInjectedCount` | manual+auto dedupe 후 prompt에 실제 주입된 reference 수 |
| `ragQuery` | 자동 retrieval에 사용된 query 문자열 |
| `ragSource` | `manual` \| `qdrant` \| `manual+qdrant` \| `none` |
| `ragFailureReason` | 실패 사유 (예: `retrieve_failed:RuntimeError`) |
| `ragRetrievalSkippedReason` | 스킵 사유 (예: `rag_disabled`, `empty_query`) |

기존 trace 필드(`ragContextAvailable`, `ragReferenceCount`, `appliedReferenceCount`, `fallbackUsed`, `source`, `resultType`, `routeDecision`, `executionMode`, `generationMode`, `skeletonFirst`, `deferredSections`)는 그대로 유지됩니다.

---

## 관련 코드

| 파일 | 역할 |
| --- | --- |
| `app/api/routes/agentic.py` | `POST /ai/agentic-rag/run` 라우터 |
| `app/schemas/agentic.py` | `AgenticRagRequest`, `AgenticRagResponseData`, `AgenticRagTrace` (13차 RAG metadata 포함) |
| `app/services/agent_orchestrator.py` | `run_agentic_rag()` 및 feature_template_generate 경로의 자동 Qdrant 주입 |
| `app/services/rag_service.py` | 13차 — query 합성, Qdrant retrieval 래퍼, 수동/자동 dedupe 병합 |
| `app/services/retriever_service.py` | `QdrantService` + `EmbeddingService` 조합 retriever (13차에서 재사용) |
| `app/services/agent_router.py` | intent → `service_name` |
| `tests/test_agentic_rag_api.py` | 라우팅 스모크 테스트 |
| `tests/test_agentic_rag_auto_rag_injection.py` | 13차 자동 Qdrant 주입 통합 테스트 |
| `tests/test_rag_service.py` | 13차 rag_service helper 단위 테스트 |

`/ai/chat` 전용 1차 Agent 구조는 [agentic-rag-phase1.md](./agentic-rag-phase1.md)를 참고하세요.

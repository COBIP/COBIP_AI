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

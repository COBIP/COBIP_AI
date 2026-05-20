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
   - **feature_template_generate**: `RetrieverService`로 검색 후 `referenceContext.ragReferences`에 저장
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
    "includeInterview": true
  },
  "useRag": false
}
```

`featureTemplate`을 생략하면 메시지에서 `language`, `featureName`, `level` 등을 **추론**합니다. 명시 필드를 쓰는 편이 안정적입니다.

선택 필드:

| 필드 | 설명 |
| --- | --- |
| `message` | 필수. 자연어 요청 |
| `context` | 선택. 챗봇 맥락 또는 `referenceContext.userContext` |
| `useRag` | 선택. `true`이면 RAG 사용 시도 (서버 `RAG_ENABLED` 필요) |
| `featureTemplate` | 선택. 기능템플릿 생성 시 구조화 입력 |

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
| `feature_template` | `data.result`가 템플릿 (`template`, `source`, `request`) |

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

chat 경로일 때 `data.result.agent.trace`에는 `/ai/chat`과 동일한 **하위** trace(`HybridIntentClassifier`, handler명, `toolCandidates` 등)가 추가로 포함될 수 있습니다.

### `source` 위치

통합 trace에는 **`source` 필드가 없습니다**. LLM/폴백 출처는 다음에 있습니다.

- chat: `data.result.source` (`ollama` \| `fallback`)
- feature_template: `data.result.source` (`ollama` \| `fallback`)

---

## 관련 코드

| 파일 | 역할 |
| --- | --- |
| `app/api/routes/agentic.py` | `POST /ai/agentic-rag/run` 라우터 |
| `app/schemas/agentic.py` | `AgenticRagRequest`, `AgenticRagResponseData`, `AgenticRagTrace` |
| `app/services/agent_orchestrator.py` | `run_agentic_rag()` |
| `app/services/agent_router.py` | intent → `service_name` |
| `tests/test_agentic_rag_api.py` | 라우팅 스모크 테스트 |

`/ai/chat` 전용 1차 Agent 구조는 [agentic-rag-phase1.md](./agentic-rag-phase1.md)를 참고하세요.

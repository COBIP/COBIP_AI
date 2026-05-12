# Agentic RAG 1차 구조 정리

## 1. 작업 개요

단순 RAG 챗봇은 **한 경로**(질문 → 선택적 검색 → LLM)로만 동작해, 사용자 의도에 따라 **검색·일반 대화·기능 템플릿 안내**를 구분하거나, 이후 **도구(tool) 확장**을 넣기 어렵습니다. Agentic RAG 1차 구조는 **intent 분류 → (메타데이터상) tool 후보 → 전용 handler**로 나누어, 같은 `/ai/chat` 엔드포인트에서도 **역할이 분리**되고 **관측(trace)·후속 단계 확장**이 가능해지도록 했습니다.

**이번 단계는 실제 멀티스텝 Agent가 아닙니다.**  
의도 분류(룰 기본, 선택적 LLM), handler 위임, trace·`toolCandidates` 같은 **1차 뼈대**만 갖춘 상태이며, tool **실행**·루프·LangChain 등은 포함하지 않습니다.

---

## 2. 전체 요청 흐름

1. 클라이언트가 **`POST /ai/chat`** 으로 JSON 본문을 보냅니다.
2. **`AgentOrchestrator`** 가 요청을 받아 전체 흐름을 조율합니다.
3. **`HybridIntentClassifier`** 가 intent와 분류 모드(`rule_based` / `llm_assisted` / `hybrid`) 및 분류 단계 정보를 결정합니다.
4. **`AgentToolRegistry`** 가 결정된 intent에 매핑된 **tool 이름 후보만** 조회합니다 (실행 없음).
5. intent에 맞는 **handler** (`GeneralChatHandler`, `RagSearchHandler`, 등)가 선택되어 `handle(request, agent)` 가 호출됩니다.
6. handler 내부에서는 **`ChatService`**(Ollama 경유) 또는 **고정 응답**(예: 기능 템플릿 안내)으로 `answer` 등을 채웁니다.
7. 최종적으로 **`ApiResponse`** 형태로 `success`, `message`, `data`(챗봇 본문 + `agent` 메타)가 반환됩니다.

---

## 3. Intent 분류 구조

### Intent 목록

| Intent | 설명 요약 |
|--------|-------------|
| **GENERAL_CHAT** | 일반 대화·코딩 질문 등 기본 챗봇 |
| **RAG_SEARCH** | 문서·검색·근거·RAG 등 검색 의도 |
| **FEATURE_TEMPLATE_HELP** | 기능 템플릿·요구사항·API 명세·ERD·면접 질문 등 산출물 안내 |
| **UNKNOWN** | 빈 메시지 등 분류 불가 (API에서는 보통 빈 `message` 검증으로 드물게 도달) |

### Classifier 역할

- **`RuleBasedIntentClassifier`**  
  키워드·문자열 규칙으로 intent를 결정합니다. **기본 동작의 중심**입니다.

- **`LLMIntentClassifier`**  
  짧은 시스템 프롬프트로 LLM이 네 가지 intent 중 하나만 출력하도록 요청합니다. 파싱 실패·예외 시 상위에서 안전하게 처리합니다.

- **`HybridIntentClassifier`**  
  항상 **먼저 룰**을 적용합니다.  
  - 룰이 `UNKNOWN`이고 **`AGENT_LLM_INTENT_ENABLED=true`** 이면 LLM 분류를 시도합니다.  
  - 룰이 `GENERAL_CHAT`이고 **`AGENT_LLM_INTENT_ENABLED`** 와 **`AGENT_LLM_INTENT_REFINE_GENERAL=true`** 이면 LLM으로 재분류를 시도합니다(선택).  
  그 외에는 룰 결과와 `rule_based` 모드를 유지합니다.

### 중요 설정·동작

- **기본 동작은 rule-based** 입니다 (환경 변수 미설정 시 LLM intent 경로는 타지 않음).
- **기능템플릿 관련 키워드는 RAG 관련 키워드보다 먼저** 검사되어, 같은 문장에 `문서` 등이 있어도 기능 템플릿 의도가 우선될 수 있습니다.
- **LLM intent는 기본 비활성화** 입니다.
  - **`AGENT_LLM_INTENT_ENABLED`**: `UNKNOWN`일 때 LLM 보조 분류 사용 여부 (기본 `false`).
  - **`AGENT_LLM_INTENT_REFINE_GENERAL`**: `GENERAL_CHAT`일 때 LLM 재분류 사용 여부 (기본 `false`).

---

## 4. Handler 구조

| Handler | 역할 |
|---------|------|
| **GeneralChatHandler** | 일반 대화. `useRag` + 서버 `RAG_ENABLED`일 때만 Retriever로 RAG 주입 후 `ChatService` 호출. |
| **RagSearchHandler** | RAG 검색 의도. `RAG_ENABLED`에 따라 검색 후 `ChatService` 호출. |
| **FeatureTemplateHelpHandler** | 기능 템플릿 관련 안내. **`ChatService`/Ollama를 호출하지 않고** 고정 마크다운 안내문(엔드포인트·JSON 필드 예시 등)만 반환합니다. |
| **UnknownHandler** | `UNKNOWN` intent. LLM 없이 고정 안내 문구 반환. |

---

## 5. Agent trace 구조

`/ai/chat` 응답의 `data.agent` 에 `enabled`, `intent`, `mode`, 선택적으로 **`trace`** 가 붙습니다. `trace`는 관측·디버깅용이며, 구 클라이언트 호환을 위해 생략 가능한 필드로 설계될 수 있습니다(현재 오케스트레이터 경로에서는 채워짐).

### 응답 예시 (`data.agent`)

```json
{
  "enabled": true,
  "intent": "RAG_SEARCH",
  "mode": "rule_based",
  "trace": {
    "classifier": "HybridIntentClassifier",
    "handler": "RagSearchHandler",
    "llmIntentUsed": false,
    "steps": [
      "rule_based_intent_classification",
      "tool_candidate_selection",
      "handler_dispatch"
    ],
    "latencyMs": 73,
    "toolCandidates": ["retriever_search"]
  }
}
```

- **`classifier`**: Hybrid 분류기 이름.
- **`handler`**: 실제 실행된 handler 클래스 이름.
- **`llmIntentUsed`**: 이번 요청에서 LLM intent 분류가 호출되었는지.
- **`steps`**: 룰 분류 → (선택) LLM 단계 → tool 후보 선정 → handler 실행 순서를 문자열로 표현.
- **`latencyMs`**: 오케스트레이터 기준 전체 처리 시간(ms).
- **`toolCandidates`**: intent에 매핑된 tool **이름** 목록 (실행 전).

---

## 6. Tool routing metadata

현재 단계에서는 **실제 tool 실행(`run` / `execute`)이 없습니다.**  
`AgentToolRegistry`가 intent별로 **등록된 tool 메타** 중 이름만 골라 **`trace.toolCandidates`**에 넣어, 이후 7차에서 실행 계층을 붙일 수 있게 합니다.

### 등록된 tool 후보 (이름)

| name | 용도(설명) | 매핑 intent |
|------|------------|---------------|
| **general_chat** | 일반 대화 처리용 tool | `GENERAL_CHAT` |
| **retriever_search** | Qdrant 문서 검색용 tool | `RAG_SEARCH` |
| **feature_template_guide** | 기능템플릿 생성 API 사용 안내용 tool | `FEATURE_TEMPLATE_HELP` |

`UNKNOWN`에는 별도 tool이 매핑되어 있지 않아 **`toolCandidates`는 빈 배열**일 수 있습니다.

---

## 7. API 테스트 예시

기본 URL은 `http://localhost:8000` 으로 가정합니다. `Content-Type: application/json` 을 사용합니다.

### GENERAL_CHAT

```bash
curl -sS -X POST http://localhost:8000/ai/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "안녕, 오늘 뭐해?", "useRag": false}'
```

**예상 (기본 LLM intent 비활성화 기준)**

| 항목 | 예상 값 |
|------|---------|
| `data.agent.intent` | `GENERAL_CHAT` |
| `data.agent.mode` | `rule_based` |
| `data.agent.trace.handler` | `GeneralChatHandler` |
| `data.agent.trace.toolCandidates` | `["general_chat"]` |

### RAG_SEARCH

```bash
curl -sS -X POST http://localhost:8000/ai/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "문서에서 Controller와 Service 차이를 찾아줘."}'
```

**예상**

| 항목 | 예상 값 |
|------|---------|
| `data.agent.intent` | `RAG_SEARCH` |
| `data.agent.mode` | `rule_based` |
| `data.agent.trace.handler` | `RagSearchHandler` |
| `data.agent.trace.toolCandidates` | `["retriever_search"]` |

### FEATURE_TEMPLATE_HELP

```bash
curl -sS -X POST http://localhost:8000/ai/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "기능템플릿 API로 요구사항 문서를 만들고 싶어."}'
```

**예상**

| 항목 | 예상 값 |
|------|---------|
| `data.agent.intent` | `FEATURE_TEMPLATE_HELP` |
| `data.agent.mode` | `rule_based` |
| `data.agent.trace.handler` | `FeatureTemplateHelpHandler` |
| `data.agent.trace.toolCandidates` | `["feature_template_guide"]` |

또한 이 intent에서는 **`data.ragUsed === false`**, **`data.references === []`** 가 되도록 설계되어 있습니다 (고정 안내 경로).

---

## 8. 최종 회귀 테스트 체크리스트

릴리스·머지 전에 아래를 순서대로 확인하는 것을 권장합니다.

- [ ] **Docker build** 성공 (`docker build -t cobip-ai-server .` 등)
- [ ] **`/openapi.json`** 응답 200 및 스키마 로드 가능
- [ ] **GENERAL_CHAT** intent: 일반 질문에서 `intent`·handler·답변 정상
- [ ] **RAG_SEARCH** intent: 검색 키워드 문장에서 `intent`·RAG 동작(설정 시)·handler 정상
- [ ] **FEATURE_TEMPLATE_HELP** intent: 기능템플릿 문구에서 고정 안내·handler 정상
- [ ] **`data.agent.mode`** 가 기본 설정에서 **`rule_based`** 인지 확인 (`AGENT_LLM_*` 미사용 시)
- [ ] **`trace.classifier`** 가 `HybridIntentClassifier` 인지 확인
- [ ] **`trace.handler`** 가 의도와 일치하는 handler 클래스명인지 확인
- [ ] **`trace.llmIntentUsed`** 가 설정과 일치하는지 확인 (기본 `false`)
- [ ] **`trace.steps`** 에 `rule_based_intent_classification`, `tool_candidate_selection`, `handler_dispatch` 포함 여부 확인 (LLM 경로 시 추가 단계 있을 수 있음)
- [ ] **`trace.toolCandidates`** 가 intent별 기대 목록과 일치하는지 확인
- [ ] **기능템플릿 도움** 질문에서 **`ragUsed === false`**, **`references === []`** 확인
- [ ] **CI** 워크플로 통과 (해당 브랜치 PR 기준)

---

## 9. 현재 하지 않은 것

아래는 **아직 구현하지 않았거나** 이번 1차 범위에서 **의도적으로 제외**한 항목입니다.

- 실제 **tool 실행** (registry는 후보만)
- **OpenAI-style tool calling** / 함수 호출 자동 라우팅
- **멀티스텝 Agent** 루프
- **LangChain / LangGraph**
- **`POST /ai/feature-template/generate` 자동 호출** (챗에서 API 대신 호출하지 않음)
- **LLM intent의 기본 활성화** (`AGENT_LLM_INTENT_ENABLED` 기본 `false`)
- 검색 결과 부족 시 **재검색**·**질문 재작성**
- **tool 실행 결과**를 trace에 남기는 상세 필드 (`tool result trace`)

---

## 10. 다음 단계 (7차 이후 제안)

- **실제 Tool 실행** 구조: `AgentTool`에 실행 진입점, 입력 검증, 타임아웃
- **RetrieverTool** 실행 후 **결과 요약·trace 필드** (`toolResult`, `hitCount` 등)
- **FeatureTemplateGenerateTool** 연결 여부 검토 (사용자 동의·별도 엔드포인트 호출 정책)
- **Agent step loop** 및 **최대 step 제한**·취소 토큰
- **tool result logging** (민감 정보·전문 로그 제외 원칙 유지)
- **실패 시 fallback** 정책 (LLM 실패 vs 검색 실패 vs tool 실패 구분)
- **기능템플릿 생성** 고도화 (필드 검증, 예시 품질, 다국어 등)

---

*문서 버전: Agentic RAG Phase 1 마무리(6-13 / 6-14 문서화) 기준.*

# 기능템플릿 API 가이드

COBIP_AI FastAPI 서버의 **기능템플릿 전체 생성**과 **섹션 재생성** API를 프론트엔드·연동 클라이언트가 안전하게 사용하기 위한 요약 문서입니다. (고도화 7-1 ~ 7-5 반영 기준)

---

## 1. 작업 목적

| 단계 | 내용 |
|------|------|
| **7-1 / 7-2** | `FeatureTemplateNormalizer`로 LLM·mock 응답을 보정해 **`data.template`에 9개 섹션 key가 항상 존재**하도록 정규화. top-level snake_case 별칭·`code_view.files` → `codeFiles` 등 매핑. |
| **7-3** | 전체 생성 LLM 프롬프트에서 **JSON만 출력**, 마크다운 펜스 금지, **camelCase**, 스키마 밖 key 금지 등 규칙 강화. |
| **7-4** | 요구사항·flow·apiSpec·기본문제·미션·면접·다음 추천 등 **실무형 품질 기준**을 프롬프트에 명시. |
| **7-5** | `POST /ai/feature-template/regenerate-section`에서도 **동일 normalizer 경로**를 타고, `section`/`sectionName`·snake_case 별칭을 canonical camelCase로 통일한 뒤 해당 섹션만 응답. |

**프론트 목표**: 전체 생성은 `data.template` 고정 9키로 렌더링하고, 재생성은 `data.section` + `data.content`로 해당 구역만 갱신하면 됩니다.

---

## 2. 전체 생성 API

### Endpoint

`POST /ai/feature-template/generate`

### 요청 필드 (`FeatureTemplateGenerateRequest`)

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `language` | string | 예 | 대상 언어 (예: `java`, `python`) |
| `featureName` | string | 예 | 기능 이름 |
| `level` | string(enum) | 예 | `beginner` \| `intermediate` \| `advanced` |
| `framework` | string \| null | 아니오 | 프레임워크 힌트 (예: `spring-boot`). 프롬프트의 `overview.techStack` 반영에 사용 |
| `includeCode` | boolean | 아니오 | 기본 `true`. `false`면 `codeFiles`는 항상 `[]` |
| `includeMissions` | boolean | 아니오 | 기본 `true`. `false`면 `missions`는 항상 `[]` |
| `includeInterview` | boolean | 아니오 | 기본 `true`. `false`면 `interviewQuestions`는 항상 `[]` |
| `referenceContext` | object \| null | 아니오 | RAG·외부에서 주입하는 참고 JSON (자유 형태) |

> **참고**: 전체 생성 요청 본문에는 **`techStack` 배열 필드가 없습니다.** 스택 힌트는 `framework`와 `referenceContext`로 넘기면 됩니다. **섹션 재생성** API에는 `techStack` 필드가 별도로 있습니다.

### 요청 예시 (JSON)

```json
{
  "language": "java",
  "framework": "spring-boot",
  "featureName": "로그인",
  "level": "beginner",
  "includeCode": true,
  "includeMissions": true,
  "includeInterview": true,
  "referenceContext": null
}
```

### 응답 구조 (요약)

표준 래퍼 `ApiResponse` 형태입니다.

```json
{
  "success": true,
  "message": "기능템플릿 생성이 완료되었습니다.",
  "data": {
    "template": { },
    "source": "ollama"
  }
}
```

- **`data.template`**: 아래 9개 섹션이 **항상** 포함됩니다 (값은 빈 배열·빈 객체일 수 있음).
- **`data.source`**: `"ollama"` (LLM 성공) 또는 `"fallback"` (mock·검증 실패 등). [§7](#7-source-의미) 참고.

### `data.template` 필수 9개 섹션 (camelCase)

| key | 타입 | 설명 |
|-----|------|------|
| `overview` | object | 프로젝트·기능 개요 |
| `requirements` | array | 요구사항 목록 |
| `flow` | object | 단계(`steps`)·계층(`layers`) |
| `apiSpec` | array | API 명세 목록 |
| `codeFiles` | array | 코드 파일 목록 (`includeCode=false`면 `[]`) |
| `basicQuestions` | array | 기본 문제 |
| `missions` | array | 실습 미션 (`includeMissions=false`면 `[]`) |
| `interviewQuestions` | array | 면접 질문 (`includeInterview=false`면 `[]`) |
| `nextRecommendations` | array | 다음 학습 추천 |

---

## 3. 섹션별 필드 설명

스키마 기준: `app/schemas/feature_template.py` (`OverviewSchema`, `RequirementSchema`, …).

### overview

| 필드 | 타입 | 설명 |
|------|------|------|
| `featureName` | string | 기능명 |
| `purpose` | string | 목적 |
| `useCases` | string[] | 사용 사례 |
| `resultDescription` | string | 결과/산출물 설명 |
| `techStack` | string[] | 기술 스택 (LLM이 `language`·`framework` 등을 반영해 채움) |
| `learningGoals` | string[] | 학습 목표 |

### requirements (배열 항목)

| 필드 | 타입 | 설명 |
|------|------|------|
| `requirementId` | string | 식별자 (예: `R-001`) |
| `name` | string | 요구사항 제목 |
| `description` | string | 상세 설명 |
| `inputValue` | string | 입력/데이터 |
| `processCondition` | string | 처리 조건 |
| `successResult` | string | 성공 시 기대 결과 |
| `failureResult` | string | 실패 시 기대 결과 |
| `priority` | string | 우선순위 문자열 (예: `HIGH`, `MEDIUM`, `LOW`) |
| `relatedScreenOrApi` | string | 연관 화면/API |

### flow

| 필드 | 타입 | 설명 |
|------|------|------|
| `steps` | string[] | 동작 순서 (문자열 단계) |
| `layers` | object[] | `{ "layer": string, "role": string }` 계층 역할 |

### apiSpec (배열 항목)

| 필드 | 타입 | 설명 |
|------|------|------|
| `apiName` | string | API 이름 |
| `method` | string | HTTP 메서드 |
| `endpoint` | string | 경로 |
| `description` | string | 설명 |
| `requestBody` | object \| string | 요청 본문 예시 |
| `responseBody` | object \| string | 응답 본문 예시 |
| `status` | number | HTTP 상태 코드 **정수** (문자열 `"200 OK"` 금지) |

### codeFiles (배열 항목)

| 필드 | 타입 | 설명 |
|------|------|------|
| `fileName` | string | 파일명 |
| `filePath` | string \| null | 경로 |
| `role` | string | 역할 (Controller 등) |
| `language` | string | 언어 |
| `content` | string | 소스 문자열 |

### basicQuestions (배열 항목)

| 필드 | 타입 | 설명 |
|------|------|------|
| `questionId` | string | 식별자 |
| `type` | string(enum) | `QuestionType`: `multiple_choice`, `short_answer`, `fill_blank`, `output_prediction`, `code_error_find`, `code_fill` |
| `question` | string | 문제 본문 |
| `choices` | string[] \| null | 객관식 선택지 (`type`이 객관식이 아니면 `null`) |
| `answer` | string | 정답 |
| `explanation` | string | 해설 |
| `relatedSection` | string \| null | 연관 top-level 섹션 key |
| `difficulty` | string(enum) | `beginner` \| `intermediate` \| `advanced` |

### missions (배열 항목)

| 필드 | 타입 | 설명 |
|------|------|------|
| `missionId` | string | 식별자 |
| `title` | string | 제목 |
| `description` | string | 설명 (교육 목표는 **별도 `goal` key 없이** 본문 앞에 `"미션 목표:"` 한 줄로 넣는 것을 프롬프트에서 유도) |
| `missionType` | string | 미션 유형 문자열 |
| `requirements` | string[] | 단계·힌트 등 (**별도 `hints` key 없이** 이 배열에 서술) |
| `successCriteria` | string[] | 완료 조건 |
| `relatedRequirements` | string[] | 연결 `requirementId` |
| `difficulty` | string(enum) | `beginner` \| `intermediate` \| `advanced` |

### interviewQuestions (배열 항목)

| 필드 | 타입 | 설명 |
|------|------|------|
| `questionId` | string | 식별자 |
| `question` | string | 질문 |
| `keyPoints` | string[] | 답변에 포함할 키워드·개념 (**`keywords` 필드는 스키마에 없음**) |
| `sampleAnswer` | string | 모범 답안 |
| `relatedSection` | string \| null | 연관 섹션 |

면접 문항 **난이도 전용 필드는 없음**. 난이도는 질문·답변 깊이로 조절합니다.

### nextRecommendations (배열 항목)

| 필드 | 타입 | 설명 |
|------|------|------|
| `featureName` | string | 다음에 학습할 기능 이름 (**별도 `nextFeatureName` key 없음**) |
| `reason` | string | 추천 이유 (한 줄 제목 느낌은 이 필드 첫 문장으로 서술) |
| `expectedLearning` | string | 기대 학습 내용 (권장 난이도 문구도 여기 서술 가능) |
| `priority` | number | 우선순위 정수 (1이 가장 높음 등) |

**`title` / `nextFeatureName` / `difficulty` 같은 추가 key는 사용하지 않습니다.**

---

## 4. include 플래그 동작

| 조건 | 결과 |
|------|------|
| `includeCode: false` | `template.codeFiles` → 항상 `[]` (normalizer가 강제) |
| `includeMissions: false` | `template.missions` → 항상 `[]` |
| `includeInterview: false` | `template.interviewQuestions` → 항상 `[]` |

재생성 API에서도 동일 플래그가 적용됩니다 (해당 섹션만 빈 배열로 즉시 반환하는 경우 포함).

---

## 5. 섹션 재생성 API

### Endpoint

`POST /ai/feature-template/regenerate-section`

### 요청 필드 (`FeatureTemplateRegenerateSectionRequest`)

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `section` 또는 `sectionName` | string | 예 | 동일 의미. `section` 또는 `sectionName` **중 하나만** 내면 됨 (validation alias). 값은 아래 canonical 또는 alias |
| `language` | string | 예 | 언어 |
| `featureName` | string | 예 | 기능명 |
| `level` | string(enum) | 예 | `beginner` \| `intermediate` \| `advanced` |
| `framework` | string \| null | 아니오 | 프레임워크 |
| `templateId` | number \| null | 아니오 | 추후 Spring 연동용 메타 |
| `previousContent` | object \| null | 아니오 | 이전에 생성된 동일 섹션 JSON (참고) |
| `userInstruction` | string \| null | 아니오 | 사용자 추가 지시 |
| `includeCode` | boolean | 아니오 | 기본 `true` |
| `includeMissions` | boolean | 아니오 | 기본 `true` |
| `includeInterview` | boolean | 아니오 | 기본 `true` |
| `techStack` | string[] \| null | 아니오 | **재생성 전용**: 맥락·프롬프트에 반영할 스택 힌트 |
| `currentTemplate` 또는 `context` | object \| null | 아니오 | 전체 템플릿 맥락 (`context` 키로 전달해도 동일) |

### sectionName 허용 값 (canonical)

응답의 `data.section`은 항상 아래 **camelCase** 중 하나입니다.

- `overview`
- `requirements`
- `flow`
- `apiSpec`
- `codeFiles`
- `basicQuestions`
- `missions`
- `interviewQuestions`
- `nextRecommendations`

### snake_case 및 별칭 → canonical 매핑

서버는 입력을 내부적으로 위 canonical로 통일합니다 (`app/services/feature_template_section_resolve.py`).

| 입력 예 | 통일 결과 |
|---------|-----------|
| `api_spec`, `apispec` | `apiSpec` |
| `code_view`, `code_files`, `codefiles` | `codeFiles` |
| `basic_questions`, `basicquestions` | `basicQuestions` |
| `interview`, `interview_questions`, `interviewquestions` | `interviewQuestions` |
| `next_recommendations`, `nextrecommendations` | `nextRecommendations` |

요구사항에 적힌 대표 alias:

- `api_spec` → `apiSpec`
- `basic_questions` → `basicQuestions`
- `code_view` → `codeFiles`
- `interview` → `interviewQuestions`
- `next_recommendations` → `nextRecommendations`

### 요청 예시

```json
{
  "language": "java",
  "featureName": "login",
  "level": "beginner",
  "sectionName": "requirements"
}
```

### 응답 예시

```json
{
  "success": true,
  "message": "기능템플릿 섹션 재생성이 완료되었습니다.",
  "data": {
    "section": "requirements",
    "content": [ ],
    "source": "fallback"
  }
}
```

- **`content`**: 해당 섹션 타입과 동일 — 배열 섹션이면 `array`, `overview`/`flow`면 `object`.
- **`source`**: [§7](#7-source-의미)와 동일하게 `ollama` \| `fallback`.

### 잘못된 section

허용 목록이 아니면 **HTTP 422** (`detail`에 `value_error`, 허용 섹션 목록 메시지).

---

## 6. 프론트 연동 기준

- **전체 생성**: `data.template`을 단일 상태로 두고, 아래 매핑으로 화면을 구성합니다.

| template key | UI 매핑 예 |
|--------------|------------|
| `overview` | 프로젝트 개요 |
| `requirements` | 요구사항 명세 |
| `flow` | 동작 흐름·구조 |
| `apiSpec` | API 명세 |
| `codeFiles` | 전체 코드 보기 |
| `basicQuestions` | 기본 문제 |
| `missions` | 실습 미션 |
| `interviewQuestions` | 면접 대비 |
| `nextRecommendations` | 다음 추천 학습 |

- **섹션 재생성**: `data.section`이 가리키는 key에 맞춰 **`data.content`만** 기존 `template`에 덮어쓰면 됩니다.  
  예: `section === "apiSpec"`이면 `template.apiSpec = content` (배열 통째 교체).

---

## 7. source 의미

스키마상 `source`는 **`"ollama"`** 또는 **`"fallback"`** 만 사용합니다 (`Literal`).

| 값 | 의미 |
|----|------|
| `ollama` | `OLLAMA_BASE_URL` 등이 설정된 상태에서 LLM 호출이 성공하고, JSON이 파싱·정규화·Pydantic 검증까지 통과한 경우. (`LLMService.provider`가 현재 `"ollama"`로 고정) |
| `fallback` | LLM 미설정·mock JSON·네트워크/파싱/검증 실패 등으로 **서버 내 mock 템플릿** 경로를 탄 경우. 재생성에서 `include*`로 섹션이 비활성화되어 **즉시 빈 배열**을 돌려줄 때도 `fallback`으로 표기될 수 있습니다. |

---

## 8. 7-1 ~ 7-5 완료 체크리스트

- [x] `generate` 응답 `data.template`에 **9개 섹션 key 항상 보장**
- [x] top-level **snake_case 별칭** 보정 (`FeatureTemplateNormalizer` / 매핑 테이블)
- [x] **`code_view.files` → `codeFiles`** 매핑
- [x] **`includeCode` / `includeMissions` / `includeInterview`** 반영 (빈 배열 강제)
- [x] 프롬프트에서 **스키마 밖 key 금지**·JSON-only·camelCase 유도
- [x] **requirements / apiSpec / missions / interviewQuestions / nextRecommendations** 등 품질 기준 프롬프트에 반영 (7-4)
- [x] **`regenerate-section`** 정상 동작·normalizer 동일 경로
- [x] 잘못된 `sectionName` → **422** validation
- [x] `PYTHONPATH=. pytest tests/ -q` 전체 통과 유지

---

## 9. 테스트 명령어

```bash
PYTHONPATH=. pytest tests/ -q
```

### API 스모크 (curl) 예시

로컬 서버: `http://localhost:8000`

**generate**

```bash
curl -s -X POST "http://localhost:8000/ai/feature-template/generate" \
  -H "Content-Type: application/json" \
  -d '{"language":"java","featureName":"login","level":"beginner","includeCode":false,"includeMissions":false,"includeInterview":false}'
```

**regenerate-section — requirements**

```bash
curl -s -X POST "http://localhost:8000/ai/feature-template/regenerate-section" \
  -H "Content-Type: application/json" \
  -d '{"language":"java","featureName":"login","level":"beginner","sectionName":"requirements"}'
```

**regenerate-section — api_spec**

```bash
curl -s -X POST "http://localhost:8000/ai/feature-template/regenerate-section" \
  -H "Content-Type: application/json" \
  -d '{"language":"java","featureName":"login","level":"beginner","sectionName":"api_spec"}'
```

**includeCode=false (codeFiles 빈 배열)**

```bash
curl -s -X POST "http://localhost:8000/ai/feature-template/regenerate-section" \
  -H "Content-Type: application/json" \
  -d '{"language":"java","featureName":"login","level":"beginner","sectionName":"codeFiles","includeCode":false}'
```

**wrongSection → 422**

```bash
curl -s -X POST "http://localhost:8000/ai/feature-template/regenerate-section" \
  -H "Content-Type: application/json" \
  -d '{"language":"java","featureName":"login","level":"beginner","sectionName":"wrongSection"}'
```

---

## 변경 이력

| 문서 | 설명 |
|------|------|
| 본 가이드 | 고도화 7-6 — API·프론트·체크리스트 1차 정리 |

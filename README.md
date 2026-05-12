# Cobip AI Server

기능 템플릿 기반 실무형 개발 학습 시스템의 **AI 서버**입니다.

---

## 프로젝트 목적

사용자가 학습하고 싶은 **언어/기능**을 선택하면, 해당 기능을 실무 흐름 그대로 따라가며 학습할 수 있는 **기능템플릿 학습 패키지**를 자동 생성하고, 그 위에서 문제 풀이·실습 미션·면접 대비까지 한 번에 제공합니다. AI 챗봇이 핵심 상품이 아니라, **기능템플릿 생성**이 시스템의 중심입니다.

## AI 서버 역할

본 FastAPI 서버는 학습 패키지의 **생성·채점·분석·피드백 로직만 담당**합니다.
영속 저장(PostgreSQL), 사용자/세션/권한 처리는 향후 도입될 Spring Boot 백엔드의 책임이며, AI 서버는 JSON 응답을 반환하는 무상태(stateless) 형태로 운영됩니다.

상위 라우팅은 **Agentic RAG Router**가 담당하여 요청 의도를 판단하고 다음 분기 중 하나로 위임합니다.

- 기능템플릿 생성 / 섹션 재생성
- 문법 문제 생성 / 채점 / 오답 해설
- 기능템플릿 기본 문제 채점
- 실습 미션 피드백
- 면접 답변 피드백
- 코드 분석
- 다음 기능템플릿 추천
- 보조 Q&A 챗봇

## 핵심 기능

### 1. 기능템플릿 생성
다음 9개 섹션을 **고정 순서**로 생성합니다.

1. 프로젝트 개요
2. 요구사항 명세서
3. 동작 흐름
4. **API 명세서** ← 동작 흐름 다음, 전체 코드 보기 이전 위치 고정
5. 전체 코드 보기
6. 기본 문제 풀이
7. 실습 미션
8. 면접 대비
9. 다른 기능 템플릿 제안

### 2. 문법 문제 생성 / 채점
기존 문법템플릿의 본문(JSONB content)은 **AI가 생성·수정하지 않습니다.**
AI는 그 본문을 참고하여 **추가 문제 생성, 채점, 오답 해설**만 수행합니다.

### 3. 미션 피드백
사용자가 제출한 코드를 요구사항·API 명세서와 대조해 **요구사항 만족 여부, API 일치 여부, 코드 이슈, 개선 제안**을 반환합니다.

### 4. 면접 피드백
면접 질문의 **keyPoints**가 사용자의 답변에 포함됐는지 분석하고, 누락 항목을 보강한 모범답변을 제시합니다.

### 5. 보조 Q&A 챗봇
챗봇은 **핵심 기능이 아니라 보조 기능**입니다. 학습 도중의 단순 질문 응대용으로만 사용되며, 우선순위/리소스 배분에서 항상 기능템플릿 생성보다 낮습니다.

---

## 현재 구현 상태

| 영역 | 상태 |
| --- | --- |
| 프로젝트 골격 (`app/` 구조, `__init__.py`) | ✅ 완료 |
| 환경 설정 (`pydantic-settings` 기반 `Settings`) | ✅ 완료 |
| 핵심 enum (`DifficultyLevel`, `QuestionType`, `IntentType` 등) | ✅ 완료 |
| 기능템플릿 요청/응답 스키마 | ✅ 일부 완료 (forward reference 일부 미해소) |
| 문법 / 평가 / 추천 / 챗봇 스키마 | ✅ 완료 |
| Agentic RAG Router 분기 구조 | ✅ 완료 |
| 기능템플릿 생성 service (mock) | ✅ 완료 (`로그인` 기준 상세 mock) |
| 문법 문제 생성/채점/오답 해설 service | ✅ 완료 (rule 기반 mock) |
| 미션 / 면접 / 코드 분석 service | ✅ 완료 (rule 기반 mock) |
| 추천 service | ✅ 완료 (rule 기반 mock) |
| 보조 챗봇 service | ✅ 완료 (mock) |
| LLM 호출 service (Ollama OpenAI-호환) | ✅ 검증 완료 (`qwen2.5-coder:1.5b`) |
| 임베딩 service (BGE-M3 자리) | ✅ 구조 완성 (deterministic mock 벡터) |
| Qdrant service | ✅ 구조 완성 (mock, 빈 결과) |
| Redis 클라이언트 헬퍼 | ✅ 구조 완성 (mock, `None` 반환) |
| in-memory 캐시 + rate limit | ✅ 완료 (mock) |
| FastAPI 라우터 (`/health`, `/ai/feature-template/*`, `/ai/grammar/*`, `/ai/quiz/*`, `/ai/mission/*`, `/ai/interview/*`, `/ai/code/*`, `/ai/chat`) | ✅ 완료 |
| CORS 설정 | ✅ 완료 |
| Dockerfile / docker-compose | ✅ 완료 (Ollama 포함) |
| Ollama OpenAI-호환 LLM provider | ✅ 검증 완료 (`qwen2.5-coder:1.5b`) |

> **현재 단계는 "내부 구조와 임시 rule 기반 service" 중심**입니다.  
> 라우터·service·스키마의 골격을 먼저 채우고, 실제 외부 시스템 연동은 다음 단계에서 점진적으로 도입합니다.

---

## 추후 도입 예정 (현재 미연동)

다음 외부 시스템들은 **연결 자리만 마련**되어 있으며, 실제 연동은 별도 단계에서 활성화됩니다.

- **Qdrant** — 벡터 검색 (학습 자료/예시 코드 인덱싱)
- **BGE-M3** — 한/영 통합 임베딩 모델
- **Ollama** + **qwen2.5-coder:1.5b** — OpenAI-호환 `/chat/completions` provider
- **Redis** — 응답 캐시·세션 토큰·rate limit 슬라이딩 윈도우

위 시스템이 연결되기 전에는 각 service가 **결정적 mock 응답**(같은 입력 → 같은 출력)을 반환하도록 설계되어 있어, 라우터·스키마·흐름 검증을 안전하게 진행할 수 있습니다.

---

## Ollama LLM 실행

이 AI 서버는 Ollama OpenAI-호환 API를 통해 LLM을 호출합니다.

환경 파일 생성:

```bash
cp .env.example .env
```

Docker Compose 실행:

```bash
docker compose up -d
```

Ollama 모델 pull:

```bash
docker compose exec ollama ollama pull qwen2.5-coder:1.5b
```

Ollama OpenAI-호환 API 확인:

```bash
curl http://localhost:11434/v1/models
```

FastAPI 확인:

```bash
curl -I http://localhost:8000/docs
```

기능템플릿 생성 API 검증:

```bash
curl -X POST http://localhost:8000/ai/feature-template/generate \
  -H "Content-Type: application/json" \
  -d '{
    "language": "Java",
    "featureName": "login",
    "level": "beginner"
  }'
```

성공 기준은 응답의 `data.source`가 `"ollama"`이고 `data.template`이 존재하는 것입니다.

FastAPI만 `docker run`으로 실행하고 Ollama가 호스트에서 실행 중이면 다음 예시를 사용할 수 있습니다.

```bash
docker run -d --name cobip-ai-ollama-verify -p 8000:8000 \
  --add-host=host.docker.internal:host-gateway \
  -e LLM_PROVIDER=ollama \
  -e OLLAMA_BASE_URL=http://host.docker.internal:11434/v1 \
  -e OLLAMA_MODEL=qwen2.5-coder:1.5b \
  cobip-ai-server
```

---

## 백엔드(Spring Boot) 연동

- 현재 **Spring Boot 백엔드는 존재하지 않습니다.**
- AI 서버는 향후 백엔드와 JSON 으로만 통신하며, **저장은 Spring Boot + PostgreSQL** 측에서 담당합니다.
- AI 서버 자체가 직접 DB 를 가지지 않습니다.
- 따라서 현재 단계에서는 **Spring Boot WebClient 연동 테스트, Postman/Swagger 통합 테스트는 진행하지 않습니다.**
- 백엔드 도입 시점에 맞춰 인증·인가·요청 포맷·에러 코드 표준 등 통합 규약을 별도 단계에서 정합니다.

---

## 기술 스택

- **Python 3.11+**
- **FastAPI** + **uvicorn**
- **Pydantic v2** / **pydantic-settings**
- **httpx** (LLM 호출용)
- **Qdrant** (벡터 DB, 추후 연동)
- **BGE-M3** (임베딩, 추후 연동)
- **Ollama** + **qwen2.5-coder:1.5b** (LLM)
- **Redis** (캐시, 추후 연동)
- **Docker** / **docker-compose**

---

## 디렉터리 구조

```
cobip/
├── app/
│   ├── api/
│   │   └── routes/        # FastAPI 라우터
│   ├── core/              # config, redis 등 공통 인프라
│   ├── models/            # enum 등 도메인 모델
│   ├── prompts/           # LLM 프롬프트 모음
│   ├── schemas/           # Pydantic 요청/응답 스키마
│   ├── services/          # 도메인 service (현재 rule 기반 mock 중심)
│   ├── utils/             # 공통 유틸
│   └── main.py
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

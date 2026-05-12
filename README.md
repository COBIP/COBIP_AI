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
| 보조 챗봇 service | ✅ Ollama + 선택 RAG (`RAG_ENABLED`·`useRag` 시 Retriever 주입) |
| LLM 호출 service (Ollama OpenAI-호환) | ✅ 검증 완료 (`qwen2.5-coder:1.5b`) |
| 임베딩 service (`sentence-transformers`) | ✅ lazy 로딩·`embed_text` / `embed_texts` (Chat 미연동) |
| Qdrant service (`qdrant-client`) | ✅ 연결·`health_check`·`collection_exists`·`search` (인덱싱 미구현) |
| Retriever / 인덱싱 | ✅ `POST /ai/rag/retrieve` 검색, `POST /ai/rag/index` 인덱싱 (`/ai/chat` 미연동) |
| Redis 클라이언트 헬퍼 | ✅ 구조 완성 (mock, `None` 반환) |
| in-memory 캐시 + rate limit | ✅ 완료 (mock) |
| FastAPI 라우터 (`/health`, `/ai/feature-template/*`, `/ai/grammar/*`, `/ai/quiz/*`, `/ai/mission/*`, `/ai/interview/*`, `/ai/code/*`, `/ai/rag/*`, `/ai/chat`) | ✅ 완료 |
| CORS 설정 | ✅ 완료 |
| Dockerfile / docker-compose | ✅ 완료 (Ollama 포함) |
| Ollama OpenAI-호환 LLM provider | ✅ 검증 완료 (`qwen2.5-coder:1.5b`) |

> **현재 단계는 "내부 구조와 임시 rule 기반 service" 중심**입니다.  
> 라우터·service·스키마의 골격을 먼저 채우고, 실제 외부 시스템 연동은 다음 단계에서 점진적으로 도입합니다.

---

## RAG / Qdrant / Embedding 설정 (6-3)

- `/ai/chat`은 여전히 **Ollama 기본 챗봇**이며, `useRag`·`ragUsed`·`references`는 **필드만 준비**된 상태입니다.
- **6-3**부터 `QdrantService`·`EmbeddingService`·`qdrant-client`·`sentence-transformers` 및 아래 환경변수가 추가되었습니다. **실제 문서 검색·RAG context 주입은 `/ai/chat`에 아직 연결되지 않았습니다.**
- `GET /health` 응답의 `data.qdrant`에 Qdrant 연결 가능 여부가 포함됩니다 (앱 기동은 실패해도 계속됨).
- 추후 Retriever를 붙이고 `RAG_ENABLED=true`로 운영할 때 `references`·`ragUsed`를 활용할 수 있습니다.

환경변수 예시:

| 변수 | Compose 내부 예시 | `docker run`만 쓸 때 (호스트 Qdrant) |
| --- | --- | --- |
| `RAG_ENABLED` | `false` | `false` |
| `RAG_TOP_K` | `3` | `3` |
| `QDRANT_URL` | `http://qdrant:6333` | `http://host.docker.internal:6333` |
| `QDRANT_COLLECTION` | `cobip_knowledge` | 동일 |
| `EMBEDDING_MODEL` | `BAAI/bge-m3` | 동일 |

### Retriever 검색 테스트 API (6-4)

`POST /ai/rag/retrieve`는 **Qdrant 벡터 검색만** 수행하는 확인용 API입니다. **Ollama를 호출하지 않으며**, **`/ai/chat`에 결과를 자동 주입하지 않습니다.** 다음 단계에서 `ChatService`에 Retriever 결과를 context로 넣을 예정입니다.

- `QDRANT_COLLECTION`에 포인트가 없거나 컬렉션이 없으면 `data.references == []`, `data.count == 0`이 **정상**입니다.
- 성공 시 응답 `data`에 `query`, `references`, `count`가 포함됩니다.

```bash
curl -X POST http://localhost:8000/ai/rag/retrieve \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Spring Boot Controller와 Service 차이",
    "topK": 3
  }'
```

### RAG 문서 인덱싱 API (6-5)

`POST /ai/rag/index`는 **Qdrant에 검색할 문서**를 넣는 수동 인덱싱 API입니다. `POST /ai/rag/retrieve`로 같은 컬렉션을 검색할 수 있습니다. **`/ai/chat`에는 아직 자동으로 주입되지 않으며**, 다음 단계에서 Retriever 결과를 챗봇 context로 넣을 예정입니다.

**인덱싱 예시:**

```bash
curl -X POST http://localhost:8000/ai/rag/index \
  -H "Content-Type: application/json" \
  -d '{
    "documents": [
      {
        "title": "Spring Controller와 Service 차이",
        "content": "Controller는 HTTP 요청을 받고 응답을 반환하는 계층이다. Service는 비즈니스 로직을 처리하는 계층이다.",
        "sourceType": "note",
        "metadata": {
          "topic": "spring",
          "level": "beginner"
        }
      }
    ]
  }'
```

**이후 검색 예시:** (위와 동일한 `POST /ai/rag/retrieve` 호출)

- 인덱싱 성공 시 `success: true`, `data.indexedCount >= 1`, `data.ids`에 포인트 id가 올 수 있습니다.
- 검색 시 `data.count >= 1`이면 `references[].content`, `score` 등이 채워질 수 있습니다 (질의·데이터에 따라 다름).
- **참고:** 컨테이너에서 `BAAI/bge-m3`를 처음 받을 때 Hugging Face Hub 다운로드로 **수 분 이상** 걸릴 수 있습니다. `HF_TOKEN` 설정이나 모델 캐시 볼륨 마운트를 권장합니다.

---

## 추후 도입 예정 (현재 미연동)

다음 외부 시스템들은 **연결 자리만 마련**되어 있으며, 실제 연동은 별도 단계에서 활성화됩니다.

- **Qdrant** — 벡터 검색 (학습 자료/예시 코드 인덱싱)
- **BGE-M3** — 한/영 통합 임베딩 모델
- **Ollama** + **qwen2.5-coder:1.5b** — OpenAI-호환 `/chat/completions` provider
- **Redis** — 응답 캐시·세션 토큰·rate limit 슬라이딩 윈도우

위 시스템 중 **`/ai/chat` RAG context 자동 주입**은 아직 없으며, 인덱싱은 **`POST /ai/rag/index`**, 검색은 **`POST /ai/rag/retrieve`** 로 검증합니다.

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

### 기본 챗봇 API (`POST /ai/chat`)

`/ai/chat`은 **Ollama(OpenAI 호환 API)** 기반 챗봇입니다.

**RAG(검색 context 주입, 6-6)**  
- 서버 **`RAG_ENABLED=true`** 이고 요청 **`useRag: true`** 일 때만 `RetrieverService`로 Qdrant 검색을 하고, **검색 결과가 1건 이상**이면 `data.ragUsed=true`, `data.references`에 근거가 채워집니다.  
- 검색 결과가 없거나 `RAG_ENABLED=false`이거나 `useRag`가 `true`가 아니면 **`ragUsed=false`**, **`references=[]`** 로 동작합니다 (일반 Ollama 답변).  
- **먼저 `POST /ai/rag/index`로 문서를 넣은 뒤** 같은 `QDRANT_COLLECTION`에서 검색됩니다.

```bash
curl -X POST http://localhost:8000/ai/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Spring Boot에서 Controller와 Service 차이를 쉽게 설명해줘."
  }'
```

`RAG_ENABLED=false`인 경우 `useRag: true`여도 **검색 없이** 기본 답변만 나옵니다.

**RAG 챗봇 예시 (`RAG_ENABLED=true`, `hf_cache` 권장):**

```bash
docker run -d --name cobip-ai-rag-chat-verify -p 8007:8000 \
  --add-host=host.docker.internal:host-gateway \
  -v hf_cache:/root/.cache/huggingface \
  -e LLM_PROVIDER=ollama \
  -e OLLAMA_BASE_URL=http://host.docker.internal:11434/v1 \
  -e OLLAMA_MODEL=qwen2.5-coder:1.5b \
  -e RAG_ENABLED=true \
  -e RAG_TOP_K=3 \
  -e QDRANT_URL=http://host.docker.internal:6333 \
  -e QDRANT_COLLECTION=cobip_knowledge \
  -e EMBEDDING_MODEL=BAAI/bge-m3 \
  cobip-ai-server

curl -X POST http://localhost:8007/ai/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Controller와 Service 차이를 알려줘.",
    "useRag": true
  }'
```

선택 필드 `context`는 사용자가 직접 넣은 문맥이며, RAG 검색 블록과 함께 프롬프트에 포함될 수 있습니다.

FastAPI만 `docker run`으로 실행하고 Ollama가 호스트에서 실행 중이면 다음 예시를 사용할 수 있습니다.

첫 인덱싱/검색 전에 **`BAAI/bge-m3`** 를 받아 두려면 Hugging Face 캐시 볼륨을 마운트하는 것이 좋습니다.

```bash
docker volume create hf_cache
docker run --rm -v hf_cache:/root/.cache/huggingface cobip-ai-server \
  python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-m3'); print('ok')"

docker run -d --name cobip-ai-ollama-verify -p 8000:8000 \
  --add-host=host.docker.internal:host-gateway \
  -v hf_cache:/root/.cache/huggingface \
  -e LLM_PROVIDER=ollama \
  -e OLLAMA_BASE_URL=http://host.docker.internal:11434/v1 \
  -e OLLAMA_MODEL=qwen2.5-coder:1.5b \
  -e RAG_ENABLED=false \
  -e RAG_TOP_K=3 \
  -e QDRANT_URL=http://host.docker.internal:6333 \
  -e QDRANT_COLLECTION=cobip_knowledge \
  -e EMBEDDING_MODEL=BAAI/bge-m3 \
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

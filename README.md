# COBIP AI Server

코드 학습 플랫폼(COBIP)의 AI 서버. RAG 기반 챗봇 답변을 생성한다.

## 구조

```
Spring Boot (서비스 서버) → FastAPI (AI 서버) → vLLM / Qdrant (GPU 서버)
```

## 생성된 파일

| 파일 | 역할 |
|------|------|
| `app/config.py` | `.env` 기반 설정 (vLLM URL, Qdrant URL, mock 모드) |
| `app/main.py` | FastAPI 엔트리, DI (mock/real 전환), CORS |
| `app/api/chat_router.py` | `/api/chat`, `/api/health`, `/api/problems` 엔드포인트 |
| `app/dto/schemas.py` | `ChatRequest`, `ChatResponse`, `ProblemDTO` |
| `app/service/rag_chat_service.py` | RAG 파이프라인 오케스트레이션 |
| `app/retriever/base.py` | Retriever 추상 인터페이스 (ABC) |
| `app/retriever/mock_retriever.py` | in-memory 검색 (프로토타입) |
| `app/retriever/qdrant_retriever.py` | Qdrant + BGE-M3 스켈레톤 (향후) |
| `app/llm/base.py` | LLM Client 추상 인터페이스 (ABC) |
| `app/llm/mock_llm_client.py` | Mock 답변 생성 (프로토타입) |
| `app/llm/vllm_client.py` | vLLM OpenAI-compatible API 호출 |
| `app/prompt/prompt_builder.py` | RAG context + 질문 → 프롬프트 조립 |
| `app/data/problem_store.py` | in-memory 문제 데이터 3개 |
| `Dockerfile` | Python 3.11-slim 기반 컨테이너 |
| `docker-compose.yml` | 호스트 포트 8080 → 컨테이너 8000 |
| `.env` | 환경변수 (`USE_MOCK=true` 등) |
| `requirements.txt` | 의존성 목록 |
| `.dockerignore` | Docker 빌드 시 제외 파일 |

## 실행

### Docker (권장)

```bash
cd /home/dmdthd2/COBIP_AI
docker compose up --build -d
```

컨테이너 내부는 포트 `8000`이며, 호스트에서는 `http://localhost:8080` 으로 접근한다. (호스트 `8000`이 이미 사용 중일 때를 피하기 위해 `8080:8000`으로 매핑됨)

### 로컬 실행

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## API

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/health` | 헬스체크 |
| POST | `/api/chat` | RAG 챗봇 질문 |
| GET | `/api/problems` | 전체 문제 목록 |
| GET | `/api/problems/{id}` | 문제 상세 조회 |

### POST /api/chat 요청 예시

```json
{
  "problem_id": 1,
  "user_code": "int a = \"안녕\";",
  "question": "왜 틀렸나요?"
}
```

## 환경 변수 (.env)

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `USE_MOCK` | Mock 모드 사용 여부 | `true` |
| `VLLM_BASE_URL` | vLLM 서버 URL | `http://localhost:8001/v1` |
| `VLLM_MODEL_NAME` | LLM 모델명 | `Qwen/Qwen2.5-Coder-14B-Instruct` |
| `QDRANT_URL` | Qdrant 서버 URL | `http://localhost:6333` |

## 서버 이전 시

`.env` 파일의 URL 값만 변경하면 된다. 코드 수정 불필요.


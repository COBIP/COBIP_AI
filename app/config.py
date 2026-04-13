"""
환경 설정 모듈.
.env 파일 또는 환경변수로 vLLM URL, Qdrant URL 등을 주입한다.
서버 이전 시 이 값들만 변경하면 된다.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # mock 모드: true면 MockRetriever + MockLLMClient 사용
    use_mock: bool = True

    # vLLM 서버 설정
    vllm_base_url: str = "http://localhost:8001/v1"
    vllm_model_name: str = "Qwen/Qwen2.5-Coder-14B-Instruct"
    vllm_max_tokens: int = 1024
    vllm_temperature: float = 0.3

    # Qdrant 벡터 DB 설정
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection_name: str = "cobip_chunks"

    # FastAPI 서버 설정
    host: str = "0.0.0.0"
    port: int = 8000

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()

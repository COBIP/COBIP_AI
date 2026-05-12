import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import chat, evaluation, feature_template, grammar, health, rag


@asynccontextmanager
async def lifespan(_: FastAPI):
    """`app.*` 로거의 INFO 가 컨테이너 stdout 에 남도록 한다 (docker logs 확인용)."""
    app_logger = logging.getLogger("app")
    if not app_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(levelname)s %(name)s %(message)s"),
        )
        app_logger.addHandler(handler)
        app_logger.setLevel(logging.INFO)
    yield


app = FastAPI(
    title="AI Template Server",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(feature_template.router)
app.include_router(grammar.router)
app.include_router(evaluation.router)
app.include_router(rag.router)
app.include_router(chat.router)

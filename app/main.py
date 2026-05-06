from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import chat, evaluation, feature_template, grammar, health

app = FastAPI(
    title="AI Template Server",
    version="0.1.0",
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
app.include_router(chat.router)

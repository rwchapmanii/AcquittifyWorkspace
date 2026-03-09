from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from .chat import answer
from .config import MODEL_NAME, VAULT_PATH
from .indexer import build_index, manifest_stats
from .searcher import search

app = FastAPI(title="Peregrine Local API")


class SearchRequest(BaseModel):
    query: str
    limit: int = 5


class ChatRequest(BaseModel):
    query: str
    limit: int = 5


class IndexRequest(BaseModel):
    limit: int | None = None
    rebuild: bool = False


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "model": MODEL_NAME, "vault": str(VAULT_PATH)}


@app.get("/status")
async def status() -> dict:
    return manifest_stats()


@app.post("/index")
async def index(payload: IndexRequest) -> dict:
    return build_index(limit=payload.limit, rebuild=payload.rebuild)


@app.post("/search")
async def search_endpoint(payload: SearchRequest) -> dict:
    results = search(payload.query, limit=payload.limit)
    return {"results": results}


@app.post("/chat")
async def chat_endpoint(payload: ChatRequest) -> dict:
    return answer(payload.query, limit=payload.limit)

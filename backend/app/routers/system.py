"""Health, Ollama status, and agent metadata."""
from fastapi import APIRouter

from .. import ollama_client
from ..agents import AGENTS

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/ollama")
async def ollama_status():
    return await ollama_client.status()


@router.post("/ollama/pull")
async def ollama_pull(name: str | None = None):
    from ..config import settings

    model = name or settings.ollama_model
    await ollama_client.pull_model(model)
    return {"pulled": model}


@router.get("/agents")
def agents():
    return [
        {"name": name, "role": spec["role"]}
        for name, spec in AGENTS.items()
    ]

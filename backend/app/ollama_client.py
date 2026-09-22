"""Async Ollama client used by all agents.

Handles model availability: if the configured model is missing it will try to
pull it (best-effort) or fall back to OLLAMA_FALLBACK_MODEL.
"""
import json
from typing import AsyncGenerator, Optional

import httpx

from .config import settings

_resolved_model: Optional[str] = None


async def _list_models() -> list[str]:
    try:
        async with httpx.AsyncClient(base_url=settings.ollama_base_url, timeout=15.0) as c:
            r = await c.get("/api/tags")
            r.raise_for_status()
            data = r.json()
            return [m.get("name", "") for m in data.get("models", [])]
    except Exception:
        return []


async def resolve_model() -> str:
    """Return a usable model name, pulling/falling back as needed."""
    global _resolved_model
    if _resolved_model:
        return _resolved_model

    available = await _list_models()
    want = settings.ollama_model

    def _has(name: str) -> bool:
        return any(m == name or m.startswith(name.split(":")[0] + ":") for m in available)

    if _has(want):
        _resolved_model = want
        return want

    # Try to pull the desired model (may take a long time for 20b).
    try:
        await pull_model(want)
        _resolved_model = want
        return want
    except Exception:
        pass

    fb = settings.ollama_fallback_model
    if fb and _has(fb):
        _resolved_model = fb
        return fb
    if fb:
        try:
            await pull_model(fb)
            _resolved_model = fb
            return fb
        except Exception:
            pass

    # last resort: whatever is available
    if available:
        _resolved_model = available[0]
        return available[0]
    # give the caller the configured name; error will surface on use
    return want


async def pull_model(name: str) -> None:
    async with httpx.AsyncClient(base_url=settings.ollama_base_url, timeout=None) as c:
        async with c.stream("POST", "/api/pull", json={"name": name}) as resp:
            resp.raise_for_status()
            async for _ in resp.aiter_lines():
                # consume the pull progress stream
                pass


async def status() -> dict:
    available = await _list_models()
    return {
        "base_url": settings.ollama_base_url,
        "configured_model": settings.ollama_model,
        "fallback_model": settings.ollama_fallback_model,
        "embed_model": settings.ollama_embed_model,
        "available_models": available,
        "model_ready": any(
            m == settings.ollama_model
            or m.startswith(settings.ollama_model.split(":")[0] + ":")
            for m in available
        ),
        "embed_ready": _has_name(available, settings.ollama_embed_model),
    }


def _has_name(available: list[str], name: str) -> bool:
    if not name:
        return False
    return any(m == name or m.startswith(name.split(":")[0] + ":") for m in available)


async def embed(text: str, *, model: Optional[str] = None) -> Optional[list[float]]:
    """Return a vector or None if no embed model is installed. Does not pull."""
    mdl = model or settings.ollama_embed_model
    if not mdl:
        return None
    available = await _list_models()
    if not _has_name(available, mdl):
        return None
    payload = {"model": mdl, "prompt": (text or "")[:6000]}
    try:
        async with httpx.AsyncClient(base_url=settings.ollama_base_url, timeout=60.0) as c:
            r = await c.post("/api/embeddings", json=payload)
            if r.status_code >= 400:
                r = await c.post("/api/embed", json={"model": mdl, "input": payload["prompt"]})
            r.raise_for_status()
            data = r.json()
            vec = data.get("embedding")
            if not vec and isinstance(data.get("embeddings"), list) and data["embeddings"]:
                vec = data["embeddings"][0]
            if isinstance(vec, list) and vec and isinstance(vec[0], (int, float)):
                return [float(x) for x in vec]
    except Exception:
        return None
    return None


async def chat(
    system: str,
    prompt: str,
    *,
    model: Optional[str] = None,
    temperature: float = 0.3,
    format_json: bool = False,
) -> str:
    """Non-streaming chat completion. Returns the assistant text."""
    return await chat_messages(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        model=model,
        temperature=temperature,
        format_json=format_json,
    )


async def chat_messages(
    messages: list[dict],
    *,
    model: Optional[str] = None,
    temperature: float = 0.3,
    format_json: bool = False,
) -> str:
    """Multi-turn chat. `messages` are Ollama {role, content} dicts."""
    mdl = model or await resolve_model()
    body: dict = {
        "model": mdl,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature},
    }
    if format_json:
        body["format"] = "json"

    async with httpx.AsyncClient(base_url=settings.ollama_base_url, timeout=settings.ollama_timeout) as c:
        r = await c.post("/api/chat", json=body)
        r.raise_for_status()
        data = r.json()
        return data.get("message", {}).get("content", "")


async def chat_stream(
    system: str,
    prompt: str,
    *,
    model: Optional[str] = None,
    temperature: float = 0.4,
) -> AsyncGenerator[str, None]:
    """Streaming chat completion. Yields text chunks."""
    async for chunk in chat_stream_messages(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        model=model,
        temperature=temperature,
    ):
        yield chunk


async def chat_stream_messages(
    messages: list[dict],
    *,
    model: Optional[str] = None,
    temperature: float = 0.4,
) -> AsyncGenerator[str, None]:
    """Multi-turn streaming chat. Yields text chunks as Ollama emits them."""
    mdl = model or await resolve_model()
    body = {
        "model": mdl,
        "messages": messages,
        "stream": True,
        "options": {"temperature": temperature},
    }
    async with httpx.AsyncClient(base_url=settings.ollama_base_url, timeout=settings.ollama_timeout) as c:
        async with c.stream("POST", "/api/chat", json=body) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                chunk = obj.get("message", {}).get("content", "")
                if chunk:
                    yield chunk
                if obj.get("done"):
                    break

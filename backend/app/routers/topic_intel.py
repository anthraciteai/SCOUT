"""Topic intelligence: OCR the official SBIR PDF, summarize it, and score the
raw requirements against the caller's resume + company/products pack.

This is deliberately separate from the cheap inbox ranker (matcher.py). The
ranker is keyword/embedding overlap over DSIP *summary* JSON; here we pull the
full solicitation PDF, run Docling OCR to get the real raw text, and then use
the LLM to summarize and do a requirement-by-requirement fit.

Everything is cached on disk under {data_dir}/topic_intel/{id}/ so a second
look does not re-run OCR or the model.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
from typing import Any, Optional

import httpx
from fastapi import APIRouter, HTTPException, Query

from .. import agents, docling_service, dsip, matcher, ollama_client
from ..config import settings
from ..identity import current_identity
from ..vault import get_vault

router = APIRouter(prefix="/api/topics", tags=["topic-intel"])


# ---- cache -------------------------------------------------------------

def _cache_dir(topic_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", topic_id)[:120]
    path = os.path.join(settings.data_dir, "topic_intel", safe)
    os.makedirs(path, exist_ok=True)
    return path


def _read_json(topic_id: str, name: str) -> Optional[dict[str, Any]]:
    path = os.path.join(_cache_dir(topic_id), name)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _write_json(topic_id: str, name: str, payload: dict[str, Any]) -> None:
    path = os.path.join(_cache_dir(topic_id), name)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f)
    except OSError:
        pass


# ---- raw text ----------------------------------------------------------

def _strip_html(s: str) -> str:
    return re.sub(r"<[^>]+>", " ", s or "")


def _harvest_strings(node: Any, out: list[str], budget: int = 24000) -> None:
    """Recursively pull human-readable string leaves out of the DSIP details
    JSON (schema varies by component), HTML-stripped and deduped by caller."""
    if sum(len(x) for x in out) > budget:
        return
    if isinstance(node, str):
        text = _strip_html(node).strip()
        if len(text) >= 3:
            out.append(text)
    elif isinstance(node, dict):
        for v in node.values():
            _harvest_strings(v, out, budget)
    elif isinstance(node, list):
        for v in node:
            _harvest_strings(v, out, budget)


async def _details_text(topic_id: str) -> str:
    try:
        details = await dsip.get_topic(topic_id)
    except Exception:
        return ""
    parts: list[str] = []
    _harvest_strings(details, parts)
    seen: set[str] = set()
    uniq: list[str] = []
    for p in parts:
        key = p.lower()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(p)
    return "\n".join(uniq).strip()


async def _ensure_text(topic_id: str, force: bool = False) -> dict[str, Any]:
    if not force:
        cached = _read_json(topic_id, "text.json")
        if cached and (cached.get("text") or "").strip():
            return cached

    text = ""
    source = ""
    # Primary: the official solicitation PDF, OCR'd by Docling.
    try:
        resp = await dsip.get_bytes(f"/topics/{topic_id}/download/PDF")
        data = resp.content if resp else b""
        if data:
            text = await asyncio.to_thread(
                docling_service.extract_text, f"topic_{topic_id}.pdf", data
            )
            if (text or "").strip():
                source = "pdf-ocr"
    except Exception:
        text = ""

    # Fallback: the structured /details JSON (what Browse already shows).
    if not (text or "").strip():
        text = await _details_text(topic_id)
        if text:
            source = "dsip-json"

    text = (text or "").strip()
    out = {
        "topic_id": topic_id,
        "chars": len(text),
        "source": source or "none",
        "cached_at": time.time(),
        "text": text,
    }
    _write_json(topic_id, "text.json", out)
    return out


# ---- capability text (ME + mission + products) -------------------------

def _capability_text() -> tuple[str, str]:
    """Return (capability_text, source_label) for the current caller."""
    ident = current_identity()
    if ident:
        try:
            bundle = get_vault().bundle_resume(ident).strip()
        except Exception:
            bundle = ""
        if bundle:
            return bundle, f"{ident.user_id}@{ident.company_id}"
    cid = (ident.company_id if ident else None) or settings.default_company
    company = matcher._company_only_text(cid).strip()
    return company, f"company:{cid}"


# ---- summary -----------------------------------------------------------

_SUMMARY_SYSTEM = (
    "You condense a DoD SBIR/STTR solicitation into a scannable brief for a small "
    "business deciding whether to bid. Use ONLY the provided topic text. Do not invent "
    "requirements. Quote the topic's own words for each requirement.\n"
    "Return ONLY JSON with keys: "
    '{"tldr": string (<=50 words), '
    '"problem": string (the unmet need / gap), '
    '"objective": string (what the government wants built), '
    '"who_cares": string (sponsor / end user / transition), '
    '"phases": [string], '
    '"requirements": [{"need": string, "evidence": string (exact phrase from the topic)}], '
    '"keywords": [string]}. '
    "Give 4-10 requirements. Keep each field tight."
)


async def _ensure_summary(topic_id: str, force: bool = False) -> dict[str, Any]:
    if not force:
        cached = _read_json(topic_id, "summary.json")
        if cached:
            return cached
    text_blob = await _ensure_text(topic_id, force=force)
    raw = (text_blob.get("text") or "").strip()
    if not raw:
        raise HTTPException(status_code=502, detail="No topic text available to summarize.")
    model = ""
    try:
        out = await ollama_client.chat(
            _SUMMARY_SYSTEM,
            "TOPIC TEXT:\n" + raw[:8000] + "\n\nReturn ONLY the JSON described above.",
            temperature=0.2,
            format_json=True,
        )
        model = await ollama_client.resolve_model()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Summary model call failed: {e}") from e
    data = agents._safe_json(out)
    if not isinstance(data, dict) or data.get("raw"):
        raise HTTPException(status_code=502, detail="Model did not return usable JSON.")
    payload = {
        "topic_id": topic_id,
        "source": text_blob.get("source"),
        "chars": text_blob.get("chars"),
        "model": model,
        "cached_at": time.time(),
        "tldr": str(data.get("tldr") or "")[:600],
        "problem": str(data.get("problem") or "")[:800],
        "objective": str(data.get("objective") or "")[:800],
        "who_cares": str(data.get("who_cares") or "")[:600],
        "phases": [str(p) for p in (data.get("phases") or [])][:6],
        "requirements": [
            {
                "need": str(r.get("need") or "")[:300],
                "evidence": str(r.get("evidence") or "")[:400],
            }
            for r in (data.get("requirements") or [])
            if isinstance(r, dict) and r.get("need")
        ][:10],
        "keywords": [str(k) for k in (data.get("keywords") or [])][:20],
    }
    _write_json(topic_id, "summary.json", payload)
    return payload


# ---- fit vs profile ----------------------------------------------------

_FIT_SYSTEM = (
    "You judge whether a small business can deliver a DoD SBIR/STTR topic, using ONLY "
    "the CAPABILITIES text (their resume + company mission + products) and the TOPIC "
    "requirements. Do not invent capabilities they did not state.\n"
    "For EACH topic requirement, decide status: 'meets' (clearly shown in capabilities), "
    "'partial' (adjacent / adaptable), or 'gap' (nothing relevant). Quote the capability "
    "phrase that supports a meets/partial in matched_capability; leave it empty for a gap.\n"
    "Return ONLY JSON with keys: "
    '{"overall_fit": 0-100, '
    '"recommendation": "GO|LEAN GO|LEAN NO-GO|NO-GO", '
    '"summary": string (<=60 words), '
    '"requirements": [{"need": string, "status": "meets|partial|gap", '
    '"evidence": string (from the topic), "matched_capability": string (from capabilities)}], '
    '"strengths": [string], "gaps": [string]}.'
)


async def _fit(topic_id: str, force: bool = False) -> dict[str, Any]:
    if not force:
        cached = _read_json(topic_id, "fit.json")
        if cached:
            return cached
    summary = await _ensure_summary(topic_id, force=force)
    cap_text, cap_source = _capability_text()
    if not cap_text.strip():
        raise HTTPException(
            status_code=400,
            detail="No capabilities on file. Add a resume (ME) or company products first.",
        )
    reqs = summary.get("requirements") or []
    req_lines = "\n".join(
        f"- {r['need']} (topic says: \"{r.get('evidence', '')}\")" for r in reqs
    ) or (summary.get("objective") or "")
    prompt = (
        "CAPABILITIES (resume + company + products):\n"
        + cap_text[:7000]
        + "\n\nTOPIC: "
        + str(summary.get("tldr") or "")
        + "\nOBJECTIVE: "
        + str(summary.get("objective") or "")
        + "\n\nTOPIC REQUIREMENTS:\n"
        + req_lines[:3000]
        + "\n\nReturn ONLY the JSON described above."
    )
    model = ""
    try:
        out = await ollama_client.chat(_FIT_SYSTEM, prompt, temperature=0.2, format_json=True)
        model = await ollama_client.resolve_model()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Fit model call failed: {e}") from e
    data = agents._safe_json(out)
    if not isinstance(data, dict) or data.get("raw"):
        raise HTTPException(status_code=502, detail="Model did not return usable JSON.")

    def _status(v: Any) -> str:
        s = str(v or "").strip().lower()
        return s if s in ("meets", "partial", "gap") else "gap"

    try:
        overall = max(0, min(100, int(round(float(data.get("overall_fit") or 0)))))
    except (TypeError, ValueError):
        overall = 0
    payload = {
        "topic_id": topic_id,
        "cap_source": cap_source,
        "model": model,
        "cached_at": time.time(),
        "overall_fit": overall,
        "recommendation": str(data.get("recommendation") or "").upper()[:16],
        "summary": str(data.get("summary") or "")[:600],
        "requirements": [
            {
                "need": str(r.get("need") or "")[:300],
                "status": _status(r.get("status")),
                "evidence": str(r.get("evidence") or "")[:400],
                "matched_capability": str(r.get("matched_capability") or "")[:400],
            }
            for r in (data.get("requirements") or [])
            if isinstance(r, dict) and r.get("need")
        ][:12],
        "strengths": [str(s) for s in (data.get("strengths") or [])][:8],
        "gaps": [str(g) for g in (data.get("gaps") or [])][:8],
    }
    _write_json(topic_id, "fit.json", payload)
    return payload


# ---- routes ------------------------------------------------------------

@router.get("/{topic_id}/text")
async def topic_text(topic_id: str, force: bool = Query(False)):
    try:
        return await _ensure_text(topic_id, force=force)
    except HTTPException:
        raise
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"DSIP download failed: {e}") from e


@router.post("/{topic_id}/summary")
async def topic_summary(topic_id: str, force: bool = Query(False)):
    return await _ensure_summary(topic_id, force=force)


@router.post("/{topic_id}/fit")
async def topic_fit(topic_id: str, force: bool = Query(False)):
    return await _fit(topic_id, force=force)

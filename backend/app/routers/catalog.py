"""Cached open-window catalog: list status, fetch one topic's scout phrases."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from .. import catalog
from ..db import get_session
from ..identity import current_identity
from ..models import TopicIndex
from ..vault import get_vault

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


@router.get("/status")
def catalog_status(session: Session = Depends(get_session)):
    last = catalog.latest_pass(session)
    n = len(session.exec(select(TopicIndex)).all())
    enriched = len(session.exec(select(TopicIndex).where(TopicIndex.enriched == True)).all())  # noqa: E712
    payload = last and catalog.serialize_pass(last) or {}
    if "open_ids" in payload:
        payload.pop("open_ids")
    # Sanity check the vault side — /sbirs/{id}/tags.json is the on-disk gate.
    tag_files = 0
    try:
        v = get_vault()
        tag_files = sum(1 for k in v.list_prefix("sbirs/") if k.endswith("/tags.json"))
    except Exception:
        pass
    return {
        "topics_cached": n,
        "topics_enriched": enriched,
        "topics_tagged": tag_files,
        "enrich_running": catalog.enrich_running(),
        "last_pass": payload or None,
    }


@router.post("/refresh")
async def catalog_refresh(
    force: bool = False,
    session: Session = Depends(get_session),
):
    try:
        info = await catalog.refresh_catalog(session, force=force, enrich_limit=0)
        info["enrich_started"] = catalog.schedule_enrich_all()
        info["enrich_running"] = catalog.enrich_running()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Catalog refresh failed: {e}") from e
    info.pop("open_ids", None)
    return info


@router.post("/enrich/start")
async def enrich_start():
    """Nudge the background LLM enrich for every open SBIR — safe to poke after
    a backend restart (the in-process task dies with the container)."""
    started = catalog.schedule_enrich_all()
    return {"started": started, "running": catalog.enrich_running()}


@router.post("/signal/refresh")
async def refresh_signal():
    """Re-tag ME + company/products with the LLM extractor. Fallback tags land
    immediately; the LLM upgrade completes in the background loop."""
    ident = current_identity()
    if not ident:
        raise HTTPException(status_code=401, detail="Sign in first")
    catalog.refresh_company_tags_from_vault(ident.company_id)
    catalog.refresh_resume_tags_from_bundle(ident.user_id, ident.company_id)
    return {"ok": True}


@router.get("/signal")
def matching_signal():
    """What actually feeds this user's SBIR ranking — resume + company merge."""
    ident = current_identity()
    if not ident:
        return {"identity": None}
    v = get_vault()
    cid = ident.company_id
    uid = ident.user_id
    company_tags = v.read_json(v.company_tags_key(cid)) or {}
    resume_ptr = v.read_json(v.resume_tags_key(uid)) or {}
    resume_pack: dict = resume_ptr
    if resume_ptr.get("sha") and "phrases" not in resume_ptr:
        resume_pack = v.read_json(v.resume_tags_key(uid, str(resume_ptr["sha"]))) or {}
    mission = v.read_text(f"companies/{cid}/mission.txt").strip()
    products = v.read_text(f"companies/{cid}/products.md").strip()
    me = v.read_text(f"users/{uid}/me.md").strip()
    return {
        "identity": {"user_id": uid, "company_id": cid},
        "resume": {
            "chars": len(me),
            "phrases": list(resume_pack.get("phrases") or [])[:24],
            "source": resume_pack.get("source") or "",
            "updated_at": resume_pack.get("updated_at") or "",
        },
        "company": {
            "mission_chars": len(mission),
            "product_chars": len(products),
            "phrases": list(company_tags.get("phrases") or [])[:24],
            "source": company_tags.get("source") or "",
            "updated_at": company_tags.get("updated_at") or "",
        },
    }


@router.get("/topics/{topic_id}")
def catalog_topic(topic_id: str, session: Session = Depends(get_session)):
    row = session.get(TopicIndex, topic_id)
    if not row:
        raise HTTPException(status_code=404, detail="Topic not in catalog yet — run a scan or refresh.")
    return catalog.serialize_index(row)

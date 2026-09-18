"""Cached open-window catalog: list status, fetch one topic's scout phrases."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from .. import catalog
from ..db import get_session
from ..models import TopicIndex

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


@router.get("/status")
def catalog_status(session: Session = Depends(get_session)):
    last = catalog.latest_pass(session)
    n = len(session.exec(select(TopicIndex)).all())
    enriched = len(session.exec(select(TopicIndex).where(TopicIndex.enriched == True)).all())  # noqa: E712
    payload = last and catalog.serialize_pass(last) or {}
    if "open_ids" in payload:
        payload.pop("open_ids")
    return {
        "topics_cached": n,
        "topics_enriched": enriched,
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


@router.get("/topics/{topic_id}")
def catalog_topic(topic_id: str, session: Session = Depends(get_session)):
    row = session.get(TopicIndex, topic_id)
    if not row:
        raise HTTPException(status_code=404, detail="Topic not in catalog yet — run a scan or refresh.")
    return catalog.serialize_index(row)

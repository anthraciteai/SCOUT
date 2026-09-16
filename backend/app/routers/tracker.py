"""Track topics the user is watching / bidding and their pipeline status."""
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db import get_session
from ..models import PIPELINE_STAGES, TrackedTopic

router = APIRouter(prefix="/api/tracker", tags=["tracker"])


class TrackCreate(BaseModel):
    topic_id: str
    topic_code: Optional[str] = None
    title: Optional[str] = None
    component: Optional[str] = None
    program: Optional[str] = None
    topic_status: Optional[str] = None
    status: str = "watching"
    notes: str = ""
    raw: Optional[dict] = None


class TrackUpdate(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None
    outcome: Optional[str] = None


def _serialize(t: TrackedTopic) -> dict:
    return {
        "id": t.id,
        "topic_id": t.topic_id,
        "topic_code": t.topic_code,
        "title": t.title,
        "component": t.component,
        "program": t.program,
        "status": t.status,
        "topic_status": t.topic_status,
        "notes": t.notes,
        "outcome": t.outcome,
        "created_at": t.created_at.isoformat(),
        "updated_at": t.updated_at.isoformat(),
    }


@router.get("/stages")
def stages():
    return PIPELINE_STAGES


@router.get("")
def list_tracked(session: Session = Depends(get_session)):
    rows = session.exec(select(TrackedTopic).order_by(TrackedTopic.updated_at.desc())).all()
    return [_serialize(t) for t in rows]


@router.post("")
def track_topic(body: TrackCreate, session: Session = Depends(get_session)):
    existing = session.exec(
        select(TrackedTopic).where(TrackedTopic.topic_id == body.topic_id)
    ).first()
    if existing:
        return _serialize(existing)
    t = TrackedTopic(
        topic_id=body.topic_id,
        topic_code=body.topic_code,
        title=body.title,
        component=body.component,
        program=body.program,
        topic_status=body.topic_status,
        status=body.status,
        notes=body.notes,
        raw_json=json.dumps(body.raw) if body.raw else None,
    )
    session.add(t)
    session.commit()
    session.refresh(t)
    return _serialize(t)


@router.patch("/{tracked_id}")
def update_tracked(tracked_id: int, body: TrackUpdate, session: Session = Depends(get_session)):
    t = session.get(TrackedTopic, tracked_id)
    if not t:
        raise HTTPException(status_code=404, detail="Not found")
    if body.status is not None:
        t.status = body.status
    if body.notes is not None:
        t.notes = body.notes
    if body.outcome is not None:
        t.outcome = body.outcome
    t.updated_at = datetime.utcnow()
    session.add(t)
    session.commit()
    session.refresh(t)
    return _serialize(t)


@router.delete("/{tracked_id}")
def delete_tracked(tracked_id: int, session: Session = Depends(get_session)):
    t = session.get(TrackedTopic, tracked_id)
    if not t:
        raise HTTPException(status_code=404, detail="Not found")
    session.delete(t)
    session.commit()
    return {"ok": True}

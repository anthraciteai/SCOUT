"""Track topics the user is watching / bidding and their pipeline status."""
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db import get_session
from ..models import (
    PIPELINE_STAGES,
    AnalysisRun,
    Proposal,
    ProposalReview,
    TopicIndex,
    TrackedTopic,
)

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


@router.get("/gantt")
def gantt(session: Session = Depends(get_session)):
    """Timeline data for every tracked SBIR: pre-release / open / close windows
    plus persona-review + council-analysis checkpoint markers. The frontend
    renders this as one horizontal chart to answer 'what do I work on tomorrow?'."""
    tracked = session.exec(
        select(TrackedTopic).order_by(TrackedTopic.updated_at.desc())
    ).all()
    if not tracked:
        return {"rows": [], "now_ms": int(datetime.utcnow().timestamp() * 1000)}

    topic_ids = [t.topic_id for t in tracked]

    # 1) DSIP windows from the topic index.
    idx_rows = session.exec(
        select(TopicIndex).where(TopicIndex.topic_id.in_(topic_ids))  # type: ignore[attr-defined]
    ).all()
    idx_by_tid = {r.topic_id: r for r in idx_rows}

    # 2) Council verdicts (latest per topic).
    runs = session.exec(
        select(AnalysisRun)
        .where(AnalysisRun.topic_id.in_(topic_ids))  # type: ignore[attr-defined]
        .order_by(AnalysisRun.created_at.desc())
    ).all()
    latest_run: dict[str, AnalysisRun] = {}
    for r in runs:
        latest_run.setdefault(r.topic_id, r)

    # 3) Proposal reviews (grouped by topic → persona).
    props = session.exec(
        select(Proposal).where(Proposal.topic_id.in_(topic_ids))  # type: ignore[attr-defined]
    ).all()
    prop_ids = [p.id for p in props if p.id is not None]
    reviews_by_topic: dict[str, list[dict]] = {t: [] for t in topic_ids}
    if prop_ids:
        rev_rows = session.exec(
            select(ProposalReview)
            .where(ProposalReview.proposal_id.in_(prop_ids))  # type: ignore[attr-defined]
            .order_by(ProposalReview.created_at.desc())
        ).all()
        prop_topic = {p.id: p.topic_id for p in props if p.id is not None}
        for rv in rev_rows:
            tid = prop_topic.get(rv.proposal_id)
            if not tid:
                continue
            reviews_by_topic.setdefault(tid, []).append(
                {
                    "id": rv.id,
                    "persona": rv.persona,
                    "created_at": rv.created_at.isoformat() if rv.created_at else None,
                    "created_ms": int(rv.created_at.timestamp() * 1000) if rv.created_at else None,
                    "chars": rv.proposal_chars,
                }
            )

    now_ms = int(datetime.utcnow().timestamp() * 1000)
    out = []
    for t in tracked:
        idx = idx_by_tid.get(t.topic_id)
        raw_open = idx.open_ms if idx else None
        raw_close = idx.close_ms if idx else None
        raw_prerelease = idx.prerelease_ms if idx else None

        # Fallback to snapshot on the tracked row if the catalog doesn't know it
        if (not raw_open or not raw_close) and t.raw_json:
            try:
                raw = json.loads(t.raw_json)
                if not raw_open:
                    raw_open = _ts_from_field(raw, "topicStartDate")
                if not raw_close:
                    raw_close = _ts_from_field(raw, "topicEndDate")
                if not raw_prerelease:
                    raw_prerelease = _ts_from_field(raw, "topicPreReleaseStartDate")
            except json.JSONDecodeError:
                pass

        run = latest_run.get(t.topic_id)
        out.append(
            {
                "tracked_id": t.id,
                "topic_id": t.topic_id,
                "topic_code": t.topic_code,
                "title": t.title,
                "component": t.component,
                "program": t.program,
                "stage": t.status,
                "topic_status": t.topic_status,
                "outcome": t.outcome,
                "prerelease_ms": raw_prerelease,
                "open_ms": raw_open,
                "close_ms": raw_close,
                "verdict": {
                    "fit_score": run.fit_score if run else None,
                    "recommendation": run.recommendation if run else None,
                    "heavy_lift": run.heavy_lift if run else None,
                    "at_ms": int(run.created_at.timestamp() * 1000) if run else None,
                },
                "reviews": reviews_by_topic.get(t.topic_id, []),
            }
        )
    return {"rows": out, "now_ms": now_ms}


def _ts_from_field(raw: dict, key: str) -> Optional[int]:
    v = raw.get(key)
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return int(v)
    try:
        # DSIP uses ISO strings occasionally
        return int(datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp() * 1000)
    except Exception:
        return None


@router.delete("/{tracked_id}")
def delete_tracked(tracked_id: int, session: Session = Depends(get_session)):
    t = session.get(TrackedTopic, tracked_id)
    if not t:
        raise HTTPException(status_code=404, detail="Not found")
    session.delete(t)
    session.commit()
    return {"ok": True}

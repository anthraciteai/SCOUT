"""Run the agent council on selected topics."""
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from .. import agents, dsip
from ..db import get_session
from ..models import AnalysisRun, Resume

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


class RunRequest(BaseModel):
    topic_ids: list[str]
    resume_id: Optional[int] = None


def _active_resume_text(session: Session, resume_id: Optional[int]) -> tuple[Optional[int], str]:
    if resume_id is not None:
        r = session.get(Resume, resume_id)
        if r:
            return r.id, r.text
    r = session.exec(select(Resume).where(Resume.is_active == True)).first()  # noqa: E712
    if r:
        return r.id, r.text
    r = session.exec(select(Resume)).first()
    if r:
        return r.id, r.text
    return None, ""


@router.post("/run")
async def run_analysis(req: RunRequest, session: Session = Depends(get_session)):
    if not req.topic_ids:
        raise HTTPException(status_code=400, detail="No topic_ids provided")

    resume_id, resume_text = _active_resume_text(session, req.resume_id)
    runs = []

    for topic_id in req.topic_ids:
        try:
            topic = await dsip.get_topic(topic_id)
        except Exception:
            topic = {"topicId": topic_id}

        # DSIP detail sometimes nests the topic
        if isinstance(topic, dict) and "topic" in topic and isinstance(topic["topic"], dict):
            topic = {**topic, **topic["topic"]}

        result = await agents.analyze_topic(topic, resume_text)
        score, rec = agents.extract_score_and_rec(result.get("council", {}))

        run = AnalysisRun(
            topic_id=topic_id,
            topic_code=topic.get("topicCode") or topic.get("finalTopicCode"),
            title=topic.get("topicTitle") or topic.get("title"),
            model=result.get("model", ""),
            resume_id=resume_id,
            result_json=json.dumps(result),
            fit_score=score,
            recommendation=rec,
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        runs.append(_serialize(run))

    return {"runs": runs}


def _serialize(run: AnalysisRun) -> dict:
    return {
        "id": run.id,
        "topic_id": run.topic_id,
        "topic_code": run.topic_code,
        "title": run.title,
        "model": run.model,
        "fit_score": run.fit_score,
        "recommendation": run.recommendation,
        "created_at": run.created_at.isoformat(),
        "result": json.loads(run.result_json or "{}"),
    }


@router.get("")
def list_runs(session: Session = Depends(get_session)):
    runs = session.exec(select(AnalysisRun).order_by(AnalysisRun.created_at.desc())).all()
    # light list (no full result payload)
    return [
        {
            "id": r.id,
            "topic_id": r.topic_id,
            "topic_code": r.topic_code,
            "title": r.title,
            "model": r.model,
            "fit_score": r.fit_score,
            "recommendation": r.recommendation,
            "created_at": r.created_at.isoformat(),
        }
        for r in runs
    ]


@router.get("/topic/{topic_id}")
def latest_for_topic(topic_id: str, session: Session = Depends(get_session)):
    run = session.exec(
        select(AnalysisRun)
        .where(AnalysisRun.topic_id == topic_id)
        .order_by(AnalysisRun.created_at.desc())
    ).first()
    if not run:
        raise HTTPException(status_code=404, detail="No analysis for this topic")
    return _serialize(run)


@router.get("/{run_id}")
def get_run(run_id: int, session: Session = Depends(get_session)):
    run = session.get(AnalysisRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Not found")
    return _serialize(run)

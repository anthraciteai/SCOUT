"""Run the agent council on selected topics."""
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from .. import agents, dsip
from ..db import get_session
from ..models import AnalysisRun
from ..resume_service import get_resume_text

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


class RunRequest(BaseModel):
    topic_ids: list[str]
    resume_id: Optional[int] = None
    # Optional summary metadata keyed by topic_id: {topic_code, title, component,
    # program, topic_status, solicitation_title}. The details endpoint lacks these.
    topics_meta: Optional[dict[str, dict]] = None


_META_MAP = {
    "topic_code": "topicCode",
    "title": "topicTitle",
    "component": "component",
    "program": "program",
    "topic_status": "topicStatus",
    "solicitation_title": "solicitationTitle",
}


def _merge_meta(topic: dict, meta: Optional[dict]) -> dict:
    if not meta:
        return topic
    for src, dst in _META_MAP.items():
        val = meta.get(src)
        if val and not topic.get(dst):
            topic[dst] = val
    return topic


@router.post("/run")
async def run_analysis(req: RunRequest, session: Session = Depends(get_session)):
    if not req.topic_ids:
        raise HTTPException(status_code=400, detail="No topic_ids provided")

    resume_id, resume_text = get_resume_text(session, req.resume_id)
    runs = []

    for topic_id in req.topic_ids:
        try:
            topic = await dsip.get_topic(topic_id)
        except Exception:
            topic = {"topicId": topic_id}

        # DSIP detail sometimes nests the topic
        if isinstance(topic, dict) and "topic" in topic and isinstance(topic["topic"], dict):
            topic = {**topic, **topic["topic"]}

        topic = _merge_meta(topic, (req.topics_meta or {}).get(topic_id))

        result = await agents.analyze_topic(topic, resume_text)
        score, rec = agents.extract_score_and_rec(result.get("council", {}))
        heavy_lift = agents.extract_heavy_lift(result.get("agents", {}))

        run = AnalysisRun(
            topic_id=topic_id,
            topic_code=topic.get("topicCode") or topic.get("finalTopicCode"),
            title=topic.get("topicTitle") or topic.get("title"),
            model=result.get("model", ""),
            resume_id=resume_id,
            result_json=json.dumps(result),
            fit_score=score,
            heavy_lift=heavy_lift,
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
        "heavy_lift": run.heavy_lift,
        "recommendation": run.recommendation,
        "created_at": run.created_at.isoformat(),
        "result": json.loads(run.result_json or "{}"),
    }


class AgentRequest(BaseModel):
    topic_id: str
    agent: str
    resume_id: Optional[int] = None
    topics_meta: Optional[dict[str, dict]] = None
    # JSON of already-run agents, used as peer context (e.g. for Davy/Hewer).
    context: Optional[str] = None


@router.post("/agent")
async def run_agent(req: AgentRequest, session: Session = Depends(get_session)):
    if req.agent not in agents.AGENTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown agent '{req.agent}'. Options: {list(agents.AGENTS)}",
        )
    _, resume_text = get_resume_text(session, req.resume_id)

    try:
        topic = await dsip.get_topic(req.topic_id)
    except Exception:
        topic = {"topicId": req.topic_id}
    if isinstance(topic, dict) and "topic" in topic and isinstance(topic["topic"], dict):
        topic = {**topic, **topic["topic"]}
    topic = _merge_meta(topic, (req.topics_meta or {}).get(req.topic_id))

    topic_text = agents.summarize_topic(topic)
    extra = f"\n\nPEER ASSESSMENTS:\n{req.context}" if req.context else ""
    result = await agents.run_single_agent(req.agent, topic_text, resume_text, extra=extra)
    model = await agents.ollama_client.resolve_model()
    return {"agent": req.agent, "result": result, "model": model}


@router.get("/agents")
def list_agent_names():
    return [{"name": n, "role": s["role"]} for n, s in agents.AGENTS.items()]


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
            "heavy_lift": r.heavy_lift,
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

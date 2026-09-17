"""Run the agent council on selected topics."""
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from .. import agents, dsip
from ..db import get_session
from ..identity import current_identity
from ..models import AnalysisRun
from ..resume_service import get_resume_text
from ..vault import get_vault

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


class RunRequest(BaseModel):
    topic_ids: list[str]
    resume_id: Optional[int] = None
    force: bool = False
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

        ident = current_identity()
        vault = get_vault()
        if ident:
            vault.grant_sbir(
                ident,
                topic_id,
                {
                    "topic_id": topic_id,
                    "title": topic.get("topicTitle") or topic.get("title"),
                    "topic_code": topic.get("topicCode") or topic.get("finalTopicCode"),
                },
            )
            if not req.force:
                cached = vault.cache_get(vault.user_path(topic_id, ident, "council.json"))
                if not cached:
                    cached = vault.cache_get(vault.shared_path(topic_id, ident, "council.json"))
                if cached and cached.get("result"):
                    runs.append(_from_cache(topic_id, topic, cached))
                    continue

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
        payload = _serialize(run)
        if ident:
            body = vault.cache_put(
                vault.user_path(topic_id, ident, "council.json"),
                {"result": result, "fit_score": score, "recommendation": rec, "heavy_lift": heavy_lift},
                result.get("model", ""),
                "council",
            )
            # First org council also becomes the federated copy if none exists yet.
            if not vault.exists(vault.shared_path(topic_id, ident, "council.json")):
                vault.cache_put(
                    vault.shared_path(topic_id, ident, "council.json"),
                    {"result": result, "fit_score": score, "recommendation": rec, "heavy_lift": heavy_lift, "author": ident.user_id},
                    result.get("model", ""),
                    "council",
                )
            payload["cached_at"] = body.get("cached_at")
            payload["cached"] = False
        runs.append(payload)

    return {"runs": runs}


def _from_cache(topic_id: str, topic: dict, cached: dict) -> dict:
    result = cached.get("result") or {}
    council = result.get("council") or {}
    return {
        "id": 0,
        "topic_id": topic_id,
        "topic_code": topic.get("topicCode") or topic.get("finalTopicCode") or cached.get("topic_code"),
        "title": topic.get("topicTitle") or topic.get("title"),
        "model": cached.get("model") or result.get("model") or "",
        "fit_score": cached.get("fit_score") or council.get("fit_score"),
        "heavy_lift": cached.get("heavy_lift"),
        "recommendation": cached.get("recommendation") or council.get("recommendation"),
        "created_at": cached.get("cached_at") or "",
        "cached": True,
        "cached_at": cached.get("cached_at"),
        "result": result,
    }


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
        "cached": False,
        "result": json.loads(run.result_json or "{}"),
    }


class AgentRequest(BaseModel):
    topic_id: str
    agent: str
    resume_id: Optional[int] = None
    force: bool = False
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

    ident = current_identity()
    vault = get_vault()
    cache_name = "flint.json" if req.agent == "Flint" else f"{req.agent.lower()}.json"
    if ident:
        vault.grant_sbir(
            ident,
            req.topic_id,
            {
                "topic_id": req.topic_id,
                "title": topic.get("topicTitle") or topic.get("title"),
                "topic_code": topic.get("topicCode") or topic.get("finalTopicCode"),
            },
        )
        if not req.force:
            cached = vault.cache_get(vault.user_path(req.topic_id, ident, cache_name))
            if cached and cached.get("result"):
                return {
                    "agent": req.agent,
                    "result": cached["result"],
                    "model": cached.get("model") or "",
                    "cached": True,
                    "cached_at": cached.get("cached_at"),
                }

    topic_text = agents.summarize_topic(topic)
    extra = f"\n\nPEER ASSESSMENTS:\n{req.context}" if req.context else ""
    result = await agents.run_single_agent(req.agent, topic_text, resume_text, extra=extra)
    model = await agents.ollama_client.resolve_model()
    if ident:
        vault.cache_put(
            vault.user_path(req.topic_id, ident, cache_name),
            {"result": result},
            model,
            req.agent.lower(),
        )
    return {"agent": req.agent, "result": result, "model": model, "cached": False}


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
    ident = current_identity()
    if ident:
        vault = get_vault()
        cached = vault.cache_get(vault.user_path(topic_id, ident, "council.json"))
        if not cached:
            cached = vault.cache_get(vault.shared_path(topic_id, ident, "council.json"))
        if cached and cached.get("result"):
            meta = vault.read_json(vault.shared_path(topic_id, ident, "topic.json")) or {}
            topic = {
                "topicId": topic_id,
                "topicCode": meta.get("topic_code") or meta.get("topicCode"),
                "topicTitle": meta.get("title") or meta.get("topicTitle"),
            }
            return _from_cache(topic_id, topic, cached)
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

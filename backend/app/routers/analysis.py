"""Run the agent council on selected topics."""
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from .. import agents, collab, dsip, jobs
from ..db import get_session
from ..identity import Identity, current_identity, get_identity
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
        blob_sha = None
        cached_at = None
        if ident:
            _seed_chats(vault, ident, topic_id, result.get("agents") or {})
            body = vault.cache_put(
                vault.user_path(topic_id, ident, "council.json"),
                {"result": result, "fit_score": score, "recommendation": rec, "heavy_lift": heavy_lift},
                result.get("model", ""),
                "council",
            )
            blob_sha = body.get("sha")
            cached_at = body.get("cached_at")
            if not vault.exists(vault.shared_path(topic_id, ident, "council.json")):
                vault.cache_put(
                    vault.shared_path(topic_id, ident, "council.json"),
                    {
                        "result": result,
                        "fit_score": score,
                        "recommendation": rec,
                        "heavy_lift": heavy_lift,
                        "author": ident.user_id,
                    },
                    result.get("model", ""),
                    "council",
                )
            collab.publish_card(vault, topic_id, ident)
        run = AnalysisRun(
            topic_id=topic_id,
            topic_code=topic.get("topicCode") or topic.get("finalTopicCode"),
            title=topic.get("topicTitle") or topic.get("title"),
            model=result.get("model", ""),
            resume_id=resume_id,
            result_json=json.dumps({"sha": blob_sha} if blob_sha else result),
            fit_score=score,
            heavy_lift=heavy_lift,
            recommendation=rec,
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        payload = _serialize(run)
        if ident:
            payload["cached_at"] = cached_at
            payload["cached"] = False
            payload["sha"] = blob_sha
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


def _result_from_store(raw: str) -> dict:
    try:
        obj = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    if not isinstance(obj, dict):
        return {}
    if obj.get("sha") and "agents" not in obj and "council" not in obj:
        blob = get_vault().get_blob(str(obj["sha"])) or {}
        if isinstance(blob, dict) and isinstance(blob.get("result"), dict):
            return blob["result"]
        return blob if isinstance(blob, dict) else {}
    return obj


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
        "result": _result_from_store(run.result_json or "{}"),
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
    agent_name = agents.canonical_agent(req.agent)
    cache_name = "flint.json" if agent_name == "Flint" else f"{agent_name.lower()}.json"
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
            if not cached and agent_name == "Vein":
                cached = vault.cache_get(vault.user_path(req.topic_id, ident, "vien.json"))
            if cached and cached.get("result"):
                _seed_chat(vault, ident, req.topic_id, agent_name, cached["result"], cached.get("model") or "")
                return {
                    "agent": agent_name,
                    "result": cached["result"],
                    "model": cached.get("model") or "",
                    "cached": True,
                    "cached_at": cached.get("cached_at"),
                }

    topic_text = agents.summarize_topic(topic)
    extra = ""
    if req.context and agent_name not in agents.PRODUCT_LENS:
        extra = f"\n\nPEER ASSESSMENTS:\n{req.context}"
    result = await agents.run_single_agent(agent_name, topic_text, resume_text, extra=extra)
    model = await agents.ollama_client.resolve_model()
    if ident:
        vault.cache_put(
            vault.user_path(req.topic_id, ident, cache_name),
            {"result": result},
            model,
            agent_name.lower(),
        )
        _seed_chat(vault, ident, req.topic_id, agent_name, result, model)
        collab.publish_card(vault, req.topic_id, ident)
    return {"agent": agent_name, "result": result, "model": model, "cached": False}


class ChatRequest(BaseModel):
    topic_id: str
    agent: str
    message: str
    proposal_text: Optional[str] = None
    resume_id: Optional[int] = None
    topics_meta: Optional[dict[str, dict]] = None


def _seed_chat(vault, ident: Identity, topic_id: str, agent: str, result: dict, model: str = "") -> None:
    log = vault.read_chat(topic_id, ident, agent)
    if log.get("messages"):
        return
    opening = agents.opening_message(agent, result or {})
    if not opening:
        return
    log["model"] = model
    log["messages"] = [
        {
            "role": "assistant",
            "speaker": agent,
            "text": opening,
            "kind": "opening",
            "at": datetime.utcnow().isoformat() + "Z",
        }
    ]
    vault.write_chat(topic_id, ident, agent, log)


def _seed_chats(vault, ident: Identity, topic_id: str, agent_results: dict) -> None:
    for name, result in (agent_results or {}).items():
        if isinstance(result, dict):
            _seed_chat(vault, ident, topic_id, name, result)


def _proposal_context(vault, ident: Identity, topic_id: str, live_text: Optional[str] = None) -> str:
    parts: list[str] = []
    live = (live_text or "").strip()
    if live:
        parts.append("CURRENT EDITOR DRAFT (unsaved ok):\n" + live[:6000])
    shared = vault.read_text(vault.shared_path(topic_id, ident, "proposal.md")).strip()
    if shared and shared != live:
        parts.append("SHARED ORG PROPOSAL:\n" + shared[:4000])
    mine = vault.read_text(vault.user_path(topic_id, ident, "draft.md")).strip()
    if mine and mine != live and mine != shared:
        parts.append("PRIVATE DRAFT:\n" + mine[:3000])
    return "\n\n".join(parts)


@router.get("/chat/{topic_id}/{agent}")
def get_chat(topic_id: str, agent: str, ident: Identity = Depends(get_identity)):
    if agent not in agents.AGENTS:
        raise HTTPException(status_code=400, detail=f"Unknown agent '{agent}'")
    vault = get_vault()
    log = vault.read_chat(topic_id, ident, agent)
    if not log.get("messages"):
        cache_name = "flint.json" if agent == "Flint" else f"{agent.lower()}.json"
        cached = vault.cache_get(vault.user_path(topic_id, ident, cache_name))
        if cached and cached.get("result"):
            _seed_chat(vault, ident, topic_id, agent, cached["result"], cached.get("model") or "")
            log = vault.read_chat(topic_id, ident, agent)
    return {
        "agent": agent,
        "role": agents.AGENTS[agent]["role"],
        "path": vault.chat_path(topic_id, ident, agent),
        "messages": log.get("messages") or [],
        "model": log.get("model") or "",
        "updated_at": log.get("updated_at"),
    }


@router.get("/chat/{topic_id}")
def list_chats(topic_id: str, ident: Identity = Depends(get_identity)):
    vault = get_vault()
    counts = vault.list_chats(topic_id, ident)
    chats = {}
    for name in agents.AGENTS:
        log = vault.read_chat(topic_id, ident, name)
        chats[name] = {
            "agent": name,
            "role": agents.AGENTS[name]["role"],
            "messages": log.get("messages") or [],
            "count": counts.get(name.lower(), len(log.get("messages") or [])),
            "updated_at": log.get("updated_at"),
        }
    return {"topic_id": topic_id, "chats": chats}


@router.post("/chat")
async def post_chat(req: ChatRequest, session: Session = Depends(get_session)):
    if req.agent not in agents.AGENTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown agent '{req.agent}'. Options: {list(agents.AGENTS)}",
        )
    text = (req.message or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="message is empty")
    ident = current_identity()
    if not ident:
        raise HTTPException(status_code=401, detail="Sign in to record the chat")

    agent_name = agents.canonical_agent(req.agent)
    vault = get_vault()
    vault.grant_sbir(ident, req.topic_id, {"topic_id": req.topic_id})

    try:
        topic = await dsip.get_topic(req.topic_id)
    except Exception:
        topic = {"topicId": req.topic_id}
    if isinstance(topic, dict) and "topic" in topic and isinstance(topic["topic"], dict):
        topic = {**topic, **topic["topic"]}
    topic = _merge_meta(topic, (req.topics_meta or {}).get(req.topic_id))

    _, resume_text = get_resume_text(session, req.resume_id)
    extra = _proposal_context(vault, ident, req.topic_id, req.proposal_text)
    cache_name = "flint.json" if agent_name == "Flint" else f"{agent_name.lower()}.json"
    cached = vault.cache_get(vault.user_path(req.topic_id, ident, cache_name))
    if not cached and agent_name == "Vein":
        cached = vault.cache_get(vault.user_path(req.topic_id, ident, "vien.json"))
    prior = (cached or {}).get("result") if cached else None
    if prior:
        extra = (
            (extra + "\n\n" if extra else "")
            + f"YOUR EARLIER STRUCTURED TAKE:\n{json.dumps(prior)[:2500]}"
        )

    log = vault.read_chat(req.topic_id, ident, agent_name)
    if not log.get("messages") and prior:
        _seed_chat(vault, ident, req.topic_id, agent_name, prior)
        log = vault.read_chat(req.topic_id, ident, agent_name)

    now = datetime.utcnow().isoformat() + "Z"
    history = list(log.get("messages") or [])
    user_row = {
        "role": "user",
        "speaker": ident.user_id,
        "text": text,
        "at": now,
    }
    reply = await agents.chat_with_agent(
        agent_name,
        agents.summarize_topic(topic),
        resume_text,
        history,
        text,
        extra=extra,
    )
    model = await agents.ollama_client.resolve_model()
    assistant_row = {
        "role": "assistant",
        "speaker": agent_name,
        "text": reply.strip(),
        "at": datetime.utcnow().isoformat() + "Z",
    }
    log["model"] = model
    log["messages"] = history + [user_row, assistant_row]
    saved = vault.write_chat(req.topic_id, ident, agent_name, log)
    return {
        "agent": agent_name,
        "role": agents.AGENTS[agent_name]["role"],
        "path": vault.chat_path(req.topic_id, ident, agent_name),
        "messages": saved["messages"],
        "model": model,
        "updated_at": saved.get("updated_at"),
    }


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


class BriefRequest(BaseModel):
    topic_id: str
    resume_id: Optional[int] = None
    force: bool = False
    topics_meta: Optional[dict[str, dict]] = None


def _brief_owner(ident: Optional[Identity]) -> str:
    cid = (ident.company_id if ident else None) or "shared"
    uid = (ident.user_id if ident else None) or "shared"
    return f"{cid}:{uid}"


def _brief_cached(topic_id: str, ident: Optional[Identity]) -> Optional[dict]:
    if not ident:
        return None
    vault = get_vault()
    cached = vault.cache_get(vault.user_path(topic_id, ident, "brief.json"))
    if cached and cached.get("result"):
        out = dict(cached["result"])
        out["cached"] = True
        out["cached_at"] = cached.get("cached_at")
        return out
    return None


@router.post("/brief")
async def run_brief(req: BriefRequest, session: Session = Depends(get_session)):
    """One-shot bid brief: which product to bid, why, the work, and TRL.

    Runs the product voices + Hewer + a chair synthesis as a single tracked job
    (deduped + reconnectable progress, survives leaving the page), and caches the
    brief per user in the vault."""
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
            cached = _brief_cached(req.topic_id, ident)
            if cached:
                return cached

    async def work():
        result = await agents.bid_brief(topic, resume_text)
        if ident:
            vault.cache_put(
                vault.user_path(req.topic_id, ident, "brief.json"),
                {"result": result},
                result.get("model", ""),
                "brief",
            )
        return result

    job = jobs.start("brief", req.topic_id, _brief_owner(ident), work, identity=ident)
    await job.task
    if job.state == "error":
        raise HTTPException(status_code=502, detail=job.error or "Bid brief failed")
    out = dict(job.result or {})
    out["cached"] = False
    return out


@router.get("/brief/{topic_id}/status")
async def brief_status(topic_id: str):
    """Progress of the caller's in-flight (or just-finished) bid brief."""
    ident = current_identity()
    job = jobs.get("brief", topic_id, _brief_owner(ident))
    if job is not None:
        out = job.public()
        out["result"] = job.result if job.state == "done" else None
        return out
    cached = _brief_cached(topic_id, ident)
    if cached:
        return {"state": "done", "stage": "done", "pct": 100, "result": cached}
    return {"state": "idle", "stage": "idle", "pct": 0, "result": None}


@router.get("/brief/{topic_id}")
async def brief_cached(topic_id: str):
    """The caller's cached bid brief (no model call); null if not run yet."""
    return _brief_cached(topic_id, current_identity())


@router.get("/{run_id}")
def get_run(run_id: int, session: Session = Depends(get_session)):
    run = session.get(AnalysisRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Not found")
    return _serialize(run)

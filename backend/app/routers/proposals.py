"""Proposal drafts + live LLM writing feedback (streaming)."""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from .. import dsip, ollama_client
from ..agents import summarize_topic
from ..db import get_session
from ..models import Debrief, Proposal

router = APIRouter(prefix="/api/proposals", tags=["proposals"])


REVIEWER_SYSTEM = (
    "You are a senior DoD SBIR/STTR proposal reviewer and coach. You give sharp, specific, "
    "actionable feedback that improves win probability. You evaluate against typical evaluation "
    "criteria: (1) the scientific/technical merit and feasibility, (2) the qualifications of the "
    "team, (3) the commercialization/transition potential, and (4) responsiveness to the topic. "
    "You point out unsupported claims, vague language, missing requirements from the topic, and "
    "weak win themes. Be concrete: quote the applicant's text and suggest concrete rewrites. "
    "Organize feedback under clear headings and end with a prioritized action list."
)


class ProposalCreate(BaseModel):
    title: str = "Untitled Proposal"
    content: str = ""
    topic_id: Optional[str] = None
    topic_code: Optional[str] = None
    status: str = "draft"


class ProposalUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    status: Optional[str] = None
    topic_id: Optional[str] = None
    topic_code: Optional[str] = None


class LiveFeedbackRequest(BaseModel):
    content: str
    topic_id: Optional[str] = None
    focus: Optional[str] = None  # e.g. "technical approach", "commercialization"


def _serialize(p: Proposal) -> dict:
    return {
        "id": p.id,
        "title": p.title,
        "content": p.content,
        "topic_id": p.topic_id,
        "topic_code": p.topic_code,
        "status": p.status,
        "created_at": p.created_at.isoformat(),
        "updated_at": p.updated_at.isoformat(),
    }


@router.get("")
def list_proposals(session: Session = Depends(get_session)):
    rows = session.exec(select(Proposal).order_by(Proposal.updated_at.desc())).all()
    return [_serialize(p) for p in rows]


@router.post("")
def create_proposal(body: ProposalCreate, session: Session = Depends(get_session)):
    p = Proposal(**body.model_dump())
    session.add(p)
    session.commit()
    session.refresh(p)
    return _serialize(p)


@router.get("/{pid}")
def get_proposal(pid: int, session: Session = Depends(get_session)):
    p = session.get(Proposal, pid)
    if not p:
        raise HTTPException(status_code=404, detail="Not found")
    return _serialize(p)


@router.put("/{pid}")
def update_proposal(pid: int, body: ProposalUpdate, session: Session = Depends(get_session)):
    p = session.get(Proposal, pid)
    if not p:
        raise HTTPException(status_code=404, detail="Not found")
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(p, k, v)
    p.updated_at = datetime.utcnow()
    session.add(p)
    session.commit()
    session.refresh(p)
    return _serialize(p)


@router.delete("/{pid}")
def delete_proposal(pid: int, session: Session = Depends(get_session)):
    p = session.get(Proposal, pid)
    if not p:
        raise HTTPException(status_code=404, detail="Not found")
    session.delete(p)
    session.commit()
    return {"ok": True}


async def _build_topic_context(topic_id: Optional[str]) -> str:
    if not topic_id:
        return ""
    try:
        topic = await dsip.get_topic(topic_id)
        if isinstance(topic, dict) and "topic" in topic and isinstance(topic["topic"], dict):
            topic = {**topic, **topic["topic"]}
        return "\n\nTARGET TOPIC:\n" + summarize_topic(topic)
    except Exception:
        return ""


def _stream(system: str, prompt: str) -> StreamingResponse:
    async def gen():
        async for chunk in ollama_client.chat_stream(system, prompt, temperature=0.4):
            yield chunk

    return StreamingResponse(gen(), media_type="text/plain; charset=utf-8")


@router.post("/feedback-live")
async def feedback_live(body: LiveFeedbackRequest):
    """Feedback while writing - not tied to a saved proposal. Streams text."""
    topic_ctx = await _build_topic_context(body.topic_id)
    focus = f"\nFOCUS the feedback on: {body.focus}\n" if body.focus else ""
    prompt = (
        f"{topic_ctx}{focus}\n\nDRAFT PROPOSAL TEXT (may be partial):\n"
        f"{body.content[:12000]}\n\n"
        "Give focused, actionable feedback to improve this draft now."
    )
    return _stream(REVIEWER_SYSTEM, prompt)


@router.post("/{pid}/feedback")
async def feedback_saved(pid: int, session: Session = Depends(get_session)):
    """Full review of a saved proposal, including any related debrief lessons. Streams text."""
    p = session.get(Proposal, pid)
    if not p:
        raise HTTPException(status_code=404, detail="Not found")

    topic_ctx = await _build_topic_context(p.topic_id)

    debrief_ctx = ""
    if p.topic_id:
        debriefs = session.exec(
            select(Debrief).where(Debrief.topic_id == p.topic_id)
        ).all()
        if debriefs:
            joined = "\n---\n".join(d.extracted_text[:3000] for d in debriefs)
            debrief_ctx = (
                "\n\nPRIOR GOVERNMENT FEEDBACK / DEBRIEF (learn from these weaknesses):\n"
                f"{joined[:6000]}"
            )

    prompt = (
        f"{topic_ctx}{debrief_ctx}\n\nPROPOSAL: {p.title}\n\n"
        f"{p.content[:12000]}\n\n"
        "Provide a thorough review with prioritized, concrete improvements."
    )
    return _stream(REVIEWER_SYSTEM, prompt)

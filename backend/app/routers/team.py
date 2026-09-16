"""Collier - 'who you should add' teaming/staffing recommendations."""
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session

from .. import agents, dsip
from ..db import get_session
from ..resume_service import get_resume_text

router = APIRouter(prefix="/api/team", tags=["team"])


class TeamRequest(BaseModel):
    topic_id: Optional[str] = None
    resume_id: Optional[int] = None
    proposal_content: Optional[str] = None


@router.post("/recommend")
async def recommend(req: TeamRequest, session: Session = Depends(get_session)):
    _, resume_text = get_resume_text(session, req.resume_id)

    topic: Optional[dict] = None
    if req.topic_id:
        try:
            topic = await dsip.get_topic(req.topic_id)
            if isinstance(topic, dict) and "topic" in topic and isinstance(topic["topic"], dict):
                topic = {**topic, **topic["topic"]}
        except Exception:
            topic = {"topicId": req.topic_id}

    result = await agents.recommend_team(topic, resume_text, req.proposal_content or "")
    model = await agents.ollama_client.resolve_model()
    return {"recommendation": result, "model": model, "topic_id": req.topic_id}

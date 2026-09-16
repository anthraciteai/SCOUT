"""Upload government debriefs/feedback, OCR-extract text, and learn from them."""
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlmodel import Session, select

from .. import docling_service, ollama_client
from ..db import get_session
from ..models import Debrief

router = APIRouter(prefix="/api/debriefs", tags=["debriefs"])


DEBRIEF_SYSTEM = (
    "You are a proposal post-mortem analyst. Given the government's evaluation/debrief feedback for "
    "a SBIR/STTR proposal that was not selected, extract the specific weaknesses, deficiencies, and "
    "evaluator concerns, and translate each into a concrete, reusable lesson to strengthen future "
    "proposals. Return clear sections: 'Weaknesses noted', 'Root causes', and 'Fixes for next time'."
)


def _serialize(d: Debrief) -> dict:
    return {
        "id": d.id,
        "topic_id": d.topic_id,
        "proposal_id": d.proposal_id,
        "title": d.title,
        "filename": d.filename,
        "extracted_text": d.extracted_text,
        "analysis": d.analysis,
        "created_at": d.created_at.isoformat(),
    }


@router.get("")
def list_debriefs(session: Session = Depends(get_session)):
    rows = session.exec(select(Debrief).order_by(Debrief.created_at.desc())).all()
    return [_serialize(d) for d in rows]


@router.post("")
async def upload_debrief(
    file: UploadFile = File(...),
    title: str = Form("Debrief"),
    topic_id: Optional[str] = Form(None),
    proposal_id: Optional[int] = Form(None),
    session: Session = Depends(get_session),
):
    data = await file.read()
    text = docling_service.extract_text(file.filename or "upload", data)
    d = Debrief(
        title=title,
        topic_id=topic_id,
        proposal_id=proposal_id,
        filename=file.filename,
        extracted_text=text,
    )
    session.add(d)
    session.commit()
    session.refresh(d)
    return _serialize(d)


@router.post("/{did}/analyze")
async def analyze_debrief(did: int, session: Session = Depends(get_session)):
    d = session.get(Debrief, did)
    if not d:
        raise HTTPException(status_code=404, detail="Not found")
    if not d.extracted_text.strip():
        raise HTTPException(status_code=400, detail="No extracted text to analyze")
    analysis = await ollama_client.chat(
        DEBRIEF_SYSTEM,
        f"DEBRIEF / FEEDBACK TEXT:\n{d.extracted_text[:12000]}",
        temperature=0.3,
    )
    d.analysis = analysis
    session.add(d)
    session.commit()
    session.refresh(d)
    return _serialize(d)


@router.delete("/{did}")
def delete_debrief(did: int, session: Session = Depends(get_session)):
    d = session.get(Debrief, did)
    if not d:
        raise HTTPException(status_code=404, detail="Not found")
    session.delete(d)
    session.commit()
    return {"ok": True}

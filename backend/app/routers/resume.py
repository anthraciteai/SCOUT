"""Manage the applicant's resume / capabilities used by the agents."""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlmodel import Session, select

from .. import docling_service
from ..db import get_session
from ..models import Resume

router = APIRouter(prefix="/api/resume", tags=["resume"])


class ResumeText(BaseModel):
    name: str = "My Resume"
    text: str


class ResumeUpdate(BaseModel):
    name: Optional[str] = None
    text: Optional[str] = None
    is_active: Optional[bool] = None


def _serialize(r: Resume, include_text: bool = True) -> dict:
    d = {
        "id": r.id,
        "name": r.name,
        "filename": r.filename,
        "is_active": r.is_active,
        "created_at": r.created_at.isoformat(),
        "updated_at": r.updated_at.isoformat(),
        "chars": len(r.text or ""),
    }
    if include_text:
        d["text"] = r.text
    return d


def _deactivate_all(session: Session) -> None:
    for r in session.exec(select(Resume)).all():
        if r.is_active:
            r.is_active = False
            session.add(r)


@router.get("")
def list_resumes(session: Session = Depends(get_session)):
    rows = session.exec(select(Resume).order_by(Resume.created_at.desc())).all()
    return [_serialize(r, include_text=False) for r in rows]


@router.get("/active")
def active_resume(session: Session = Depends(get_session)):
    r = session.exec(select(Resume).where(Resume.is_active == True)).first()  # noqa: E712
    if not r:
        r = session.exec(select(Resume)).first()
    if not r:
        return None
    return _serialize(r)


@router.get("/{rid}")
def get_resume(rid: int, session: Session = Depends(get_session)):
    r = session.get(Resume, rid)
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    return _serialize(r)


@router.post("/text")
def create_from_text(body: ResumeText, session: Session = Depends(get_session)):
    _deactivate_all(session)
    r = Resume(name=body.name, text=body.text, is_active=True)
    session.add(r)
    session.commit()
    session.refresh(r)
    return _serialize(r)


@router.post("/upload")
async def upload_resume(
    file: UploadFile = File(...),
    name: Optional[str] = Form(None),
    session: Session = Depends(get_session),
):
    data = await file.read()
    text = docling_service.extract_text(file.filename or "resume", data)
    _deactivate_all(session)
    r = Resume(
        name=name or (file.filename or "My Resume"),
        filename=file.filename,
        text=text,
        is_active=True,
    )
    session.add(r)
    session.commit()
    session.refresh(r)
    return _serialize(r)


@router.put("/{rid}")
def update_resume(rid: int, body: ResumeUpdate, session: Session = Depends(get_session)):
    r = session.get(Resume, rid)
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    if body.is_active:
        _deactivate_all(session)
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(r, k, v)
    r.updated_at = datetime.utcnow()
    session.add(r)
    session.commit()
    session.refresh(r)
    return _serialize(r)


@router.delete("/{rid}")
def delete_resume(rid: int, session: Session = Depends(get_session)):
    r = session.get(Resume, rid)
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    session.delete(r)
    session.commit()
    return {"ok": True}

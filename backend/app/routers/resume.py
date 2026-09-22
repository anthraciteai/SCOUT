"""Manage the applicant's resume / capabilities used by the matcher and agents."""
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlmodel import Session, select

from .. import docling_service
from ..db import get_session
from ..identity import current_identity
from ..matcher import ensure_profile
from ..models import Resume
from ..vault import get_vault

router = APIRouter(prefix="/api/resume", tags=["resume"])


class ResumeText(BaseModel):
    name: str = "My Resume"
    text: str
    kind: str = "company"  # me | company


class ResumeUpdate(BaseModel):
    name: Optional[str] = None
    text: Optional[str] = None
    is_active: Optional[bool] = None
    kind: Optional[str] = None


def _serialize(r: Resume, include_text: bool = True) -> dict:
    extract = None
    if r.extract_json:
        try:
            extract = json.loads(r.extract_json)
        except json.JSONDecodeError:
            extract = None
    d = {
        "id": r.id,
        "name": r.name,
        "filename": r.filename,
        "is_active": r.is_active,
        "kind": r.kind or "company",
        "created_at": r.created_at.isoformat(),
        "updated_at": r.updated_at.isoformat(),
        "extracted_at": r.extracted_at.isoformat() if r.extracted_at else None,
        "extract": extract,
        "chars": len(r.text or ""),
    }
    if include_text:
        d["text"] = r.text
    return d


def _deactivate_kind(session: Session, kind: str) -> None:
    for r in session.exec(select(Resume).where(Resume.kind == kind)).all():
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


@router.get("/me")
def me_resume(session: Session = Depends(get_session)):
    from ..resume_service import get_me

    ident = current_identity()
    r = get_me(session)
    if ident:
        text = get_vault().read_text(f"users/{ident.user_id}/me.md").strip()
        if text:
            name = (
                get_vault().read_text(f"users/{ident.user_id}/display_name.txt").strip()
                or ident.display_name
                or "ME"
            )
            if r:
                d = _serialize(r)
                d["text"] = text
                d["chars"] = len(text)
                d["kind"] = "me"
                d["name"] = name
                return d
            return {
                "id": 0,
                "name": name,
                "filename": None,
                "is_active": True,
                "kind": "me",
                "created_at": "",
                "updated_at": "",
                "extracted_at": None,
                "extract": None,
                "chars": len(text),
                "text": text,
            }
    if not r:
        return None
    return _serialize(r)


@router.post("/extract")
async def extract_active(
    resume_id: Optional[int] = None,
    force: bool = True,
    session: Session = Depends(get_session),
):
    """Run (or refresh) the cheap profile extract used by the matcher."""
    r: Optional[Resume] = None
    if resume_id is not None:
        r = session.get(Resume, resume_id)
    if r is None:
        r = session.exec(select(Resume).where(Resume.is_active == True)).first()  # noqa: E712
    if r is None:
        r = session.exec(select(Resume)).first()
    if r is None:
        raise HTTPException(status_code=400, detail="No resume on file")
    if not (r.text or "").strip():
        raise HTTPException(status_code=400, detail="Active resume is empty")
    await ensure_profile(session, r, force=force)
    return _serialize(r)


@router.get("/{rid}")
def get_resume(rid: int, session: Session = Depends(get_session)):
    r = session.get(Resume, rid)
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    return _serialize(r)


@router.post("/text")
def create_from_text(body: ResumeText, session: Session = Depends(get_session)):
    kind = body.kind if body.kind in ("me", "company") else "company"
    _deactivate_kind(session, kind)
    r = Resume(name=body.name, text=body.text, is_active=True, kind=kind)
    session.add(r)
    session.commit()
    session.refresh(r)
    _sync_vault(kind, body.name, body.text)
    return _serialize(r)


@router.post("/upload")
async def upload_resume(
    file: UploadFile = File(...),
    name: Optional[str] = Form(None),
    kind: str = Form("company"),
    session: Session = Depends(get_session),
):
    data = await file.read()
    text = docling_service.extract_text(file.filename or "resume", data)
    kind = kind if kind in ("me", "company") else "company"
    _deactivate_kind(session, kind)
    r = Resume(
        name=name or (file.filename or ("ME" if kind == "me" else "My Resume")),
        filename=file.filename,
        text=text,
        is_active=True,
        kind=kind,
    )
    session.add(r)
    session.commit()
    session.refresh(r)
    _sync_vault(kind, r.name, text)
    return _serialize(r)


@router.put("/{rid}")
def update_resume(rid: int, body: ResumeUpdate, session: Session = Depends(get_session)):
    r = session.get(Resume, rid)
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    data = body.model_dump(exclude_unset=True)
    if data.get("kind") not in (None, "me", "company"):
        data.pop("kind")
    target_kind = data.get("kind") or r.kind or "company"
    if data.get("kind") or data.get("is_active"):
        _deactivate_kind(session, target_kind)
        data["is_active"] = True
    for k, v in data.items():
        setattr(r, k, v)
    r.updated_at = datetime.utcnow()
    session.add(r)
    session.commit()
    session.refresh(r)
    _sync_vault(r.kind or "company", r.name, r.text)
    return _serialize(r)


@router.delete("/{rid}")
def delete_resume(rid: int, session: Session = Depends(get_session)):
    r = session.get(Resume, rid)
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    session.delete(r)
    session.commit()
    return {"ok": True}


def _sync_vault(kind: str, name: str, text: str) -> None:
    ident = current_identity()
    if not ident or not (text or "").strip():
        return
    v = get_vault()
    from .. import catalog

    if kind == "me":
        v.write_text(f"users/{ident.user_id}/me.md", text)
        if name:
            v.write_text(f"users/{ident.user_id}/display_name.txt", name.strip() + "\n")
        # User's matching pack is ME + their company's mission/products,
        # not just the raw upload. Anthracite's product line becomes part
        # of Keny's SBIR alignment automatically.
        catalog.refresh_resume_tags_from_bundle(ident.user_id, ident.company_id)
    elif kind == "company":
        v.write_text(f"companies/{ident.company_id}/products.md", text)
        catalog.refresh_company_tags_from_vault(ident.company_id)
        # Every employee's resume pack now inherits the new product terms.
        for uid in v.company_employees(ident.company_id):
            catalog.refresh_resume_tags_from_bundle(uid, ident.company_id)

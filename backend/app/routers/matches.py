"""Inbox matches: scan DSIP against the active resume, list ranked results.

The council never runs here. Deep-score is a separate Analysis call from the UI.
"""
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from .. import catalog
from ..db import get_session
from ..matcher import run_scan, serialize_match
from ..models import MatchScan, OpportunityMatch, Resume
from ..resume_service import get_resume_text

router = APIRouter(prefix="/api/matches", tags=["matches"])


def _active_resume(session: Session, resume_id: Optional[int]) -> Resume:
    if resume_id is not None:
        r = session.get(Resume, resume_id)
        if not r:
            raise HTTPException(status_code=404, detail="Resume not found")
        return r
    r = session.exec(select(Resume).where(Resume.is_active == True)).first()  # noqa: E712
    if not r:
        r = session.exec(select(Resume)).first()
    if not r:
        raise HTTPException(status_code=400, detail="No resume on file. Add a profile first.")
    if not (r.text or "").strip():
        raise HTTPException(status_code=400, detail="Active resume is empty.")
    return r


def _latest_scan(session: Session, resume_id: Optional[int]) -> Optional[MatchScan]:
    q = select(MatchScan).order_by(MatchScan.created_at.desc())
    if resume_id is not None:
        q = select(MatchScan).where(MatchScan.resume_id == resume_id).order_by(
            MatchScan.created_at.desc()
        )
    return session.exec(q).first()


def _payload(session: Session, resume: Optional[Resume]) -> dict:
    if not resume:
        return {
            "resume": None,
            "profile": None,
            "scanned_at": None,
            "queries": [],
            "match_count": 0,
            "model": "",
            "matches": [],
        }
    scan = _latest_scan(session, resume.id)
    rows = session.exec(
        select(OpportunityMatch)
        .where(OpportunityMatch.resume_id == resume.id)
        .order_by(OpportunityMatch.score.desc())
    ).all()
    profile = None
    if resume.extract_json:
        try:
            profile = json.loads(resume.extract_json)
        except json.JSONDecodeError:
            profile = None
    if isinstance(profile, dict):
        profile = {k: v for k, v in profile.items() if k != "_embedding"}
    last_cat = catalog.latest_pass(session)
    cat = catalog.serialize_pass(last_cat) if last_cat else None
    if cat:
        cat.pop("open_ids", None)
    return {
        "resume": {
            "id": resume.id,
            "name": resume.name,
            "chars": len(resume.text or ""),
            "updated_at": resume.updated_at.isoformat() if resume.updated_at else None,
        },
        "profile": profile,
        "scanned_at": scan.created_at.isoformat() if scan else None,
        "queries": json.loads(scan.queries_json) if scan and scan.queries_json else [],
        "match_count": scan.match_count if scan else 0,
        "model": scan.model if scan else "",
        "catalog": cat,
        "matches": [serialize_match(r) for r in rows],
    }


@router.get("")
def list_matches(resume_id: Optional[int] = None, session: Session = Depends(get_session)):
    rid, text = get_resume_text(session, resume_id)
    if rid is None or not text.strip():
        return _payload(session, None)
    resume = session.get(Resume, rid)
    return _payload(session, resume)


@router.post("/scan")
async def scan_matches(
    resume_id: Optional[int] = None,
    force_extract: bool = False,
    session: Session = Depends(get_session),
):
    resume = _active_resume(session, resume_id)
    try:
        result = await run_scan(session, resume, force_extract=force_extract)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Match scan failed: {e}") from e
    result["resume"] = {
        "id": resume.id,
        "name": resume.name,
        "chars": len(resume.text or ""),
        "updated_at": resume.updated_at.isoformat() if resume.updated_at else None,
    }
    return result

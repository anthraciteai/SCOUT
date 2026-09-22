"""Inbox matches: scan DSIP against the active resume, list ranked results.

The council never runs here. Deep-score is a separate Analysis call from the UI.
"""
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from .. import catalog, ollama_client
from ..db import get_session
from ..identity import current_identity
from ..matcher import run_scan, serialize_match
from ..models import MatchScan, OpportunityMatch, Resume
from ..resume_service import get_resume_text
from ..vault import get_vault

router = APIRouter(prefix="/api/matches", tags=["matches"])


class ScanRequest(BaseModel):
    resume_id: Optional[int] = None
    force_extract: bool = False
    # New: pick who we're ranking for.
    mode: str = "me"  # "me" | "employee" | "company"
    employee_id: Optional[str] = None
    include_company: bool = True


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


def _new_ids(session: Session, resume_id: int) -> tuple[list[str], Optional[MatchScan]]:
    """topic_ids that were NOT in the previous scan's top-50 (excluding the
    very first scan for this resume, which would flag everything as new)."""
    scans = session.exec(
        select(MatchScan)
        .where(MatchScan.resume_id == resume_id)
        .order_by(MatchScan.created_at.desc())
    ).all()
    if len(scans) < 2:
        return [], None
    curr = scans[0]
    prev = scans[1]
    try:
        curr_top = set(json.loads(curr.top_ids_json or "[]"))
        prev_top = set(json.loads(prev.top_ids_json or "[]"))
    except json.JSONDecodeError:
        return [], prev
    new = curr_top - prev_top
    return list(new), prev


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
            "new_since": None,
            "new_topic_ids": [],
        }
    scan = _latest_scan(session, resume.id)
    rows = session.exec(
        select(OpportunityMatch)
        .where(OpportunityMatch.resume_id == resume.id)
        .order_by(OpportunityMatch.score.desc())
    ).all()
    new_ids, prev_scan = _new_ids(session, resume.id)
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
    matches = [serialize_match(r) for r in rows]
    new_set = set(new_ids)
    for m in matches:
        m["is_new"] = m["topic_id"] in new_set
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
        "new_since": prev_scan.created_at.isoformat() if prev_scan else None,
        "new_topic_ids": new_ids,
        "matches": matches,
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
    body: Optional[ScanRequest] = None,
    resume_id: Optional[int] = None,
    force_extract: bool = False,
    session: Session = Depends(get_session),
):
    """Run a scan. `body` selects the source (self / another employee / company only)."""
    if body is None:
        body = ScanRequest(resume_id=resume_id, force_extract=force_extract)
    resume = _active_resume(session, body.resume_id)
    mode = (body.mode or "me").lower()
    if mode not in ("me", "employee", "company"):
        raise HTTPException(status_code=400, detail=f"Unknown mode '{mode}'")
    if mode == "employee" and not body.employee_id:
        raise HTTPException(status_code=400, detail="employee_id is required for mode=employee")
    try:
        result = await run_scan(
            session,
            resume,
            force_extract=body.force_extract or (mode != "me") or (not body.include_company),
            mode=mode,
            employee_id=body.employee_id,
            include_company=body.include_company,
        )
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Match scan failed: {e}") from e
    result["resume"] = {
        "id": resume.id,
        "name": resume.name,
        "chars": len(resume.text or ""),
        "updated_at": resume.updated_at.isoformat() if resume.updated_at else None,
    }
    return result


WHY_SYSTEM = (
    "You are a matching-explainer. In 3-4 short sentences say WHY this DoD "
    "SBIR/STTR topic matched this profile. Quote the exact overlapping phrases "
    "(inside `backticks`) so the reader can trace the signal, mention any "
    "obvious mismatch or stretch, and end with a single one-line verdict: "
    "'Verdict: <write today | worth a look | stretch>'. No headings, no lists, "
    "no fluff — write it like a smart teammate slacking you 'why this'."
)


@router.post("/{topic_id}/why")
async def explain_match(topic_id: str, session: Session = Depends(get_session)):
    """Stream a plain-English explanation of *this* match, using the phrases
    we already stored on the last scan (topic tags, reasons, resume phrases).
    Nothing new is computed against DSIP — we just render the trail.
    """
    row = session.exec(
        select(OpportunityMatch).where(OpportunityMatch.topic_id == topic_id)
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="No cached match for this topic. Run a scan first.")

    scan = session.exec(
        select(MatchScan).where(MatchScan.resume_id == row.resume_id).order_by(MatchScan.created_at.desc())
    ).first()
    resume: Optional[Resume] = session.get(Resume, row.resume_id) if row.resume_id else None

    try:
        reasons = json.loads(row.reasons_json or "[]")
    except json.JSONDecodeError:
        reasons = []
    try:
        topic_phrases = json.loads(row.tags_json or "[]")
    except json.JSONDecodeError:
        topic_phrases = []
    try:
        raw = json.loads(row.raw_json or "{}")
    except json.JSONDecodeError:
        raw = {}
    profile: dict = {}
    if resume and resume.extract_json:
        try:
            profile = json.loads(resume.extract_json)
        except json.JSONDecodeError:
            profile = {}
    resume_phrases = list(
        (profile.get("phrases") or [])
        + (profile.get("keywords") or [])
        + (profile.get("skills") or [])
    )[:24]

    ident = current_identity()
    company_phrases: list = []
    if ident:
        try:
            pack = get_vault().read_json(get_vault().company_tags_key(ident.company_id)) or {}
            company_phrases = list(pack.get("phrases") or [])[:16]
        except Exception:
            company_phrases = []

    title = row.title or raw.get("topicTitle") or raw.get("title") or row.topic_code
    prompt = (
        f"TOPIC: {row.topic_code} — {title}\n"
        f"COMPONENT: {row.component or ''} · PROGRAM: {row.program or ''}\n"
        f"SCORE: {row.score}\n"
        f"REASONS_ON_FILE: {reasons}\n"
        f"TOPIC_PHRASES (from scout tagger): {topic_phrases[:16]}\n"
        f"THIS PERSON'S RESUME PHRASES: {resume_phrases}\n"
        f"THEIR COMPANY PACK PHRASES: {company_phrases}\n"
        f"SCAN CONTEXT: {(scan.model if scan else '') or 'local'}\n\n"
        "Explain WHY this matched. Cite the phrases that overlap in backticks, "
        "note any mismatch, end with 'Verdict: …'."
    )

    async def gen():
        async for chunk in ollama_client.chat_stream(WHY_SYSTEM, prompt, temperature=0.2):
            yield chunk

    return StreamingResponse(gen(), media_type="text/plain; charset=utf-8")


@router.get("/rerank/options")
def rerank_options():
    """Sources the user can pick from in the rerank dialog. Company-mates only."""
    ident = current_identity()
    v = get_vault()
    if not ident:
        return {"identity": None, "you": None, "coworkers": [], "company_id": None}
    cid = ident.company_id
    coworkers = []
    for uid in v.company_employees(cid):
        if uid == ident.user_id:
            continue
        display = v.read_text(f"users/{uid}/display_name.txt").strip() or uid
        me_chars = len(v.read_text(f"users/{uid}/me.md") or "")
        coworkers.append(
            {
                "user_id": uid,
                "display_name": display,
                "me_chars": me_chars,
                "has_resume": me_chars > 0,
            }
        )
    you_display = v.read_text(f"users/{ident.user_id}/display_name.txt").strip() or ident.user_id
    you_chars = len(v.read_text(f"users/{ident.user_id}/me.md") or "")
    return {
        "identity": {"user_id": ident.user_id, "company_id": cid},
        "company_id": cid,
        "you": {
            "user_id": ident.user_id,
            "display_name": you_display,
            "me_chars": you_chars,
            "has_resume": you_chars > 0,
        },
        "coworkers": sorted(coworkers, key=lambda c: c["display_name"].lower()),
        "company": {
            "mission_chars": len(v.read_text(f"companies/{cid}/mission.txt") or ""),
            "product_chars": len(v.read_text(f"companies/{cid}/products.md") or ""),
        },
    }

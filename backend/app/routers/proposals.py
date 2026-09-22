"""Proposal drafts + live LLM writing feedback (streaming)."""
import hashlib
import json
import re
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from .. import dsip, ollama_client
from ..agents import summarize_topic
from ..db import engine, get_session
from ..models import Debrief, Proposal, ProposalCost, ProposalReview, ProposalTaskPlan

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


# --- Persona reviewers ---------------------------------------------------
# Three named voices the user can run against any past proposal. Each returns
# a markdown-style review that is snapshotted into `proposal_review` so past
# reviews stay browseable even after the proposal text changes.
PERSONAS: dict[str, dict[str, str]] = {
    "technical": {
        "label": "Technical expert",
        "blurb": "Hewer-style engineering review: feasibility, algorithm/architecture rigor, TRL, integration risk.",
        "system": (
            "You are a senior technical expert (chief engineer) reviewing a DoD SBIR/STTR "
            "proposal draft. Focus strictly on the SCIENTIFIC AND TECHNICAL substance: "
            "algorithms, architecture, hardware/software integration, TRL claims, test "
            "and evaluation plan, data pipeline, safety and assurance, edge cases, and "
            "the plausibility of the Phase I -> II lift. Call out anything hand-wavy "
            "('using AI', 'leveraging cloud') and demand specifics. Quote the applicant's "
            "text when you critique. Be direct.\n"
            "Return a MARKDOWN review with headings: '## Technical merit', '## Feasibility "
            "and risk', '## What is missing', '## Concrete rewrites (quote → fix)', "
            "'## Priority actions (top 5)'. End with a single line: "
            "`SCORE: <0-100>` — your gut technical-strength score."
        ),
    },
    "military": {
        "label": "Military / mission",
        "blurb": "Anthracite-style capture BD: sponsor mission fit, operator utility, transition path, competitor read.",
        "system": (
            "You are a retired O-5/O-6 turned government business developer reviewing a "
            "DoD SBIR/STTR draft. Focus on WHY THE SPONSOR CARES: the warfighter problem "
            "in operator language, whether the proposed solution actually maps to a "
            "sponsor mission need, unit-level utility, the transition path to a program "
            "of record (Phase III / OTA / rapid fielding), likely incumbents and "
            "competitors, and the credibility of the win themes for a TPOC / PM. Push "
            "back on any claim that a uniformed operator would not buy.\n"
            "Return a MARKDOWN review with headings: '## Sponsor mission fit', "
            "'## Operator utility (in the field)', '## Competitive landscape', "
            "'## Transition path (Phase I → II → III)', "
            "'## Win themes a TPOC can brief', '## Priority actions (top 5)'. "
            "End with a single line: `SCORE: <0-100>` — your capture-strength score."
        ),
    },
    "researcher": {
        "label": "Researcher",
        "blurb": "Academic/research reviewer: literature grounding, novelty, method rigor, publication/IP.",
        "system": (
            "You are a research-institution PI (STTR / academic partner). Review this "
            "DoD SBIR/STTR draft as a NIH/NSF-style scientific reviewer would. Focus on: "
            "novelty vs the state of the art, quality of literature grounding (are the "
            "right prior works cited or referenced), method rigor and reproducibility, "
            "statistical / experimental plan, data quality and provenance, publication or "
            "IP strategy, and STTR-specific research-partner suitability. If the draft "
            "over-claims novelty, say so and cite what already exists. If the method is "
            "under-specified, call it out.\n"
            "Return a MARKDOWN review with headings: '## Novelty vs prior art', "
            "'## Method rigor', '## Data and evaluation plan', "
            "'## Literature / prior work to cite', '## Publication / IP strategy', "
            "'## Priority actions (top 5)'. End with a single line: "
            "`SCORE: <0-100>` — your research-quality score."
        ),
    },
}


def _persona(name: str) -> dict[str, str]:
    key = (name or "").strip().lower()
    if key not in PERSONAS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown persona '{name}'. Try one of: {', '.join(PERSONAS)}",
        )
    return PERSONAS[key]


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


# NOTE: static / literal routes MUST be declared before "/{pid}" routes so that
# FastAPI does not try to parse "personas" or "reviews" as an int pid.
@router.get("/personas")
def list_personas_static():
    """Discoverable list of the review voices. UI drives its tabs from this."""
    return [
        {"key": k, "label": v["label"], "blurb": v["blurb"]}
        for k, v in PERSONAS.items()
    ]


@router.get("/reviews/summary")
def reviews_summary_static(session: Session = Depends(get_session)):
    """Cross-proposal review counts for the overview chart."""
    rows = session.exec(select(ProposalReview)).all()
    by_persona: dict[str, int] = {}
    by_proposal: dict[int, dict[str, int]] = {}
    for r in rows:
        by_persona[r.persona] = by_persona.get(r.persona, 0) + 1
        buc = by_proposal.setdefault(r.proposal_id, {})
        buc[r.persona] = buc.get(r.persona, 0) + 1
    return {
        "total": len(rows),
        "by_persona": by_persona,
        "by_proposal": by_proposal,
    }


@router.delete("/reviews/{rid}")
def delete_review_static(rid: int, session: Session = Depends(get_session)):
    r = session.get(ProposalReview, rid)
    if not r:
        raise HTTPException(status_code=404, detail="Review not found")
    session.delete(r)
    session.commit()
    return {"ok": True}


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


# --- Persona reviews (browseable) ---------------------------------------

def _serialize_review(r: ProposalReview) -> dict:
    return {
        "id": r.id,
        "proposal_id": r.proposal_id,
        "persona": r.persona,
        "persona_label": PERSONAS.get(r.persona, {}).get("label", r.persona),
        "title": r.title,
        "topic_id": r.topic_id,
        "topic_code": r.topic_code,
        "proposal_sha": r.proposal_sha,
        "proposal_chars": r.proposal_chars,
        "body": r.body,
        "model": r.model,
        "created_at": r.created_at.isoformat(),
    }


def _sha16(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


@router.get("/{pid}/reviews")
def list_reviews(
    pid: int,
    persona: Optional[str] = None,
    session: Session = Depends(get_session),
):
    """All persona-review snapshots for this proposal, newest first."""
    q = select(ProposalReview).where(ProposalReview.proposal_id == pid)
    if persona:
        q = q.where(ProposalReview.persona == persona.lower())
    rows = session.exec(q.order_by(ProposalReview.created_at.desc())).all()
    return [_serialize_review(r) for r in rows]


@router.post("/{pid}/review/{persona}")
async def run_persona_review(
    pid: int, persona: str, session: Session = Depends(get_session),
):
    """Stream a persona review AND persist the completed text so past reviews
    stay browseable. UI shows each new snapshot at the top of that persona's
    tab. Returns text/plain stream; final chunk is the review body."""
    p = session.get(Proposal, pid)
    if not p:
        raise HTTPException(status_code=404, detail="Not found")
    persona_spec = _persona(persona)

    topic_ctx = await _build_topic_context(p.topic_id)
    debrief_ctx = ""
    if p.topic_id:
        debriefs = session.exec(
            select(Debrief).where(Debrief.topic_id == p.topic_id)
        ).all()
        if debriefs:
            joined = "\n---\n".join(d.extracted_text[:2500] for d in debriefs)
            debrief_ctx = (
                "\n\nPRIOR GOVERNMENT FEEDBACK / DEBRIEF (learn from these weaknesses):\n"
                f"{joined[:5000]}"
            )

    prompt = (
        f"{topic_ctx}{debrief_ctx}\n\nPROPOSAL: {p.title}\n\n"
        f"{p.content[:12000]}\n\n"
        f"Review this proposal in your persona ({persona_spec['label']})."
    )

    sha = _sha16(p.content)
    title = p.title
    topic_id = p.topic_id
    topic_code = p.topic_code

    async def gen():
        collected: list[str] = []
        try:
            async for chunk in ollama_client.chat_stream(
                persona_spec["system"], prompt, temperature=0.3
            ):
                collected.append(chunk)
                yield chunk
        finally:
            body = "".join(collected).strip()
            if body:
                try:
                    model = await ollama_client.resolve_model()
                except Exception:
                    model = ""
                # Use a fresh session — the request session may be closed by
                # the time streaming completes.
                with Session(engine) as s2:
                    row = ProposalReview(
                        proposal_id=pid,
                        persona=persona.lower(),
                        title=title,
                        topic_id=topic_id,
                        topic_code=topic_code,
                        proposal_sha=sha,
                        proposal_chars=len(p.content or ""),
                        body=body,
                        model=model,
                    )
                    s2.add(row)
                    s2.commit()

    return StreamingResponse(gen(), media_type="text/plain; charset=utf-8")


# =========================================================================
# TECHNICAL-APPROACH TASK PLAN (Gantt source)
# =========================================================================
# The draft's Functional Requirements + Technical Approach are broken into
# bite-size, dependency-linked tasks that the frontend renders as a Gantt.
# The endpoint is intentionally cautious: it refuses to run on a stub draft
# so users don't waste an LLM turn on nothing.

TASK_PLAN_MIN_CHARS = 1500  # below this the draft is a stub — refuse politely

TASK_PLAN_SYSTEM = (
    "You are Dyno, a Phase I/II SBIR technical program manager. You read a "
    "proposal draft and translate the Technical Approach + Functional "
    "Requirements sections into a concrete, dependency-linked task plan the "
    "PI can actually execute. You keep tasks BITE-SIZED (typically 1-4 weeks "
    "each), give every task a testable deliverable, and honor SBIR phase "
    "durations (Phase I ~6 months, Phase II ~24 months). You return STRICT "
    "JSON matching the requested schema. If the draft is too vague, still "
    "return valid JSON but flag it clearly in 'assumptions'. Never invent "
    "tech the draft does not mention."
)

TASK_PLAN_INSTRUCTIONS = """\
Return a JSON object with this EXACT shape:
{
  "phases": [
    {"key": "phase1", "label": "Phase I - Feasibility (6 mo)", "duration_weeks": 26}
  ],
  "requirements": [
    {"id": "FR1", "text": "The system shall ..."}
  ],
  "tasks": [
    {
      "id": "T1",
      "title": "Bench-scale sensor characterization",
      "phase": "phase1",
      "start_week": 0,
      "duration_weeks": 3,
      "depends_on": [],
      "deliverable": "characterization report + raw data",
      "requirements": ["FR1", "FR3"],
      "owner_role": "rf_engineer"
    }
  ],
  "assumptions": "1-2 sentence caveat about what you had to guess."
}

Rules:
- Prefer 8-16 tasks total across all phases. Bite-sized only.
- start_week is measured from the phase start; tasks may overlap.
- depends_on lists other task ids that MUST finish first.
- Every task references at least one requirement id (from 'requirements').
- Use snake-cased owner roles ("rf_engineer", "swe", "pm", ...).
- If the draft only supports Phase I, include only phase1.
- Return ONLY the JSON object, no prose, no markdown fences."""


def _safe_json(text: str) -> dict:
    """Extract the first JSON object we can find, tolerant of stray prose."""
    if not text:
        return {}
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    i = text.find("{")
    j = text.rfind("}")
    if i >= 0 and j > i:
        try:
            return json.loads(text[i : j + 1])
        except json.JSONDecodeError:
            pass
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


def _serialize_plan(row: ProposalTaskPlan) -> dict:
    try:
        plan = json.loads(row.plan_json or "{}")
    except json.JSONDecodeError:
        plan = {}
    return {
        "id": row.id,
        "proposal_id": row.proposal_id,
        "proposal_sha": row.proposal_sha,
        "proposal_chars": row.proposal_chars,
        "plan": plan,
        "model": row.model,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("/{pid}/tasks")
def latest_task_plan(pid: int, session: Session = Depends(get_session)):
    """Latest task-plan snapshot for the proposal. 200 with snapshot:null if none."""
    row = session.exec(
        select(ProposalTaskPlan)
        .where(ProposalTaskPlan.proposal_id == pid)
        .order_by(ProposalTaskPlan.created_at.desc())
    ).first()
    p = session.get(Proposal, pid)
    ready = bool(p and len(p.content or "") >= TASK_PLAN_MIN_CHARS)
    return {
        "proposal_id": pid,
        "current_chars": len(p.content or "") if p else 0,
        "min_chars": TASK_PLAN_MIN_CHARS,
        "ready": ready,
        "current_sha": _sha16(p.content) if p else "",
        "snapshot": _serialize_plan(row) if row else None,
    }


@router.get("/{pid}/tasks/history")
def task_plan_history(pid: int, session: Session = Depends(get_session)):
    rows = session.exec(
        select(ProposalTaskPlan)
        .where(ProposalTaskPlan.proposal_id == pid)
        .order_by(ProposalTaskPlan.created_at.desc())
    ).all()
    return [_serialize_plan(r) for r in rows]


@router.post("/{pid}/tasks/generate")
async def generate_task_plan(pid: int, session: Session = Depends(get_session)):
    """LLM-generate a bite-sized task plan from the current draft. Refuses if
    the draft is too thin to be worth the round-trip."""
    p = session.get(Proposal, pid)
    if not p:
        raise HTTPException(status_code=404, detail="Not found")
    content = p.content or ""
    if len(content) < TASK_PLAN_MIN_CHARS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Draft is only {len(content)} chars. Come back at "
                f"{TASK_PLAN_MIN_CHARS}+ so the Technical Approach has enough "
                "meat to slice into tasks."
            ),
        )

    topic_ctx = await _build_topic_context(p.topic_id)
    prompt = (
        f"{topic_ctx}\n\nPROPOSAL: {p.title}\n\n"
        f"DRAFT (Functional Requirements + Technical Approach are in here):\n"
        f"{content[:14000]}\n\n{TASK_PLAN_INSTRUCTIONS}"
    )
    # Stream so long CPU generations don't hit the non-stream ReadTimeout.
    collected: list[str] = []
    async for chunk in ollama_client.chat_stream(
        TASK_PLAN_SYSTEM, prompt, temperature=0.2
    ):
        collected.append(chunk)
    raw = "".join(collected)
    plan = _safe_json(raw)
    if not plan or "tasks" not in plan:
        raise HTTPException(
            status_code=502,
            detail="LLM did not return a usable task plan. Try again.",
        )
    try:
        model = await ollama_client.resolve_model()
    except Exception:
        model = ""
    row = ProposalTaskPlan(
        proposal_id=pid,
        proposal_sha=_sha16(content),
        proposal_chars=len(content),
        plan_json=json.dumps(plan),
        model=model,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return _serialize_plan(row)


# =========================================================================
# COST STUDIO -- Dynomite (BOM builder) + Budget Man (rollup)
# =========================================================================
# One ProposalCost row per proposal. Dynomite streams conversational replies
# and emits the FULL updated BOM as a fenced ```json``` block at the end of
# each turn; the backend parses & persists it so the frontend just re-fetches.
# Budget Man is a non-stream endpoint that applies the saved rates + Phase
# caps to produce a structured rollup + a short human summary.

DYNOMITE_SYSTEM = """\
You are Dynomite -- a chatty, no-BS SBIR cost estimator whose only job is to
help the user build a defensible Bill of Materials (BOM) for their proposal.
You ask targeted questions ("who's doing what, for how many hours, at what
labor rate?"), sanity-check numbers (fully-loaded rates, allowable travel,
GSA-per-diem realism, ITAR/export risks), and steer the user toward a BOM
Budget Man can roll up cleanly.

RULES:
- Speak like a shop foreman: short, direct, mildly playful.
- After every user turn, output your normal reply, then a fenced JSON block
  containing the ENTIRE current BOM (not a diff). Schema:
  ```json
  {
    "bom": [
      {
        "id": "L1",
        "category": "labor" | "materials" | "equipment" | "travel" | "subcontract" | "odc",
        "name": "Senior software engineer",
        "qty": 320,
        "unit": "hours" | "each" | "trip" | "lot" | "month",
        "unit_cost": 165.0,
        "notes": "Loaded rate incl. fringe/OH per company DCAA rates"
      }
    ]
  }
  ```
- ONLY include items you and the user have discussed/confirmed. Do not
  invent stuff to pad the list.
- Preserve prior line-item ids; new items get the next Ln id.
- Keep the reply concise (<= ~180 words). The JSON at the end is required.
- If the user just says "hi", introduce yourself and ask about the phase +
  scope in one sentence, then emit an empty BOM: `{"bom": []}`."""


BUDGET_MAN_SYSTEM = """\
You are Budget Man -- the finance guy who takes Dynomite's BOM, applies
indirect rates and the SBIR Phase cap, and produces a clean, brief rollup.
You never invent line items; you only aggregate what's provided. You point
out (in one or two sharp bullets) any red flags: exceeding the phase cap,
labor > 66% of direct, missing travel for a proposal that clearly needs a
site visit, unrealistic unit costs, etc."""


PHASE_CAPS = {
    "phase1": 314_363,
    "phase2": 2_095_748,
    "direct_to_phase2": 2_095_748,
}

PHASE_LABELS = {
    "phase1": "Phase I",
    "phase2": "Phase II",
    "direct_to_phase2": "Direct to Phase II",
}

DEFAULT_RATES = {
    "fringe_pct": 32.0,       # applied to labor
    "overhead_pct": 45.0,     # applied to labor + fringe
    "ga_pct": 12.0,           # applied to (direct + fringe + overhead)
    "fee_pct": 7.0,           # applied to subtotal (DoD SBIR cap 7%)
}


class RatesBody(BaseModel):
    fringe_pct: Optional[float] = None
    overhead_pct: Optional[float] = None
    ga_pct: Optional[float] = None
    fee_pct: Optional[float] = None
    phase: Optional[str] = None


class BomLine(BaseModel):
    id: Optional[str] = None
    category: str
    name: str
    qty: float = 0.0
    unit: str = "each"
    unit_cost: float = 0.0
    notes: Optional[str] = None


class BomBody(BaseModel):
    bom: list[BomLine]


class DynomiteBody(BaseModel):
    message: str


def _load_cost(session: Session, pid: int, create: bool = False) -> Optional[ProposalCost]:
    row = session.exec(
        select(ProposalCost).where(ProposalCost.proposal_id == pid)
    ).first()
    if row or not create:
        return row
    row = ProposalCost(
        proposal_id=pid,
        bom_json="[]",
        rates_json=json.dumps(DEFAULT_RATES),
        chat_json="[]",
        phase="phase1",
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def _cost_payload(row: ProposalCost) -> dict:
    try:
        bom = json.loads(row.bom_json or "[]")
    except json.JSONDecodeError:
        bom = []
    try:
        rates = json.loads(row.rates_json or "{}")
    except json.JSONDecodeError:
        rates = {}
    try:
        chat = json.loads(row.chat_json or "[]")
    except json.JSONDecodeError:
        chat = []
    try:
        rollup = json.loads(row.rollup_json) if row.rollup_json else None
    except json.JSONDecodeError:
        rollup = None
    return {
        "proposal_id": row.proposal_id,
        "phase": row.phase,
        "phase_label": PHASE_LABELS.get(row.phase, row.phase),
        "phase_cap": PHASE_CAPS.get(row.phase),
        "bom": bom,
        "rates": {**DEFAULT_RATES, **rates},
        "chat": chat,
        "rollup": rollup,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.get("/{pid}/cost")
def get_cost(pid: int, session: Session = Depends(get_session)):
    row = _load_cost(session, pid, create=True)
    return _cost_payload(row)


@router.put("/{pid}/cost/rates")
def update_rates(
    pid: int, body: RatesBody, session: Session = Depends(get_session)
):
    row = _load_cost(session, pid, create=True)
    try:
        rates = json.loads(row.rates_json or "{}")
    except json.JSONDecodeError:
        rates = {}
    rates = {**DEFAULT_RATES, **rates}
    for k, v in body.model_dump(exclude_unset=True).items():
        if k == "phase" and v in PHASE_CAPS:
            row.phase = v
        elif k in ("fringe_pct", "overhead_pct", "ga_pct", "fee_pct") and v is not None:
            rates[k] = float(v)
    row.rates_json = json.dumps(rates)
    row.updated_at = datetime.utcnow()
    session.add(row)
    session.commit()
    session.refresh(row)
    return _cost_payload(row)


@router.put("/{pid}/cost/bom")
def replace_bom(
    pid: int, body: BomBody, session: Session = Depends(get_session)
):
    """Manual override -- replace the entire BOM (used by the inline editor)."""
    row = _load_cost(session, pid, create=True)
    cleaned = []
    for i, ln in enumerate(body.bom, start=1):
        cleaned.append(
            {
                "id": ln.id or f"L{i}",
                "category": ln.category,
                "name": ln.name,
                "qty": float(ln.qty or 0),
                "unit": ln.unit or "each",
                "unit_cost": float(ln.unit_cost or 0),
                "notes": ln.notes or "",
            }
        )
    row.bom_json = json.dumps(cleaned)
    row.updated_at = datetime.utcnow()
    session.add(row)
    session.commit()
    session.refresh(row)
    return _cost_payload(row)


@router.delete("/{pid}/cost/chat")
def clear_chat(pid: int, session: Session = Depends(get_session)):
    row = _load_cost(session, pid, create=True)
    row.chat_json = "[]"
    row.updated_at = datetime.utcnow()
    session.add(row)
    session.commit()
    return _cost_payload(row)


def _looks_like_bom_line(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    return "name" in item and ("category" in item or "unit_cost" in item or "qty" in item)


def _as_bom(parsed: Any) -> Optional[list[dict]]:
    """Coerce whatever the model returned into a BOM list, if plausible."""
    if isinstance(parsed, dict):
        if isinstance(parsed.get("bom"), list):
            return parsed["bom"]
        # Some models emit {"items": [...]} or top-level line-items dict-of-dicts
        if isinstance(parsed.get("items"), list):
            return parsed["items"]
    if isinstance(parsed, list) and all(_looks_like_bom_line(x) for x in parsed):
        return parsed
    return None


def _extract_bom_block(text: str) -> Optional[list[dict]]:
    """Pull the last JSON block out of Dynomite's reply. Accepts both the
    documented `{"bom": [...]}` shape and bare `[...]` arrays of line items
    (models forget the wrapper about half the time).
    """
    if not text:
        return None
    # 1) any fenced block (with or without a ```json tag), scanned last-first
    fenced = list(
        re.finditer(r"```(?:json)?\s*([\{\[].*?[\}\]])\s*```", text, re.DOTALL)
    )
    for m in reversed(fenced):
        try:
            parsed = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        bom = _as_bom(parsed)
        if bom is not None:
            return bom
    # 2) trailing raw JSON (no fence) — try `{...}` and `[...]` at the tail
    tail = text.rstrip()
    for opener, closer in (("{", "}"), ("[", "]")):
        start = tail.rfind(opener)
        end = tail.rfind(closer)
        if start >= 0 and end > start:
            try:
                parsed = json.loads(tail[start : end + 1])
            except json.JSONDecodeError:
                continue
            bom = _as_bom(parsed)
            if bom is not None:
                return bom
    return None


def _clean_bom(raw: list[dict]) -> list[dict]:
    ok_cats = {"labor", "materials", "equipment", "travel", "subcontract", "odc"}
    out: list[dict] = []
    for i, ln in enumerate(raw or [], start=1):
        if not isinstance(ln, dict):
            continue
        cat = str(ln.get("category") or "odc").lower()
        if cat not in ok_cats:
            cat = "odc"
        try:
            qty = float(ln.get("qty") or 0)
            unit_cost = float(ln.get("unit_cost") or 0)
        except (TypeError, ValueError):
            qty, unit_cost = 0.0, 0.0
        out.append(
            {
                "id": str(ln.get("id") or f"L{i}"),
                "category": cat,
                "name": str(ln.get("name") or "")[:200],
                "qty": qty,
                "unit": str(ln.get("unit") or "each")[:20],
                "unit_cost": unit_cost,
                "notes": str(ln.get("notes") or "")[:400],
            }
        )
    return out


@router.post("/{pid}/cost/chat")
async def dynomite_chat(
    pid: int, body: DynomiteBody, session: Session = Depends(get_session)
):
    """Dynomite streams a conversational reply; when the stream closes we
    parse the trailing JSON block and persist the updated BOM."""
    p = session.get(Proposal, pid)
    if not p:
        raise HTTPException(status_code=404, detail="Proposal not found")
    row = _load_cost(session, pid, create=True)
    try:
        chat = json.loads(row.chat_json or "[]")
    except json.JSONDecodeError:
        chat = []
    try:
        current_bom = json.loads(row.bom_json or "[]")
    except json.JSONDecodeError:
        current_bom = []

    trimmed = chat[-12:]
    messages = [{"role": "system", "content": DYNOMITE_SYSTEM}]
    context_lines = [
        f"PROPOSAL: {p.title}",
        f"PHASE: {PHASE_LABELS.get(row.phase, row.phase)} (cap ${PHASE_CAPS.get(row.phase, 0):,})",
        f"DRAFT SNIPPET:\n{(p.content or '')[:2500]}",
        f"CURRENT BOM SO FAR:\n{json.dumps(current_bom, indent=2)}",
    ]
    messages.append({"role": "system", "content": "\n\n".join(context_lines)})
    for turn in trimmed:
        role = turn.get("role")
        if role in ("user", "assistant") and turn.get("content"):
            messages.append({"role": role, "content": turn["content"]})
    messages.append({"role": "user", "content": body.message})

    async def gen():
        collected: list[str] = []
        try:
            async for chunk in ollama_client.chat_stream_messages(
                messages, temperature=0.35
            ):
                collected.append(chunk)
                yield chunk
        finally:
            reply = "".join(collected).strip()
            if not reply:
                return
            new_bom = _extract_bom_block(reply)
            with Session(engine) as s2:
                row2 = _load_cost(s2, pid, create=True)
                try:
                    chat2 = json.loads(row2.chat_json or "[]")
                except json.JSONDecodeError:
                    chat2 = []
                chat2.append({"role": "user", "content": body.message})
                chat2.append({"role": "assistant", "content": reply})
                row2.chat_json = json.dumps(chat2[-50:])
                if new_bom is not None:
                    row2.bom_json = json.dumps(_clean_bom(new_bom))
                row2.updated_at = datetime.utcnow()
                s2.add(row2)
                s2.commit()

    return StreamingResponse(gen(), media_type="text/plain; charset=utf-8")


def _rollup(bom: list[dict], rates: dict, phase: str) -> dict:
    fringe_pct = float(rates.get("fringe_pct", 0)) / 100.0
    overhead_pct = float(rates.get("overhead_pct", 0)) / 100.0
    ga_pct = float(rates.get("ga_pct", 0)) / 100.0
    fee_pct = min(float(rates.get("fee_pct", 0)) / 100.0, 0.07)  # DoD cap 7%

    by_cat: dict[str, float] = {c: 0.0 for c in ("labor", "materials", "equipment", "travel", "subcontract", "odc")}
    lines: list[dict] = []
    for ln in bom:
        subtotal = float(ln.get("qty", 0)) * float(ln.get("unit_cost", 0))
        by_cat[ln.get("category", "odc")] = by_cat.get(ln.get("category", "odc"), 0.0) + subtotal
        lines.append({**ln, "subtotal": round(subtotal, 2)})

    labor = by_cat["labor"]
    fringe = labor * fringe_pct
    overhead = (labor + fringe) * overhead_pct
    direct_ex_labor = (
        by_cat["materials"]
        + by_cat["equipment"]
        + by_cat["travel"]
        + by_cat["subcontract"]
        + by_cat["odc"]
    )
    total_direct_indirect = labor + fringe + overhead + direct_ex_labor
    ga = total_direct_indirect * ga_pct
    subtotal_before_fee = total_direct_indirect + ga
    fee = subtotal_before_fee * fee_pct
    total = subtotal_before_fee + fee

    cap = PHASE_CAPS.get(phase)
    warnings: list[str] = []
    if cap and total > cap:
        warnings.append(
            f"Total ${total:,.0f} exceeds the {PHASE_LABELS.get(phase, phase)} cap of ${cap:,}."
        )
    if labor and (total_direct_indirect > 0) and labor / total_direct_indirect > 0.75:
        warnings.append(
            "Labor is >75% of direct+indirect -- reviewers may want more materials/travel justification."
        )
    if float(rates.get("fee_pct", 0)) > 7.0:
        warnings.append("DoD SBIR fee is typically capped at 7%. Rate was clamped for the rollup.")
    if bom and not any(ln.get("category") == "travel" for ln in bom):
        warnings.append("No travel line -- most DoD SBIRs need at least a kickoff visit.")

    return {
        "phase": phase,
        "phase_label": PHASE_LABELS.get(phase, phase),
        "phase_cap": cap,
        "lines": lines,
        "by_category": {k: round(v, 2) for k, v in by_cat.items()},
        "labor": round(labor, 2),
        "fringe": round(fringe, 2),
        "overhead": round(overhead, 2),
        "direct_non_labor": round(direct_ex_labor, 2),
        "g_and_a": round(ga, 2),
        "fee": round(fee, 2),
        "total": round(total, 2),
        "headroom": round(cap - total, 2) if cap else None,
        "warnings": warnings,
    }


@router.post("/{pid}/cost/rollup")
async def budget_man_rollup(pid: int, session: Session = Depends(get_session)):
    """Deterministic rollup + a short LLM narrative from Budget Man."""
    row = _load_cost(session, pid, create=True)
    try:
        bom = json.loads(row.bom_json or "[]")
        rates = {**DEFAULT_RATES, **json.loads(row.rates_json or "{}")}
    except json.JSONDecodeError:
        bom, rates = [], DEFAULT_RATES
    rollup = _rollup(bom, rates, row.phase)

    narrative = ""
    if bom:
        prompt = (
            f"Phase: {rollup['phase_label']} (cap ${rollup['phase_cap']:,})\n"
            f"BOM:\n{json.dumps(bom, indent=2)}\n\n"
            f"Rollup:\n{json.dumps(rollup, indent=2)}\n\n"
            "Write a 4-6 sentence summary the PI can read to the team. Call "
            "out any warnings from the rollup. No headings. End with one line: "
            "'Bottom line: $X submitted vs $Y cap → $Z headroom (...)'."
        )
        try:
            narrative = await ollama_client.chat(
                BUDGET_MAN_SYSTEM, prompt, temperature=0.2
            )
        except Exception as e:  # noqa: BLE001
            narrative = f"[budget-man narrative unavailable: {e}]"

    payload: dict[str, Any] = {**rollup, "narrative": narrative.strip()}
    row.rollup_json = json.dumps(payload)
    row.updated_at = datetime.utcnow()
    session.add(row)
    session.commit()
    return payload


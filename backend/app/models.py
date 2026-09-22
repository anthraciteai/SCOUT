from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field


def _now() -> datetime:
    return datetime.utcnow()


class Resume(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = "My Resume"
    filename: Optional[str] = None
    text: str = ""
    is_active: bool = True
    kind: Optional[str] = Field(default="company")  # "me" | "company"
    extract_json: Optional[str] = None  # structured profile for the matcher
    extracted_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class TrackedTopic(SQLModel, table=True):
    """A DSIP topic the user is watching / bidding."""
    id: Optional[int] = Field(default=None, primary_key=True)
    topic_id: str = Field(index=True)          # DSIP topicId
    topic_code: Optional[str] = None
    title: Optional[str] = None
    component: Optional[str] = None
    program: Optional[str] = None
    status: str = "watching"                   # pipeline stage (see PIPELINE_STAGES)
    topic_status: Optional[str] = None         # DSIP status (Open / Pre-Release ...)
    notes: str = ""
    outcome: Optional[str] = None              # awarded / not_selected / withdrawn / pending
    raw_json: Optional[str] = None             # snapshot of DSIP topic
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class AnalysisRun(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    topic_id: str = Field(index=True)
    topic_code: Optional[str] = None
    title: Optional[str] = None
    model: str = ""
    resume_id: Optional[int] = None
    # JSON string: {"agents": {name: {...}}, "council": {...}}
    result_json: str = "{}"
    fit_score: Optional[float] = None          # 0-100 council score
    heavy_lift: Optional[float] = None         # 0-10 effort to adapt product (Hewer)
    recommendation: Optional[str] = None       # GO / NO-GO / LEAN GO ...
    created_at: datetime = Field(default_factory=_now)


class Proposal(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    topic_id: Optional[str] = Field(default=None, index=True)
    topic_code: Optional[str] = None
    title: str = "Untitled Proposal"
    content: str = ""
    status: str = "draft"                      # draft / submitted / awarded / not_selected
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class ProposalReview(SQLModel, table=True):
    """Snapshot of a persona review of a proposal. One row per run so the user
    can browse historical reviews (Technical / Military / Researcher lenses)
    without them getting overwritten by later runs."""

    __tablename__ = "proposal_review"

    id: Optional[int] = Field(default=None, primary_key=True)
    proposal_id: int = Field(index=True)
    persona: str = Field(index=True)  # "technical" | "military" | "researcher"
    title: str = ""                    # snapshot of proposal title at review time
    topic_id: Optional[str] = None
    topic_code: Optional[str] = None
    proposal_sha: str = ""             # sha of the reviewed content, so we can flag drift
    proposal_chars: int = 0
    body: str = ""                     # rendered review (markdown-ish)
    model: str = ""
    created_at: datetime = Field(default_factory=_now)


class ProposalTaskPlan(SQLModel, table=True):
    """LLM-extracted, bite-sized task plan derived from the current draft's
    Functional Requirements + Technical Approach. Snapshot per generation so
    users can watch the plan evolve as they write."""

    __tablename__ = "proposal_task_plan"

    id: Optional[int] = Field(default=None, primary_key=True)
    proposal_id: int = Field(index=True)
    proposal_sha: str = ""       # hash of the reviewed draft
    proposal_chars: int = 0
    plan_json: str = "{}"        # {"phases": [...], "tasks": [...], "assumptions": "..."}
    model: str = ""
    created_at: datetime = Field(default_factory=_now)


class ProposalCost(SQLModel, table=True):
    """Per-proposal cost estimate state — the BOM that Dynomite builds
    conversationally, plus the rate assumptions Budget Man rolls up with.
    One row per proposal; upserted."""

    __tablename__ = "proposal_cost"

    id: Optional[int] = Field(default=None, primary_key=True)
    proposal_id: int = Field(index=True, unique=True)
    phase: str = "phase1"                        # "phase1" | "phase2" | "direct_to_phase2"
    bom_json: str = "[]"                         # ordered array of line items
    rates_json: str = "{}"                       # fringe / overhead / g_and_a / fee percentages
    chat_json: str = "[]"                        # Dynomite chat transcript (last N turns)
    rollup_json: Optional[str] = None            # last Budget Man rollup (structured + narrative)
    updated_at: datetime = Field(default_factory=_now)


class Debrief(SQLModel, table=True):
    """Uploaded government feedback / debrief for a proposal that lost."""
    id: Optional[int] = Field(default=None, primary_key=True)
    topic_id: Optional[str] = Field(default=None, index=True)
    proposal_id: Optional[int] = Field(default=None, index=True)
    title: str = "Debrief"
    filename: Optional[str] = None
    extracted_text: str = ""
    analysis: Optional[str] = None             # LLM analysis of the feedback
    created_at: datetime = Field(default_factory=_now)


class OpportunityMatch(SQLModel, table=True):
    """A ranked opportunity from the last matcher scan (not a council run)."""

    __tablename__ = "opportunity_match"

    id: Optional[int] = Field(default=None, primary_key=True)
    topic_id: str = Field(index=True)
    resume_id: Optional[int] = Field(default=None, index=True)
    topic_code: Optional[str] = None
    title: Optional[str] = None
    component: Optional[str] = None
    program: Optional[str] = None
    topic_status: Optional[str] = None
    score: float = 0.0  # 0-100 keyword overlap
    reasons_json: str = "[]"
    queries_json: str = "[]"  # which profile queries retrieved this
    tags_json: str = "[]"
    raw_json: Optional[str] = None
    created_at: datetime = Field(default_factory=_now)


class TopicIndex(SQLModel, table=True):
    """Cached open-window topic. Enriched once per content fingerprint (monthly drop)."""

    __tablename__ = "topic_index"

    topic_id: str = Field(primary_key=True)
    topic_code: Optional[str] = None
    title: Optional[str] = None
    component: Optional[str] = None
    program: Optional[str] = None
    topic_status: Optional[str] = None
    solicitation_title: Optional[str] = None
    fingerprint: str = Field(index=True, default="")
    content_sha: str = ""
    tags_json: str = "{}"
    embedding_json: Optional[str] = None
    raw_json: Optional[str] = None
    open_ms: Optional[int] = Field(default=None, index=True)
    close_ms: Optional[int] = None
    prerelease_ms: Optional[int] = None
    enriched: bool = False
    first_seen_at: datetime = Field(default_factory=_now)
    indexed_at: datetime = Field(default_factory=_now)


class CatalogPass(SQLModel, table=True):
    """One pagination pass over the open DSIP window."""

    __tablename__ = "catalog_pass"

    id: Optional[int] = Field(default=None, primary_key=True)
    pages: int = 0
    listed: int = 0
    new_topics: int = 0
    reused: int = 0
    enriched: int = 0
    newest_open_ms: Optional[int] = None
    embed_model: str = ""
    created_at: datetime = Field(default_factory=_now)


class MatchScan(SQLModel, table=True):
    """Metadata for the latest matcher pass."""

    id: Optional[int] = Field(default=None, primary_key=True)
    resume_id: Optional[int] = Field(default=None, index=True)
    queries_json: str = "[]"
    match_count: int = 0
    model: str = ""
    # Snapshot of the ranking so we can badge "NEW since <last scan>" without
    # replaying scores. Stored as a JSON list of topic_ids (top-50, ordered).
    top_ids_json: str = "[]"
    created_at: datetime = Field(default_factory=_now)


PIPELINE_STAGES = [
    "watching",
    "analyzing",
    "decided_bid",
    "writing",
    "submitted",
    "awarded",
    "not_selected",
]

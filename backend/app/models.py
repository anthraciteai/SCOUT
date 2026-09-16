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


PIPELINE_STAGES = [
    "watching",
    "analyzing",
    "decided_bid",
    "writing",
    "submitted",
    "awarded",
    "not_selected",
]

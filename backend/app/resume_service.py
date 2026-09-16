from typing import Optional

from sqlmodel import Session, select

from .models import Resume


def get_resume_text(session: Session, resume_id: Optional[int]) -> tuple[Optional[int], str]:
    """Return (resume_id, text) for the requested resume, else the active/first one."""
    if resume_id is not None:
        r = session.get(Resume, resume_id)
        if r:
            return r.id, r.text
    r = session.exec(select(Resume).where(Resume.is_active == True)).first()  # noqa: E712
    if r:
        return r.id, r.text
    r = session.exec(select(Resume)).first()
    if r:
        return r.id, r.text
    return None, ""

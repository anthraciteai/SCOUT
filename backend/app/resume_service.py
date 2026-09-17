from typing import Optional

from sqlmodel import Session, select

from .identity import current_identity
from .models import Resume
from .vault import get_vault


def get_me(session: Session) -> Optional[Resume]:
    return session.exec(select(Resume).where(Resume.kind == "me")).first()


def get_company(session: Session) -> Optional[Resume]:
    r = session.exec(
        select(Resume).where(Resume.kind == "company").where(Resume.is_active == True)  # noqa: E712
    ).first()
    if r:
        return r
    r = session.exec(select(Resume).where(Resume.kind == "company")).first()
    if r:
        return r
    # Pre-kind rows (migration default company) still match above.
    return session.exec(select(Resume).where(Resume.kind != "me")).first()


def bundle_text(session: Session) -> tuple[Optional[int], str]:
    """ME + company, labeled. Prefer ME id for analysis rows.

    When a signed-in org user has vault files, those win so Ken/Jake/Matt
    each bring their own toolbox plus the shared company pack.
    """
    ident = current_identity()
    if ident:
        packed = get_vault().bundle_resume(ident)
        if packed.strip():
            me = get_me(session)
            return (me.id if me else None), packed
    me = get_me(session)
    company = get_company(session)
    parts: list[str] = []
    if me and (me.text or "").strip():
        parts.append("=== ME (this person — tools, jobs, stack) ===\n" + me.text)
    if company and (company.text or "").strip():
        if not me or company.id != me.id:
            parts.append("=== COMPANY / PRODUCTS ===\n" + company.text)
    rid = (me.id if me else None) or (company.id if company else None)
    return rid, "\n\n".join(parts)


def get_resume_text(session: Session, resume_id: Optional[int]) -> tuple[Optional[int], str]:
    """Return (resume_id, text). Specific id wins; otherwise ME+company bundle."""
    if resume_id is not None:
        r = session.get(Resume, resume_id)
        if r:
            return r.id, r.text
    return bundle_text(session)

"""Cheap SCOUT ranker: extract a profile, search DSIP, score keyword overlap.

No council agents run here. The LLM is used at most once, to turn a resume into
search queries + keywords. If Ollama is down, a stopword fallback still scans.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Optional

from sqlmodel import Session, select

from . import agents, dsip, ollama_client
from .models import MatchScan, OpportunityMatch, Resume

# Open + pre-release (same as topics.SCOPE_MAP["open"])
_OPEN_CYCLES = ["openTopics"]
_OPEN_STATUSES = [591, 592]

_STOP = {
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "with", "by",
    "from", "as", "at", "is", "are", "was", "were", "be", "been", "being",
    "this", "that", "these", "those", "it", "its", "we", "our", "you", "your",
    "i", "my", "me", "they", "them", "their", "he", "she", "his", "her",
    "have", "has", "had", "do", "does", "did", "will", "would", "can", "could",
    "should", "may", "might", "must", "not", "no", "yes", "if", "then", "than",
    "so", "such", "into", "over", "after", "before", "about", "between",
    "through", "during", "without", "within", "also", "more", "most", "other",
    "new", "used", "using", "use", "including", "include", "based", "work",
    "working", "worked", "experience", "experienced", "skills", "skill",
    "responsible", "responsibilities", "team", "teams", "project", "projects",
    "role", "roles", "years", "year", "strong", "ability", "able", "well",
    "across", "various", "related", "etc", "via", "per", "all", "any",
    "company", "inc", "llc", "ltd", "university", "bachelor", "master",
    "resume", "summary", "objective", "professional", "position", "positions",
}

PROFILE_SYSTEM = (
    "You extract a search profile from a resume or capability statement so it can "
    "be matched against DoD SBIR/STTR topic listings. Be concrete: prefer technologies, "
    "mission domains, and product nouns that would appear in a topic title "
    "(e.g. 'unmanned aerial systems', 'computer vision', 'C-UAS', 'RF sensing') "
    "over generic terms like 'engineering' or 'leadership'.\n"
    "Return ONLY JSON with keys: "
    '{"summary": string, '
    '"skills": [string], '
    '"domains": [string], '
    '"search_queries": [string], '
    '"keywords": [string]}. '
    "search_queries: 3-6 short DSIP search strings (2-4 words each). "
    "keywords: 12-30 lowercase phrases used for overlap scoring."
)


def _strip_html(s: str) -> str:
    return re.sub(r"<[^>]+>", " ", s or "")


def _tokens(text: str) -> list[str]:
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9+\-/]{2,}", (text or "").lower())
    return [w for w in words if w not in _STOP and not w.isdigit()]


def _uniq(items: list[str], limit: Optional[int] = None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in items:
        s = " ".join(str(raw).strip().split())
        if not s:
            continue
        key = s.lower()
        if key in seen or key in _STOP:
            continue
        seen.add(key)
        out.append(s)
        if limit and len(out) >= limit:
            break
    return out


def fallback_profile(resume_text: str) -> dict[str, Any]:
    """Deterministic profile when the LLM is unavailable."""
    toks = _tokens(resume_text)
    counts: dict[str, int] = {}
    for t in toks:
        counts[t] = counts.get(t, 0) + 1
    ranked = sorted(counts, key=lambda w: (-counts[w], -len(w), w))
    keywords = [w for w in ranked if 3 < len(w) < 24][:24]
    queries: list[str] = []
    for i in range(0, min(len(keywords), 10), 2):
        pair = " ".join(keywords[i : i + 2])
        if pair:
            queries.append(pair)
    return {
        "summary": "Fallback keyword profile (LLM extract unavailable).",
        "skills": keywords[:12],
        "domains": [],
        "search_queries": queries[:5] or keywords[:3],
        "keywords": keywords,
        "_source": "fallback",
    }


async def extract_profile(resume_text: str) -> dict[str, Any]:
    text = (resume_text or "").strip()
    if not text:
        return fallback_profile("")
    try:
        out = await ollama_client.chat(
            PROFILE_SYSTEM,
            "RESUME / CAPABILITY STATEMENT:\n"
            f"{text[:8000]}\n\nRespond with ONLY the JSON described in your instructions.",
            temperature=0.2,
            format_json=True,
        )
        data = agents._safe_json(out)
        if data.get("raw") or not isinstance(data, dict):
            return fallback_profile(text)
        skills = _uniq([str(x) for x in (data.get("skills") or [])], 20)
        domains = _uniq([str(x) for x in (data.get("domains") or [])], 12)
        queries = _uniq([str(x) for x in (data.get("search_queries") or [])], 6)
        keywords = _uniq(
            [str(x) for x in (data.get("keywords") or [])] + skills + domains,
            40,
        )
        if not queries and not keywords:
            return fallback_profile(text)
        if not queries:
            queries = keywords[:4]
        return {
            "summary": str(data.get("summary") or "")[:800],
            "skills": skills,
            "domains": domains,
            "search_queries": queries,
            "keywords": keywords,
            "_source": "llm",
        }
    except Exception:
        return fallback_profile(text)


def canned_queries(resume_text: str) -> list[str]:
    """Pull bullet lines under a '## Scout queries' heading, if present."""
    text = resume_text or ""
    lower = text.lower()
    marker = "## scout queries"
    idx = lower.find(marker)
    if idx == -1:
        return []
    rest = text[idx + len(marker) :]
    nxt = re.search(r"\n##\s+", rest)
    block = rest[: nxt.start()] if nxt else rest
    found: list[str] = []
    for line in block.splitlines():
        s = line.strip().lstrip("-*").strip()
        if s:
            found.append(s)
    return _uniq(found, 10)


def overlay_canned(resume_text: str, profile: dict[str, Any]) -> dict[str, Any]:
    extra = canned_queries(resume_text)
    if not extra:
        return profile
    tokens: list[str] = list(extra)
    for phrase in extra:
        for tok in re.findall(r"[A-Za-z][A-Za-z0-9+\-]{1,}", phrase):
            if tok.lower() not in _STOP and len(tok) >= 3:
                tokens.append(tok)
    profile["search_queries"] = _uniq(extra, 8)
    profile["keywords"] = _uniq(tokens + list(profile.get("keywords") or []), 40)
    profile["_canned"] = True
    return profile


def profile_is_stale(resume: Resume) -> bool:
    if not resume.extract_json:
        return True
    if resume.extracted_at is None:
        return True
    if resume.updated_at and resume.extracted_at < resume.updated_at:
        return True
    return False


async def ensure_profile(session: Session, resume: Resume, force: bool = False) -> dict[str, Any]:
    if not force and not profile_is_stale(resume):
        try:
            return json.loads(resume.extract_json or "{}")
        except json.JSONDecodeError:
            pass
    text = resume.text or ""
    # Packs with explicit Scout queries skip the LLM so scheduled scans stay fast.
    if canned_queries(text) and not force:
        profile = overlay_canned(text, fallback_profile(text))
    else:
        profile = overlay_canned(text, await extract_profile(text))
    resume.extract_json = json.dumps(profile)
    resume.extracted_at = datetime.utcnow()
    session.add(resume)
    session.commit()
    session.refresh(resume)
    return profile


def _topic_blob(topic: dict[str, Any]) -> tuple[str, str]:
    title = " ".join(
        str(topic.get(k) or "")
        for k in ("topicTitle", "title", "topicCode", "finalTopicCode")
    )
    body_parts = [
        topic.get("keywords"),
        topic.get("objective"),
        topic.get("topicObjective"),
        topic.get("description"),
        topic.get("topicDescription"),
        topic.get("component"),
        topic.get("command"),
        topic.get("technologyAreas"),
        topic.get("modernizationPriorities"),
        topic.get("program"),
    ]
    body = " ".join(_strip_html(str(p)) for p in body_parts if p)
    return title, f"{title} {body}"


def _contains(haystack: str, needle: str) -> bool:
    n = needle.strip().lower()
    if len(n) < 3:
        return False
    if " " in n or "-" in n or "/" in n:
        return n in haystack
    return bool(re.search(rf"\b{re.escape(n)}\b", haystack))


def score_topic(topic: dict[str, Any], profile: dict[str, Any]) -> tuple[float, list[str]]:
    title, blob = _topic_blob(topic)
    hay_title = title.lower()
    hay_all = blob.lower()
    terms = _uniq(
        list(profile.get("keywords") or [])
        + list(profile.get("skills") or [])
        + list(profile.get("domains") or []),
        40,
    )
    hits: list[str] = []
    title_hits: list[str] = []
    for term in terms:
        if _contains(hay_all, term):
            hits.append(term)
        if _contains(hay_title, term):
            title_hits.append(term)
    if not terms:
        return 0.0, []
    overlap = len(hits) / max(len(terms), 1)
    title_frac = min(len(title_hits) / 3.0, 1.0)
    score = 70.0 * overlap + 30.0 * title_frac
    score = max(0.0, min(100.0, round(score, 1)))
    reasons: list[str] = []
    for t in title_hits[:4]:
        reasons.append(f"Title mentions “{t}”")
    for t in hits:
        if t not in title_hits:
            reasons.append(f"Matched “{t}”")
        if len(reasons) >= 6:
            break
    return score, reasons


def _topic_id(topic: dict[str, Any]) -> Optional[str]:
    tid = topic.get("topicId") or topic.get("id")
    return str(tid) if tid else None


async def _search_query(query: str, size: int = 25, page: int = 0) -> list[dict[str, Any]]:
    param = dsip.build_search_param(
        search_text=query or None,
        solicitation_cycle_names=_OPEN_CYCLES,
        topic_release_status=_OPEN_STATUSES,
        sort_by="finalTopicCode,asc",
    )
    res = await dsip.search_topics(param, size=size, page=page)
    data = res.get("data") if isinstance(res, dict) else res
    if not isinstance(data, list):
        return []
    return [t for t in data if isinstance(t, dict)]


def _ingest(
    found: dict[str, dict[str, Any]], rows: list[dict[str, Any]], label: str
) -> None:
    for topic in rows:
        tid = _topic_id(topic)
        if not tid:
            continue
        if tid not in found:
            found[tid] = {"topic": topic, "queries": [label]}
        elif label not in found[tid]["queries"]:
            found[tid]["queries"].append(label)


async def gather_candidates(queries: list[str], size_per: int = 25) -> dict[str, dict[str, Any]]:
    """topic_id -> {topic, queries: [str]}.

    Always score a wide open-window sample, then overlay targeted DSIP searches.
    """
    found: dict[str, dict[str, Any]] = {}
    for page in range(4):
        try:
            rows = await _search_query("", size=50, page=page)
        except Exception:
            break
        if not rows:
            break
        _ingest(found, rows, "(open window)")
        if len(rows) < 50:
            break
    for q in _uniq(queries, 8):
        try:
            rows = await _search_query(q, size=size_per, page=0)
        except Exception:
            continue
        _ingest(found, rows, q)
    return found


def persist_scan(
    session: Session,
    resume: Resume,
    profile: dict[str, Any],
    scored: list[dict[str, Any]],
    model: str,
) -> MatchScan:
    old = session.exec(
        select(OpportunityMatch).where(OpportunityMatch.resume_id == resume.id)
    ).all()
    for row in old:
        session.delete(row)

    for item in scored:
        topic = item["topic"]
        row = OpportunityMatch(
            topic_id=item["topic_id"],
            resume_id=resume.id,
            topic_code=topic.get("topicCode") or topic.get("finalTopicCode"),
            title=topic.get("topicTitle") or topic.get("title"),
            component=topic.get("component"),
            program=topic.get("program"),
            topic_status=topic.get("topicStatus"),
            score=item["score"],
            reasons_json=json.dumps(item["reasons"]),
            queries_json=json.dumps(item["queries"]),
            raw_json=json.dumps(topic),
        )
        session.add(row)

    scan = MatchScan(
        resume_id=resume.id,
        queries_json=json.dumps(profile.get("search_queries") or []),
        match_count=len(scored),
        model=model,
    )
    session.add(scan)
    session.commit()
    session.refresh(scan)
    return scan


def serialize_match(row: OpportunityMatch) -> dict[str, Any]:
    try:
        reasons = json.loads(row.reasons_json or "[]")
    except json.JSONDecodeError:
        reasons = []
    try:
        queries = json.loads(row.queries_json or "[]")
    except json.JSONDecodeError:
        queries = []
    try:
        raw = json.loads(row.raw_json or "{}")
    except json.JSONDecodeError:
        raw = {}
    return {
        "id": row.id,
        "topic_id": row.topic_id,
        "topic_code": row.topic_code,
        "title": row.title,
        "component": row.component,
        "program": row.program,
        "topic_status": row.topic_status,
        "score": row.score,
        "reasons": reasons,
        "queries": queries,
        "topic": raw,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


async def run_scan(session: Session, resume: Resume, force_extract: bool = False) -> dict[str, Any]:
    profile = await ensure_profile(session, resume, force=force_extract)
    model = ""
    try:
        model = await ollama_client.resolve_model()
    except Exception:
        model = profile.get("_source") or ""

    queries = list(profile.get("search_queries") or [])
    found = await gather_candidates(queries)
    if not found:
        raise RuntimeError(
            "DSIP returned no topics for the profile queries. Check the DSIP proxy and try again."
        )
    scored: list[dict[str, Any]] = []
    for tid, bundle in found.items():
        topic = bundle["topic"]
        score, reasons = score_topic(topic, profile)
        targeted = [q for q in bundle["queries"] if not str(q).startswith("(open")]
        if targeted:
            score = min(100.0, round(score + 8.0, 1))
            reasons.append("Search: " + "; ".join(targeted[:2]))
        elif reasons:
            pass
        scored.append(
            {
                "topic_id": tid,
                "topic": topic,
                "score": score,
                "reasons": reasons[:8],
                "queries": bundle["queries"],
            }
        )
    scored.sort(key=lambda x: (-x["score"], x.get("topic_code") or ""))
    # Keep anything with a real overlap signal, cap the inbox.
    kept = [s for s in scored if s["score"] >= 15][:40]
    if not kept:
        kept = [s for s in scored if s["score"] > 0][:20]

    scan = persist_scan(session, resume, profile, kept, model)
    rows = session.exec(
        select(OpportunityMatch)
        .where(OpportunityMatch.resume_id == resume.id)
        .order_by(OpportunityMatch.score.desc())
    ).all()
    return {
        "profile": profile,
        "scanned_at": scan.created_at.isoformat(),
        "queries": json.loads(scan.queries_json or "[]"),
        "match_count": scan.match_count,
        "model": scan.model,
        "matches": [serialize_match(r) for r in rows],
    }

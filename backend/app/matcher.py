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

from . import agents, catalog, dsip, ollama_client
from .identity import current_identity
from .models import MatchScan, OpportunityMatch, Resume
from .config import settings
from .vault import get_vault

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
        profile = {
            "summary": str(data.get("summary") or "")[:800],
            "skills": skills,
            "domains": domains,
            "search_queries": queries,
            "keywords": keywords,
            "phrases": _uniq(keywords + skills + domains, 40),
            "_source": "llm",
        }
        try:
            vec = await ollama_client.embed(catalog.embed_text(profile["phrases"], profile["summary"]))
            if vec:
                profile["_embedding"] = vec
        except Exception:
            pass
        return profile
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


def _bundle_for(user_id: str, company_id: str) -> str:
    """ME + mission + products for a specific (user, company). Same layout as
    `Vault.bundle_resume` but without requiring the caller's identity."""
    v = get_vault()
    parts: list[str] = []
    me = v.read_text(f"users/{user_id}/me.md").strip()
    if me:
        parts.append(f"=== ME (this person — tools, jobs, stack) ===\n{me}")
    mission = v.read_text(f"companies/{company_id}/mission.txt").strip()
    products = v.read_text(f"companies/{company_id}/products.md").strip()
    company = "\n\n".join(p for p in (mission, products) if p)
    if company:
        parts.append(f"=== COMPANY / PRODUCTS ===\n{company}")
    return "\n\n".join(parts)


def _company_only_text(company_id: str) -> str:
    v = get_vault()
    mission = v.read_text(f"companies/{company_id}/mission.txt").strip()
    products = v.read_text(f"companies/{company_id}/products.md").strip()
    parts: list[str] = []
    if mission:
        parts.append(f"=== COMPANY MISSION ===\n{mission}")
    if products:
        parts.append(f"=== COMPANY / PRODUCTS ===\n{products}")
    return "\n\n".join(parts)


def _profile_source(
    resume: Resume,
    *,
    mode: str = "me",
    employee_id: Optional[str] = None,
    include_company: bool = True,
) -> tuple[str, str, dict[str, str]]:
    """Return (llm_text, tag_text, breakdown).

    Modes:
      - "me"        : signed-in user's bundle (their ME + company).
      - "employee"  : a specific coworker's bundle (their ME + company).
      - "company"   : just the company pack, no personal ME.

    `include_company=False` on "me" or "employee" trims to just the personal
    ME text — useful for "rank me as-if I had no company", eg a solo bid.
    """
    ident = current_identity()
    kind = (resume.kind or "company").lower()
    raw = resume.text or ""
    breakdown: dict[str, str] = {"kind": kind, "mode": mode, "include_company": include_company}
    v = get_vault()

    if mode == "company":
        cid = (ident.company_id if ident else None) or settings.default_company
        text = _company_only_text(cid)
        if text:
            breakdown["source"] = "company"
            breakdown["company_id"] = cid
            return text, text, breakdown
        breakdown["source"] = "raw"
        return raw, raw, breakdown

    if mode == "employee" and employee_id:
        uid = employee_id.strip().lower()
        cid = (ident.company_id if ident else None) or settings.default_company
        # Auth check — only same-company members can rank-as another employee.
        if ident and not v.exists(v.employee_key(cid, uid)):
            raise ValueError(f"{uid} is not in {cid}")
        text = _bundle_for(uid, cid) if include_company else v.read_text(f"users/{uid}/me.md").strip()
        if text:
            breakdown["source"] = "employee_bundle" if include_company else "employee_me"
            breakdown["company_id"] = cid
            breakdown["user_id"] = uid
            return text, text, breakdown
        breakdown["source"] = "raw"
        return raw, raw, breakdown

    # Default: "me" — signed-in user's own bundle.
    if ident and kind == "me":
        try:
            if include_company:
                bundle = v.bundle_resume(ident).strip()
            else:
                bundle = v.read_text(f"users/{ident.user_id}/me.md").strip() or raw
        except Exception:
            bundle = ""
        if bundle:
            breakdown["source"] = "bundle" if include_company else "me_only"
            breakdown["company_id"] = ident.company_id
            breakdown["user_id"] = ident.user_id
            return bundle, raw, breakdown
    breakdown["source"] = "raw"
    return raw, raw, breakdown


async def ensure_profile(
    session: Session,
    resume: Resume,
    force: bool = False,
    *,
    mode: str = "me",
    employee_id: Optional[str] = None,
    include_company: bool = True,
) -> dict[str, Any]:
    # Overrides ALWAYS force a re-extract because the cached profile came
    # from a different source text.
    override = mode != "me" or not include_company
    if not force and not override and not profile_is_stale(resume):
        try:
            return json.loads(resume.extract_json or "{}")
        except json.JSONDecodeError:
            pass
    llm_text, tag_text, breakdown = _profile_source(
        resume, mode=mode, employee_id=employee_id, include_company=include_company,
    )
    # Packs with explicit Scout queries skip the LLM so scheduled scans stay fast.
    if canned_queries(llm_text) and not force:
        profile = overlay_canned(llm_text, fallback_profile(llm_text))
    else:
        profile = overlay_canned(llm_text, await extract_profile(llm_text))
    profile["_source_breakdown"] = breakdown
    resume.extract_json = json.dumps(profile)
    resume.extracted_at = datetime.utcnow()
    session.add(resume)
    session.commit()
    session.refresh(resume)
    ident = current_identity()
    phrases = {
        "phrases": list(profile.get("phrases") or profile.get("keywords") or []),
        "kinds": {},
        "source": profile.get("_source") or "",
    }
    try:
        if (resume.kind or "company") == "me" and ident:
            # Store the bundled tags under this user's resume version so
            # score_catalog_row's side_phrases pick them up on every match.
            catalog.write_resume_tags(ident.user_id, phrases, tag_text, kind="me")
        else:
            cid = (ident.company_id if ident else None) or settings.default_company
            catalog.write_company_tags(cid, phrases)
    except Exception:
        pass
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


# Tokens that match almost every topic in the DoD UAS / defense corpus. They
# carry little signal on their own, so they're heavily downweighted in scoring
# and never shown as a match reason. (A title ending in "…for Unmanned Aerial
# Systems" should NOT out-rank a topic that is actually about your tech.)
_DOMAIN_STOP = {
    "unmanned", "aerial", "air", "system", "systems", "vehicle", "vehicles",
    "technology", "technologies", "capability", "capabilities", "solution",
    "solutions", "platform", "platforms", "device", "devices", "data",
    "software", "hardware", "sensor", "sensors", "development", "design",
    "advanced", "novel", "defense", "military", "operational", "mission",
    "performance", "support", "integration", "analysis", "management", "small",
    "based", "enabled", "autonomous",
}


def _term_weight(term: str) -> float:
    """How discriminating a profile term is. Generic corpus words barely count;
    specific multi-word phrases and acronyms (C-UAS, PX4, ROS2, TAK) count more.
    This is a cheap stand-in for IDF without needing a corpus."""
    t = term.strip()
    low = t.lower()
    if low in _DOMAIN_STOP:
        return 0.3
    if " " in low or "-" in low or "/" in low:
        words = [w for w in re.split(r"[ \-/]+", low) if w]
        if words and all(w in _DOMAIN_STOP for w in words):
            return 0.4  # phrase built only from generic words, e.g. "unmanned aerial systems"
        return 2.0
    if len(t) <= 6 and (t.isupper() or any(c.isdigit() for c in t)):
        return 1.6  # acronym / model number: PX4, TAK, ROS2, LLM
    return 1.0


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
    if not terms:
        return 0.0, []
    total_w = sum(_term_weight(t) for t in terms)
    hit_w = 0.0
    title_w = 0.0
    hits: list[str] = []
    title_hits: list[str] = []
    for term in terms:
        w = _term_weight(term)
        if _contains(hay_all, term):
            hits.append(term)
            hit_w += w
        if _contains(hay_title, term):
            title_hits.append(term)
            title_w += w
    # Reward absolute specific signal, not fraction-of-whole-profile (dividing
    # by the full profile size punishes people with broad resumes). Cap the
    # denominator so matching a handful of your *strong* terms already reads as
    # a strong match, while a pile of generic-word hits does not.
    denom = min(max(total_w, 1.0), 10.0)
    overlap = min(1.0, hit_w / denom)
    title_frac = min(title_w / 4.0, 1.0)
    score = 65.0 * overlap + 35.0 * title_frac
    score = max(0.0, min(100.0, round(score, 1)))
    # Cite specific matches only — generic corpus words (weight < 1) are noise.
    reasons: list[str] = []
    for t in title_hits:
        if _term_weight(t) >= 1.0:
            reasons.append(f"Title mentions “{t}”")
        if len(reasons) >= 4:
            break
    for t in hits:
        if t in title_hits or _term_weight(t) < 1.0:
            continue
        reasons.append(f"Matched “{t}”")
        if len(reasons) >= 6:
            break
    return score, reasons


def _cos_signal(cos: float) -> float:
    """Stretch the meaningful band of embedding cosine into 0..1.

    nomic-embed-text parks even unrelated topic/profile pairs around 0.42 and
    tops out near ~0.80 for a genuinely on-point match, so raw cosine*100 badly
    understates real fit (and compresses everything into a narrow mid band).
    Map [0.42, 0.80] -> [0, 1], clamped."""
    lo, hi = 0.42, 0.80
    return max(0.0, min(1.0, (cos - lo) / (hi - lo)))


def score_catalog_row(row, profile: dict[str, Any]) -> tuple[float, list[str], list[str]]:
    """Blend keyword overlap, open-vocab phrase Jaccard, and optional cosine."""
    try:
        topic = json.loads(row.raw_json or "{}")
    except json.JSONDecodeError:
        topic = {}
    kw_score, reasons = score_topic(topic, profile)
    tags = catalog.parse_tags(row.tags_json)
    phrases = [str(p) for p in (tags.get("phrases") or []) if p]
    ident = current_identity()
    side = catalog.load_side_phrases(
        (ident.company_id if ident else None) or settings.default_company,
        ident.user_id if ident else None,
    )
    prof = (
        list(profile.get("phrases") or [])
        + list(profile.get("keywords") or [])
        + list(profile.get("skills") or [])
        + list(profile.get("domains") or [])
        + list(side)
    )
    shared = catalog.expand_phrases(prof) & catalog.expand_phrases(phrases)
    jac = catalog.jaccard(catalog.expand_phrases(prof), catalog.expand_phrases(phrases))
    tag_score = round(100.0 * jac, 1)
    vec_t = catalog.parse_embedding(row.embedding_json)
    vec_r = profile.get("_embedding") if isinstance(profile.get("_embedding"), list) else None
    cos = catalog.cosine(vec_t, vec_r)
    if cos is None:
        score = 0.6 * kw_score + 0.4 * tag_score
    else:
        # Lean on semantic similarity: it catches "Counter-Unmanned Aerial
        # Systems" ≈ "C-UAS" that literal keyword overlap misses, and resists
        # the generic-word inflation that keyword overlap is prone to. The
        # cosine is stretched first (see _cos_signal) because nomic-embed-text
        # never drops near 0 — raw cosine badly understates real fit.
        cs = _cos_signal(cos)
        score = 0.4 * kw_score + 0.15 * tag_score + 0.45 * (cs * 100.0)
        reasons.append(f"Embedding {cos:.2f}")
    for p in list(shared)[:4]:
        reasons.insert(0, f"Tag “{p}”")
    score = max(0.0, min(100.0, round(score, 1)))
    return score, reasons[:8], phrases


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
            tags_json=json.dumps(item.get("phrases") or []),
            raw_json=json.dumps(topic),
        )
        session.add(row)

    top_ids = [item["topic_id"] for item in scored[:50] if item.get("topic_id")]
    scan = MatchScan(
        resume_id=resume.id,
        queries_json=json.dumps(profile.get("search_queries") or []),
        match_count=len(scored),
        model=model,
        top_ids_json=json.dumps(top_ids),
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
    try:
        phrases = json.loads(row.tags_json or "[]")
    except json.JSONDecodeError:
        phrases = []
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
        "phrases": phrases if isinstance(phrases, list) else [],
        "topic": raw,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


async def run_scan(
    session: Session,
    resume: Resume,
    force_extract: bool = False,
    *,
    mode: str = "me",
    employee_id: Optional[str] = None,
    include_company: bool = True,
) -> dict[str, Any]:
    from . import jobs  # local import avoids a cycle (jobs imports identity only)

    jobs.progress("Reading your resume & building a search profile…", 10)
    profile = await ensure_profile(
        session,
        resume,
        force=force_extract,
        mode=mode,
        employee_id=employee_id,
        include_company=include_company,
    )
    model = ""
    try:
        model = await ollama_client.resolve_model()
    except Exception:
        model = profile.get("_source") or ""

    queries = list(profile.get("search_queries") or [])
    catalog_info: dict[str, Any] = {}
    scored: list[dict[str, Any]] = []
    # Inbox ranking must list the whole open window. LLM phrase enrich is a
    # separate catalog pass — do not block Scan on 24 Ollama calls.
    jobs.progress("Refreshing the open-topic catalog from DSIP…", 30)
    try:
        catalog_info = await catalog.refresh_catalog(session, enrich_limit=0)
    except Exception:
        catalog_info = {"error": "catalog refresh failed; using live DSIP sample"}
    rows = catalog.open_rows(session, catalog_info.get("open_ids") or [])
    if rows:
        jobs.progress(f"Scoring {len(rows)} open topics against your profile…", 60)
        if not profile.get("_embedding"):
            try:
                vec = await ollama_client.embed(
                    catalog.embed_text(
                        list(profile.get("phrases") or profile.get("keywords") or []),
                        str(profile.get("summary") or ""),
                    )
                )
                if vec:
                    profile["_embedding"] = vec
            except Exception:
                pass
        for row in rows:
            score, reasons, phrases = score_catalog_row(row, profile)
            try:
                topic = json.loads(row.raw_json or "{}")
            except json.JSONDecodeError:
                topic = {}
            if not topic:
                topic = {
                    "topicId": row.topic_id,
                    "topicTitle": row.title,
                    "topicCode": row.topic_code,
                    "component": row.component,
                    "program": row.program,
                    "topicStatus": row.topic_status,
                    "topicStartDate": row.open_ms,
                    "topicEndDate": row.close_ms,
                }
            scored.append(
                {
                    "topic_id": row.topic_id,
                    "topic": topic,
                    "score": score,
                    "reasons": reasons,
                    "queries": queries[:4] or ["(catalog)"],
                    "phrases": phrases,
                }
            )
    else:
        found = await gather_candidates(queries)
        if not found:
            raise RuntimeError(
                "DSIP returned no topics for the profile queries. Check the DSIP proxy and try again."
            )
        for tid, bundle in found.items():
            topic = bundle["topic"]
            score, reasons = score_topic(topic, profile)
            targeted = [q for q in bundle["queries"] if not str(q).startswith("(open")]
            if targeted:
                score = min(100.0, round(score + 8.0, 1))
                reasons.append("Search: " + "; ".join(targeted[:2]))
            scored.append(
                {
                    "topic_id": tid,
                    "topic": topic,
                    "score": score,
                    "reasons": reasons[:8],
                    "queries": bundle["queries"],
                    "phrases": [],
                }
            )

    if not scored:
        raise RuntimeError(
            "DSIP returned no topics for the profile queries. Check the DSIP proxy and try again."
        )
    # Show the honest ABSOLUTE score — no forced rescale to 100. The weighted
    # overlap + capped denominator (see score_topic) keeps real spread without
    # pinning the top match to a fake "100% match". Ordering is unchanged.
    scored.sort(key=lambda x: (-x["score"], str(x.get("topic_code") or "")))
    # Anyone can bid anything — rank high to low, do not hide the long tail.
    kept = scored

    scan = persist_scan(session, resume, profile, kept, model)
    catalog_info["enrich_started"] = catalog.schedule_enrich_all()
    catalog_info["enrich_running"] = catalog.enrich_running()
    rows = session.exec(
        select(OpportunityMatch)
        .where(OpportunityMatch.resume_id == resume.id)
        .order_by(OpportunityMatch.score.desc())
    ).all()
    pub = {k: v for k, v in profile.items() if k != "_embedding"}
    return {
        "profile": pub,
        "scanned_at": scan.created_at.isoformat(),
        "queries": json.loads(scan.queries_json or "[]"),
        "match_count": scan.match_count,
        "model": scan.model,
        "catalog": {k: v for k, v in catalog_info.items() if k != "open_ids"},
        "matches": [serialize_match(r) for r in rows],
    }

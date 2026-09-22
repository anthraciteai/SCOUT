"""Incremental open-window catalog: paginate DSIP, cache tags, optional embeddings.

Monthly solicitation drops show up as new topic_ids / changed fingerprints.
We only call details + LLM on the delta. Phrases are open vocabulary — kinds
are optional labels, never a closed enum.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
from datetime import datetime
from typing import Any, Optional

from sqlmodel import Session, select

from . import agents, dsip, ollama_client
from .config import settings
from .models import CatalogPass, TopicIndex

TAG_SYSTEM = (
    "You extract matching phrases from a DoD SBIR/STTR topic so a small-business "
    "capability statement can be compared to it. OPEN VOCABULARY: invent precise "
    "phrases from the text. Do not force the topic into a fixed taxonomy. If it is "
    "about something unusual, say that unusual thing.\n"
    "Return ONLY JSON: "
    '{"phrases": [string], '
    '"kinds": {"<phrase>": "mission|platform|capability|constraint|customer|other"}}.\n'
    "phrases: 8-25 short phrases (1-5 words). Include official keywords plus terms "
    "the listing buried in the objective/description. "
    "kinds is OPTIONAL grouping for display. Every phrase must stay in phrases even "
    "if you do not know a kind — use other. Never drop a phrase because it does not fit."
)

# Additive synonyms so Ken's ULog still hits "flight log" without a rigid enum.
_ALIASES: dict[str, list[str]] = {
    "ulog": ["flight log", "ulog", "px4 log", "black box"],
    "tak": ["tak", "atak", "wintak"],
    "cop": ["cop", "common operating picture", "situational awareness"],
    "ddil": ["ddil", "disconnected", "denied", "intermittent", "air-gapped", "air gapped"],
    "cuas": ["c-uas", "cuas", "counter-uas", "counter uas"],
    "jetson": ["jetson", "orin", "edge gpu", "nvidia"],
    "ollama": ["ollama", "on-device llm", "local llm", "air-gapped llm"],
    "mqtt": ["mqtt", "message bus"],
    "px4": ["px4", "autopilot", "ardupilot"],
}


def _strip_html(s: str) -> str:
    return re.sub(r"<[^>]+>", " ", s or "")


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def fingerprint(topic: dict[str, Any]) -> str:
    """Cheap search-row identity. Changes when a round amends title/dates/keywords."""
    keys = (
        "topicId",
        "topicTitle",
        "title",
        "topicCode",
        "finalTopicCode",
        "topicStatus",
        "keywords",
        "topicStartDate",
        "topicEndDate",
        "topicPreReleaseStartDate",
        "solicitationTitle",
    )
    blob = "|".join(str(topic.get(k) or "") for k in keys)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def content_sha(topic: dict[str, Any]) -> str:
    blob = "|".join(
        _strip_html(str(topic.get(k) or ""))
        for k in (
            "topicTitle",
            "title",
            "keywords",
            "objective",
            "topicObjective",
            "description",
            "topicDescription",
        )
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _ms(topic: dict[str, Any], *keys: str) -> Optional[int]:
    for k in keys:
        v = topic.get(k)
        if isinstance(v, (int, float)) and v > 0:
            return int(v)
        if isinstance(v, str) and v.isdigit():
            return int(v)
    return None


_STOP = {
    "the", "and", "for", "with", "from", "that", "this", "are", "not", "our", "you",
    "your", "into", "onto", "than", "then", "also", "only", "have", "has", "was",
    "were", "will", "can", "may", "any", "all", "use", "used", "using", "via",
}


def fallback_phrases(topic: dict[str, Any]) -> dict[str, Any]:
    """No LLM: keywords, alias hits, product names — not a dump of every token."""
    phrases: list[str] = []
    raw_kw = topic.get("keywords") or ""
    if isinstance(raw_kw, list):
        phrases.extend(str(x) for x in raw_kw)
    else:
        phrases.extend(re.split(r"[,;|/]+", str(raw_kw)))
    for k in ("component", "command", "program", "technologyAreas", "modernizationPriorities"):
        v = topic.get(k)
        if isinstance(v, list):
            phrases.extend(str(x) for x in v)
        elif v:
            phrases.append(str(v))
    title = str(topic.get("topicTitle") or topic.get("title") or "")
    phrases.extend(re.findall(r"[A-Za-z][A-Za-z0-9+\-]{2,}", title))
    blob = _strip_html(
        " ".join(
            str(topic.get(k) or "")
            for k in ("description", "objective", "topicObjective", "topicDescription")
        )
    )
    lower = blob.lower()
    for syns in _ALIASES.values():
        if any(s.lower() in lower for s in syns):
            phrases.append(syns[0])
    phrases.extend(re.findall(r"\*\*([^*]{2,40})\*\*", blob))
    cleaned: list[str] = []
    seen: set[str] = set()
    for p in phrases:
        s = " ".join(str(p).strip().split())
        key = _norm(s)
        if len(key) < 3 or key in seen or key in _STOP:
            continue
        seen.add(key)
        cleaned.append(s[:60])
        if len(cleaned) >= 24:
            break
    return {"phrases": cleaned, "kinds": {}, "source": "fallback"}


async def extract_phrases(topic: dict[str, Any]) -> dict[str, Any]:
    obj = _strip_html(str(topic.get("objective") or topic.get("topicObjective") or ""))
    desc = _strip_html(str(topic.get("description") or topic.get("topicDescription") or ""))
    title = str(topic.get("topicTitle") or topic.get("title") or "")
    if len(obj) + len(desc) < 80:
        return fallback_phrases(topic)
    prompt = (
        f"TITLE: {title}\n"
        f"COMPONENT: {topic.get('component') or ''}\n"
        f"DSIP KEYWORDS: {topic.get('keywords') or ''}\n"
        f"OBJECTIVE:\n{obj[:2500]}\n\n"
        f"DESCRIPTION:\n{desc[:3500]}\n\n"
        "Respond with ONLY the JSON described."
    )
    try:
        out = await ollama_client.chat(TAG_SYSTEM, prompt, temperature=0.1, format_json=True)
        data = agents._safe_json(out)
        if not isinstance(data, dict) or data.get("raw"):
            return fallback_phrases(topic)
        phrases = []
        seen: set[str] = set()
        for p in data.get("phrases") or []:
            s = " ".join(str(p).strip().split())
            key = _norm(s)
            if len(key) < 3 or key in seen:
                continue
            seen.add(key)
            phrases.append(s[:80])
        kinds = {}
        if isinstance(data.get("kinds"), dict):
            kinds = {str(k): str(v) for k, v in data["kinds"].items() if k}
        if not phrases:
            return fallback_phrases(topic)
        fb = fallback_phrases(topic)
        for p in fb["phrases"]:
            key = _norm(p)
            if key not in seen:
                phrases.append(p)
                seen.add(key)
        return {"phrases": phrases[:30], "kinds": kinds, "source": "llm"}
    except Exception:
        return fallback_phrases(topic)


def expand_phrases(phrases: list[str]) -> set[str]:
    out: set[str] = set()
    for p in phrases or []:
        n = _norm(p)
        if n:
            out.add(n)
        for canon, alts in _ALIASES.items():
            if canon in n or any(_norm(a) in n or n in _norm(a) for a in alts):
                out.add(canon)
                out.update(_norm(a) for a in alts if _norm(a))
    return out


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / max(len(a | b), 1)


def cosine(a: Optional[list[float]], b: Optional[list[float]]) -> Optional[float]:
    if not a or not b or len(a) != len(b):
        return None
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return None
    return max(0.0, min(1.0, dot / (na * nb)))


def embed_text(phrases: list[str], title: str = "", extra: str = "") -> str:
    return " ".join([title] + list(phrases or []) + [extra])[:4000]


def parse_tags(raw: str) -> dict[str, Any]:
    try:
        obj = json.loads(raw or "{}")
    except json.JSONDecodeError:
        obj = {}
    if not isinstance(obj, dict):
        obj = {}
    obj.setdefault("phrases", [])
    obj.setdefault("kinds", {})
    return obj


def parse_embedding(raw: Optional[str]) -> Optional[list[float]]:
    if not raw:
        return None
    try:
        vec = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if isinstance(vec, list) and vec and isinstance(vec[0], (int, float)):
        return [float(x) for x in vec]
    return None


def _tag_pack(tags: dict[str, Any], extra: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    body = {
        "phrases": list(tags.get("phrases") or []),
        "kinds": tags.get("kinds") or {},
        "source": tags.get("source") or "",
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }
    if extra:
        body.update(extra)
    return body


def write_topic_tags(topic_id: str, tags: dict[str, Any], fingerprint: str = "") -> None:
    """sbirs/{sbir_id}/tags.json — existence means this solicitation was tagged."""
    from .vault import get_vault

    v = get_vault()
    pack = _tag_pack(
        tags,
        {
            "fingerprint": fingerprint,
            "dsip_keywords": tags.get("dsip_keywords") or "",
            "topic_id": topic_id,
        },
    )
    v.write_json(v.topic_tags_key(topic_id), pack)


def write_company_tags(company_id: str, tags: dict[str, Any]) -> None:
    from .vault import get_vault

    v = get_vault()
    v.write_json(v.company_tags_key(company_id), _tag_pack(tags))


def write_resume_tags(user_id: str, tags: dict[str, Any], text: str, kind: str = "me") -> str:
    """Bytes at resume/v/{sha}/tags.json. Live tags.json is a pointer — existence means tagged."""
    from .vault import get_vault

    sha = hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]
    v = get_vault()
    pack = _tag_pack(tags, {"sha": sha, "kind": kind})
    v.write_json(v.resume_tags_key(user_id, sha), pack)
    pointer = {"sha": sha, "kind": kind, "updated_at": pack["updated_at"]}
    v.write_json(v.resume_tags_key(user_id), pointer, compact=True)
    v.write_json(v.resume_current_key(user_id), pointer, compact=True)
    return sha


def _resume_pack(user_id: str) -> dict[str, Any]:
    from .vault import get_vault

    v = get_vault()
    if not v.exists(v.resume_tags_key(user_id)):
        return {}
    pack = v.read_json(v.resume_tags_key(user_id)) or {}
    sha = pack.get("sha")
    if sha and "phrases" not in pack:
        return v.read_json(v.resume_tags_key(user_id, str(sha))) or {}
    return pack


def load_side_phrases(company_id: Optional[str] = None, user_id: Optional[str] = None) -> list[str]:
    """Company pack + current resume version. Prefix-listable; no SBIR dump."""
    from .vault import get_vault

    v = get_vault()
    out: list[str] = []
    if company_id:
        pack = v.read_json(v.company_tags_key(company_id)) or {}
        out.extend(str(p) for p in (pack.get("phrases") or []) if p)
    if user_id:
        pack = _resume_pack(user_id)
        out.extend(str(p) for p in (pack.get("phrases") or []) if p)
    return out


def _synth_topic(title: str, description: str) -> dict[str, Any]:
    return {
        "topicTitle": title,
        "keywords": "",
        "description": description,
        "objective": description[:2500],
        "component": title,
    }


def refresh_company_tags_from_vault(company_id: str) -> None:
    """Write fallback tags immediately, then schedule an LLM upgrade.

    Products/mission need real open-vocab phrases (`unmanned aviation`,
    `TAK plugin`, `on-device inference`) for the matcher to lift SBIRs an
    employee's raw resume doesn't literally mention.
    """
    from .vault import get_vault

    v = get_vault()
    mission = v.read_text(f"companies/{company_id}/mission.txt")
    products = v.read_text(f"companies/{company_id}/products.md")
    blob = f"{mission}\n{products}".strip()
    tags = fallback_phrases(_synth_topic(company_id, blob))
    write_company_tags(company_id, tags)
    _schedule_llm(_llm_company_tags(company_id, blob, mission, products))


def refresh_resume_tags_from_text(user_id: str, text: str, kind: str = "me") -> None:
    """Immediate fallback tags for the user's ME resume. LLM upgrade is scheduled."""
    tags = fallback_phrases(_synth_topic(user_id, text))
    write_resume_tags(user_id, tags, text, kind=kind)
    _schedule_llm(_llm_resume_tags(user_id, text, kind))


def refresh_resume_tags_from_bundle(user_id: str, company_id: str) -> None:
    """Merge ME + company mission/products so the resume tag pack reflects the role
    the user actually plays at their company. Fallback first, LLM in background."""
    from .vault import get_vault

    v = get_vault()
    me = v.read_text(f"users/{user_id}/me.md").strip()
    mission = v.read_text(f"companies/{company_id}/mission.txt").strip()
    products = v.read_text(f"companies/{company_id}/products.md").strip()
    blob = "\n\n".join(x for x in (me, mission, products) if x)
    if not blob:
        return
    tags = fallback_phrases(_synth_topic(user_id, blob))
    write_resume_tags(user_id, tags, blob, kind="me")
    _schedule_llm(_llm_resume_tags(user_id, blob, "me"))


async def _llm_company_tags(
    company_id: str, blob: str, mission: str, products: str
) -> None:
    if not blob:
        return
    try:
        tags = await extract_phrases(_synth_topic(company_id, blob))
    except Exception:
        return
    if not tags.get("phrases"):
        return
    tags.setdefault("source", "llm")
    tags["mission_chars"] = len(mission or "")
    tags["product_chars"] = len(products or "")
    write_company_tags(company_id, tags)


async def _llm_resume_tags(user_id: str, blob: str, kind: str) -> None:
    if not blob:
        return
    try:
        tags = await extract_phrases(_synth_topic(user_id, blob))
    except Exception:
        return
    if not tags.get("phrases"):
        return
    tags.setdefault("source", "llm")
    write_resume_tags(user_id, tags, blob, kind=kind)


def _schedule_llm(coro) -> None:
    """Fire-and-forget an async LLM upgrade. Silently drops if no loop is running."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No loop (called from a sync endpoint outside FastAPI). Just close it.
        try:
            coro.close()
        except Exception:
            pass
        return
    loop.create_task(coro)


def _topic_id(topic: dict[str, Any]) -> Optional[str]:
    tid = topic.get("topicId") or topic.get("id")
    return str(tid) if tid else None


async def paginate_open_window() -> tuple[list[dict[str, Any]], int]:
    """Full open + pre-release listing. Search JSON is cheap; this is not the LLM."""
    page_size = max(10, int(settings.catalog_page_size or 50))
    max_pages = max(1, int(settings.catalog_max_pages or 40))
    out: list[dict[str, Any]] = []
    pages = 0
    total_hint: Optional[int] = None
    param = dsip.build_search_param(
        solicitation_cycle_names=["openTopics"],
        topic_release_status=[591, 592],
        sort_by="topicStartDate,desc",
    )
    for page in range(max_pages):
        res = await dsip.search_topics(param, size=page_size, page=page)
        pages += 1
        if isinstance(res, dict) and res.get("total") is not None:
            try:
                total_hint = int(res["total"])
            except (TypeError, ValueError):
                total_hint = None
        rows = res.get("data") if isinstance(res, dict) else res
        if not isinstance(rows, list) or not rows:
            break
        out.extend(t for t in rows if isinstance(t, dict))
        if total_hint is not None and len(out) >= total_hint:
            break
        if len(rows) < page_size:
            break
    return out, pages


def _row_from_summary(topic: dict[str, Any], fp: str) -> dict[str, Any]:
    tid = _topic_id(topic) or ""
    return {
        "topic_id": tid,
        "topic_code": topic.get("topicCode") or topic.get("finalTopicCode"),
        "title": topic.get("topicTitle") or topic.get("title"),
        "component": topic.get("component"),
        "program": topic.get("program"),
        "topic_status": topic.get("topicStatus"),
        "solicitation_title": topic.get("solicitationTitle"),
        "fingerprint": fp,
        "open_ms": _ms(topic, "topicStartDate"),
        "close_ms": _ms(topic, "topicEndDate"),
        "prerelease_ms": _ms(topic, "topicPreReleaseStartDate"),
        "raw_json": json.dumps(topic),
    }


async def _enrich(topic: dict[str, Any]) -> tuple[dict[str, Any], Optional[list[float]], dict[str, Any]]:
    tid = _topic_id(topic)
    merged = dict(topic)
    if tid:
        try:
            details = await dsip.get_topic(tid)
            if isinstance(details, dict):
                inner = details.get("topic") if isinstance(details.get("topic"), dict) else details
                merged = {**merged, **inner}
        except Exception:
            pass
    tags = await extract_phrases(merged)
    tags["dsip_keywords"] = merged.get("keywords") or ""
    vec = await ollama_client.embed(
        embed_text(tags.get("phrases") or [], str(merged.get("topicTitle") or merged.get("title") or ""))
    )
    return tags, vec, merged


def _enrich_cap(enrich_limit: Optional[int]) -> int:
    """0 in settings (or a huge explicit cap) means every open topic."""
    if enrich_limit is not None:
        return max(0, int(enrich_limit))
    n = int(settings.catalog_enrich_per_pass or 0)
    return n if n > 0 else 10**9


async def refresh_catalog(
    session: Session, *, force: bool = False, enrich_limit: Optional[int] = None
) -> dict[str, Any]:
    summaries, pages = await paginate_open_window()
    cap = _enrich_cap(enrich_limit)
    listed = 0
    new_topics = 0
    reused = 0
    enriched_n = 0
    newest = 0
    open_ids: list[str] = []

    for topic in summaries:
        tid = _topic_id(topic)
        if not tid:
            continue
        listed += 1
        open_ids.append(tid)
        fp = fingerprint(topic)
        open_ms = _ms(topic, "topicStartDate") or 0
        if open_ms > newest:
            newest = open_ms
        row = session.get(TopicIndex, tid)
        meta = _row_from_summary(topic, fp)
        if row is None:
            new_topics += 1
            row = TopicIndex(topic_id=tid, first_seen_at=datetime.utcnow())
        unchanged = (
            not force
            and bool(row.fingerprint)
            and row.fingerprint == fp
            and bool(row.tags_json)
            and row.tags_json != "{}"
        )
        if unchanged:
            reused += 1
            for k, v in meta.items():
                if k == "raw_json" and row.raw_json:
                    continue
                setattr(row, k, v)
            session.add(row)
            session.commit()
            try:
                write_topic_tags(tid, parse_tags(row.tags_json), fp)
            except Exception:
                pass
        else:
            fallback = fallback_phrases(topic)
            row.tags_json = json.dumps(fallback)
            row.content_sha = content_sha(topic)
            row.enriched = False
            for k, v in meta.items():
                setattr(row, k, v)
            row.indexed_at = datetime.utcnow()
            session.add(row)
            session.commit()
            try:
                write_topic_tags(tid, fallback, fp)
            except Exception:
                pass

        need_llm = force or not bool(row.enriched)
        if need_llm and enriched_n < cap:
            tags, vec, merged = await _enrich(topic)
            row = session.get(TopicIndex, tid)
            if row:
                row.tags_json = json.dumps(tags)
                row.content_sha = content_sha(merged)
                row.raw_json = json.dumps(merged)
                row.enriched = True
                if vec:
                    row.embedding_json = json.dumps(vec)
                row.indexed_at = datetime.utcnow()
                session.add(row)
                session.commit()
                try:
                    write_topic_tags(tid, tags, fp)
                except Exception:
                    pass
            enriched_n += 1

    st = {}
    try:
        st = await ollama_client.status()
    except Exception:
        st = {}
    embed_model = settings.ollama_embed_model if st.get("embed_ready") else ""
    pass_row = CatalogPass(
        pages=pages,
        listed=listed,
        new_topics=new_topics,
        reused=reused,
        enriched=enriched_n,
        newest_open_ms=newest or None,
        embed_model=embed_model or "",
    )
    session.add(pass_row)
    session.commit()
    session.refresh(pass_row)
    return serialize_pass(pass_row, open_ids=open_ids)


def serialize_pass(row: CatalogPass, open_ids: Optional[list[str]] = None) -> dict[str, Any]:
    return {
        "id": row.id,
        "pages": row.pages,
        "listed": row.listed,
        "new_topics": row.new_topics,
        "reused": row.reused,
        "enriched": row.enriched,
        "newest_open_ms": row.newest_open_ms,
        "embed_model": row.embed_model,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "open_ids": open_ids or [],
        "open_count": len(open_ids or []),
    }


def serialize_index(row: TopicIndex) -> dict[str, Any]:
    tags = parse_tags(row.tags_json)
    try:
        raw = json.loads(row.raw_json or "{}")
    except json.JSONDecodeError:
        raw = {}
    return {
        "topic_id": row.topic_id,
        "topic_code": row.topic_code,
        "title": row.title,
        "component": row.component,
        "program": row.program,
        "topic_status": row.topic_status,
        "solicitation_title": row.solicitation_title,
        "fingerprint": row.fingerprint,
        "phrases": tags.get("phrases") or [],
        "kinds": tags.get("kinds") or {},
        "source": tags.get("source"),
        "dsip_keywords": tags.get("dsip_keywords") or raw.get("keywords") or "",
        "has_embedding": bool(row.embedding_json),
        "enriched": bool(row.enriched),
        "open_ms": row.open_ms,
        "close_ms": row.close_ms,
        "prerelease_ms": row.prerelease_ms,
        "indexed_at": row.indexed_at.isoformat() if row.indexed_at else None,
        "topic": raw,
    }


def open_rows(session: Session, open_ids: list[str]) -> list[TopicIndex]:
    if not open_ids:
        return []
    want = set(open_ids)
    rows = session.exec(select(TopicIndex)).all()
    return [r for r in rows if r.topic_id in want]


def latest_pass(session: Session) -> Optional[CatalogPass]:
    return session.exec(select(CatalogPass).order_by(CatalogPass.created_at.desc())).first()


_enrich_task: Optional[asyncio.Task] = None


def enrich_running() -> bool:
    return bool(_enrich_task and not _enrich_task.done())


def schedule_enrich_all() -> bool:
    """Run the LLM details pass over every open sbir_id in the background."""
    global _enrich_task
    if enrich_running():
        return False
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return False
    _enrich_task = loop.create_task(_enrich_all_job())
    return True


async def _enrich_all_job() -> None:
    from .db import engine

    with Session(engine) as session:
        await refresh_catalog(session)

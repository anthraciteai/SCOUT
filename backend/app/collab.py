"""Group-desk collaboration: shareable approach cards, cheap overlap, cached Collier.

Private draft.md never goes on the desk. Flint sparks + heading skeletons become
sbir/{topic}/{company}/shared/approaches/{user}.json. Set-diff flags overlap;
Collier only sees the cards plus that report.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Optional

from .agents import _safe_json
from .identity import Identity
from .vault import Vault, _now, _ok

_HEADING = re.compile(r"^(#{1,3})\s+(.+)$")
_WORD = re.compile(r"[a-z0-9][a-z0-9+.#/-]{1,}")
_STOP = {
    "the", "and", "for", "with", "that", "this", "from", "into", "onto", "over",
    "your", "their", "have", "has", "are", "was", "were", "will", "can", "not",
    "but", "our", "you", "they", "them", "its", "use", "used", "using", "via",
    "then", "than", "also", "just", "more", "than", "able", "make", "made",
    "already", "existing", "proposal", "topic", "approach", "technical",
    "section", "draft", "shared", "private", "would", "could", "should",
}

COLLIER_DESK = (
    "You are Collier on the SCOUT group desk. You see APPROACH CARDS (sparks, tools, "
    "section names) — never private draft prose. A deterministic overlap report is included. "
    "Suggest how the named people should split work and what to promote into the shared "
    "proposal. Overlap is usually a feature (one bid, two hands), not a conflict.\n"
    "Return ONLY JSON with keys: "
    '{"overlaps": [{"theme": string, "who": [user_id], "split": string}], '
    '"gaps": [string], '
    '"promote": [string]}.'
)


def content_sha(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


def _norm_tool(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def _tokens(*parts: str) -> set[str]:
    bag: set[str] = set()
    for part in parts:
        for w in _WORD.findall((part or "").lower()):
            if w in _STOP or len(w) < 3:
                continue
            bag.add(w)
    return bag


def _flint_blob(vault: Vault, topic_id: str, company_id: str, user_id: str) -> dict:
    tid, cid, uid = _ok(topic_id), _ok(company_id), _ok(user_id)
    cached = vault.cache_get(f"sbir/{tid}/{cid}/users/{uid}/flint.json") or {}
    result = cached.get("result") if isinstance(cached, dict) else None
    if isinstance(result, dict) and (result.get("sparks") or result.get("tools_in_play")):
        return result
    council = vault.cache_get(f"sbir/{tid}/{cid}/users/{uid}/council.json") or {}
    inner = council.get("result") if isinstance(council, dict) else None
    agents = (inner or {}).get("agents") if isinstance(inner, dict) else {}
    flint = (agents or {}).get("Flint") if isinstance(agents, dict) else None
    return flint if isinstance(flint, dict) else {}


def _davy_blob(vault: Vault, topic_id: str, company_id: str, user_id: str) -> dict:
    tid, cid, uid = _ok(topic_id), _ok(company_id), _ok(user_id)
    cached = vault.cache_get(f"sbir/{tid}/{cid}/users/{uid}/davy.json") or {}
    result = cached.get("result") if isinstance(cached, dict) else None
    if isinstance(result, dict) and (result.get("win_themes") or result.get("discriminators")):
        return result
    council = vault.cache_get(f"sbir/{tid}/{cid}/users/{uid}/council.json") or {}
    inner = council.get("result") if isinstance(council, dict) else None
    agents = (inner or {}).get("agents") if isinstance(inner, dict) else {}
    davy = (agents or {}).get("Davy") if isinstance(agents, dict) else None
    return davy if isinstance(davy, dict) else {}


def _draft_skeleton(text: str) -> tuple[list[str], list[str]]:
    """Heading names + one short claim per section. Not the private narrative."""
    if not (text or "").strip():
        return [], []
    sections: list[dict[str, Any]] = []
    current = {"heading": "", "body": []}
    for line in text.splitlines():
        m = _HEADING.match(line.strip())
        if m:
            if current["heading"] or any(x.strip() for x in current["body"]):
                sections.append(current)
            current = {"heading": m.group(2).strip(), "body": []}
        else:
            current["body"].append(line)
    if current["heading"] or any(x.strip() for x in current["body"]):
        sections.append(current)
    headings: list[str] = []
    claims: list[str] = []
    for sec in sections:
        heading = (sec.get("heading") or "").strip()
        body = " ".join(ln.strip() for ln in sec.get("body") or [] if ln.strip())
        if heading:
            headings.append(heading)
        claim_src = heading
        if body:
            # First sentence-ish, capped — enough to fingerprint the take, not the essay.
            snippet = re.split(r"(?<=[.!?])\s+", body, maxsplit=1)[0].strip()
            snippet = snippet[:140].rstrip()
            if heading:
                claim_src = f"{heading}: {snippet}" if snippet else heading
            elif snippet:
                claim_src = snippet
        if claim_src:
            claims.append(claim_src)
    return headings, claims[:8]


def extract_card(vault: Vault, topic_id: str, company_id: str, user_id: str) -> Optional[dict]:
    tid, cid, uid = _ok(topic_id), _ok(company_id), _ok(user_id)
    flint = _flint_blob(vault, tid, cid, uid)
    davy = _davy_blob(vault, tid, cid, uid)
    draft = vault.read_text(f"sbir/{tid}/{cid}/users/{uid}/draft.md")
    headings, claims = _draft_skeleton(draft)
    skills = vault.lines(f"users/{uid}/skills.txt")

    tools: list[str] = []
    seen_tools: set[str] = set()

    def add_tool(raw: str) -> None:
        t = _norm_tool(raw)
        key = t.lower()
        if not t or key in seen_tools:
            return
        seen_tools.add(key)
        tools.append(t)

    for row in flint.get("tools_in_play") or []:
        if isinstance(row, dict):
            add_tool(str(row.get("tool") or ""))
        elif row:
            add_tool(str(row))
    sparks: list[str] = []
    spark_tools: list[str] = []
    for spark in flint.get("sparks") or []:
        if not isinstance(spark, dict):
            continue
        title = (spark.get("title") or "").strip()
        hook = (spark.get("hook") or "").strip()
        label = title or hook
        if label:
            sparks.append(label[:160])
        for t in spark.get("tools") or []:
            add_tool(str(t))
            spark_tools.append(str(t))
    left = (flint.get("left_field") or "").strip()
    if left:
        sparks.append(left[:160])

    for theme in (davy.get("win_themes") or []) + (davy.get("discriminators") or []):
        s = str(theme).strip()
        if s:
            claims.append(s[:140])

    for sk in skills:
        # Only keep skills that actually appear in the flint/draft skeleton.
        blob = " ".join(sparks + claims + spark_tools + tools).lower()
        if sk.lower() in blob:
            add_tool(sk)

    if not (tools or sparks or headings or claims):
        return None

    display = vault.read_text(f"users/{uid}/display_name.txt").strip() or uid
    body = {
        "user_id": uid,
        "display_name": display,
        "tools": tools[:16],
        "sparks": sparks[:8],
        "sections": headings[:12],
        "claims": claims[:10],
    }
    raw = json.dumps(body, sort_keys=True, ensure_ascii=False)
    body["sha"] = content_sha(raw)
    body["updated_at"] = _now()
    return body


def publish_card(vault: Vault, topic_id: str, ident: Identity) -> Optional[dict]:
    card = extract_card(vault, topic_id, ident.company_id, ident.user_id)
    key = vault.approach_key(topic_id, ident.company_id, ident.user_id)
    if not card:
        return None
    existing = vault.read_json(key) or {}
    if existing.get("sha") == card.get("sha"):
        return existing
    vault.write_json(key, card)
    return card


def sync_cards(vault: Vault, topic_id: str, company_id: str) -> list[dict]:
    """Rebuild stale approach cards from flint/council/draft. No LLM."""
    cid = _ok(company_id)
    cards: list[dict] = []
    for uid in vault.company_employees(cid):
        card = extract_card(vault, topic_id, cid, uid)
        if not card:
            continue
        key = vault.approach_key(topic_id, cid, uid)
        existing = vault.read_json(key) or {}
        if existing.get("sha") != card.get("sha"):
            vault.write_json(key, card)
        cards.append(card)
    cards.sort(key=lambda c: c.get("user_id") or "")
    return cards


def fingerprint(cards: list[dict]) -> str:
    joined = "|".join(sorted(str(c.get("sha") or "") for c in cards))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:24]


def _shared_label(tokens: set[str], sparks_a: list[str], sparks_b: list[str]) -> str:
    # Prefer a spark title that contains 2+ shared tokens.
    for title in sparks_a + sparks_b:
        hit = _tokens(title) & tokens
        if len(hit) >= 2:
            return title[:80]
    # Else the most distinctive shared tokens.
    prefer = [t for t in ("mqtt", "cop", "ulog", "tak", "health", "ollama", "jetson", "px4", "vein", "davy") if t in tokens]
    rest = sorted(tokens - set(prefer), key=len, reverse=True)
    words = prefer + rest
    if not words:
        return "technical approach"
    return " ".join(words[:4])


def overlap_report(cards: list[dict]) -> dict:
    overlaps: list[dict] = []
    seen_pairs: set[tuple[str, str]] = set()
    for i, a in enumerate(cards):
        for b in cards[i + 1 :]:
            ta = {_norm_tool(t).lower() for t in (a.get("tools") or []) if t}
            tb = {_norm_tool(t).lower() for t in (b.get("tools") or []) if t}
            shared_tools = sorted(ta & tb)
            tok_a = _tokens(*(a.get("sparks") or []), *(a.get("claims") or []), *(a.get("tools") or []))
            tok_b = _tokens(*(b.get("sparks") or []), *(b.get("claims") or []), *(b.get("tools") or []))
            shared_tok = tok_a & tok_b
            union = tok_a | tok_b
            jacc = (len(shared_tok) / len(union)) if union else 0.0
            sections_a = {s.lower() for s in (a.get("sections") or [])}
            sections_b = {s.lower() for s in (b.get("sections") or [])}
            same_heading = sorted(sections_a & sections_b)
            score = len(shared_tools) * 2 + len(shared_tok) + (1 if same_heading else 0) + (2 if jacc >= 0.2 else 0)
            if score < 3 and not (shared_tools and len(shared_tok) >= 2):
                continue
            who = tuple(sorted([a["user_id"], b["user_id"]]))
            if who in seen_pairs:
                continue
            seen_pairs.add(who)
            theme = _shared_label(shared_tok | {t.lower() for t in shared_tools}, a.get("sparks") or [], b.get("sparks") or [])
            only_a = sorted(ta - tb)
            only_b = sorted(tb - ta)
            split = (
                f"{a.get('display_name') or a['user_id']} covers {', '.join(only_a) or 'their stack'}; "
                f"{b.get('display_name') or b['user_id']} covers {', '.join(only_b) or 'theirs'}."
            )
            overlaps.append(
                {
                    "theme": theme,
                    "who": list(who),
                    "score": score,
                    "tools": shared_tools[:8],
                    "split": split,
                    "sections": same_heading[:4],
                }
            )
    overlaps.sort(key=lambda o: (-int(o.get("score") or 0), o.get("theme") or ""))

    overlapped = {uid for o in overlaps for uid in o.get("who") or []}
    gaps: list[str] = []
    for c in cards:
        uid = c.get("user_id")
        if uid in overlapped:
            continue
        name = c.get("display_name") or uid
        tools = ", ".join(c.get("tools") or []) or "no shared tools yet"
        gaps.append(f"{name} has an approach card ({tools}) but no technical overlap yet — capture / win-theme slot.")

    return {
        "overlaps": overlaps,
        "gaps": gaps,
    }


def _merge_llm(det: dict, llm: dict) -> dict:
    by_who = {}
    for row in llm.get("overlaps") or []:
        if not isinstance(row, dict):
            continue
        key = tuple(sorted(str(x) for x in (row.get("who") or [])))
        by_who[key] = row
    merged = []
    for row in det.get("overlaps") or []:
        extra = by_who.get(tuple(sorted(row.get("who") or []))) or {}
        item = dict(row)
        if extra.get("theme"):
            item["theme"] = extra["theme"]
        if extra.get("split"):
            item["split"] = extra["split"]
        merged.append(item)
    gaps = [str(g) for g in (llm.get("gaps") or det.get("gaps") or []) if g]
    promote = [str(p) for p in (llm.get("promote") or []) if p][:8]
    return {"overlaps": merged, "gaps": gaps, "promote": promote}


async def suggest(cards: list[dict], det: dict) -> dict:
    from . import ollama_client

    slim = [
        {
            "user_id": c.get("user_id"),
            "display_name": c.get("display_name"),
            "tools": c.get("tools"),
            "sparks": c.get("sparks"),
            "sections": c.get("sections"),
            "claims": c.get("claims"),
        }
        for c in cards
    ]
    prompt = (
        "APPROACH CARDS (org-visible, not private drafts):\n"
        + json.dumps(slim, ensure_ascii=False)[:3500]
        + "\n\nDETERMINISTIC OVERLAP:\n"
        + json.dumps(det, ensure_ascii=False)[:2000]
        + "\n\nName overlap, split the work, and give paste-ready promote bullets for shared/proposal.md."
    )
    raw = await ollama_client.chat(COLLIER_DESK, prompt, temperature=0.2, format_json=True)
    parsed = _safe_json(raw)
    if not isinstance(parsed, dict) or parsed.get("raw"):
        return {**det, "promote": []}
    return _merge_llm(det, parsed)


def load_cached(vault: Vault, topic_id: str, company_id: str, fp: str) -> Optional[dict]:
    obj = vault.read_json(vault.collab_key(topic_id, company_id))
    if not isinstance(obj, dict):
        return None
    if obj.get("fingerprint") != fp:
        return None
    return obj


def workspace_collab(vault: Vault, topic_id: str, company_id: str) -> dict:
    """Always-on desk payload: cards + set-diff. LLM note only if cache matches."""
    cards = sync_cards(vault, topic_id, company_id)
    det = overlap_report(cards)
    fp = fingerprint(cards)
    cached = load_cached(vault, topic_id, company_id, fp) if len(cards) >= 2 else None
    promote = (cached or {}).get("promote") or []
    overlaps = (cached or {}).get("overlaps") or det["overlaps"]
    gaps = (cached or {}).get("gaps") or det["gaps"]
    proposal = vault.read_text(f"sbir/{_ok(topic_id)}/{_ok(company_id)}/shared/proposal.md")
    return {
        "fingerprint": fp,
        "cards": cards,
        "overlaps": overlaps,
        "gaps": gaps,
        "promote": promote,
        "llm": bool(cached and cached.get("llm")),
        "cached": bool(cached),
        "stale": bool(len(cards) >= 2 and not cached),
        "proposal_sha": content_sha(proposal),
    }


async def refresh_collab(vault: Vault, topic_id: str, company_id: str, force: bool = False) -> dict:
    cards = sync_cards(vault, topic_id, company_id)
    det = overlap_report(cards)
    fp = fingerprint(cards)
    if len(cards) < 2:
        body = {
            "fingerprint": fp,
            "cards": cards,
            "overlaps": [],
            "gaps": det.get("gaps") or [],
            "promote": [],
            "llm": False,
            "cached": False,
            "stale": False,
            "proposal_sha": content_sha(
                vault.read_text(f"sbir/{_ok(topic_id)}/{_ok(company_id)}/shared/proposal.md")
            ),
        }
        return body
    if not force:
        cached = load_cached(vault, topic_id, company_id, fp)
        if cached:
            cached["cached"] = True
            cached["stale"] = False
            cached["cards"] = cards
            cached["proposal_sha"] = content_sha(
                vault.read_text(f"sbir/{_ok(topic_id)}/{_ok(company_id)}/shared/proposal.md")
            )
            return cached
    try:
        merged = await suggest(cards, det)
        llm_ok = True
    except Exception:
        merged = {**det, "promote": []}
        llm_ok = False
    body = {
        "fingerprint": fp,
        "cards": cards,
        "overlaps": merged.get("overlaps") or det["overlaps"],
        "gaps": merged.get("gaps") or det["gaps"],
        "promote": merged.get("promote") or [],
        "llm": llm_ok,
        "cached": False,
        "stale": False,
        "updated_at": _now(),
        "proposal_sha": content_sha(
            vault.read_text(f"sbir/{_ok(topic_id)}/{_ok(company_id)}/shared/proposal.md")
        ),
    }
    vault.write_json(vault.collab_key(topic_id, company_id), body)
    return body


def promote_into_shared(
    vault: Vault,
    topic_id: str,
    ident: Identity,
    *,
    theme: str = "",
    bullets: Optional[list[str]] = None,
    expected_sha: Optional[str] = None,
) -> dict:
    key = vault.shared_path(topic_id, ident, "proposal.md")
    current = vault.read_text(key)
    sha = content_sha(current)
    if expected_sha and expected_sha != sha:
        return {"ok": False, "conflict": True, "proposal_sha": sha, "shared_proposal": current}
    lines: list[str] = []
    heading = (theme or "Desk overlap").strip()
    marker = heading.lower()
    if marker and marker in current.lower():
        # Already promoted this theme — still ok, just don't duplicate.
        return {"ok": True, "conflict": False, "proposal_sha": sha, "shared_proposal": current, "skipped": True}
    lines.append(f"## {heading}")
    lines.append("")
    for b in bullets or []:
        text = str(b).strip()
        if not text:
            continue
        if not text.startswith("-"):
            text = f"- {text}"
        lines.append(text)
    if len(lines) <= 2:
        return {"ok": True, "conflict": False, "proposal_sha": sha, "shared_proposal": current, "skipped": True}
    lines.append("")
    block = "\n".join(lines)
    new = (current.rstrip() + "\n\n" + block) if current.strip() else block
    vault.write_text(key, new)
    return {
        "ok": True,
        "conflict": False,
        "proposal_sha": content_sha(new),
        "shared_proposal": new,
        "skipped": False,
    }

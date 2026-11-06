"""Org desk + per-SBIR workspace. Cached council/Flint live in the vault."""
import re
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from .. import catalog, collab, docling_service
from ..identity import Identity, get_identity
from ..vault import get_vault

router = APIRouter(prefix="/api/org", tags=["org"])


class TextBody(BaseModel):
    text: str = ""
    expected_sha: Optional[str] = None


class SkillsBody(BaseModel):
    skills: list[str] = []
    me: Optional[str] = None
    display_name: Optional[str] = None


class ProductProfile(BaseModel):
    """One product an org sells, with a 'build prompt' that teaches Scout what
    kind of SBIR/STTR work fits it. Multi-tenant: every company defines its own."""

    id: str = ""
    name: str = ""
    summary: str = ""   # one-liner: what it is
    prompt: str = ""    # the build prompt: what to look for / how to judge fit
    keywords: list[str] = []  # explicit terms that should pull topics toward this product


class ProductProfilesBody(BaseModel):
    products: list[ProductProfile] = []


class EmployeeEditBody(BaseModel):
    """Edit another employee. Any field left None is not touched.

    Same-company members can edit each other's roster fields so a small crew
    can keep the pack accurate without asking the founder to log in as each
    person. Actual gate flips (hire/unhire) go through the POST/DELETE routes.
    """

    display_name: Optional[str] = None
    skills: Optional[list[str]] = None
    me: Optional[str] = None


def _assert_company(ident: Identity, company_id: Optional[str] = None) -> str:
    v = get_vault()
    cid = company_id or ident.company_id
    if not v.in_company(ident, cid):
        raise HTTPException(
            status_code=403,
            detail=f"{ident.user_id} is not employed (missing companies/{cid}/employees/{ident.user_id})",
        )
    return cid


@router.get("/company")
def company(ident: Identity = Depends(get_identity), company_id: Optional[str] = None):
    v = get_vault()
    cid = _assert_company(ident, company_id)
    return {
        "company_id": cid,
        "mission": v.read_text(f"companies/{cid}/mission.txt"),
        "products": v.read_text(f"companies/{cid}/products.md"),
        "employees": v.roster(cid),
        "groups": _groups(v, cid),
        "sbirs": v.federated_sbirs(ident),
    }


@router.put("/company/mission")
def put_mission(body: TextBody, ident: Identity = Depends(get_identity)):
    cid = _assert_company(ident)
    v = get_vault()
    v.write_text(f"companies/{cid}/mission.txt", body.text)
    catalog.refresh_company_tags_from_vault(cid)
    for uid in v.company_employees(cid):
        catalog.refresh_resume_tags_from_bundle(uid, cid)
    return {"ok": True}


@router.put("/company/products")
def put_products(body: TextBody, ident: Identity = Depends(get_identity)):
    cid = _assert_company(ident)
    v = get_vault()
    v.write_text(f"companies/{cid}/products.md", body.text)
    catalog.refresh_company_tags_from_vault(cid)
    for uid in v.company_employees(cid):
        catalog.refresh_resume_tags_from_bundle(uid, cid)
    return {"ok": True}


@router.get("/company/product-profiles")
def get_product_profiles(ident: Identity = Depends(get_identity), company_id: Optional[str] = None):
    """Structured per-product build-prompts. Migrates the legacy products.md on
    first read so existing orgs get a starting list to enrich."""
    cid = _assert_company(ident, company_id)
    v = get_vault()
    stored = v.read_json(f"companies/{cid}/products.json")
    profiles = _coerce_profiles(stored)
    if profiles is None:
        profiles = _parse_products_md(v.read_text(f"companies/{cid}/products.md"))
    return {"company_id": cid, "products": profiles}


@router.put("/company/product-profiles")
def put_product_profiles(body: ProductProfilesBody, ident: Identity = Depends(get_identity)):
    """Save the structured products. Also regenerates products.md (so display +
    tagging keep working) and re-tags the company/people so matching reflects the
    new per-product build-prompts immediately."""
    cid = _assert_company(ident)
    v = get_vault()
    profiles: list[dict] = []
    seen: set[str] = set()
    for p in body.products:
        name = (p.name or "").strip()
        if not name:
            continue
        pid = (p.id or "").strip() or _slug(name)
        while pid in seen:
            pid = f"{pid}-x"
        seen.add(pid)
        profiles.append(
            {
                "id": pid,
                "name": name,
                "summary": (p.summary or "").strip(),
                "prompt": (p.prompt or "").strip(),
                "keywords": _clean_keywords(p.keywords),
            }
        )
    v.write_json(f"companies/{cid}/products.json", {"products": profiles})
    v.write_text(f"companies/{cid}/products.md", _profiles_to_md(profiles))
    catalog.refresh_company_tags_from_vault(cid)
    for uid in v.company_employees(cid):
        catalog.refresh_resume_tags_from_bundle(uid, cid)
    return {"ok": True, "company_id": cid, "products": profiles}


@router.put("/me")
def put_me(body: SkillsBody, ident: Identity = Depends(get_identity)):
    v = get_vault()
    uid = ident.user_id
    if body.display_name is not None:
        v.write_text(f"users/{uid}/display_name.txt", body.display_name.strip() + "\n")
    if body.me is not None:
        v.write_text(f"users/{uid}/me.md", body.me)
    if body.skills:
        v.write_text(f"users/{uid}/skills.txt", "\n".join(s.strip() for s in body.skills if s.strip()) + "\n")
    v.refresh_user_meta(uid)
    catalog.refresh_resume_tags_from_bundle(uid, ident.company_id)
    return {"ok": True}


@router.post("/company/employees/{user_id}")
def hire_employee(
    user_id: str,
    body: Optional[EmployeeEditBody] = None,
    ident: Identity = Depends(get_identity),
):
    """Hire (or re-hire) an employee. If a body is included, seed their
    display name / skills / me in one shot so a fresh add is immediately
    useful in matching."""
    cid = _assert_company(ident)
    uid = user_id.strip().lower()
    if not uid:
        raise HTTPException(status_code=400, detail="user_id is required")
    v = get_vault()
    name = (
        (body.display_name.strip() if body and body.display_name else "")
        or v.read_text(f"users/{uid}/display_name.txt").strip()
        or uid
    )
    v.hire(cid, uid, name)
    if body:
        if body.display_name is not None:
            v.write_text(f"users/{uid}/display_name.txt", (body.display_name.strip() or uid) + "\n")
        if body.skills is not None:
            cleaned = [s.strip() for s in body.skills if s and s.strip()]
            v.write_text(f"users/{uid}/skills.txt", ("\n".join(cleaned) + "\n") if cleaned else "")
        if body.me is not None:
            v.write_text(f"users/{uid}/me.md", body.me)
    catalog.refresh_resume_tags_from_bundle(uid, cid)
    return {"ok": True, "employees": v.company_employees(cid)}


@router.put("/company/employees/{user_id}")
def edit_employee(
    user_id: str,
    body: EmployeeEditBody,
    ident: Identity = Depends(get_identity),
):
    """Edit a same-company employee's display_name / skills / me."""
    cid = _assert_company(ident)
    uid = user_id.strip().lower()
    v = get_vault()
    if not v.exists(v.employee_key(cid, uid)):
        raise HTTPException(status_code=404, detail=f"{uid} is not in {cid}")
    if body.display_name is not None:
        v.write_text(f"users/{uid}/display_name.txt", (body.display_name.strip() or uid) + "\n")
    if body.skills is not None:
        cleaned = [s.strip() for s in body.skills if s and s.strip()]
        v.write_text(f"users/{uid}/skills.txt", ("\n".join(cleaned) + "\n") if cleaned else "")
    if body.me is not None:
        v.write_text(f"users/{uid}/me.md", body.me)
    v.refresh_user_meta(uid)
    catalog.refresh_resume_tags_from_bundle(uid, cid)
    return {
        "ok": True,
        "user_id": uid,
        "display_name": v.read_text(f"users/{uid}/display_name.txt").strip() or uid,
        "skills": v.lines(f"users/{uid}/skills.txt"),
    }


@router.get("/company/employees/{user_id}/resume")
def get_employee_resume(user_id: str, ident: Identity = Depends(get_identity)):
    """Peek at the resume the org has on file for this employee. Read-only."""
    cid = _assert_company(ident)
    uid = user_id.strip().lower()
    v = get_vault()
    if not v.exists(v.employee_key(cid, uid)):
        raise HTTPException(status_code=404, detail=f"{uid} is not in {cid}")
    text = v.read_text(f"users/{uid}/me.md")
    meta = v.read_json(f"users/{uid}/resume/current.json") or {}
    filename = v.read_text(f"users/{uid}/resume/filename.txt").strip()
    return {
        "user_id": uid,
        "chars": len(text or ""),
        "filename": filename or None,
        "resume_sha": meta.get("sha"),
        "updated_at": meta.get("updated_at"),
        "text": text,
    }


@router.post("/company/employees/{user_id}/resume")
async def upload_employee_resume(
    user_id: str,
    file: UploadFile = File(...),
    ident: Identity = Depends(get_identity),
):
    """Attach (or replace) an employee's resume. Extracts text via Docling,
    writes it to `users/{uid}/me.md` in the vault, then re-tags their pack
    against the company mission/products so matching immediately reflects
    the new toolbox."""
    cid = _assert_company(ident)
    uid = user_id.strip().lower()
    v = get_vault()
    if not v.exists(v.employee_key(cid, uid)):
        raise HTTPException(status_code=404, detail=f"{uid} is not in {cid}")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    try:
        text = docling_service.extract_text(file.filename or "resume", data)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"Docling failed: {e}") from e
    text = (text or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="No text extracted from upload")
    v.write_text(f"users/{uid}/me.md", text)
    if file.filename:
        v.write_text(f"users/{uid}/resume/filename.txt", file.filename.strip() + "\n")
    v.refresh_user_meta(uid)
    catalog.refresh_resume_tags_from_bundle(uid, cid)
    meta = v.read_json(f"users/{uid}/resume/current.json") or {}
    return {
        "ok": True,
        "user_id": uid,
        "chars": len(text),
        "filename": file.filename,
        "resume_sha": meta.get("sha"),
    }


@router.delete("/company/employees/{user_id}/resume")
def delete_employee_resume(user_id: str, ident: Identity = Depends(get_identity)):
    """Blank out an employee's ME + tagged pack. The employment gate stays."""
    cid = _assert_company(ident)
    uid = user_id.strip().lower()
    v = get_vault()
    if not v.exists(v.employee_key(cid, uid)):
        raise HTTPException(status_code=404, detail=f"{uid} is not in {cid}")
    v.write_text(f"users/{uid}/me.md", "")
    v.delete(f"users/{uid}/resume/filename.txt")
    v.refresh_user_meta(uid)
    catalog.refresh_resume_tags_from_bundle(uid, cid)
    return {"ok": True, "user_id": uid}


@router.delete("/company/employees/{user_id}")
def unhire_employee(user_id: str, ident: Identity = Depends(get_identity)):
    cid = _assert_company(ident)
    uid = user_id.strip().lower()
    if uid == ident.user_id:
        raise HTTPException(status_code=400, detail="Cannot unhire yourself")
    v = get_vault()
    v.unhire(cid, uid)
    return {"ok": True, "employees": v.company_employees(cid)}


@router.get("/sbir")
def list_sbir(ident: Identity = Depends(get_identity)):
    v = get_vault()
    _assert_company(ident)
    items = []
    for tid in v.federated_sbirs(ident):
        items.append(_sbir_summary(v, ident, tid))
    return {"sbirs": items}


@router.get("/sbir/{topic_id}")
def get_sbir(topic_id: str, ident: Identity = Depends(get_identity)):
    v = get_vault()
    cid = _assert_company(ident)
    if not v.can_read_sbir(ident, topic_id, cid):
        raise HTTPException(status_code=403, detail="No access to this SBIR")
    return _sbir_detail(v, ident, topic_id)


@router.post("/sbir/{topic_id}/grant")
def grant_sbir(
    topic_id: str,
    meta: Optional[dict] = None,
    ident: Identity = Depends(get_identity),
):
    v = get_vault()
    _assert_company(ident)
    v.grant_sbir(ident, topic_id, meta or {"topic_id": topic_id})
    return _sbir_detail(v, ident, topic_id)


@router.put("/sbir/{topic_id}/shared/{name}")
def put_shared(topic_id: str, name: str, body: TextBody, ident: Identity = Depends(get_identity)):
    v = get_vault()
    _assert_company(ident)
    if name not in ("proposal.md", "notes.md"):
        raise HTTPException(status_code=400, detail="writable shared files: proposal.md, notes.md")
    v.grant_sbir(ident, topic_id, {"topic_id": topic_id})
    current = v.read_text(v.shared_path(topic_id, ident, name))
    if name == "proposal.md" and body.expected_sha and collab.content_sha(current) != body.expected_sha:
        raise HTTPException(
            status_code=409,
            detail="Shared proposal changed. Reload and retry.",
        )
    v.write_text(v.shared_path(topic_id, ident, name), body.text)
    return {"ok": True, "proposal_sha": collab.content_sha(body.text) if name == "proposal.md" else None}


class PromoteBody(BaseModel):
    theme: str = ""
    bullets: list[str] = []
    expected_sha: Optional[str] = None


@router.put("/sbir/{topic_id}/mine/{name}")
def put_mine(topic_id: str, name: str, body: TextBody, ident: Identity = Depends(get_identity)):
    v = get_vault()
    _assert_company(ident)
    if name not in ("draft.md", "notes.md"):
        raise HTTPException(status_code=400, detail="writable personal files: draft.md, notes.md")
    v.grant_sbir(ident, topic_id, {"topic_id": topic_id})
    v.write_text(v.user_path(topic_id, ident, name), body.text)
    card = None
    if name == "draft.md":
        v.set_draft_gate(topic_id, ident, body.text)
        card = collab.publish_card(v, topic_id, ident)
    return {"ok": True, "approach": card}


@router.get("/sbir/{topic_id}/collab")
def get_collab(topic_id: str, ident: Identity = Depends(get_identity)):
    v = get_vault()
    cid = _assert_company(ident)
    if not v.can_read_sbir(ident, topic_id, cid):
        raise HTTPException(status_code=403, detail="No access to this SBIR")
    return collab.workspace_collab(v, topic_id, cid)


@router.post("/sbir/{topic_id}/collab/refresh")
async def refresh_collab(
    topic_id: str,
    force: bool = False,
    ident: Identity = Depends(get_identity),
):
    v = get_vault()
    cid = _assert_company(ident)
    if not v.can_read_sbir(ident, topic_id, cid):
        raise HTTPException(status_code=403, detail="No access to this SBIR")
    v.grant_sbir(ident, topic_id, {"topic_id": topic_id})
    return await collab.refresh_collab(v, topic_id, cid, force=force)


@router.post("/sbir/{topic_id}/collab/promote")
def promote_collab(topic_id: str, body: PromoteBody, ident: Identity = Depends(get_identity)):
    v = get_vault()
    _assert_company(ident)
    v.grant_sbir(ident, topic_id, {"topic_id": topic_id})
    result = collab.promote_into_shared(
        v,
        topic_id,
        ident,
        theme=body.theme,
        bullets=body.bullets,
        expected_sha=body.expected_sha,
    )
    if result.get("conflict"):
        raise HTTPException(
            status_code=409,
            detail="Shared proposal changed under you. Reload and promote again.",
        )
    return result


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-") or "product"


def _clean_keywords(raw) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for k in raw or []:
        k = str(k).strip()
        if k and k.lower() not in seen:
            seen.add(k.lower())
            out.append(k)
    return out


def _coerce_profiles(stored) -> Optional[list[dict]]:
    """Normalize whatever is in products.json into a list, or None if absent."""
    if isinstance(stored, dict):
        stored = stored.get("products")
    if not isinstance(stored, list):
        return None
    out: list[dict] = []
    for p in stored:
        if not isinstance(p, dict):
            continue
        name = str(p.get("name") or "").strip()
        if not name:
            continue
        out.append(
            {
                "id": str(p.get("id") or "").strip() or _slug(name),
                "name": name,
                "summary": str(p.get("summary") or "").strip(),
                "prompt": str(p.get("prompt") or "").strip(),
                "keywords": _clean_keywords(p.get("keywords")),
            }
        )
    return out


def _parse_products_md(md: str) -> list[dict]:
    """Best-effort migration of the legacy `**NAME** — summary` markdown into
    structured profiles so an existing org isn't starting from scratch."""
    out: list[dict] = []
    for block in re.split(r"\n\s*\n", (md or "").strip()):
        block = block.strip()
        if not block or block.startswith("#"):
            continue
        m = re.match(r"\*\*(.+?)\*\*\s*[—\-:]*\s*(.*)", block, re.S)
        if not m:
            continue
        name = m.group(1).strip()
        summary = " ".join(m.group(2).split())
        out.append(
            {
                "id": _slug(name),
                "name": name,
                "summary": summary[:400],
                "prompt": "",
                "keywords": [],
            }
        )
    return out


def _profiles_to_md(profiles: list[dict]) -> str:
    """Render structured products back to markdown so the existing tag pipeline
    and other readers of products.md keep working."""
    lines = ["# Products", ""]
    for p in profiles:
        summary = p.get("summary") or ""
        lines.append(f"**{p['name']}**{(' — ' + summary) if summary else ''}")
        if p.get("prompt"):
            lines.append("")
            lines.append(p["prompt"])
        if p.get("keywords"):
            lines.append("")
            lines.append("Keywords: " + ", ".join(p["keywords"]))
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _groups(v, cid: str) -> list[dict]:
    found = {}
    for key in v.list_prefix(f"groups/{cid}/"):
        parts = key.split("/")
        if len(parts) < 4:
            continue
        gid = parts[2]
        found.setdefault(gid, {"group_id": gid, "members": [], "sbirs": []})
        if parts[-1] == "members.txt":
            found[gid]["members"] = v.lines(key)
        if parts[-1] == "sbir.txt":
            found[gid]["sbirs"] = v.lines(key)
    return list(found.values())


def _sbir_summary(v, ident: Identity, topic_id: str) -> dict:
    cid = ident.company_id
    topic_meta = v.read_json(f"sbir/{topic_id}/{cid}/shared/topic.json") or {}
    work = v.read_json(v.work_meta_key(topic_id, cid, ident.user_id)) or {}
    writers = []
    prefix = f"sbir/{topic_id}/{cid}/users/"
    for key in v.list_prefix(prefix):
        if key.endswith("/meta.json"):
            uid = key[len(prefix) :].split("/", 1)[0]
            if uid and uid not in writers:
                writers.append(uid)
    report = collab.workspace_collab(v, topic_id, cid)
    return {
        "topic_id": topic_id,
        "title": topic_meta.get("title") or topic_meta.get("topicTitle") or topic_id,
        "topic_code": topic_meta.get("topic_code") or topic_meta.get("topicCode"),
        "cached_council": v.exists(v.user_path(topic_id, ident, "council.json"))
        or v.exists(v.shared_path(topic_id, ident, "council.json")),
        "cached_flint": bool(work.get("flint"))
        if work
        else v.exists(v.user_path(topic_id, ident, "flint.json")),
        "chat_turns": int(work.get("chat_turns") or 0),
        "has_shared_proposal": v.exists(v.shared_path(topic_id, ident, "proposal.md")),
        "has_my_draft": bool(work.get("has_draft"))
        if work
        else v.exists(v.draft_gate_key(topic_id, cid, ident.user_id)),
        "writers": writers,
        "cached_at": work.get("cached_at"),
        "company_id": cid,
        "overlap_count": len(report.get("overlaps") or []),
    }


def _sbir_detail(v, ident: Identity, topic_id: str) -> dict:
    summary = _sbir_summary(v, ident, topic_id)
    cid = ident.company_id
    others = []
    for uid in v.company_employees(cid):
        if uid == ident.user_id:
            continue
        other_meta = v.read_json(v.work_meta_key(topic_id, cid, uid)) or {}
        others.append(
            {
                "user_id": uid,
                "display_name": v.read_text(f"users/{uid}/display_name.txt").strip() or uid,
                "skills": v.lines(f"users/{uid}/skills.txt"),
                "company_id": cid,
                "has_flint": bool(other_meta.get("flint"))
                if other_meta
                else v.exists(f"sbir/{topic_id}/{cid}/users/{uid}/flint.json"),
                "has_draft": bool(other_meta.get("has_draft"))
                if other_meta
                else v.exists(v.draft_gate_key(topic_id, cid, uid)),
            }
        )
    return {
        **summary,
        "shared_proposal": v.read_text(v.shared_path(topic_id, ident, "proposal.md")),
        "shared_notes": v.read_text(v.shared_path(topic_id, ident, "notes.md")),
        "my_draft": v.read_text(v.user_path(topic_id, ident, "draft.md")),
        "my_notes": v.read_text(v.user_path(topic_id, ident, "notes.md")),
        "my_council": v.cache_get(v.user_path(topic_id, ident, "council.json")),
        "shared_council": v.cache_get(v.shared_path(topic_id, ident, "council.json")),
        "my_flint": v.cache_get(v.user_path(topic_id, ident, "flint.json")),
        "my_chats": v.list_chats(topic_id, ident),
        "teammates": others,
        "collab": collab.workspace_collab(v, topic_id, cid),
        "meta": v.read_json(v.work_meta_key(topic_id, cid, ident.user_id)),
        "paths": {
            "shared": f"sbir/{topic_id}/{cid}/shared/",
            "mine": f"sbir/{topic_id}/{cid}/users/{ident.user_id}/",
            "employees": f"companies/{cid}/employees/{ident.user_id}",
            "blob": "blobs/{sha}.json.gz",
        },
    }

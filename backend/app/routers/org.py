"""Org desk + per-SBIR workspace. Cached council/Flint live in the vault."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..identity import Identity, get_identity
from ..vault import get_vault

router = APIRouter(prefix="/api/org", tags=["org"])


class TextBody(BaseModel):
    text: str = ""


class SkillsBody(BaseModel):
    skills: list[str] = []
    me: Optional[str] = None
    display_name: Optional[str] = None


def _assert_company(ident: Identity, company_id: Optional[str] = None) -> str:
    v = get_vault()
    cid = company_id or ident.company_id
    if not v.in_company(ident, cid):
        raise HTTPException(
            status_code=403,
            detail=f"{ident.user_id} is not in companies/{cid}/employees.txt",
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
    get_vault().write_text(f"companies/{cid}/mission.txt", body.text)
    return {"ok": True}


@router.put("/company/products")
def put_products(body: TextBody, ident: Identity = Depends(get_identity)):
    cid = _assert_company(ident)
    get_vault().write_text(f"companies/{cid}/products.md", body.text)
    return {"ok": True}


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
    return {"ok": True}


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
    v.write_text(v.shared_path(topic_id, ident, name), body.text)
    return {"ok": True}


@router.put("/sbir/{topic_id}/mine/{name}")
def put_mine(topic_id: str, name: str, body: TextBody, ident: Identity = Depends(get_identity)):
    v = get_vault()
    _assert_company(ident)
    if name not in ("draft.md", "notes.md"):
        raise HTTPException(status_code=400, detail="writable personal files: draft.md, notes.md")
    v.grant_sbir(ident, topic_id, {"topic_id": topic_id})
    v.write_text(v.user_path(topic_id, ident, name), body.text)
    return {"ok": True}


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
    meta = v.read_json(f"sbir/{topic_id}/{cid}/shared/topic.json") or {}
    my_council = v.read_json(v.user_path(topic_id, ident, "council.json"))
    shared_council = v.read_json(v.shared_path(topic_id, ident, "council.json"))
    my_flint = v.read_json(v.user_path(topic_id, ident, "flint.json"))
    writers = []
    prefix = f"sbir/{topic_id}/{cid}/users/"
    for key in v.list_prefix(prefix):
        rest = key[len(prefix) :]
        uid = rest.split("/", 1)[0]
        if uid and uid not in writers:
            writers.append(uid)
    return {
        "topic_id": topic_id,
        "title": meta.get("title") or meta.get("topicTitle") or topic_id,
        "topic_code": meta.get("topic_code") or meta.get("topicCode"),
        "cached_council": bool(my_council or shared_council),
        "cached_flint": bool(my_flint),
        "has_shared_proposal": bool(v.read_text(v.shared_path(topic_id, ident, "proposal.md")).strip()),
        "has_my_draft": bool(v.read_text(v.user_path(topic_id, ident, "draft.md")).strip()),
        "writers": writers,
        "cached_at": (my_council or shared_council or my_flint or {}).get("cached_at"),
    }


def _sbir_detail(v, ident: Identity, topic_id: str) -> dict:
    summary = _sbir_summary(v, ident, topic_id)
    cid = ident.company_id
    others = []
    for uid in v.company_employees(cid):
        if uid == ident.user_id:
            continue
        flint = v.read_json(f"sbir/{topic_id}/{cid}/users/{uid}/flint.json")
        draft = v.read_text(f"sbir/{topic_id}/{cid}/users/{uid}/draft.md").strip()
        others.append(
            {
                "user_id": uid,
                "display_name": v.read_text(f"users/{uid}/display_name.txt").strip() or uid,
                "skills": v.lines(f"users/{uid}/skills.txt"),
                "has_flint": bool(flint),
                "has_draft": bool(draft),
                # Private drafts stay private. Only a hint that they are writing.
            }
        )
    return {
        **summary,
        "shared_proposal": v.read_text(v.shared_path(topic_id, ident, "proposal.md")),
        "shared_notes": v.read_text(v.shared_path(topic_id, ident, "notes.md")),
        "my_draft": v.read_text(v.user_path(topic_id, ident, "draft.md")),
        "my_notes": v.read_text(v.user_path(topic_id, ident, "notes.md")),
        "my_council": v.read_json(v.user_path(topic_id, ident, "council.json")),
        "shared_council": v.read_json(v.shared_path(topic_id, ident, "council.json")),
        "my_flint": v.read_json(v.user_path(topic_id, ident, "flint.json")),
        "teammates": others,
        "paths": {
            "shared": f"sbir/{topic_id}/{cid}/shared/",
            "mine": f"sbir/{topic_id}/{cid}/users/{ident.user_id}/",
            "employees": f"companies/{cid}/employees.txt",
            "sbir_txt": f"users/{ident.user_id}/sbir.txt",
        },
    }

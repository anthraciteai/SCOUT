"""Login, /me, and org roster. companies/{id}/employees/{you} is the access gate."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..config import settings
from ..identity import Identity, get_identity, issue_token
from ..org_seed import PEOPLE, verify_password
from ..vault import get_vault

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginBody(BaseModel):
    username: str
    password: str = ""
    company_id: Optional[str] = None


@router.get("/status")
def status():
    v = get_vault()
    users = []
    company = settings.default_company
    for p in PEOPLE:
        if not v.exists(v.employee_key(company, p["user_id"])):
            continue
        users.append(
            {
                "user_id": p["user_id"],
                "display_name": v.read_text(f"users/{p['user_id']}/display_name.txt").strip()
                or p["display_name"],
            }
        )
    extra = [
        u
        for u in v.company_employees(company)
        if u not in {p["user_id"] for p in PEOPLE}
    ]
    for uid in extra:
        users.append(
            {
                "user_id": uid,
                "display_name": v.read_text(f"users/{uid}/display_name.txt").strip() or uid,
            }
        )
    return {
        "auth_disabled": settings.auth_disabled,
        "keycloak_url": settings.keycloak_public_url or settings.keycloak_url,
        "keycloak_realm": settings.keycloak_realm,
        "keycloak_client_id": settings.keycloak_audience,
        "default_company": settings.default_company,
        "users": users,
    }


@router.post("/login")
async def login(body: LoginBody):
    v = get_vault()
    uid = (body.username or "").strip().lower()
    if not uid:
        raise HTTPException(status_code=400, detail="username required")
    company = (body.company_id or settings.default_company).strip()

    if not v.in_company(Identity(user_id=uid, company_id=company, display_name=uid, groups=[]), company):
        raise HTTPException(
            status_code=403,
            detail=f"{uid} is not employed at {company} (missing companies/{company}/employees/{uid})",
        )

    if not settings.auth_disabled:
        if not verify_password(v, uid, body.password):
            # Optional: resource-owner grant against Keycloak
            if settings.keycloak_url and body.password:
                if not await _keycloak_password(uid, body.password):
                    raise HTTPException(status_code=401, detail="Bad password")
            else:
                raise HTTPException(status_code=401, detail="Bad password")

    name = v.read_text(f"users/{uid}/display_name.txt").strip() or uid
    if not v.read_text(f"users/{uid}/display_name.txt").strip():
        v.write_text(f"users/{uid}/display_name.txt", uid + "\n")
    groups = ["capture"]
    for g_key in v.list_prefix(f"groups/{company}/"):
        # groups/{cid}/{gid}/members.txt
        parts = g_key.split("/")
        if len(parts) >= 4 and parts[-1] == "members.txt":
            gid = parts[2]
            if uid in v.lines(g_key) and gid not in groups:
                groups.append(gid)
    ident = Identity(
        user_id=uid,
        company_id=company,
        display_name=name,
        groups=groups,
        auth="stub",
    )
    token = issue_token(ident)
    return {"token": token, "user": _serialize(ident, v)}


@router.get("/me")
def me(ident: Identity = Depends(get_identity)):
    return _serialize(ident, get_vault())


def _serialize(ident: Identity, v) -> dict:
    return {
        "user_id": ident.user_id,
        "display_name": ident.display_name
        or v.read_text(f"users/{ident.user_id}/display_name.txt").strip()
        or ident.user_id,
        "company_id": ident.company_id,
        "groups": ident.groups,
        "auth": ident.auth,
        "skills": v.lines(f"users/{ident.user_id}/skills.txt"),
        "sbirs": v.user_sbirs(ident.user_id),
        "companies": v.user_companies(ident.user_id),
        "in_company": v.in_company(ident, ident.company_id),
    }


async def _keycloak_password(username: str, password: str) -> bool:
    import httpx
    from ..config import settings as s

    url = (
        f"{s.keycloak_url.rstrip('/')}/realms/{s.keycloak_realm}"
        "/protocol/openid-connect/token"
    )
    data = {
        "grant_type": "password",
        "client_id": s.keycloak_audience,
        "username": username,
        "password": password,
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.post(url, data=data)
        return r.status_code == 200
    except Exception:
        return False

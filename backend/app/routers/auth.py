"""Login, /me, and org roster. companies/{id}/employees/{you} is the access gate."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..config import settings
from ..identity import Identity, get_identity, issue_token, parse_keycloak_jwt
from ..org_seed import PEOPLE, verify_password
from ..vault import get_vault

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginBody(BaseModel):
    username: str
    password: str = ""
    company_id: Optional[str] = None


class RefreshBody(BaseModel):
    refresh_token: str


def _keycloak_mode() -> bool:
    return bool(settings.keycloak_url) and not settings.auth_disabled


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

    # Keycloak mode: get a REAL access token, verify it via the JWKS path, and
    # hand it to the browser so every later request is JWK-validated. All
    # Keycloak traffic stays server-side (no browser CORS).
    if _keycloak_mode():
        return await _keycloak_login(v, uid, body.password)

    # Stub / dev mode.
    if not v.in_company(Identity(user_id=uid, company_id=company, display_name=uid, groups=[]), company):
        raise HTTPException(
            status_code=403,
            detail=f"{uid} is not employed at {company} (missing companies/{company}/employees/{uid})",
        )

    if not settings.auth_disabled:
        if not verify_password(v, uid, body.password):
            raise HTTPException(status_code=401, detail="Bad password")

    name = _ensure_display_name(v, uid, uid)
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


@router.post("/refresh")
async def refresh(body: RefreshBody):
    """Exchange a Keycloak refresh token for a fresh access token (Keycloak
    mode only). Lets the SPA keep a short-lived access token alive."""
    if not _keycloak_mode():
        raise HTTPException(status_code=400, detail="Refresh only applies in Keycloak mode")
    tok = await _keycloak_grant({"grant_type": "refresh_token", "refresh_token": body.refresh_token})
    if not tok or not tok.get("access_token"):
        raise HTTPException(status_code=401, detail="Refresh failed")
    return await _token_response(get_vault(), tok)


async def _keycloak_login(v, uid: str, password: str) -> dict:
    if not password:
        raise HTTPException(status_code=401, detail="Password required")
    tok = await _keycloak_grant(
        {"grant_type": "password", "username": uid, "password": password, "scope": "openid"}
    )
    if not tok or not tok.get("access_token"):
        raise HTTPException(status_code=401, detail="Keycloak rejected credentials")
    return await _token_response(v, tok)


async def _token_response(v, tok: dict) -> dict:
    # Verify the token we just received through our own JWKS path so the browser
    # only ever holds a token the backend will actually accept.
    ident = await parse_keycloak_jwt(tok["access_token"])
    if not v.in_company(ident, ident.company_id):
        raise HTTPException(
            status_code=403,
            detail=f"{ident.user_id} is not employed at {ident.company_id}",
        )
    _ensure_display_name(v, ident.user_id, ident.display_name)
    return {
        "token": tok["access_token"],
        "refresh_token": tok.get("refresh_token"),
        "id_token": tok.get("id_token"),  # used as id_token_hint on logout
        "expires_in": tok.get("expires_in"),
        "user": _serialize(ident, v),
    }


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


def _ensure_display_name(v, uid: str, fallback: str) -> str:
    """Return the stored display name, seeding it from the fallback if empty."""
    name = v.read_text(f"users/{uid}/display_name.txt").strip()
    if not name:
        name = (fallback or uid).strip() or uid
        v.write_text(f"users/{uid}/display_name.txt", name + "\n")
    return name


async def _keycloak_grant(extra: dict) -> Optional[dict]:
    """Run an OIDC grant against the realm token endpoint. Returns the token
    JSON (access_token / refresh_token / expires_in) or None on failure."""
    import httpx

    url = (
        f"{settings.keycloak_url.rstrip('/')}/realms/{settings.keycloak_realm}"
        "/protocol/openid-connect/token"
    )
    data = {"client_id": settings.keycloak_audience, **extra}
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.post(url, data=data)
        if r.status_code == 200:
            return r.json()
    except Exception:
        return None
    return None

"""Request-scoped identity. Stub HMAC tokens, optional Keycloak userinfo."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Optional

import httpx
from fastapi import Header, HTTPException, Request

from .config import settings

_IDENT: ContextVar[Optional["Identity"]] = ContextVar("scout_identity", default=None)


@dataclass
class Identity:
    user_id: str
    company_id: str
    display_name: str
    groups: list[str] = field(default_factory=list)
    auth: str = "stub"  # stub | keycloak | disabled


def current_identity() -> Optional[Identity]:
    return _IDENT.get()


def set_identity(ident: Optional[Identity]):
    return _IDENT.set(ident)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def issue_token(ident: Identity, ttl: int = 60 * 60 * 24 * 14) -> str:
    payload = {
        "u": ident.user_id,
        "c": ident.company_id,
        "n": ident.display_name,
        "g": ident.groups,
        "exp": int(time.time()) + ttl,
    }
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64(
        hmac.new(settings.auth_secret.encode(), body.encode(), hashlib.sha256).digest()
    )
    return f"scout.{body}.{sig}"


def parse_stub_token(token: str) -> Identity:
    try:
        kind, body, sig = token.split(".", 2)
    except ValueError as e:
        raise HTTPException(status_code=401, detail="Bad token") from e
    if kind != "scout":
        raise HTTPException(status_code=401, detail="Bad token")
    expect = _b64(
        hmac.new(settings.auth_secret.encode(), body.encode(), hashlib.sha256).digest()
    )
    if not hmac.compare_digest(expect, sig):
        raise HTTPException(status_code=401, detail="Bad token")
    payload = json.loads(_unb64(body))
    if int(payload.get("exp") or 0) < time.time():
        raise HTTPException(status_code=401, detail="Token expired")
    return Identity(
        user_id=str(payload["u"]),
        company_id=str(payload.get("c") or "anthracite"),
        display_name=str(payload.get("n") or payload["u"]),
        groups=list(payload.get("g") or []),
        auth="stub",
    )


async def parse_keycloak_token(token: str) -> Identity:
    url = (
        f"{settings.keycloak_url.rstrip('/')}/realms/{settings.keycloak_realm}"
        "/protocol/openid-connect/userinfo"
    )
    async with httpx.AsyncClient(timeout=10.0) as c:
        r = await c.get(url, headers={"Authorization": f"Bearer {token}"})
    if r.status_code != 200:
        raise HTTPException(status_code=401, detail="Keycloak rejected token")
    info = r.json()
    uid = info.get("preferred_username") or info.get("sub")
    if not uid:
        raise HTTPException(status_code=401, detail="Keycloak token has no username")
    groups = info.get("groups") or []
    groups = [str(g).lstrip("/") for g in groups]
    company = settings.default_company
    for g in groups:
        if g and g != "capture":
            company = g
            break
    return Identity(
        user_id=str(uid),
        company_id=company,
        display_name=str(info.get("name") or uid),
        groups=groups or ["capture"],
        auth="keycloak",
    )


async def identity_from_bearer(authorization: Optional[str]) -> Optional[Identity]:
    if not authorization:
        return None
    raw = authorization[7:].strip() if authorization.lower().startswith("bearer ") else authorization.strip()
    if not raw:
        return None
    if raw.startswith("scout."):
        return parse_stub_token(raw)
    if settings.keycloak_url:
        return await parse_keycloak_token(raw)
    raise HTTPException(status_code=401, detail="Unknown token")


async def get_identity(
    authorization: Optional[str] = Header(default=None),
) -> Identity:
    ident = await identity_from_bearer(authorization)
    if ident:
        return ident
    if settings.auth_disabled:
        return Identity(
            user_id="dev",
            company_id=settings.default_company,
            display_name="Dev",
            groups=["capture"],
            auth="disabled",
        )
    raise HTTPException(status_code=401, detail="Sign in")


async def optional_identity(
    authorization: Optional[str] = Header(default=None),
) -> Optional[Identity]:
    try:
        return await get_identity(authorization=authorization)
    except HTTPException:
        return None


async def bind_identity_middleware(request: Request, call_next):
    ident = None
    try:
        ident = await identity_from_bearer(request.headers.get("authorization"))
    except HTTPException:
        ident = None
    if ident is None and settings.auth_disabled:
        ident = Identity(
            user_id="dev",
            company_id=settings.default_company,
            display_name="Dev",
            groups=["capture"],
            auth="disabled",
        )
    token = set_identity(ident)
    try:
        return await call_next(request)
    finally:
        _IDENT.reset(token)

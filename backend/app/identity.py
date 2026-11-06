"""Request-scoped identity.

Three token shapes are understood:
  - ``scout.<body>.<sig>``  dev stub, HMAC-signed with ``auth_secret``.
  - Keycloak access token    verified *locally* against the realm JWKS
                             (RS256 signature + exp + issuer + audience). No
                             per-request round-trip to Keycloak.
  - none, when ``auth_disabled`` is set (dev) -> a fixed ``dev`` identity.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Optional

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


# ---- Keycloak: local JWK/JWT validation --------------------------------
#
# We verify the access token's RS256 signature against the realm JWKS, plus
# exp / issuer / audience, entirely in-process. PyJWKClient fetches the JWKS
# once and caches the keys (keyed by ``kid``), so steady state is zero network.

_jwk_client: Any = None
_jwk_url: str = ""


def _jwks_url() -> str:
    base = settings.keycloak_url.rstrip("/")
    return f"{base}/realms/{settings.keycloak_realm}/protocol/openid-connect/certs"


def _get_jwk_client():
    """Process-wide PyJWKClient, rebuilt only if the JWKS URL changes."""
    global _jwk_client, _jwk_url
    from jwt import PyJWKClient  # local import: optional dep

    url = _jwks_url()
    if _jwk_client is None or _jwk_url != url:
        _jwk_client = PyJWKClient(url, cache_keys=True, lifespan=3600)
        _jwk_url = url
    return _jwk_client


def _expected_issuers() -> list[str]:
    out: list[str] = []
    for base in (settings.keycloak_url, settings.keycloak_public_url):
        b = (base or "").rstrip("/")
        if b:
            out.append(f"{b}/realms/{settings.keycloak_realm}")
    return out


def _check_issuer(claims: dict[str, Any]) -> None:
    expected = _expected_issuers()
    if expected and claims.get("iss") not in expected:
        raise HTTPException(status_code=401, detail="Token issuer mismatch")


def _check_audience(claims: dict[str, Any]) -> None:
    # Keycloak puts the client id in ``azp`` and often ``account`` in ``aud``,
    # so accept the configured audience in either slot.
    want = (settings.keycloak_audience or "").strip()
    if not want:
        return
    aud = claims.get("aud")
    auds = aud if isinstance(aud, list) else [aud] if aud else []
    if want in auds or claims.get("azp") == want:
        return
    raise HTTPException(status_code=401, detail="Token audience mismatch")


def _company_from_groups(groups: list[str]) -> str:
    for g in groups:
        if g and g != "capture":
            return g
    return settings.default_company


def _identity_from_claims(claims: dict[str, Any], auth: str) -> Identity:
    uid = claims.get("preferred_username") or claims.get("sub")
    if not uid:
        raise HTTPException(status_code=401, detail="Token has no username")
    groups = [str(g).lstrip("/") for g in (claims.get("groups") or [])]
    return Identity(
        user_id=str(uid),
        company_id=_company_from_groups(groups),
        display_name=str(claims.get("name") or uid),
        groups=groups or ["capture"],
        auth=auth,
    )


async def parse_keycloak_jwt(token: str) -> Identity:
    import jwt  # local import: optional dep

    try:
        signing_key = await asyncio.to_thread(
            _get_jwk_client().get_signing_key_from_jwt, token
        )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — JWKS fetch / kid lookup failures
        raise HTTPException(status_code=401, detail=f"Signing key lookup failed: {e}") from e

    try:
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            # We enforce aud/iss ourselves (Keycloak's aud is quirky).
            options={"require": ["exp"], "verify_aud": False},
            leeway=30,
        )
    except jwt.ExpiredSignatureError as e:
        raise HTTPException(status_code=401, detail="Token expired") from e
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}") from e

    _check_issuer(claims)
    _check_audience(claims)
    return _identity_from_claims(claims, auth="keycloak")


async def identity_from_bearer(authorization: Optional[str]) -> Optional[Identity]:
    if not authorization:
        return None
    raw = authorization[7:].strip() if authorization.lower().startswith("bearer ") else authorization.strip()
    if not raw:
        return None
    if raw.startswith("scout."):
        return parse_stub_token(raw)
    if settings.keycloak_url:
        return await parse_keycloak_jwt(raw)
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

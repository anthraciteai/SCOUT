"""Regression tests for local Keycloak JWK/JWT validation.

No live Keycloak: we mint our own RSA keypair, sign tokens with it, and point
the JWK client at the matching public key. This locks down signature, exp,
issuer and audience checks, plus the group -> company mapping.
"""
import asyncio
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app import identity
from app.identity import Identity

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PUB = _KEY.public_key()


class _FakeSigningKey:
    key = _PUB


class _FakeJwkClient:
    def get_signing_key_from_jwt(self, token):  # noqa: ARG002
        return _FakeSigningKey()


def _issue(claims: dict, key=_KEY) -> str:
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "test"})


def _parse(token: str) -> Identity:
    return asyncio.run(identity.parse_keycloak_jwt(token))


@pytest.fixture(autouse=True)
def _wire(monkeypatch):
    monkeypatch.setattr(identity, "_get_jwk_client", lambda: _FakeJwkClient())
    monkeypatch.setattr(identity.settings, "keycloak_url", "http://kc:8080")
    monkeypatch.setattr(identity.settings, "keycloak_public_url", "")
    monkeypatch.setattr(identity.settings, "keycloak_realm", "scout")
    monkeypatch.setattr(identity.settings, "keycloak_audience", "scout-frontend")
    monkeypatch.setattr(identity.settings, "default_company", "anthracite")


def _base_claims(**over) -> dict:
    claims = {
        "iss": "http://kc:8080/realms/scout",
        "aud": "scout-frontend",
        "exp": int(time.time()) + 300,
        "preferred_username": "alice",
        "name": "Alice A",
        "groups": ["/acme", "/capture"],
    }
    claims.update(over)
    return claims


def test_valid_token_maps_to_identity():
    ident = _parse(_issue(_base_claims()))
    assert isinstance(ident, Identity)
    assert ident.user_id == "alice"
    assert ident.company_id == "acme"  # first non-"capture" group
    assert ident.display_name == "Alice A"
    assert ident.auth == "keycloak"
    assert ident.groups == ["acme", "capture"]


def test_audience_in_azp_is_accepted():
    claims = _base_claims(aud="account", azp="scout-frontend")
    ident = _parse(_issue(claims))
    assert ident.user_id == "alice"


def test_expired_token_rejected():
    with pytest.raises(identity.HTTPException) as e:
        _parse(_issue(_base_claims(exp=int(time.time()) - 120)))
    assert e.value.status_code == 401


def test_wrong_audience_rejected():
    claims = _base_claims(aud="someone-else", azp="someone-else")
    with pytest.raises(identity.HTTPException) as e:
        _parse(_issue(claims))
    assert e.value.status_code == 401
    assert "audience" in e.value.detail.lower()


def test_wrong_issuer_rejected():
    with pytest.raises(identity.HTTPException) as e:
        _parse(_issue(_base_claims(iss="http://evil/realms/scout")))
    assert e.value.status_code == 401
    assert "issuer" in e.value.detail.lower()


def test_bad_signature_rejected():
    # Sign with a *different* key than the one the JWK client hands back.
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(identity.HTTPException) as e:
        _parse(_issue(_base_claims(), key=other))
    assert e.value.status_code == 401


def test_company_from_groups_fallback():
    assert identity._company_from_groups(["capture"]) == "anthracite"
    assert identity._company_from_groups([]) == "anthracite"
    assert identity._company_from_groups(["capture", "acme"]) == "acme"

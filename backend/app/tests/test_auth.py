"""Login / refresh behavior.

In Keycloak mode the browser must receive a REAL Keycloak access token (so
later requests hit the JWK-validation path), not a stub token. In dev mode it
still gets a stub token. Keycloak + vault are mocked.
"""
import asyncio

import pytest

from app.routers import auth
from app.identity import Identity


class FakeVault:
    def __init__(self):
        self.store: dict[str, str] = {}

    def read_text(self, key):
        return self.store.get(key, "")

    def write_text(self, key, val):
        self.store[key] = val

    def lines(self, key):
        return []

    def list_prefix(self, prefix):
        return []

    def user_sbirs(self, uid):
        return []

    def user_companies(self, uid):
        return [self._company] if getattr(self, "_company", None) else []

    def in_company(self, ident, company_id=None):
        return True


async def _fake_grant(extra):
    # Echo which grant was requested so refresh vs password is distinguishable.
    kind = extra.get("grant_type")
    return {
        "access_token": f"KC_{kind}",
        "refresh_token": f"R_{kind}",
        "expires_in": 300,
    }


async def _fake_parse(token):
    return Identity(
        user_id="alice",
        company_id="acme",
        display_name="Alice A",
        groups=["acme"],
        auth="keycloak",
    )


@pytest.fixture
def kc(monkeypatch):
    monkeypatch.setattr(auth.settings, "keycloak_url", "http://kc:8080")
    monkeypatch.setattr(auth.settings, "auth_disabled", False)
    monkeypatch.setattr(auth, "_keycloak_grant", _fake_grant)
    monkeypatch.setattr(auth, "parse_keycloak_jwt", _fake_parse)
    monkeypatch.setattr(auth, "get_vault", lambda: FakeVault())


def test_keycloak_login_returns_real_access_token(kc):
    res = asyncio.run(auth.login(auth.LoginBody(username="alice", password="pw")))
    assert res["token"] == "KC_password"  # the Keycloak token, NOT a stub
    assert not res["token"].startswith("scout.")
    assert res["refresh_token"] == "R_password"
    assert res["user"]["user_id"] == "alice"
    assert res["user"]["auth"] == "keycloak"


def test_keycloak_login_requires_password(kc):
    with pytest.raises(auth.HTTPException) as e:
        asyncio.run(auth.login(auth.LoginBody(username="alice", password="")))
    assert e.value.status_code == 401


def test_refresh_exchanges_refresh_token(kc):
    res = asyncio.run(auth.refresh(auth.RefreshBody(refresh_token="R_password")))
    assert res["token"] == "KC_refresh_token"
    assert res["user"]["user_id"] == "alice"


def test_refresh_rejected_outside_keycloak_mode(monkeypatch):
    monkeypatch.setattr(auth.settings, "keycloak_url", "")
    monkeypatch.setattr(auth.settings, "auth_disabled", True)
    with pytest.raises(auth.HTTPException) as e:
        asyncio.run(auth.refresh(auth.RefreshBody(refresh_token="x")))
    assert e.value.status_code == 400


def test_dev_login_still_issues_stub_token(monkeypatch):
    monkeypatch.setattr(auth.settings, "auth_disabled", True)
    monkeypatch.setattr(auth.settings, "keycloak_url", "")
    monkeypatch.setattr(auth, "get_vault", lambda: FakeVault())
    res = asyncio.run(auth.login(auth.LoginBody(username="dev")))
    assert res["token"].startswith("scout.")
    assert res["user"]["user_id"] == "dev"

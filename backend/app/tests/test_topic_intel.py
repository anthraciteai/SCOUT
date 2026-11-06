"""Regression tests for the topic-intel OCR/summarize/fit helpers.

Covers the pure text handling and the on-disk cache. The async routes
themselves call Docling / Ollama / DSIP and are exercised manually; here we
lock down the deterministic pieces they rely on.
"""
import pytest

from app.routers import topic_intel


def test_strip_html():
    assert topic_intel._strip_html("<b>x</b> y").strip() == "x  y".strip()
    assert topic_intel._strip_html(None) == ""


def test_harvest_strings_collects_and_strips_from_nested_json():
    details = {
        "objective": "<p>Develop an autonomous system</p>",
        "phases": [{"title": "Phase I"}, {"title": "Phase II"}],
        "keywords": ["autonomy", "x"],  # "x" is < 3 chars -> dropped
        "count": 7,  # non-string ignored
        "nested": {"deep": {"note": "contested logistics"}},
    }
    out: list[str] = []
    topic_intel._harvest_strings(details, out)
    joined = "\n".join(out)
    assert "Develop an autonomous system" in joined
    assert "Phase I" in joined
    assert "Phase II" in joined
    assert "contested logistics" in joined
    assert "autonomy" in out
    assert "x" not in out  # too short
    assert "<p>" not in joined  # html stripped


def test_harvest_strings_respects_budget():
    big = "y" * 5000
    out: list[str] = []
    topic_intel._harvest_strings({"a": big, "b": big, "c": big, "d": big, "e": big}, out, budget=6000)
    # Stops adding once the running length exceeds the budget.
    assert sum(len(x) for x in out) <= 5000 + 6000


@pytest.fixture
def fresh_vault(tmp_path, monkeypatch):
    """Point the vault at a throwaway dir and reset the process-wide singleton."""
    import app.vault as vault_mod

    monkeypatch.setattr(vault_mod.settings, "vault_dir", str(tmp_path / "vault"))
    monkeypatch.setattr(topic_intel.settings, "data_dir", str(tmp_path))
    vault_mod._vault = None
    yield vault_mod.get_vault()
    vault_mod._vault = None


# ---- storage: shared topic artifacts live globally -------------------

def test_shared_cache_roundtrip(fresh_vault):
    payload = {"topic_id": "abc_123", "chars": 10, "text": "hello"}
    topic_intel._write_shared("abc_123", "text", payload)
    assert topic_intel._read_shared("abc_123", "text") == payload
    # distinct kinds do not collide
    assert topic_intel._read_shared("abc_123", "summary") is None


def test_shared_cache_is_global_not_company_scoped(fresh_vault):
    # text/summary are keyed only by topic id (sbirs/{id}/intel/...), so the
    # same cached copy is reused regardless of who asks -> one compute, org-wide.
    key = fresh_vault.intel_text_key("t9")
    assert key == "sbirs/t9/intel/text.json"
    assert "companies/" not in key and "/users/" not in key


def test_legacy_disk_cache_is_migrated_on_read(fresh_vault, tmp_path):
    # Simulate a pre-vault disk cache; _read_shared should promote it.
    legacy_dir = tmp_path / "topic_intel" / "t5"
    legacy_dir.mkdir(parents=True)
    (legacy_dir / "summary.json").write_text('{"tldr": "old"}')
    got = topic_intel._read_shared("t5", "summary")
    assert got == {"tldr": "old"}
    # and it is now in the vault (no second disk read needed)
    assert fresh_vault.read_json(fresh_vault.intel_summary_key("t5")) == {"tldr": "old"}


# ---- identity scoping (shared summary vs per-user fit) ----------------

def test_ident_key_falls_back_to_default_company_and_shared_user(monkeypatch):
    monkeypatch.setattr(topic_intel, "current_identity", lambda: None)
    monkeypatch.setattr(topic_intel.settings, "default_company", "anthracite")
    assert topic_intel._ident_key() == ("anthracite", "shared")


def test_ident_key_uses_and_sanitizes_identity(monkeypatch):
    class _Ident:
        company_id = "acme/corp"
        user_id = "user@42"

    monkeypatch.setattr(topic_intel, "current_identity", lambda: _Ident())
    assert topic_intel._ident_key() == ("acme_corp", "user_42")


def test_fit_key_is_scoped_per_user(fresh_vault):
    a = fresh_vault.intel_fit_key("t1", "acme", "alice")
    b = fresh_vault.intel_fit_key("t1", "acme", "bob")
    assert a != b
    assert a == "sbir/t1/acme/users/alice/fit.json"


def test_fit_cache_is_isolated_between_users(fresh_vault):
    # Two users score the same topic; each reads back only their own fit.
    topic_intel._write_fit("t1", "acme", "alice", {"overall_fit": 90})
    topic_intel._write_fit("t1", "acme", "bob", {"overall_fit": 10})
    assert topic_intel._read_fit("t1", "acme", "alice") == {"overall_fit": 90}
    assert topic_intel._read_fit("t1", "acme", "bob") == {"overall_fit": 10}
    # A brand-new user has no cached fit yet.
    assert topic_intel._read_fit("t1", "acme", "carol") is None

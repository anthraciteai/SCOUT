"""Regression tests for the topic-intel OCR/summarize/fit helpers.

Covers the pure text handling and the on-disk cache. The async routes
themselves call Docling / Ollama / DSIP and are exercised manually; here we
lock down the deterministic pieces they rely on.
"""
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


def test_cache_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(topic_intel.settings, "data_dir", str(tmp_path))
    payload = {"topic_id": "abc_123", "chars": 10, "text": "hello"}
    topic_intel._write_json("abc_123", "text.json", payload)
    got = topic_intel._read_json("abc_123", "text.json")
    assert got == payload
    # missing file -> None
    assert topic_intel._read_json("abc_123", "nope.json") is None


def test_cache_dir_sanitizes_topic_id(tmp_path, monkeypatch):
    monkeypatch.setattr(topic_intel.settings, "data_dir", str(tmp_path))
    # path separators / odd chars must not escape the cache root
    d = topic_intel._cache_dir("../../etc/passwd")
    assert str(tmp_path) in d
    assert "/etc/passwd" not in d


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


def test_fit_name_is_scoped_per_identity():
    assert (
        topic_intel._fit_name("acme", "alice")
        != topic_intel._fit_name("acme", "bob")
    )
    assert topic_intel._fit_name("acme", "alice") == "fit__acme__alice.json"


def test_fit_cache_is_isolated_between_users(tmp_path, monkeypatch):
    monkeypatch.setattr(topic_intel.settings, "data_dir", str(tmp_path))
    # Two users score the same topic; each must read back only their own fit.
    topic_intel._write_json("t1", topic_intel._fit_name("acme", "alice"), {"overall_fit": 90})
    topic_intel._write_json("t1", topic_intel._fit_name("acme", "bob"), {"overall_fit": 10})
    assert topic_intel._read_json("t1", topic_intel._fit_name("acme", "alice")) == {"overall_fit": 90}
    assert topic_intel._read_json("t1", topic_intel._fit_name("acme", "bob")) == {"overall_fit": 10}
    # A brand-new user has no cached fit yet.
    assert topic_intel._read_json("t1", topic_intel._fit_name("acme", "carol")) is None

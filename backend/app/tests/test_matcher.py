"""Regression tests for the cheap inbox ranker's pure helpers.

These guard the scoring math and text handling that the whole inbox depends
on. No network / LLM / DB — just deterministic functions.
"""
from app import matcher


def test_strip_html_removes_tags():
    assert matcher._strip_html("<p>hello <b>world</b></p>").strip() == "hello  world".strip()
    assert matcher._strip_html("") == ""
    assert matcher._strip_html(None) == ""  # tolerant of None


def test_tokens_lowercases_and_drops_stopwords_and_short():
    toks = matcher._tokens("The Autonomous DRONE navigates to a base")
    assert "autonomous" in toks
    assert "drone" in toks
    assert "navigates" in toks
    # stopwords removed
    assert "the" not in toks
    assert "to" not in toks
    # every surviving token is >= 3 chars and lowercase
    assert all(len(t) >= 3 and t == t.lower() for t in toks)


def test_tokens_excludes_pure_digits():
    assert "2024" not in matcher._tokens("built 2024 systems")


def test_uniq_dedupes_case_insensitively_and_honors_limit():
    assert matcher._uniq(["AI", "ai", "ML", "ml", "ML"]) == ["AI", "ML"]
    assert matcher._uniq(["AI", "ML", "RF"], limit=2) == ["AI", "ML"]
    assert matcher._uniq(["", "  ", "AI"]) == ["AI"]


def test_contains_uses_word_boundary_for_single_words():
    assert matcher._contains("edge autonomy systems", "autonomy") is True
    assert matcher._contains("autonomyx", "autonomy") is False
    # too short to match
    assert matcher._contains("an ai tool", "ai") is False


def test_contains_substring_for_phrases_and_hyphens():
    assert matcher._contains("real-time control loop", "real-time") is True
    assert matcher._contains("computer vision pipeline", "computer vision") is True
    assert matcher._contains("vision only", "computer vision") is False


def test_topic_blob_joins_title_and_body_fields():
    title, blob = matcher._topic_blob(
        {
            "topicTitle": "Edge Autonomy",
            "topicCode": "AF251-001",
            "objective": "<p>navigate contested airspace</p>",
            "keywords": "drone, swarm",
        }
    )
    assert "Edge Autonomy" in title
    assert "AF251-001" in title
    assert "navigate contested airspace" in blob
    assert "drone" in blob
    assert "<p>" not in blob  # html stripped


def test_score_topic_returns_zero_with_no_profile_terms():
    score, reasons = matcher.score_topic({"topicTitle": "Anything"}, {})
    assert score == 0.0
    assert reasons == []


def test_score_topic_is_bounded_and_rewards_title_hits():
    topic = {
        "topicTitle": "Autonomous Drone Swarm",
        "objective": "autonomy and navigation for swarms",
    }
    profile = {"keywords": ["autonomy", "drone", "swarm"], "skills": [], "domains": []}
    score, reasons = matcher.score_topic(topic, profile)
    assert 0.0 <= score <= 100.0
    assert score > 0.0
    assert any("Title mentions" in r for r in reasons)


def test_score_topic_no_overlap_scores_zero():
    topic = {"topicTitle": "Hypersonic Materials", "objective": "thermal protection"}
    profile = {"keywords": ["payroll", "accounting"], "skills": [], "domains": []}
    score, reasons = matcher.score_topic(topic, profile)
    assert score == 0.0
    assert reasons == []

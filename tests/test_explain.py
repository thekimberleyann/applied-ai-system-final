"""Tests for the generation + orchestration layers (src/llm_client.py, src/explain.py).

These pin the RAG feature's reliability guarantees:
  * the offline stub is deterministic (same inputs -> identical text),
  * the explanation is GROUNDED -- its descriptive clause is drawn from the
    retrieved note, never invented,
  * the no-note guardrail returns a score-only fallback that never describes the
    song,
  * the LLM layer NEVER re-ranks: explain_recommendations returns exactly the
    recommender's order and scores,
  * the structured results carry confidence + grounded flags,
  * a decimal in a note is not mistaken for a sentence break.

Everything runs with force_offline=True so the tests are deterministic and need no
API key or network.

Run from the repo root:  python -m pytest
"""

import os

from src.explain import explain_recommendations, format_block
from src.llm_client import VibeExplainer
from src.recommender import load_songs, recommend_songs
from src.retriever import load_notes

REAL_CSV = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "songs.csv",
)
REAL_NOTES = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "song_notes.md",
)

DEFAULT_PROFILE = {
    "favorite_genre": "pop",
    "favorite_mood": "happy",
    "target_energy": 0.8,
}


def _offline_client() -> VibeExplainer:
    return VibeExplainer(force_offline=True)


def test_offline_mode_selected():
    """force_offline pins the deterministic path even if a key is in the env."""
    assert _offline_client().mode == "offline"


def test_offline_explanation_is_deterministic():
    """Same inputs must produce byte-identical output on repeated calls."""
    client = _offline_client()
    song = {"title": "Summer Anthem", "genre": "pop", "mood": "happy"}
    reasons = ["genre match (+2.0)", "mood match (+1.0)", "energy close to target (+1.00)"]
    note = "An upbeat pop anthem by Coast Kids, high energy at 0.80 and a danceable 120 BPM."
    first = client.explain(song, 4.0, reasons, note, DEFAULT_PROFILE)
    second = client.explain(song, 4.0, reasons, note, DEFAULT_PROFILE)
    assert first == second


def test_explanation_is_grounded_in_the_note():
    """The descriptive clause comes from the note, and a decimal is not a break.

    The full first sentence of the note (which contains '0.80') must appear in the
    explanation -- proving the stub grounds on the note AND that the decimal point
    did not truncate the sentence at '0'.
    """
    client = _offline_client()
    song = {"title": "Summer Anthem", "genre": "pop", "mood": "happy"}
    reasons = ["genre match (+2.0)", "mood match (+1.0)", "energy close to target (+1.00)"]
    note = "An upbeat pop anthem by Coast Kids, high energy at 0.80 and a danceable 120 BPM."
    text = client.explain(song, 4.0, reasons, note, DEFAULT_PROFILE)
    assert "high energy at 0.80 and a danceable 120 BPM" in text
    # And it names why it matched, from the deterministic reasons.
    assert "your favorite genre" in text


def test_no_note_triggers_score_only_fallback():
    """With no retrieved note the guardrail returns a score-only line.

    The fallback must NOT contain any note prose (there is none to ground on) and
    must restate the deterministic reasons instead.
    """
    client = _offline_client()
    song = {"title": "Mystery Track", "genre": "pop", "mood": "happy"}
    reasons = ["energy close to target (+0.50)"]
    text = client.explain(song, 0.5, reasons, note=None, prefs=DEFAULT_PROFILE)
    assert "score alone" in text
    assert "energy close to target (+0.50)" in text


def test_llm_layer_never_reranks():
    """explain_recommendations must return the recommender's exact order/scores."""
    songs = load_songs(REAL_CSV)
    notes = load_notes(REAL_NOTES)
    client = _offline_client()

    baseline = recommend_songs(DEFAULT_PROFILE, songs, k=5)
    explained = explain_recommendations(DEFAULT_PROFILE, songs, notes, client, k=5)

    baseline_seq = [(s["title"], round(score, 2)) for s, score, _ in baseline]
    explained_seq = [(r["song"]["title"], round(r["score"], 2)) for r in explained]
    assert explained_seq == baseline_seq


def test_results_carry_confidence_and_grounded_flags():
    """Each structured result exposes confidence (0-1) and a grounded bool."""
    songs = load_songs(REAL_CSV)
    notes = load_notes(REAL_NOTES)
    results = explain_recommendations(DEFAULT_PROFILE, songs, notes, _offline_client(), k=5)
    assert len(results) == 5
    for r in results:
        assert 0.0 <= r["confidence"] <= 1.0
        assert isinstance(r["grounded"], bool)
        assert r["explanation"]
    # On the real catalog every pick has a note, so all should be grounded.
    assert all(r["grounded"] for r in results)


def test_format_block_renders_why_lines():
    """The printable block includes the header and a 'why:' line per song."""
    songs = load_songs(REAL_CSV)
    notes = load_notes(REAL_NOTES)
    results = explain_recommendations(DEFAULT_PROFILE, songs, notes, _offline_client(), k=3)
    block = format_block("=== TEST ===", results)
    assert "=== TEST ===" in block
    assert block.count("why:") == 3

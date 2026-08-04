"""Tests for the glass-box inspection layer.

The contract these pin, in order of importance:

  1. The Inspector can never disagree with the system it describes. The full
     retrieval board's winner must match the note retrieve_note actually picked.
     A debugging view that reports a different answer than the code took is
     worse than no view, because it sends you hunting for a bug that is in the
     view rather than the system.
  2. Observation does not perturb. A run's output is identical whether or not it
     was inspected. This is the same shape as the guardrail pinning that the
     explanation layer never re-ranks.
  3. Prompt assembly is pure and works with no API key, since the reviewer's
     default configuration has no credentials.
"""

from __future__ import annotations

import copy
import os

from src.explain import explain_recommendations
from src.glassbox import (
    inspect_run,
    inspect_song,
    rank_table,
    retrieval_board,
    score_breakdown,
)
from src.llm_client import VibeExplainer, build_explain_prompt
from src.recommender import load_songs, recommend_songs
from src.retriever import MIN_CONFIDENCE, load_notes, retrieve_note, score_all_notes

DATA = os.path.join(os.path.dirname(__file__), "..", "data")
PREFS = {"favorite_genre": "pop", "favorite_mood": "happy", "target_energy": 0.80}


def _catalog():
    return load_songs(os.path.join(DATA, "songs.csv"))


def _notes():
    return load_notes(os.path.join(DATA, "song_notes.md"))


# ---------------------------------------------------------------------------
# 1. The board cannot lie about the pick
# ---------------------------------------------------------------------------

def test_board_winner_agrees_with_retrieve_note_for_every_song():
    """score_all_notes must never contradict the note retrieve_note chose.

    Checked across the WHOLE catalog rather than one song, because the two
    disagree only in the specific case where the exact-title tiebreak overrides
    a higher-overlap sibling, and a single-song test could easily miss it.
    """
    songs, notes = _catalog(), _notes()

    for song in songs:
        board = score_all_notes(song, notes)
        _note, confidence, picked_title = retrieve_note(song, notes)

        if picked_title is None:
            # Nothing cleared the floor. Then no board row may claim to.
            assert all(not row["above_floor"] for row in board), song["title"]
            continue

        row = next(r for r in board if r["title"] == picked_title)
        # The confidence retrieve_note reports IS this row's overlap.
        assert row["overlap"] == confidence, song["title"]
        assert row["above_floor"], song["title"]


def test_board_is_ordered_by_overlap_descending():
    """The board shows what pure token overlap would have retrieved.

    Ordering by overlap (not by the tiebreak-adjusted pick) is what makes a
    disagreement between the two visible in the Inspector.
    """
    songs, notes = _catalog(), _notes()
    board = score_all_notes(songs[0], notes)
    overlaps = [row["overlap"] for row in board]
    assert overlaps == sorted(overlaps, reverse=True)


def test_board_covers_every_note_exactly_once():
    songs, notes = _catalog(), _notes()
    board = score_all_notes(songs[0], notes)
    assert len(board) == len(notes)
    assert {row["title"] for row in board} == set(notes)


def test_floor_flag_matches_the_module_constant():
    """above_floor must be derived from MIN_CONFIDENCE, not a copied literal."""
    songs, notes = _catalog(), _notes()
    for row in score_all_notes(songs[0], notes):
        assert row["above_floor"] == (row["overlap"] >= MIN_CONFIDENCE)


# ---------------------------------------------------------------------------
# 2. Observation does not perturb
# ---------------------------------------------------------------------------

def test_inspecting_a_run_does_not_change_its_results():
    """The guardrail for an observability layer: looking must not alter.

    Runs the real explanation pipeline before and after a full inspection and
    requires byte-identical output.
    """
    songs, notes = _catalog(), _notes()
    client = VibeExplainer(force_offline=True)

    before = explain_recommendations(PREFS, songs, notes, client, k=5)
    inspect_run(PREFS, songs, notes, k=5)
    after = explain_recommendations(PREFS, songs, notes, client, k=5)

    assert [r["explanation"] for r in before] == [r["explanation"] for r in after]
    assert [r["song"]["title"] for r in before] == [r["song"]["title"] for r in after]


def test_inspection_does_not_mutate_the_catalog_or_corpus():
    songs, notes = _catalog(), _notes()
    songs_snapshot = copy.deepcopy(songs)
    notes_snapshot = copy.deepcopy(notes)

    inspect_run(PREFS, songs, notes, k=5)

    assert songs == songs_snapshot
    assert notes == notes_snapshot


def test_ranking_order_matches_the_real_recommender():
    """The Inspector's table must be the recommender's ordering, not its own."""
    songs, notes = _catalog(), _notes()
    rows = rank_table(PREFS, songs, k=5, limit=len(songs))
    expected = [s["title"] for s, _sc, _r in recommend_songs(PREFS, songs, k=len(songs))]
    assert [row["title"] for row in rows] == expected


# ---------------------------------------------------------------------------
# 3. Score breakdown reconciles
# ---------------------------------------------------------------------------

def test_breakdown_terms_sum_to_the_total():
    """Inherits score_song's reasons-sum-to-the-score guarantee.

    The breakdown parses the reasons rather than recomputing the recipe, so if
    this ever fails it means the parsing drifted, not that the recipe changed.
    """
    songs = _catalog()
    for song in songs:
        b = score_breakdown(PREFS, song)
        assert round(sum(b["terms"].values()), 2) == round(b["total"], 2), song["title"]


def test_breakdown_marks_the_shown_cut():
    songs = _catalog()
    rows = rank_table(PREFS, songs, k=5)
    assert [row["shown"] for row in rows[:5]] == [True] * 5
    assert all(not row["shown"] for row in rows[5:])


# ---------------------------------------------------------------------------
# 4. The prompt panel works with no API key
# ---------------------------------------------------------------------------

def test_prompt_is_built_offline_without_any_key(monkeypatch):
    """The panel that shows what retrieval feeds the model must not need credentials."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    songs, notes = _catalog(), _notes()

    record = inspect_song(PREFS, songs[0], notes)
    assert record["prompt"] is not None
    assert "Use ONLY facts stated in the note" in record["prompt"]


def test_prompt_contains_the_retrieved_note_and_nothing_invented():
    """Grounding, made visible: the note text must literally appear in the prompt."""
    songs, notes = _catalog(), _notes()
    record = inspect_song(PREFS, songs[0], notes)
    assert record["retrieval"]["picked_note"] in record["prompt"]


def test_prompt_is_deterministic():
    reasons = ["genre match (+2.0)"]
    a = build_explain_prompt(reasons, "A note.", PREFS)
    b = build_explain_prompt(reasons, "A note.", PREFS)
    assert a == b


def test_no_prompt_is_built_when_nothing_clears_the_floor():
    """The fallback guardrail: no note means no prompt, not an ungrounded one."""
    notes = _notes()
    alien = {"title": "Zzzz Qqqq", "genre": "zzzz", "mood": "qqqq", "energy": 0.5}

    record = inspect_song(PREFS, alien, notes)
    assert record["retrieval"]["grounded"] is False
    assert record["prompt"] is None
    assert "confidence floor" in record["prompt_withheld_reason"]


# ---------------------------------------------------------------------------
# 5. The tiebreak disagreement is reported honestly
# ---------------------------------------------------------------------------

def test_tiebreak_override_is_reported_when_it_happens():
    """At least one real song must exercise the override, or the flag is untested.

    If this fails after a corpus edit it does not necessarily mean a bug: it may
    mean no song's note is out-competed by a sibling any more. Check the board
    before assuming the flag broke.
    """
    songs, notes = _catalog(), _notes()
    overrides = [
        retrieval_board(song, notes)
        for song in songs
        if retrieval_board(song, notes)["tiebreak_overrode"]
    ]
    assert overrides, "no song exercises the exact-title tiebreak override"

    for board in overrides:
        # In an override the picked note is NOT the overlap leader, which is
        # precisely the discrepancy the Inspector exists to show.
        assert board["picked_title"] != board["overlap_winner"]
        assert board["picked_title"] == board["song_title"]


def test_strict_overrides_are_distinguished_from_ties():
    """A tie broken by title is not a retrieval failure; a strict loss is.

    Most overrides on this catalog are equal-overlap ties, where any tiebreak
    rule must pick something. Only a few are cases where a sibling note genuinely
    scored higher and the song's own note would have LOST. Reporting the two as
    one number would overstate how often overlap mis-retrieves.
    """
    songs, notes = _catalog(), _notes()
    boards = [retrieval_board(song, notes) for song in songs]

    strict = [b for b in boards if b["strict_override"]]
    overrides = [b for b in boards if b["tiebreak_overrode"]]

    # Every strict override is an override, but not the reverse.
    assert len(strict) < len(overrides)

    for b in strict:
        picked = next(r for r in b["board"] if r["title"] == b["picked_title"])
        assert b["board"][0]["overlap"] > picked["overlap"]

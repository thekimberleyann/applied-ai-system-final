"""Tests for the retrieval evaluation harness.

Two jobs. First, pin the metric functions themselves, because a broken metric is
worse than no metric: it produces a number that looks authoritative and is wrong.
Second, pin the measured properties of the shipped retriever, so that a corpus
edit or a similarity change that degrades retrieval fails a test instead of
silently lowering quality.
"""

from __future__ import annotations

from dataclasses import replace

import os

from src.evaluate_retrieval import (
    evaluate,
    gold_pairs,
    hit_at_k,
    leave_one_out,
    reciprocal_rank,
)
from src.config import DEFAULT_RETRIEVAL
from src.recommender import load_songs
from src.retriever import MIN_CONFIDENCE, load_notes, missing_notes, retrieve_note

DATA = os.path.join(os.path.dirname(__file__), "..", "data")


def _catalog():
    return load_songs(os.path.join(DATA, "songs.csv"))


def _notes():
    return load_notes(os.path.join(DATA, "song_notes.md"))


# ---------------------------------------------------------------------------
# The metrics themselves, on hand-built boards where the answer is obvious
# ---------------------------------------------------------------------------

def _board(*titles: str) -> list[dict]:
    """A minimal ranked board: only the ordering matters to these metrics."""
    return [{"title": t, "overlap": 1.0, "exact": False, "above_floor": True}
            for t in titles]


def test_hit_at_k_respects_the_cutoff():
    board = _board("a", "b", "c", "d")
    assert hit_at_k(board, "a", 1) is True
    assert hit_at_k(board, "c", 1) is False
    assert hit_at_k(board, "c", 3) is True
    assert hit_at_k(board, "d", 3) is False


def test_reciprocal_rank_is_one_over_position():
    board = _board("a", "b", "c")
    assert reciprocal_rank(board, "a") == 1.0
    assert reciprocal_rank(board, "b") == 0.5
    assert round(reciprocal_rank(board, "c"), 4) == round(1 / 3, 4)


def test_reciprocal_rank_is_zero_when_gold_is_absent():
    """A missing gold document scores 0, not an error and not a small number."""
    assert reciprocal_rank(_board("a", "b"), "zzz") == 0.0


# ---------------------------------------------------------------------------
# The gold set
# ---------------------------------------------------------------------------

def test_every_song_has_a_gold_note():
    """A song with no note has no correct answer and cannot be scored.

    If this fails, someone added a catalog row without writing its note. That is
    exactly the situation leave_one_out shows is dangerous, so it is worth
    catching here as well.
    """
    songs, notes = _catalog(), _notes()
    assert len(gold_pairs(songs, notes)) == len(songs)


# ---------------------------------------------------------------------------
# Measured properties of the shipped retriever
# ---------------------------------------------------------------------------

def test_shipped_retriever_always_finds_the_right_note_first():
    """hit@1 of 1.0 is the contract the exact-title tiebreak exists to deliver."""
    songs, notes = _catalog(), _notes()
    result = evaluate(songs, notes)
    assert result["hit@1"] == 1.0
    assert result["mrr"] == 1.0


def test_the_tiebreak_is_load_bearing_not_decoration():
    """Pure token overlap is measurably worse, which is why the tiebreak exists.

    This pins the JUSTIFICATION for the tiebreak. If a future similarity metric
    made overlap good enough on its own, this test would fail and the tiebreak
    could then be reconsidered on evidence rather than removed on a hunch.
    """
    songs, notes = _catalog(), _notes()
    shipped = evaluate(songs, notes)
    overlap = evaluate(songs, notes, replace(DEFAULT_RETRIEVAL, use_exact_title_tiebreak=False))

    assert overlap["hit@1"] < shipped["hit@1"]
    assert overlap["mrr"] < shipped["mrr"]
    # The right note is always somewhere in the top 3 even without the tiebreak,
    # so the failure is a RANKING failure, not a recall failure. That distinction
    # decides the fix: reranking helps here, a better corpus would not.
    assert overlap["hit@3"] == 1.0


def test_confidence_floor_has_headroom_over_correct_retrievals():
    """No correct retrieval may sit at or below the floor.

    If this fails, the floor is rejecting a note the system needs, which turns
    the guardrail into a bug. Delta Dust is the closest at 0.25 against a floor
    of 0.15, so the margin is real but not large.
    """
    songs, notes = _catalog(), _notes()
    for song in songs:
        _note, confidence, picked = retrieve_note(song, notes)
        assert picked is not None, song["title"]
        assert confidence > MIN_CONFIDENCE, f"{song['title']} at {confidence}"


def test_a_song_with_no_note_of_its_own_falls_back():
    """The guardrail the metadata filter restored.

    History, because the numbers make the case: before the filter, deleting a
    song's own note left all 46 catalog songs still retrieving a SIBLING's note
    at 0.60 to 0.80, far above the 0.15 floor, and being explained with another
    song's facts at high reported confidence. No threshold could fix that.
    Correct retrievals span margins of 0.00 to 0.50 and wrong ones 0.00 to 0.40,
    so 44 of 46 correct cases sat inside the wrong-case range.

    The fix filters on identity rather than on the score. This test is the
    regression pin: leave-one-out must now leak nothing.
    """
    songs, notes = _catalog(), _notes()
    result = leave_one_out(songs, notes)

    assert result["leaked"] == 0, f"{result['leaked']} songs grounded on a wrong note"


def test_missing_notes_reports_the_gap_at_load_time():
    """A song added without a note must be reportable BEFORE retrieval runs.

    This is the other half of the fix. The filter makes the failure safe; this
    makes it visible, because the realistic cause is a song added to songs.csv
    with no matching entry in song_notes.md.
    """
    songs, notes = _catalog(), _notes()

    # The shipped corpus is complete.
    assert missing_notes(songs, notes) == []

    # Remove one note and it must be named.
    trimmed = {k: v for k, v in notes.items() if k != songs[0]["title"]}
    assert missing_notes(songs, trimmed) == [songs[0]["title"]]


def test_a_song_missing_its_note_is_not_grounded():
    """End to end: no note of its own means no grounded explanation."""
    songs, notes = _catalog(), _notes()
    song = songs[0]
    trimmed = {k: v for k, v in notes.items() if k != song["title"]}

    note, _confidence, picked = retrieve_note(song, trimmed)
    assert note is None
    assert picked is None

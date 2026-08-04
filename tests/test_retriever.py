"""Tests for the retrieval layer (src/retriever.py).

These lock down the RAG feature's retrieval half:
  * the corpus parses into one note per catalog song, keyed by exact title,
  * a real song retrieves its OWN note with high confidence,
  * confidence is always a sane 0.0-1.0 value,
  * a song with nothing relevant in the corpus returns no note (the guardrail
    path), rather than forcing a bad match,
  * the MIN_CONFIDENCE floor is the thing that decides match vs no-match.

Run from the repo root:  python -m pytest
"""

import os

from src.recommender import load_songs
from src.retriever import (
    MIN_CONFIDENCE,
    load_notes,
    retrieve_note,
)

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


def test_corpus_has_a_note_for_every_song():
    """Every song in the catalog must have a note, keyed by its exact title."""
    songs = load_songs(REAL_CSV)
    notes = load_notes(REAL_NOTES)
    assert len(notes) == len(songs) == 46
    for song in songs:
        assert song["title"] in notes, f"missing note for {song['title']!r}"
        assert notes[song["title"]].strip(), "note body should not be empty"


def test_song_retrieves_its_own_note_with_high_confidence():
    """A real song's best match is its own note, well above the floor."""
    songs = load_songs(REAL_CSV)
    notes = load_notes(REAL_NOTES)
    # Summer Anthem shares title + genre + mood tokens with its own note, so it
    # should match itself with strong confidence.
    summer = next(s for s in songs if s["title"] == "Summer Anthem")
    note, confidence, matched_title = retrieve_note(summer, notes)
    assert matched_title == "Summer Anthem"
    assert note == notes["Summer Anthem"]
    assert confidence >= MIN_CONFIDENCE
    assert 0.0 <= confidence <= 1.0


def test_every_catalog_song_is_grounded():
    """All 46 real songs clear the confidence floor and get a grounded note."""
    songs = load_songs(REAL_CSV)
    notes = load_notes(REAL_NOTES)
    for song in songs:
        note, confidence, matched_title = retrieve_note(song, notes)
        assert note is not None, f"{song['title']} unexpectedly fell back"
        assert matched_title == song["title"]
        assert 0.0 <= confidence <= 1.0


def test_unknown_song_falls_back_to_no_note():
    """A song with no relevant note returns (None, score, None) -- the guardrail.

    We build a song whose title/genre/mood words appear in no note, so nothing
    clears MIN_CONFIDENCE and retrieval reports "no usable note found."
    """
    notes = load_notes(REAL_NOTES)
    alien = {"title": "Zzzqqx", "genre": "zzzqqx", "mood": "qqxzzz"}
    note, confidence, matched_title = retrieve_note(alien, notes)
    assert note is None
    assert matched_title is None
    assert confidence < MIN_CONFIDENCE


def test_empty_corpus_returns_no_match():
    """Retrieval against an empty corpus never crashes; it just finds nothing."""
    song = {"title": "Summer Anthem", "genre": "pop", "mood": "happy"}
    note, confidence, matched_title = retrieve_note(song, {})
    assert note is None
    assert matched_title is None
    assert confidence == 0.0

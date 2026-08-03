"""Pytest suite for VibeFinder's recommender.

These tests are a quality add: the assignment does not require them, but they act
as a reproducibility and regression guard and they document the scoring recipe as
executable specification. They lock down:
  * load_songs casting, normalization, and malformed-row skipping,
  * the default profile's #1 pick on the real catalog,
  * energy-term symmetry around the target,
  * the "reason components sum to the score" invariant,
  * genre (+2.0) outranking a mood-only (+1.0) match,
  * recommend_songs' size / ordering / crash-safety contract, and
  * determinism: exact score ties keep the catalog's original order.

Run from the repo root:  python -m pytest
"""

import os
import re

import pytest

from src.recommender import load_songs, score_song, recommend_songs


# ---------------------------------------------------------------------------
# Fixtures and shared data
# ---------------------------------------------------------------------------

# The default profile main.py uses. Kept here so the tests document it too.
DEFAULT_PROFILE = {
    "favorite_genre": "pop",
    "favorite_mood": "happy",
    "target_energy": 0.8,
}

# Absolute path to the real catalog, resolved relative to the repo root. This
# test file lives in tests/, so the repo root is one directory up. Resolving it
# this way means pytest works regardless of the directory it is invoked from.
REAL_CSV = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "songs.csv",
)


@pytest.fixture
def small_catalog() -> list[dict]:
    """A tiny hand-built catalog for fast, self-contained unit tests.

    Genres and moods are already lower-cased exactly as load_songs would leave
    them, so these dicts stand in for loaded rows.
    """
    return [
        # Perfect match to DEFAULT_PROFILE: pop + happy + energy == target 0.8.
        # Expected score = 2.0 + 1.0 + 1.0 = 4.00.
        {"title": "Perfect", "artist": "A", "genre": "pop", "mood": "happy",
         "energy": 0.80, "tempo_bpm": 120, "popularity": 0.9},
        # pop + happy but energy 0.85 (0.05 off target) -> esim = 0.95.
        # Expected score = 2.0 + 1.0 + 0.95 = 3.95.
        {"title": "CloseEnergy", "artist": "B", "genre": "pop", "mood": "happy",
         "energy": 0.85, "tempo_bpm": 122, "popularity": 0.8},
        # Genre-only match (pop, wrong mood). Same energy (0.20) as MoodOnly.
        {"title": "GenreOnly", "artist": "C", "genre": "pop", "mood": "sad",
         "energy": 0.20, "tempo_bpm": 80, "popularity": 0.5},
        # Mood-only match (happy, wrong genre). Same energy (0.20) as GenreOnly,
        # so the ONLY difference between them is genre vs mood -- lets us prove
        # a genre match (+2.0) outranks a mood match (+1.0).
        {"title": "MoodOnly", "artist": "D", "genre": "rock", "mood": "happy",
         "energy": 0.20, "tempo_bpm": 140, "popularity": 0.6},
        # No match at all.
        {"title": "NoMatch", "artist": "E", "genre": "jazz", "mood": "calm",
         "energy": 0.10, "tempo_bpm": 70, "popularity": 0.3},
    ]


# ---------------------------------------------------------------------------
# load_songs / real data
# ---------------------------------------------------------------------------

def test_real_csv_loads_twenty_rows():
    """The shipped catalog must load exactly 46 well-formed songs."""
    songs = load_songs(REAL_CSV)
    assert len(songs) == 46
    # Spot-check the casting and normalization contract on the first row.
    first = songs[0]
    assert isinstance(first["energy"], float)
    assert isinstance(first["tempo_bpm"], int)
    assert isinstance(first["popularity"], float)
    # genre/mood must be normalized to lower-case.
    assert first["genre"] == first["genre"].lower()
    assert first["mood"] == first["mood"].lower()


def test_load_songs_skips_malformed_rows(tmp_path):
    """Bad rows (non-numeric cells, a short row, a blank line) are dropped; the
    good rows survive. This proves one corrupt line cannot break the load."""
    csv_text = (
        "title,artist,genre,mood,energy,tempo_bpm,popularity\n"
        "Good One,A,Pop,Happy,0.8,120,0.9\n"            # valid
        "Bad Energy,B,Pop,Happy,notanumber,120,0.9\n"   # energy cast fails -> drop
        "Bad Tempo,C,Rock,Sad,0.5,fast,0.4\n"           # tempo cast fails -> drop
        # This row has 5 of the 7 columns, so ONLY the two NUMERIC trailing
        # columns (tempo_bpm, popularity) are missing. DictReader fills those
        # with None, and float(None)/int(None) raise TypeError -- the already
        # caught path. It does NOT exercise the AttributeError bug (all string
        # columns are present), which is exactly why this test used to pass
        # while that bug was live. The Truncated row below is the real guard.
        "Numbers Missing,D,Jazz,Calm,0.3\n"             # missing numeric cols -> drop (TypeError)
        # Regression guard for the AttributeError crash: this row stops after 2
        # columns, so genre/mood are missing. DictReader yields None for them,
        # and the None.strip() in load_songs raises AttributeError. Before the
        # fix this row crashed the whole load; now it must be skipped like any
        # other malformed row.
        "Truncated,B\n"                                 # missing string cols -> drop (AttributeError)
        "\n"                                             # fully blank line -> drop
        "Good Two,E,Jazz,Calm,0.3,90,0.5\n"             # valid
    )
    p = tmp_path / "songs.csv"
    p.write_text(csv_text, encoding="utf-8")

    songs = load_songs(str(p))
    titles = [s["title"] for s in songs]
    assert titles == ["Good One", "Good Two"]  # only the 2 valid rows remain


def test_load_songs_skips_row_missing_string_columns(tmp_path):
    """Regression guard: a row so short that a STRING column (genre/mood/artist)
    is missing must be skipped, not crash the load.

    csv.DictReader fills missing trailing fields with None rather than omitting
    the key, so a truncated row makes row["genre"] == None. load_songs calls
    None.strip(), which raises AttributeError -- a different exception than the
    ValueError/TypeError a bad numeric cell raises. This test pins that the
    except clause catches AttributeError too, so the good rows still load."""
    csv_text = (
        "title,artist,genre,mood,energy,tempo_bpm,popularity\n"
        "Good,A,Pop,Happy,0.8,120,0.9\n"    # valid, must survive
        "Truncated,B\n"                     # missing genre/mood -> AttributeError -> drop
    )
    p = tmp_path / "songs.csv"
    p.write_text(csv_text, encoding="utf-8")

    songs = load_songs(str(p))
    titles = [s["title"] for s in songs]
    assert titles == ["Good"]  # the truncated row was skipped, not fatal


def test_load_songs_missing_popularity_column_raises(tmp_path):
    """A HEADER missing a required column is a broken FILE, not a broken row, so
    it must raise ValueError -- not silently return [] and let main.py print
    "Loaded songs: 0". Here the `popularity` column is dropped from the header;
    without the fix every row raised KeyError, every row was swallowed by the
    per-row guard, and the load looked like an empty (but valid) dataset. We also
    assert the error names the exact missing column so the message is actionable."""
    csv_text = (
        # Note: no `popularity` column in this header.
        "title,artist,genre,mood,energy,tempo_bpm\n"
        "Song,Artist,Pop,Happy,0.8,120\n"
    )
    p = tmp_path / "songs.csv"
    p.write_text(csv_text, encoding="utf-8")

    with pytest.raises(ValueError) as excinfo:
        load_songs(str(p))
    # The message must name the specific column that is absent.
    assert "popularity" in str(excinfo.value)


def test_load_songs_missing_several_columns_names_all(tmp_path):
    """When MULTIPLE required columns are absent, the error must list every one of
    them, not just the first, so a user can fix the file in one pass."""
    csv_text = (
        # Missing three columns: mood, tempo_bpm, popularity.
        "title,artist,genre,energy\n"
        "Song,Artist,Pop,0.8\n"
    )
    p = tmp_path / "songs.csv"
    p.write_text(csv_text, encoding="utf-8")

    with pytest.raises(ValueError) as excinfo:
        load_songs(str(p))
    msg = str(excinfo.value)
    # All three missing columns must be named.
    assert "mood" in msg
    assert "tempo_bpm" in msg
    assert "popularity" in msg


def test_load_songs_empty_file_raises_clear_error(tmp_path):
    """A zero-byte file has no header at all, so csv.DictReader.fieldnames is None.
    We must convert that into the SAME clear ValueError rather than crashing with a
    confusing TypeError from set(None). This pins the documented None-handling."""
    p = tmp_path / "songs.csv"
    p.write_text("", encoding="utf-8")  # completely empty: zero bytes

    with pytest.raises(ValueError):
        load_songs(str(p))


def test_load_songs_header_only_returns_empty(tmp_path):
    """A file with a CORRECT header but no data rows is a legitimate empty catalog,
    not an error: it must still return [] without raising. This pins the existing
    promise so the new header-validation cannot regress it into a false failure."""
    csv_text = "title,artist,genre,mood,energy,tempo_bpm,popularity\n"  # header only
    p = tmp_path / "songs.csv"
    p.write_text(csv_text, encoding="utf-8")

    assert load_songs(str(p)) == []


def test_load_songs_normalizes_case_and_whitespace(tmp_path):
    """genre/mood are trimmed + lower-cased so matching is case-insensitive."""
    csv_text = (
        "title,artist,genre,mood,energy,tempo_bpm,popularity\n"
        "Song,Artist,  PoP ,  HAPPY ,0.5,100,0.5\n"
    )
    p = tmp_path / "songs.csv"
    p.write_text(csv_text, encoding="utf-8")

    song = load_songs(str(p))[0]
    assert song["genre"] == "pop"
    assert song["mood"] == "happy"


# ---------------------------------------------------------------------------
# score_song
# ---------------------------------------------------------------------------

def test_perfect_match_scores_four(small_catalog):
    """pop + happy + energy exactly on target -> 4.00 (the max)."""
    perfect = small_catalog[0]
    score, reasons = score_song(DEFAULT_PROFILE, perfect)
    assert score == pytest.approx(4.0)
    # All three reason lines should be present for a full match.
    assert any("genre match" in r for r in reasons)
    assert any("mood match" in r for r in reasons)
    assert any("energy close to target" in r for r in reasons)


def test_score_is_case_insensitive():
    """Upper-case user prefs still match a normalized (lower-case) song."""
    song = {"genre": "pop", "mood": "happy", "energy": 0.8}
    prefs = {"favorite_genre": "POP", "favorite_mood": "Happy", "target_energy": 0.8}
    score, _ = score_song(prefs, song)
    assert score == pytest.approx(4.0)


def test_energy_term_is_symmetric():
    """A song 0.1 ABOVE target scores the same energy term as one 0.1 BELOW."""
    prefs = {"favorite_genre": "none", "favorite_mood": "none", "target_energy": 0.5}
    above = {"genre": "x", "mood": "y", "energy": 0.6}  # +0.1
    below = {"genre": "x", "mood": "y", "energy": 0.4}  # -0.1
    score_above, _ = score_song(prefs, above)
    score_below, _ = score_song(prefs, below)
    # Neither matches genre/mood, so the whole score IS the energy term.
    assert score_above == pytest.approx(score_below)
    assert score_above == pytest.approx(0.9)  # 1.0 - 0.1


@pytest.mark.parametrize("song", [
    {"genre": "pop", "mood": "happy", "energy": 0.8},    # full match, exact energy
    {"genre": "pop", "mood": "happy", "energy": 0.83},   # off-round energy (esim 0.97)
    {"genre": "pop", "mood": "sad", "energy": 0.3},      # genre only
    {"genre": "rock", "mood": "happy", "energy": 0.6},   # mood only
    {"genre": "jazz", "mood": "calm", "energy": 0.1},    # no match
    {"genre": "pop", "mood": "happy", "energy": 0.0},    # extreme energy gap
])
@pytest.mark.parametrize("prefs", [
    {"favorite_genre": "pop", "favorite_mood": "happy", "target_energy": 0.8},
    {"favorite_genre": "rock", "favorite_mood": "calm", "target_energy": 0.2},
])
def test_reason_components_sum_to_score(song, prefs):
    """The core explainability invariant: the numeric value in each reason
    string must sum to the returned score. We parse the "+X" out of every reason
    and add them up. Because the energy term is rounded once and reused, this
    holds structurally (we still use approx to be safe against float display)."""
    score, reasons = score_song(prefs, song)
    total = 0.0
    for r in reasons:
        # Each reason ends in "(+<number>)"; pull the number back out.
        m = re.search(r"\+([0-9]+\.?[0-9]*)\)", r)
        assert m is not None, f"reason has no parseable value: {r!r}"
        total += float(m.group(1))
    assert total == pytest.approx(score)


def test_genre_beats_mood(small_catalog):
    """A genre-only match (+2.0) must outscore a mood-only match (+1.0)."""
    genre_only = small_catalog[2]  # pop + wrong mood
    mood_only = small_catalog[3]   # wrong genre + happy, SAME energy as above
    genre_score, _ = score_song(DEFAULT_PROFILE, genre_only)
    mood_score, _ = score_song(DEFAULT_PROFILE, mood_only)
    # Energy terms are identical (both energy 0.20), so the gap is purely 2.0 vs 1.0.
    assert genre_score > mood_score
    assert genre_score - mood_score == pytest.approx(1.0)


def test_score_does_not_crash_on_missing_fields():
    """Missing song energy or absent user fields degrade gracefully to +0."""
    # Song missing 'energy' -> energy term is 0.0, but genre/mood still score.
    score, reasons = score_song(
        {"favorite_genre": "pop", "favorite_mood": "happy", "target_energy": 0.8},
        {"genre": "pop", "mood": "happy"},  # no 'energy' key
    )
    assert score == pytest.approx(3.0)  # 2.0 + 1.0 + 0.0
    assert any("energy close to target (+0.00)" in r for r in reasons)

    # Empty profile against a full song -> no genre/mood match and no target
    # energy, so the score is 0.0.
    score2, _ = score_song({}, {"genre": "pop", "mood": "happy", "energy": 0.8})
    assert score2 == pytest.approx(0.0)


def test_unknown_genre_is_just_a_non_match():
    """An unknown/unseen genre does not raise; it simply fails to match."""
    score, _ = score_song(
        {"favorite_genre": "polka", "favorite_mood": "happy", "target_energy": 0.5},
        {"genre": "pop", "mood": "happy", "energy": 0.5},
    )
    # No genre match (+0), mood matches (+1.0), energy exact (+1.0) -> 2.0.
    assert score == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# recommend_songs
# ---------------------------------------------------------------------------

def test_default_top_pick_is_pop_happy(small_catalog):
    """Top recommendation for the default profile is a pop/happy song at 4.00."""
    results = recommend_songs(DEFAULT_PROFILE, small_catalog, k=5)
    top_song, top_score, _ = results[0]
    assert top_song["genre"] == "pop"
    assert top_song["mood"] == "happy"
    assert top_score == pytest.approx(4.0)
    assert top_song["title"] == "Perfect"


def test_default_ranking_on_real_data():
    """On the real catalog with the default profile, Summer Anthem (energy 0.80)
    ranks first at 4.00, then Sunshine Pop (energy 0.85) at 3.95 -- the energy
    term breaks the genre+mood tie."""
    songs = load_songs(REAL_CSV)
    results = recommend_songs(DEFAULT_PROFILE, songs, k=5)

    first_song, first_score, _ = results[0]
    second_song, second_score, _ = results[1]

    assert first_song["title"] == "Summer Anthem"
    assert first_score == pytest.approx(4.0)
    assert second_song["title"] == "Sunshine Pop"
    assert second_score == pytest.approx(3.95)


def test_recommend_respects_k(small_catalog):
    """recommend_songs returns at most k results."""
    assert len(recommend_songs(DEFAULT_PROFILE, small_catalog, k=2)) == 2
    assert len(recommend_songs(DEFAULT_PROFILE, small_catalog, k=3)) == 3


def test_recommend_k_larger_than_catalog(small_catalog):
    """k bigger than the catalog just returns everything (no error)."""
    results = recommend_songs(DEFAULT_PROFILE, small_catalog, k=999)
    assert len(results) == len(small_catalog)


def test_recommend_scores_are_non_increasing(small_catalog):
    """Results must be sorted best-first (scores never rise as you descend)."""
    results = recommend_songs(DEFAULT_PROFILE, small_catalog, k=5)
    scores = [score for (_song, score, _reasons) in results]
    assert scores == sorted(scores, reverse=True)


def test_recommend_empty_catalog_returns_empty():
    """An empty catalog yields [] rather than crashing."""
    assert recommend_songs(DEFAULT_PROFILE, [], k=5) == []


def test_recommend_handles_empty_genre_profile(small_catalog):
    """A profile with empty genre/mood does not crash; ranks purely by energy."""
    prefs = {"favorite_genre": "", "favorite_mood": "", "target_energy": 0.8}
    results = recommend_songs(prefs, small_catalog, k=5)
    assert len(results) == len(small_catalog)
    # With no genre/mood matches, ranking is purely by energy closeness to 0.8;
    # the song at energy 0.80 (Perfect) should still be first.
    assert results[0][0]["title"] == "Perfect"


def test_recommend_is_deterministic_and_stable():
    """Identical inputs give identical output order, and EXACT score ties keep
    the catalog's original order (Python's stable sort + non-mutating sorted())."""
    # TieA and TieB are engineered to the same score (both perfect matches at
    # energy 0.8), placed in a known catalog order.
    catalog = [
        {"title": "TieA", "genre": "pop", "mood": "happy", "energy": 0.8},
        {"title": "TieB", "genre": "pop", "mood": "happy", "energy": 0.8},
        {"title": "Lower", "genre": "rock", "mood": "sad", "energy": 0.1},
    ]
    prefs = {"favorite_genre": "pop", "favorite_mood": "happy", "target_energy": 0.8}

    results1 = recommend_songs(prefs, catalog, k=5)
    results2 = recommend_songs(prefs, catalog, k=5)

    order1 = [s["title"] for (s, _sc, _r) in results1]
    order2 = [s["title"] for (s, _sc, _r) in results2]

    assert order1 == order2                # deterministic across calls
    assert order1[:2] == ["TieA", "TieB"]  # a true tie keeps catalog order

    # sorted() must NOT mutate the caller's catalog.
    assert [s["title"] for s in catalog] == ["TieA", "TieB", "Lower"]

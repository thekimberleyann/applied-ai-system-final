"""Tests for the diversity re-ranking side-car (src/diversity.py).

These lock down the documented behavior of the post-ranking genre cap:
  * the exact default-profile BEFORE/AFTER at cap 1,
  * the size insight: cap 2 was dead code on the 20-song catalog but FIRES on the
    46-song catalog (catalog size, not the algorithm, gated its usefulness),
  * the sacred pass-through of scores and reasons (same objects, same values),
  * that neither the input list nor the song dicts are ever mutated,
  * the empty-result edge cases (empty ranked, k<=0, max_per_genre<=0),
  * that an unreachable k returns fewer than k rather than relaxing the cap,
  * that a song dict with no 'genre' key does not crash,
  * and stability (kept songs keep their relative order from `ranked`).

Run from the repo root:  python -m pytest
"""

import os

from src.recommender import load_songs, recommend_songs
from src.diversity import diversify, diversity_report, PROFILE as DEFAULT_PROFILE

REAL_CSV = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "songs.csv",
)


# A tiny hand-built ranked list used by the pure-logic tests below. The shape
# matches recommend_songs output exactly: (song, score, reasons) tuples already
# in descending-score order. Genres are chosen so we can exercise the cap.
def _fake_ranked() -> list:
    return [
        ({"title": "A", "genre": "pop"}, 4.00, ["genre match (+2.0)"]),
        ({"title": "B", "genre": "pop"}, 3.95, ["mood match (+1.0)"]),
        ({"title": "C", "genre": "rock"}, 2.00, ["energy close to target (+0.50)"]),
        ({"title": "D", "genre": "jazz"}, 1.00, ["energy close to target (+0.10)"]),
        ({"title": "E", "genre": "rock"}, 0.90, []),
    ]


# ---------------------------------------------------------------------------
# The documented default-profile behavior (real catalog)
# ---------------------------------------------------------------------------

def test_default_profile_before_after_cap_one():
    """The exact verified BEFORE/AFTER for pop/happy/0.80 at max_per_genre=1.

    On the 46-song catalog the baseline top-5 holds THREE pop songs (Summer Anthem
    4.00, Sunshine Pop 3.95, Confetti Skies 3.92) plus two disco songs. The cap-1
    diversified list keeps only the top pop song and backfills across genres."""
    songs = load_songs(REAL_CSV)
    baseline, diversified = diversity_report(DEFAULT_PROFILE, songs, k=5, max_per_genre=1)

    assert [s["title"] for (s, _sc, _r) in baseline] == [
        "Summer Anthem",
        "Sunshine Pop",
        "Confetti Skies",
        "Velvet Hustle",
        "Mirrorball Fever",
    ]
    assert [s["title"] for (s, _sc, _r) in diversified] == [
        "Summer Anthem",
        "Velvet Hustle",
        "Midnight Drive",
        "Crown Season",
        "Static Rebellion",
    ]


def test_cap_two_now_fires_on_expanded_catalog():
    """The SIZE INSIGHT: max_per_genre=2 was dead code on the original 20-song
    catalog (no top-5 ever held 3 of one genre) but FIRES on the 46-song catalog.

    For pop/happy/0.80 the baseline top-5 now holds three pop songs, so a cap of 2
    changes the result: it drops the third pop song (Confetti Skies) and backfills.
    This proves the diversity cap's usefulness was gated by catalog SIZE, not by the
    algorithm -- exactly the point the model card now makes."""
    songs = load_songs(REAL_CSV)
    baseline = [s["title"] for (s, _sc, _r) in recommend_songs(DEFAULT_PROFILE, songs, k=5)]
    _b, diversified = diversity_report(DEFAULT_PROFILE, songs, k=5, max_per_genre=2)
    div_titles = [s["title"] for (s, _sc, _r) in diversified]

    # Cap 2 is no longer a no-op: the diversified top-5 differs from the baseline.
    assert div_titles != baseline
    # Specifically, the third pop song is dropped and the list is backfilled.
    assert baseline.count("Confetti Skies") == 1  # present in the raw baseline
    assert div_titles == [
        "Summer Anthem",
        "Sunshine Pop",
        "Velvet Hustle",
        "Mirrorball Fever",
        "Midnight Drive",
    ]
    assert "Confetti Skies" not in div_titles  # the 3rd pop was capped out


# ---------------------------------------------------------------------------
# The sacred pass-through and no-mutation guarantees
# ---------------------------------------------------------------------------

def test_scores_and_reasons_pass_through_unchanged():
    """diversify returns the SAME tuple objects it was given -- identical scores,
    identical (same-identity) reasons lists. Selection must never touch scoring."""
    ranked = _fake_ranked()
    out = diversify(ranked, k=5, max_per_genre=1)

    # Every returned tuple must be one of the exact input tuples (identity), so
    # the score and reasons cannot have been rebuilt or altered.
    for item in out:
        assert any(item is original for original in ranked)
    # Spot-check the values and the reasons-list identity for the kept 'A'.
    a_original = ranked[0]
    assert out[0] is a_original
    assert out[0][1] == 4.00
    assert out[0][2] is a_original[2]


def test_input_list_and_song_dicts_are_not_mutated():
    """diversify must not reorder/shorten the input list nor edit any song dict."""
    ranked = _fake_ranked()
    # Snapshot the list contents (by identity) and the song dicts (by value).
    list_snapshot = list(ranked)
    dict_snapshots = [dict(item[0]) for item in ranked]

    diversify(ranked, k=3, max_per_genre=1)

    assert ranked == list_snapshot  # same tuples, same order, same length
    for item, snap in zip(ranked, dict_snapshots):
        assert item[0] == snap  # no injected keys, no changed values


# ---------------------------------------------------------------------------
# Edge cases: every empty-result path
# ---------------------------------------------------------------------------

def test_empty_ranked_returns_empty():
    assert diversify([], k=5, max_per_genre=1) == []


def test_k_zero_or_negative_returns_empty():
    ranked = _fake_ranked()
    assert diversify(ranked, k=0, max_per_genre=1) == []
    assert diversify(ranked, k=-3, max_per_genre=1) == []


def test_max_per_genre_zero_or_negative_returns_empty():
    """A cap of zero forbids keeping any song, so the only honest result is []."""
    ranked = _fake_ranked()
    assert diversify(ranked, k=5, max_per_genre=0) == []
    assert diversify(ranked, k=5, max_per_genre=-1) == []


# ---------------------------------------------------------------------------
# Cap vs k, missing genre, stability
# ---------------------------------------------------------------------------

def test_unreachable_k_returns_fewer_not_relaxed_cap():
    """If the genre cap makes k unreachable we return fewer than k, never relax
    the cap. Three genres at cap 1 can yield at most 3 songs even when k=10."""
    ranked = _fake_ranked()  # genres: pop, pop, rock, jazz, rock -> 3 distinct
    out = diversify(ranked, k=10, max_per_genre=1)
    assert [item[0]["title"] for item in out] == ["A", "C", "D"]
    assert len(out) == 3  # fewer than the requested k=10


def test_missing_genre_key_does_not_crash():
    """A song dict with no 'genre' key is treated as its own bucket, not a crash."""
    ranked = [
        ({"title": "NoGenre1"}, 3.0, []),  # no 'genre' key at all
        ({"title": "NoGenre2"}, 2.0, []),  # a second missing-genre song
        ({"title": "Pop1", "genre": "pop"}, 1.0, []),
    ]
    # cap 1: both missing-genre songs share the ONE sentinel bucket, so only the
    # first is kept, then the pop song. This also proves the sentinel is a single
    # shared bucket rather than a per-song free pass.
    out = diversify(ranked, k=5, max_per_genre=1)
    assert [item[0]["title"] for item in out] == ["NoGenre1", "Pop1"]


def test_kept_songs_preserve_relative_order():
    """Stability: kept songs come out in the same relative order as in `ranked`."""
    ranked = _fake_ranked()
    out = diversify(ranked, k=5, max_per_genre=1)
    # Expected keeps at cap 1: A(pop), C(rock), D(jazz). B(pop) and E(rock) are
    # skipped by the cap; the survivors stay in their original ranked order.
    assert [item[0]["title"] for item in out] == ["A", "C", "D"]

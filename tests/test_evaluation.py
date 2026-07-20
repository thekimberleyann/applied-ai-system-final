"""Phase 4 evaluation tests: adversarial-profile behavior, the energy tie-break
flip, and the popularity-bias experiment.

These lock down the findings written up in the model card so a future change that
silently alters them would fail CI. They also assert the most important safety
property of the experiment: it never contaminates the pure recipe.

Run from the repo root:  python -m pytest
"""

import os

import pytest

from src.recommender import load_songs, score_song, recommend_songs
from src.experiment_popularity import (
    PROFILE as FOLK_PROFILE,
    rank_with_popularity,
    score_with_popularity,
)

REAL_CSV = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "songs.csv",
)


@pytest.fixture
def songs() -> list[dict]:
    return load_songs(REAL_CSV)


# ---------------------------------------------------------------------------
# Adversarial profiles
# ---------------------------------------------------------------------------

def test_energy_ceiling_flips_pop_winner(songs):
    """The pop/happy winner flips on target energy alone: at 0.80 Summer Anthem
    (energy 0.80) wins; at 1.0 Sunshine Pop (energy 0.85, closer to the
    unreachable ceiling) wins."""
    low = {"favorite_genre": "pop", "favorite_mood": "happy", "target_energy": 0.80}
    ceiling = {"favorite_genre": "pop", "favorite_mood": "happy", "target_energy": 1.0}

    assert recommend_songs(low, songs, k=1)[0][0]["title"] == "Summer Anthem"
    assert recommend_songs(ceiling, songs, k=1)[0][0]["title"] == "Sunshine Pop"


def test_ghost_genre_kills_the_genre_term(songs):
    """An unknown genre (kpop) means no song can earn the +2.0 genre term, so the
    best possible score is mood (+1.0) plus energy (<=1.0) = at most 2.0."""
    ghost = {"favorite_genre": "kpop", "favorite_mood": "happy", "target_energy": 0.80}
    results = recommend_songs(ghost, songs, k=5)
    top_song, top_score, _ = results[0]
    assert top_score <= 2.0
    assert top_song["title"] == "Summer Anthem"  # mood happy + energy 1.00 = 2.00


def test_conflicted_profile_still_ranks_categorical_match_first(songs):
    """"Conflicted" (blues/sad but high target energy) does NOT flip the ranking:
    the unique genre+mood match (Rainy Day Blues) wins by a wide margin despite a
    0.55 energy miss. This is the categorical-dominance finding -- energy is a weak
    tiebreaker whenever a unique genre+mood match exists."""
    conflicted = {"favorite_genre": "blues", "favorite_mood": "sad", "target_energy": 0.95}
    results = recommend_songs(conflicted, songs, k=5)
    top_song, top_score, _ = results[0]
    assert top_song["title"] == "Rainy Day Blues"
    assert top_score == pytest.approx(3.45)  # 2.0 + 1.0 + round(1 - 0.55, 2)
    # The runner-up scores on energy alone, far below the categorical match.
    assert results[1][1] < 1.5


# ---------------------------------------------------------------------------
# Popularity-bias experiment
# ---------------------------------------------------------------------------

def test_popularity_never_dethrones_the_categorical_number_one(songs):
    """Even at the aggressive weight 2.0, the perfect genre+mood match stays #1
    (the ~2-point categorical moat). This is what keeps the demo honest."""
    for weight in (1.0, 2.0):
        top = rank_with_popularity(FOLK_PROFILE, songs, weight, k=1)
        assert top[0][0]["title"] == "Wandering Roads"


def test_popularity_buries_niche_and_lifts_hits_at_weight_two(songs):
    """At weight 2.0, two pop hits that share neither genre nor mood with a folk
    fan invade the top-5, and two genuine near-matches drop out."""
    pure_names = [s["title"] for (s, _sc, _r) in recommend_songs(FOLK_PROFILE, songs, k=5)]
    pop_names = [s["title"] for (s, _t, _p) in rank_with_popularity(FOLK_PROFILE, songs, 2.0, k=5)]

    lifted = [n for n in pop_names if n not in pure_names]
    buried = [n for n in pure_names if n not in pop_names]

    assert set(lifted) == {"Summer Anthem", "Sunshine Pop"}
    assert set(buried) == {"Rainy Day Blues", "Acoustic Morning"}


def test_experiment_does_not_touch_the_pure_recipe(songs):
    """The pure score must be independent of popularity, and the experiment must
    not mutate the shared catalog dicts."""
    # 1. Changing a song's popularity does not change its pure taste score.
    song = dict(songs[0])  # a copy we can mutate freely
    pure_before, _ = score_song(FOLK_PROFILE, song)
    song["popularity"] = 1.0
    pure_after, _ = score_song(FOLK_PROFILE, song)
    assert pure_before == pytest.approx(pure_after)

    # 2. score_with_popularity returns the SAME pure component the recipe gives.
    total, pure = score_with_popularity(FOLK_PROFILE, songs[0], 2.0)
    recipe_pure, _ = score_song(FOLK_PROFILE, songs[0])
    assert pure == pytest.approx(recipe_pure)

    # 3. Running the experiment leaves the catalog dicts untouched (no injected
    #    score keys, order and contents unchanged), so a later pure run is clean.
    before_keys = [set(s.keys()) for s in songs]
    rank_with_popularity(FOLK_PROFILE, songs, 2.0, k=5)
    after_keys = [set(s.keys()) for s in songs]
    assert before_keys == after_keys
    assert "total" not in songs[0] and "pop_score" not in songs[0]

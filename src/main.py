"""VibeFinder CLI entry point and Phase 4 evaluation driver.

Run with:  python -m src.main

Loads the song catalog, then prints ranked recommendations (title, score, and the
reasons each song was chosen) for the default taste profile followed by a battery
of Phase 4 evaluation profiles:

  * Diverse / stress profiles -- one clean in-catalog match per corner of taste
    space, to confirm the recipe behaves across very different listeners.
  * Adversarial profiles -- deliberately awkward inputs that probe the recipe's
    edges (conflicting signals, an unknown genre, an unreachable energy target).

This file only READS from recommender.py. It never changes the scoring recipe.
The popularity-bias experiment lives in its own module, src/experiment_popularity.py.
"""

from __future__ import annotations

import os

from src.recommender import load_songs, recommend_songs

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "songs.csv")

# The default profile the app has always run: a mainstream, upbeat listener.
# NOTE the key names: score_song reads favorite_genre / favorite_mood /
# target_energy, so every profile dict below MUST use exactly these keys or the
# genre/mood terms will never match and the energy term will be skipped.
DEFAULT_PROFILE = {
    "favorite_genre": "pop",
    "favorite_mood": "happy",
    "target_energy": 0.8,
}

# Diverse / stress battery: each is a clean, in-catalog match at a different point
# in taste space (label, profile).
DIVERSE_PROFILES = [
    ("High-Energy Pop (pop / happy / energy 0.95)",
     {"favorite_genre": "pop", "favorite_mood": "happy", "target_energy": 0.95}),
    ("Chill Lofi (lofi / chill / energy 0.30)",
     {"favorite_genre": "lofi", "favorite_mood": "chill", "target_energy": 0.30}),
    ("Deep Intense Rock (rock / intense / energy 0.95)",
     {"favorite_genre": "rock", "favorite_mood": "intense", "target_energy": 0.95}),
    ("Romantic R&B (r&b / romantic / energy 0.50)",
     {"favorite_genre": "r&b", "favorite_mood": "romantic", "target_energy": 0.50}),
]

# Adversarial battery: each profile is designed to probe one edge of the recipe.
ADVERSARIAL_PROFILES = [
    # Conflicted: genre (blues) and mood (sad) both point at the low-energy song
    # Rainy Day Blues (energy 0.40), but the target energy is high (0.95). This is
    # a tug of war between the categorical terms and the energy term. Teaching
    # point: the unique genre+mood match still wins easily -- a 3.0 categorical
    # floor swamps even a large energy miss -- so energy is a weak tiebreaker
    # whenever a unique genre+mood match exists.
    ("Conflicted (blues / sad but target energy 0.95)",
     {"favorite_genre": "blues", "favorite_mood": "sad", "target_energy": 0.95}),

    # Ghost Genre: 'kpop' is not in the catalog, so the genre term is a dead +0.0
    # for every song. The ranking is decided by mood and energy alone -- a demo of
    # graceful degradation (the system does not crash, it just quietly loses a
    # whole scoring term).
    ("Ghost Genre (kpop not in catalog)",
     {"favorite_genre": "kpop", "favorite_mood": "happy", "target_energy": 0.80}),

    # Energy Ceiling: no song reaches energy 1.0 (the catalog max is Iron Fury at
    # 0.98), so the energy term can never hit its full +1.0. Compared against the
    # default (pop/happy/0.80) this flips the pop/happy winner: at target 0.80
    # Summer Anthem (0.80) wins, but at target 1.0 Sunshine Pop (0.85, closer to
    # the unreachable ceiling) wins.
    ("Energy Ceiling (pop / happy / target energy 1.0)",
     {"favorite_genre": "pop", "favorite_mood": "happy", "target_energy": 1.0}),
]


def print_recommendations(header: str, prefs: dict, songs: list[dict], k: int = 5) -> None:
    """Print one labeled block: a header then the top-k songs with per-term reasons.

    DRY helper reused by the default run and every evaluation profile so the output
    format stays identical and is easy to paste into the model card. recommend_songs
    does the scoring and the stable descending sort; we never reorder here.
    """
    print(header)
    for rank, (song, score, reasons) in enumerate(
        recommend_songs(prefs, songs, k=k), start=1
    ):
        print(f"{rank}. {song['title']}  (score {score:.2f})")
        for reason in reasons:
            # The reasons already carry their per-term point values, and those
            # values sum to the score, so this is the full per-term breakdown.
            print(f"     - {reason}")
    print()  # blank line between blocks


def main() -> None:
    songs = load_songs(DATA_PATH)
    print(f"Loaded songs: {len(songs)}")
    print()

    # 1. The default run (unchanged output, still documented in the README).
    print_recommendations(
        "=== Recommendations for the default profile (pop / happy) ===",
        DEFAULT_PROFILE,
        songs,
    )

    # 2. Diverse / stress battery.
    print("### DIVERSE / STRESS PROFILES ###")
    print()
    for label, prefs in DIVERSE_PROFILES:
        print_recommendations(f"=== {label} ===", prefs, songs)

    # 3. Adversarial battery.
    print("### ADVERSARIAL PROFILES ###")
    print()
    for label, prefs in ADVERSARIAL_PROFILES:
        print_recommendations(f"=== {label} ===", prefs, songs)


if __name__ == "__main__":
    main()

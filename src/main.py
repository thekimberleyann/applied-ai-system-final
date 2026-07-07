"""VibeFinder CLI entry point.

Run with:  python -m src.main

Loads the song catalog, then prints ranked recommendations (title, score, and the
reasons each song was chosen) for a default taste profile. Diverse test profiles
are added in Phase 4.
"""

from __future__ import annotations

import os

from src.recommender import load_songs, recommend_songs

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "songs.csv")

DEFAULT_PROFILE = {
    "favorite_genre": "pop",
    "favorite_mood": "happy",
    "target_energy": 0.8,
}


def main() -> None:
    songs = load_songs(DATA_PATH)
    print(f"Loaded songs: {len(songs)}")

    print("\n=== Recommendations for the default profile (pop / happy) ===")
    for rank, (song, score, reasons) in enumerate(
        recommend_songs(DEFAULT_PROFILE, songs, k=5), start=1
    ):
        print(f"{rank}. {song['title']}  (score {score:.2f})")
        for reason in reasons:
            print(f"     - {reason}")


if __name__ == "__main__":
    main()

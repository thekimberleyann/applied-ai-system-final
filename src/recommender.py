"""VibeFinder recommender — core logic (starter stubs).

CLI-first design: all recommendation logic lives here and is verified via
src/main.py before any UI is added. Functions are stubbed now and implemented
in Phase 3.

Data model:
  * A "song" is a dict with keys: title, artist, genre, mood, energy (0.0-1.0),
    tempo_bpm. load_songs() converts numeric columns to float/int for math.
  * "user_prefs" is a dict of target values, e.g.
    {"favorite_genre": "pop", "favorite_mood": "happy", "target_energy": 0.8}.
"""

from __future__ import annotations


def load_songs(path: str) -> list[dict]:
    """Load the song catalog from a CSV into a list of dicts (numbers as float/int)."""
    raise NotImplementedError("Phase 3: read CSV with the csv module; cast energy/tempo")


def score_song(user_prefs: dict, song: dict) -> tuple[float, list[str]]:
    """Return (score, reasons) for one song given the user's taste profile."""
    raise NotImplementedError("Phase 3: genre/mood match points + energy similarity + reasons")


def recommend_songs(user_prefs: dict, songs: list[dict], k: int = 5) -> list:
    """Score every song and return the top-k, highest score first."""
    raise NotImplementedError("Phase 3: score all songs, sort desc, return top k")

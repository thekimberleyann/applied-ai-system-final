"""VibeFinder recommender -- core logic.

VibeFinder is a small content-based music recommender. There is no machine
learning here: we score each song against a user's stated taste profile using a
transparent, hand-written "recipe" so that every recommendation can be explained
in plain language. That explainability is the whole point of the assignment.

CLI-first design: all recommendation logic lives here and is exercised through
src/main.py before any UI is added.

Scoring recipe (maximum possible score = 4.0):
  * genre match:  +2.0 when the song's genre equals the user's favorite genre
  * mood match:   +1.0 when the song's mood equals the user's favorite mood
  * energy term:  +esim, where esim = max(0.0, 1.0 - abs(song_energy - target))
                  rounded to 2 decimals. esim is largest (1.0) when the song's
                  energy is exactly on the target and shrinks as they diverge.

All genre/mood comparisons are case-insensitive and whitespace-trimmed, so
"Pop", " pop " and "pop" are treated as the same genre.

Data model:
  * A "song" is a dict with keys: title, artist, genre, mood, energy (0.0-1.0),
    tempo_bpm, popularity (0.0-1.0). load_songs() casts the numeric columns.
    popularity is loaded for data/display only; the recipe does NOT score on it.
  * "user_prefs" is a dict of target values, e.g.
    {"favorite_genre": "pop", "favorite_mood": "happy", "target_energy": 0.8}.
"""

from __future__ import annotations

import csv


def _to_float(value) -> float | None:
    """Best-effort float conversion.

    Returns the float value, or None when the value is missing (None) or is not
    numeric. Used so score_song can degrade gracefully on a hand-built song dict
    that is missing an energy value, instead of raising.
    """
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def load_songs(path: str) -> list[dict]:
    """Load the song catalog from a CSV into a list of dicts (numbers cast).

    Expected CSV header:
        title,artist,genre,mood,energy,tempo_bpm,popularity

    We keep title and artist as written (they are for display, only trimmed of
    stray surrounding whitespace), but we normalize genre and mood to trimmed
    lower-case so later matching is case-insensitive. score_song() normalizes the
    user's preferences the same way so both sides always compare like-for-like.

    Numeric casting: energy -> float, tempo_bpm -> int, popularity -> float.

    Robustness: a single row with a bad numeric cell (for example energy="abc",
    a blank line, or a short row missing columns) is SKIPPED, not fatal. We catch
    ValueError / TypeError / KeyError per row so one corrupt line cannot break
    loading the other good songs. An empty file (header only) returns [].
    """
    songs: list[dict] = []

    # newline="" is the documented way to open a file for the csv module so it
    # can handle any newlines embedded inside quoted fields itself.
    with open(path, newline="", encoding="utf-8") as f:
        # DictReader maps each row to a dict keyed by the header names, which is
        # exactly the shape main.py wants (song['title'], song['genre'], ...).
        reader = csv.DictReader(f)

        for row in reader:
            try:
                # Build the cast/normalized song dict. If any cast fails or any
                # expected key is missing/None, the try block raises and we drop
                # this one row (see the except below) while keeping the rest.
                song = {
                    # Display fields: kept verbatim, only trimmed.
                    "title": row["title"].strip(),
                    "artist": row["artist"].strip(),
                    # Match fields: trimmed + lower-cased for case-insensitive
                    # comparison against the (also normalized) user profile.
                    "genre": row["genre"].strip().lower(),
                    "mood": row["mood"].strip().lower(),
                    # Numeric fields: cast to real types. A bad cell such as ""
                    # or "abc" raises ValueError; a None (short row) raises
                    # TypeError; both are caught below and drop the row.
                    "energy": float(row["energy"]),
                    "tempo_bpm": int(row["tempo_bpm"]),
                    "popularity": float(row["popularity"]),
                }
            except (ValueError, TypeError, KeyError, AttributeError):
                # Malformed row: skip it and keep loading the rest of the file.
                # We deliberately do NOT re-raise so one bad line is survivable.
                #
                # Why AttributeError is in this tuple: csv.DictReader fills any
                # MISSING TRAILING fields of a short row with None (it does not
                # leave the key out). So a truncated row that stops before the
                # genre/mood/artist columns gives row["genre"] == None, and the
                # None.strip() call above raises AttributeError -- not the
                # ValueError/TypeError a bad numeric cell would raise. Without
                # AttributeError here, one such short row would crash the whole
                # load instead of being skipped like the docstring promises.
                continue

            songs.append(song)

    return songs


def score_song(user_prefs: dict, song: dict) -> tuple[float, list[str]]:
    """Return (score, reasons) for one song given the user's taste profile.

    The reasons list is a human-readable explanation of how the score was built.
    IMPORTANT GUARANTEE (checked by a test): the numeric value inside each reason
    string sums to exactly the returned score, because:
        * the genre reason contributes exactly 2.0,
        * the mood reason contributes exactly 1.0,
        * the energy reason contributes exactly esim (already rounded to 2dp),
    and score = 2.0*genre_hit + 1.0*mood_hit + esim.

    Graceful, documented, non-crashing behavior on missing data:
        * A missing/blank favorite_genre or favorite_mood simply cannot match
          (+0), and an unknown genre is just a non-match, never an error.
        * If either the song energy or the target_energy is missing/non-numeric,
          the energy term is 0.0. We still append the energy reason (at +0.00)
          so the reasons list keeps a stable shape and always sums to the score.
    """
    reasons: list[str] = []
    score = 0.0

    # --- Genre dimension (+2.0) -------------------------------------------
    # Normalize BOTH sides the same way load_songs normalized the catalog, so
    # the comparison is case-insensitive even when score_song is called directly
    # on a hand-built dict (as the tests do). We require the user's genre to be
    # non-empty so a blank profile field cannot spuriously match a blank song
    # field ("" == "").
    user_genre = str(user_prefs.get("favorite_genre", "")).strip().lower()
    song_genre = str(song.get("genre", "")).strip().lower()
    if user_genre and user_genre == song_genre:
        score += 2.0
        reasons.append("genre match (+2.0)")

    # --- Mood dimension (+1.0) --------------------------------------------
    user_mood = str(user_prefs.get("favorite_mood", "")).strip().lower()
    song_mood = str(song.get("mood", "")).strip().lower()
    if user_mood and user_mood == song_mood:
        score += 1.0
        reasons.append("mood match (+1.0)")

    # --- Energy dimension (+esim) -----------------------------------------
    # esim is a closeness score in 0.0 .. 1.0: it is 1.0 when the song's energy
    # exactly equals the target and falls off linearly as they diverge, floored
    # at 0.0 by max(). abs() makes the penalty symmetric -- a song 0.1 ABOVE the
    # target and one 0.1 BELOW score the same energy term. This term is what
    # breaks ties between songs that match on both genre and mood.
    target_energy = _to_float(user_prefs.get("target_energy"))
    song_energy = _to_float(song.get("energy"))
    if target_energy is None or song_energy is None:
        # One value is missing -> no meaningful similarity. Contribute 0.0
        # rather than crashing (documented behavior).
        esim = 0.0
    else:
        # Round to 2 decimals ONCE and reuse this exact value both as the score
        # contribution and in the reason string below. This is why the reasons
        # always sum to the score with no rounding drift.
        esim = round(max(0.0, 1.0 - abs(song_energy - target_energy)), 2)
    score += esim
    # The energy reason is ALWAYS appended (even at +0.00) so the reasons list
    # has a stable shape and its components always reconcile to the score.
    reasons.append(f"energy close to target (+{esim:.2f})")

    return (score, reasons)


def recommend_songs(user_prefs: dict, songs: list[dict], k: int = 5) -> list:
    """Score every song and return the top-k as (song, score, reasons) tuples.

    Edge cases handled:
        * empty catalog         -> returns []
        * k larger than catalog -> returns all songs (slicing past the end is
                                   safe in Python)
        * k <= 0                -> returns [] (an empty slice)
    """
    # Score every song and pair it with its explanation.
    scored = []
    for song in songs:
        score, reasons = score_song(user_prefs, song)
        scored.append((song, score, reasons))

    # Sort by score DESCENDING. We deliberately use sorted() (not list.sort())
    # for two reasons:
    #   1. sorted() is NON-MUTATING: it returns a new list and never reorders the
    #      caller's original `songs` catalog as a side effect.
    #   2. Python's sort is STABLE, so songs with the exact same score keep their
    #      original catalog order. With reverse=True this is fully deterministic:
    #      identical inputs always produce identical output order.
    # t[1] is the score element of each (song, score, reasons) 3-tuple. We sort
    # on score only (no secondary key) precisely so ties fall back to catalog
    # order rather than to some hidden tie-breaker.
    ranked = sorted(scored, key=lambda t: t[1], reverse=True)

    # Slicing is safe even when k > len(ranked) or k <= 0.
    return ranked[:k]

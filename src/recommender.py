"""VibeFinder recommender -- core logic.

VibeFinder is a small content-based music recommender. There is no machine
learning here: we score each song against a user's stated taste profile using a
transparent, hand-written "recipe" so that every recommendation can be explained
in plain language. That explainability is the whole point of the assignment.

CLI-first design: all recommendation logic lives here and is exercised through
src/main.py before any UI is added.

Scoring recipe (maximum possible score = 4.0 at the default weights):
  * genre match:  +2.0 when the song's genre equals the user's favorite genre
  * mood match:   +1.0 when the song's mood equals the user's favorite mood
  * energy term:  +esim, where esim = max(0.0, 1.0 - abs(song_energy - target))
                  scaled by the energy weight and rounded to 2 decimals. esim is
                  largest (1.0) when the song's energy is exactly on the target
                  and shrinks as they diverge.

Those three numbers are the DEFAULTS, not constants. They live in
ScoringConfig in src/config.py and every function here accepts an optional
config that falls back to those defaults, so a caller who passes nothing gets
precisely the behavior documented above. Changing a weight also changes the
maximum score (the 4.0 ceiling is just 2.0 + 1.0 + 1.0, not a normalization);
src/config.py explains why we report that rather than rescale it away.

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

from src.config import ScoringConfig, scoring_or_default

# The seven columns every catalog CSV MUST declare in its header row. We keep
# this as a module-level constant (rather than inlining it) so the header check
# in load_songs and any future writer stay in lock-step on the exact schema.
# Order here is only for a stable, readable error message; the check itself is
# order-independent because it compares SETS of names, not positions.
REQUIRED_COLUMNS = (
    "title",
    "artist",
    "genre",
    "mood",
    "energy",
    "tempo_bpm",
    "popularity",
)


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

    Header validation (HARD error, checked ONCE before any row is read):
    a missing HEADER column is a broken FILE, not a broken row, so it must fail
    loudly instead of silently. Before the fix, if the header lost (say) the
    `popularity` column, EVERY row raised KeyError, EVERY row was swallowed by the
    per-row guard below, and load_songs returned [] -- so `python -m src.main`
    printed "Loaded songs: 0" as if the program worked but the data was empty.
    That is exactly the failure this validation converts into a clear error.
    We read reader.fieldnames once and, if any of the seven REQUIRED_COLUMNS are
    absent, raise ValueError naming precisely which columns are missing.

    Two boundary cases are handled explicitly and documented:
      * A COMPLETELY EMPTY file (zero bytes) makes reader.fieldnames None. Calling
        set() on None would raise a confusing TypeError, so we treat None as "no
        columns at all" and raise the SAME clear ValueError (every required
        column is reported missing) instead of a cryptic crash.
      * A HEADER-ONLY file (correct header, no data rows) passes validation and
        returns [] -- an empty catalog is a legitimate, non-error state.

    Robustness (per ROW, unchanged): a single row with a bad numeric cell (for
    example energy="abc", a blank line, or a short row missing columns) is
    SKIPPED, not fatal. We catch ValueError / TypeError / KeyError / AttributeError
    per row so one corrupt line cannot break loading the other good songs. Note
    the distinction: a missing whole COLUMN is fatal (above), but a bad or missing
    CELL in one row is survivable (below).
    """
    songs: list[dict] = []

    # newline="" is the documented way to open a file for the csv module so it
    # can handle any newlines embedded inside quoted fields itself.
    with open(path, newline="", encoding="utf-8") as f:
        # DictReader maps each row to a dict keyed by the header names, which is
        # exactly the shape main.py wants (song['title'], song['genre'], ...).
        reader = csv.DictReader(f)

        # --- Validate the HEADER once, up front (before the row loop) ---------
        # reader.fieldnames is the parsed header row, or None for a zero-byte
        # file (there is no header to parse). We guard the None case explicitly
        # so set(None) never raises a confusing TypeError -- an empty file simply
        # has none of the required columns.
        header = reader.fieldnames  # list[str] | None
        present = set(header) if header is not None else set()
        # Report the missing columns in the canonical REQUIRED_COLUMNS order (not
        # set order) so the error message is stable and easy to read.
        missing = [col for col in REQUIRED_COLUMNS if col not in present]
        if missing:
            # A missing column means the file's schema is broken. Fail loudly and
            # name exactly which columns are absent, rather than silently loading
            # zero songs and letting the caller misread it as "empty dataset."
            raise ValueError(
                "songs CSV is missing required column(s): "
                + ", ".join(missing)
            )

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


def score_song(user_prefs: dict, song: dict,
               config: ScoringConfig | None = None) -> tuple[float, list[str]]:
    """Return (score, reasons) for one song given the user's taste profile.

    The reasons list is a human-readable explanation of how the score was built.
    IMPORTANT GUARANTEE (checked by a test): the numeric value inside each reason
    string sums to exactly the returned score, because:
        * the genre reason contributes exactly config.genre_weight,
        * the mood reason contributes exactly config.mood_weight,
        * the energy reason contributes exactly the energy term (rounded to 2dp),
    and score = genre_weight*genre_hit + mood_weight*mood_hit + energy_term.

    HOW THAT GUARANTEE SURVIVES ARBITRARY WEIGHTS
        It would be easy to break this while making the weights configurable, so
        the two mechanics that preserve it are worth naming:

        1. The genre and mood reasons interpolate the weight itself rather than a
           hard-coded "2.0"/"1.0" literal, and they use plain f-string formatting
           of a float, which in Python emits repr() and therefore round-trips the
           exact value. The string cannot say a different number from the one
           added to the score.
        2. The energy term is rounded ONCE, AFTER the weight is applied, and that
           single rounded float is both added to the score and formatted into the
           reason. Rounding the closeness first and multiplying afterwards would
           reintroduce drift (0.33 closeness at weight 0.7 adds 0.231 but would
           print +0.23), which is precisely the bug the round-once-reuse
           discipline exists to prevent.

    `config` is optional and defaults to DEFAULT_SCORING, so every existing call
    site (`score_song(prefs, song)`) behaves exactly as it always has. With the
    default weights of 2.0 / 1.0 / 1.0 the maximum score is 4.0; see
    ScoringConfig for why a changed weight moves that scale and why we do not
    renormalize it.

    Graceful, documented, non-crashing behavior on missing data:
        * A missing/blank favorite_genre or favorite_mood simply cannot match
          (+0), and an unknown genre is just a non-match, never an error.
        * If either the song energy or the target_energy is missing/non-numeric,
          the energy term is 0.0. We still append the energy reason (at +0.00)
          so the reasons list keeps a stable shape and always sums to the score.
    """
    cfg = scoring_or_default(config)
    reasons: list[str] = []
    score = 0.0

    # --- Genre dimension (+genre_weight, default 2.0) ----------------------
    # Normalize BOTH sides the same way load_songs normalized the catalog, so
    # the comparison is case-insensitive even when score_song is called directly
    # on a hand-built dict (as the tests do). We require the user's genre to be
    # non-empty so a blank profile field cannot spuriously match a blank song
    # field ("" == "").
    #
    # float() before formatting so an integer weight (a caller passing 2 rather
    # than 2.0) still prints "2.0" and not "2". The default path is unaffected:
    # float(2.0) is 2.0, and f"{2.0}" is "genre match (+2.0)", character for
    # character what this line produced before it took a weight.
    genre_weight = float(cfg.genre_weight)
    user_genre = str(user_prefs.get("favorite_genre", "")).strip().lower()
    song_genre = str(song.get("genre", "")).strip().lower()
    if user_genre and user_genre == song_genre:
        score += genre_weight
        reasons.append(f"genre match (+{genre_weight})")

    # --- Mood dimension (+mood_weight, default 1.0) ------------------------
    mood_weight = float(cfg.mood_weight)
    user_mood = str(user_prefs.get("favorite_mood", "")).strip().lower()
    song_mood = str(song.get("mood", "")).strip().lower()
    if user_mood and user_mood == song_mood:
        score += mood_weight
        reasons.append(f"mood match (+{mood_weight})")

    # --- Energy dimension (+energy_weight * closeness) ---------------------
    # Closeness is a score in 0.0 .. 1.0: it is 1.0 when the song's energy
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
        # Apply the weight BEFORE rounding, then round to 2 decimals ONCE and
        # reuse that exact value both as the score contribution and in the
        # reason string below. Order matters here: rounding the closeness first
        # and scaling afterwards would produce a contribution with more than two
        # decimals for any weight other than 1.0, and the reason string (printed
        # at 2dp) would then no longer sum to the score.
        #
        # At the default weight of 1.0 this is arithmetically identical to the
        # original `round(max(0.0, 1.0 - abs(diff)), 2)`, because multiplying by
        # 1.0 is exact in IEEE-754 floating point. Default output is unchanged.
        closeness = max(0.0, 1.0 - abs(song_energy - target_energy))
        esim = round(closeness * float(cfg.energy_weight), 2)
    score += esim
    # The energy reason is ALWAYS appended (even at +0.00) so the reasons list
    # has a stable shape and its components always reconcile to the score.
    reasons.append(f"energy close to target (+{esim:.2f})")

    return (score, reasons)


def recommend_songs(user_prefs: dict, songs: list[dict], k: int = 5,
                    config: ScoringConfig | None = None) -> list:
    """Score every song and return the top-k as (song, score, reasons) tuples.

    `config` is threaded straight through to score_song and defaults to
    DEFAULT_SCORING. It is added AFTER k so every existing positional call
    (`recommend_songs(prefs, songs, 5)`) keeps working unchanged.

    Edge cases handled:
        * empty catalog         -> returns []
        * k larger than catalog -> returns all songs (slicing past the end is
                                   safe in Python)
        * k <= 0                -> returns [] (an empty slice)
    """
    scored = []
    for song in songs:
        score, reasons = score_song(user_prefs, song, config)
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

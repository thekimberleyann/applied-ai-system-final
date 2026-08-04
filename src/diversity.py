"""VibeFinder -- diversity re-ranking side-car (post-ranking selection).

The shipped recipe in recommender.py is PURE: it scores taste only (genre, mood,
energy) on a fixed 0.0-4.0 scale, and every reason string sums exactly to the
score. That "reasons sum to the score" guarantee is sacred, and nothing is
allowed to push a score above 4.0 or below 0.0. So diversity is deliberately
NOT a scoring term here -- not a bonus, not a penalty. Touching the score at all
would break the guarantee and the fixed scale.

Instead this module sits BESIDE the recipe, exactly like
src/experiment_popularity.py does: it consumes the already-ranked output of
recommend_songs and performs a POST-RANKING SELECTION. It walks the ranked list
top-to-bottom and picks which k items to actually show, enforcing a cap on how
many songs of any one genre may appear. Scores and reasons pass through
completely untouched -- the very same (song, score, reasons) tuples come out.
Because the shipped recommender is never modified, this reverts cleanly by
construction: delete this file and the recommender is exactly as it was.

Run with:  python -m src.diversity

THE MOST IMPORTANT FINDING (be honest about it):
A cap of max_per_genre=2 was DEAD CODE on the original 20-song catalog and is
LIVE on the shipped 46-song one. Both halves are kept here, because the change
between them is the real lesson: the knob's usefulness was gated by CATALOG
SIZE, not by the algorithm.
  * 20-song catalog: at most 2 songs of any single genre (pop x2, hip-hop x2,
    everything else x1). Sweeping all 2178 (genre, mood, energy) profiles, no
    top-5 anywhere held 3 songs of one genre, so a cap of 2 could never fire.
  * 46-song catalog: eight genres carry 3 songs (pop, rock, jazz, blues,
    hip-hop, metal, dreampop, disco). Sweeping all 2299 profiles, 968 of them
    produce a top-5 holding 3 of one genre, so a cap of 2 fires routinely.
Every number in this paragraph is produced by src/sweep.py (run
`python -m src.sweep`), which is committed precisely so these claims can be
re-derived rather than trusted. An earlier version of this docstring quoted a
sweep whose script was never committed, and its figures silently went stale
when the catalog grew. That is the mistake this file no longer makes.

A cap of 1 remains the default, but the original reason for that default (cap 2
does nothing) no longer holds, so it now rests on the trade-off below instead.

THE TRADE-OFF (do not oversell this):
Diversity is not free. On the default profile (pop / happy / 0.80) enforcing
one-per-genre demotes Sunshine Pop (3.95) and Confetti Skies (3.92), both
genuine pop/happy matches, and promotes Velvet Hustle (disco, 2.00), Midnight
Drive (synthwave, 0.95) and Crown Season (hip-hop, 0.95), none of which match
the user's genre. The cost at slot 2 alone is 1.95 points (3.95 replaced by
2.00). It does mitigate the documented "genre dominance" bias (near-identical
pop hits crowding the top), but it trades the user's stated taste
for breadth they never asked for. For that reason diversity is kept OUT of the
shipped recommend_songs, just as popularity was: the shipped recipe answers
"what fits my vibe," and this side-car answers a different question, "show me a
spread of genres." Different question, different module.
"""

from __future__ import annotations

import os

from src.recommender import load_songs, recommend_songs

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "songs.csv")

# The default demo profile -- the same mainstream, upbeat listener src/main.py
# has always run (pop / happy / 0.80). We reuse it so the BEFORE/AFTER printed
# here lines up with the numbers documented in the model card and the tests.
PROFILE_LABEL = "Default listener (pop / happy / energy 0.80)"
PROFILE = {
    "favorite_genre": "pop",
    "favorite_mood": "happy",
    "target_energy": 0.8,
}


def diversify(ranked: list, k: int = 5, max_per_genre: int = 1) -> list:
    """Select up to k items from an already-ranked list, capping per-genre count.

    `ranked` is the output of recommend_songs: a list of (song, score, reasons)
    3-tuples ALREADY sorted by score descending. Callers should pass the FULL
    ranked catalog -- call recommend_songs with k=len(songs) -- not a
    pre-truncated top-5. If you hand this a top-5, there is nothing below the cut
    to backfill from, so a demoted song just leaves a hole instead of being
    replaced by the next eligible genre.

    Algorithm (a single stable top-down pass):
      * Walk `ranked` in order (that order is already the recipe's descending,
        catalog-order-stable ranking, so we never re-sort and never introduce a
        hidden tiebreaker).
      * Keep a song when its genre has been kept FEWER than max_per_genre times
        so far; otherwise skip it and move on.
      * Stop as soon as k songs are kept.

    What passes through UNCHANGED: we return the exact same (song, score,
    reasons) tuple objects we were given. We never rebuild them, never touch a
    score, never edit a reasons list, and never write into a song dict. The
    "reasons sum to the score" guarantee is therefore untouched because we never
    go near the score at all -- this is pure selection, layered on top.

    Determinism: because we only ever keep-or-skip while walking a stable input,
    the kept songs come out in the same RELATIVE order they had in `ranked`. Ties
    thus still fall back to catalog order, exactly as recommend_songs promises.

    Edge cases (all handled, all deliberate):
      * empty `ranked`      -> [] (nothing to select from).
      * k <= 0              -> [] (an empty selection was requested).
      * max_per_genre <= 0  -> [] and we document WHY: a cap of zero (or less)
                              means NO song of ANY genre may ever be kept, so the
                              only correct result is the empty list. We do NOT
                              silently treat it as 1; that would invent output the
                              caller did not ask for.
      * cap makes k unreachable -> we return FEWER than k rather than relaxing the
                              cap. The cap is the whole point; honoring k by
                              breaking the cap would defeat it. Example: a catalog
                              of one genre with max_per_genre=1 returns exactly 1
                              song no matter how large k is.
      * a song dict missing a 'genre' key must not crash -> we read the genre with
                              .get(...) and a sentinel default, so a missing genre
                              is simply treated as its own bucket (it can still be
                              kept, and it is capped independently of real genres).

    We never mutate the input `ranked` list or any song dict; the returned list
    is a fresh list holding references to the original, unmodified tuples.
    """
    # Guard the empty-result cases up front. Each of these means "there is no
    # valid non-empty selection," so we return a brand-new empty list (never the
    # caller's list) and stop. max_per_genre <= 0 is included here on purpose: a
    # cap of zero forbids keeping anything, so [] is the only honest answer.
    if not ranked or k <= 0 or max_per_genre <= 0:
        return []

    # kept accumulates the tuples we decide to show, in the order we meet them
    # (which is the ranked order), so the result is stable by construction.
    kept: list = []
    # genre_counts tracks how many songs of each genre we have kept so far, so we
    # can enforce the per-genre cap. Keys are the normalized genre strings we read
    # off each song (or the missing-genre sentinel below).
    genre_counts: dict = {}

    # A distinctive sentinel for songs that have no 'genre' key at all. Using an
    # object() rather than a string like "" or "unknown" guarantees this bucket
    # can never accidentally collide with a real genre value in the data.
    MISSING_GENRE = object()

    for item in ranked:
        # Each item is a (song, score, reasons) tuple. We only need the song to
        # read its genre; score and reasons ride along untouched.
        song = item[0]

        # Read the genre defensively. A hand-built song dict might omit 'genre'
        # entirely; .get with the sentinel default means that case is handled as
        # its own bucket instead of raising KeyError. Real catalog genres are
        # already trimmed/lower-cased by load_songs, so equal genres share a key.
        genre = song.get("genre", MISSING_GENRE)

        # Keep this song only if its genre still has room under the cap. Default
        # the running count to 0 for a genre we have not seen yet.
        if genre_counts.get(genre, 0) < max_per_genre:
            kept.append(item)
            # Record that this genre now occupies one more slot.
            genre_counts[genre] = genre_counts.get(genre, 0) + 1
            # Stop the moment we have filled k slots. This is what makes an
            # unreachable-k case return fewer than k: if we run off the end of
            # `ranked` before hitting k, we simply return what we have.
            if len(kept) >= k:
                break

    return kept


def diversity_report(prefs: dict, songs: list[dict], k: int = 5, max_per_genre: int = 1) -> tuple:
    """Return (baseline_top_k, diversified_top_k) so a caller can print before/after.

    baseline_top_k is the pure recipe's top-k straight from recommend_songs. The
    diversified list is built by ranking the FULL catalog (k=len(songs)) and then
    running diversify over that complete ranking -- passing the full ranking is
    what gives diversify something to backfill from when it demotes a song. Both
    lists are ordinary lists of (song, score, reasons) tuples; nothing is mutated.
    """
    # BEFORE: the pure recipe's own top-k, exactly what the app ships today.
    baseline_top_k = recommend_songs(prefs, songs, k=k)

    # AFTER: rank the WHOLE catalog first (so there is material below the top-k to
    # promote), then apply the genre cap as a post-ranking selection step.
    full_ranked = recommend_songs(prefs, songs, k=len(songs))
    diversified_top_k = diversify(full_ranked, k=k, max_per_genre=max_per_genre)

    return baseline_top_k, diversified_top_k


def _print_before_after(baseline: list, diversified: list) -> None:
    """Print the pure top-k (BEFORE) beside the genre-capped top-k (AFTER)."""
    baseline_names = [song["title"] for (song, _s, _r) in baseline]
    diversified_names = [song["title"] for (song, _s, _r) in diversified]

    # The two lists can differ in length (the cap may yield fewer than k), so we
    # iterate over the longer of the two and blank out any missing row.
    rows = max(len(baseline), len(diversified))
    print(f"{'#':<3}{'BEFORE (pure recipe)':<40}{'AFTER (one per genre)':<40}")
    for i in range(rows):
        # Format one side's cell, or leave it blank if that side has no row here.
        if i < len(baseline):
            b_song, b_score, _b = baseline[i]
            before = f"{b_song['title']} [{b_song['genre']}] {b_score:.2f}"
        else:
            before = ""
        if i < len(diversified):
            a_song, a_score, _a = diversified[i]
            after = f"{a_song['title']} [{a_song['genre']}] {a_score:.2f}"
        else:
            after = ""
        print(f"{i + 1:<3}{before:<40}{after:<40}")

    # Who moved: demoted = fell out of the shown list; promoted = climbed in.
    demoted = [n for n in baseline_names if n not in diversified_names]
    promoted = [n for n in diversified_names if n not in baseline_names]
    print(f"  DEMOTED (dropped from the shown list): {', '.join(demoted) if demoted else '(none)'}")
    print(f"  PROMOTED (climbed into the shown list): {', '.join(promoted) if promoted else '(none)'}")
    print()


def main() -> None:
    songs = load_songs(DATA_PATH)

    print("=" * 72)
    print("DIVERSITY RE-RANKING (post-ranking selection side-car)")
    print(f"Profile: {PROFILE_LABEL}")
    print("The pure recipe in recommender.py is NOT modified; this is a side-car.")
    print("=" * 72)
    print()

    # --- The headline demo: cap of 1 actually changes the output ---------------
    baseline, diversified = diversity_report(PROFILE, songs, k=5, max_per_genre=1)
    print("--- max_per_genre = 1  (at most one song per genre) ---")
    _print_before_after(baseline, diversified)

    # --- The dead-cap demo: cap of 2 is a no-op on this catalog ----------------
    # We print it precisely to make the finding visible: the AFTER column is
    # identical to the pure recipe because no genre ever appears 3+ times.
    _base2, diversified2 = diversity_report(PROFILE, songs, k=5, max_per_genre=2)
    base2_names = [s["title"] for (s, _s, _r) in baseline]
    div2_names = [s["title"] for (s, _s, _r) in diversified2]
    print("--- max_per_genre = 2  (dead on the 20-song catalog, LIVE on this one) ---")
    print(f"  BASELINE top-5:     {', '.join(base2_names)}")
    print(f"  max_per_genre=2:    {', '.join(div2_names)}")
    print(f"  identical to baseline? {base2_names == div2_names}")
    print()

    print("CONCLUSION")
    print("-" * 72)
    print(
        "Diversity here is a POST-RANKING selection step, not a score. The pure\n"
        "recipe still produces the scores and reasons; this side-car only decides\n"
        "which of the already-ranked songs to show, capping how many share a genre.\n"
        "The 0.0-4.0 scale and the reasons-sum-to-the-score guarantee are untouched.\n"
        "\n"
        "The honest finding, and how it CHANGED: a cap of 2 was dead code on the\n"
        "original 20-song catalog (at most 2 songs per genre, and across all 2178\n"
        "swept profiles no top-5 ever held 3 of a genre). On this 46-song catalog\n"
        "eight genres carry 3 songs, 968 of 2299 swept profiles produce a top-5\n"
        "holding 3 of one genre, and the cap fires -- see the differing lists above.\n"
        "The knob was gated by catalog size, not by the algorithm. Re-derive these\n"
        "numbers yourself with: python -m src.sweep\n"
        "\n"
        "And a cap of 1 is not free. On this profile it demotes Sunshine Pop, a\n"
        "real 3.95 pop/happy match, and promotes Velvet Hustle at 2.00, a disco\n"
        "song matching the listener's mood but NOT their genre. That is a 1.95-point\n"
        "quality cost at slot 2 for one slot of genre breadth. It does curb the genre-dominance\n"
        "bias (two near-identical pop hits at the top), but it spends the listener's\n"
        "stated taste on variety they did not ask for. That trade is why diversity\n"
        "stays OUT of the shipped recipe, exactly as popularity did: the shipped\n"
        "recommender answers 'what fits my vibe,' and this answers 'give me a spread.'"
    )


if __name__ == "__main__":
    main()

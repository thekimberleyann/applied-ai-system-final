"""VibeFinder -- Phase 4 popularity-bias experiment (Kim's locked decision).

The shipped recipe in recommender.py is PURE: it scores taste only (genre, mood,
energy) and never looks at how popular a song is. This module asks a "what if"
question WITHOUT touching that recipe: what happens to the rankings if we bolt a
popularity term on top?

It is a strictly additive, side-car experiment. It imports the pure scorer, adds
POP_WEIGHT * popularity on top of each pure score, and compares the top-5 BEFORE
(pure) and AFTER (popularity-boosted) at two weights. Because recommender.py is
never modified, the experiment reverts cleanly by construction: delete this file
and nothing about the shipped recommender changes.

Run with:  python -m src.experiment_popularity

The honest headline (verified arithmetic, see the conclusion): the true #1 here,
a folk/nostalgic exact match, holds a 2.15-point lead over the next song, and
popularity (range 0.0-1.0) cannot climb that gap until the weight passes 3.52.
More broadly, we swept every profile in this catalog that has an exact genre+mood
match and found that no non-matching song overtakes such a #1 below weight 2.73 --
above the aggressive 2.0 the experiment uses -- so the #1 is safe at every weight
shown. That moat is a property of THIS catalog's numbers, not a theorem of the
recipe: a genre-only rival with a perfect energy fit can reach 3.0 and tie a
genre+mood match. The real bias lands below #1: even a mild, defensible weight
lets popular NON-matches invade the top 5 and push genuine niche matches down.
"""

from __future__ import annotations

import os

from src.recommender import load_songs, score_song, recommend_songs

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "songs.csv")

# The demonstration weights. We show TWO on purpose:
#   1.0 = mild / realistic: popularity reorders genuine near-matches.
#   2.0 = aggressive: popular non-matches crash into the top 5.
# Showing the effect scale is more honest (and more informative) than a single
# tuned value. POP_WEIGHT is a demonstration knob only; it is NOT part of the
# shipped recommender.
POP_WEIGHTS = [1.0, 2.0]

# The experiment profile: a folk / nostalgic listener at a calm energy. This is
# the most vivid case in the catalog because the deserved #1, Wandering Roads
# (folk / nostalgic / 0.40), is also the LOWEST-popularity song in the catalog
# (0.18) -- the ultimate "hidden gem." Behind it sit genuine mood matches and,
# further back, high-popularity pop hits that share nothing with a folk fan.
PROFILE_LABEL = "Folk fan (folk / nostalgic / energy 0.40)"
PROFILE = {
    "favorite_genre": "folk",
    "favorite_mood": "nostalgic",
    "target_energy": 0.40,
}


def score_with_popularity(prefs: dict, song: dict, pop_weight: float) -> tuple[float, float]:
    """Return (total, pure) for one song under the experimental scorer.

    The pure taste score comes straight from the sealed recipe (score_song); we
    then add pop_weight * popularity on top. We do NOT write anything back into the
    song dict, so the shared catalog is never mutated and a later pure run in the
    same process is not contaminated.
    """
    pure, _reasons = score_song(prefs, song)
    total = round(pure + pop_weight * float(song["popularity"]), 2)
    return total, pure


def rank_with_popularity(prefs: dict, songs: list[dict], pop_weight: float, k: int = 5) -> list:
    """Score every song with the popularity add-on and return the top-k.

    Each element is (song, total, pure). We stable-sort by total descending, the
    same convention the shipped recommend_songs uses, so equal totals keep catalog
    order. We build a fresh list of tuples and never mutate the input catalog.
    """
    scored = [(song,) + score_with_popularity(prefs, song, pop_weight) for song in songs]
    scored.sort(key=lambda row: row[1], reverse=True)
    return scored[:k]


def _print_before_after(songs: list[dict], pop_weight: float) -> None:
    """Print the pure top-5 (BEFORE) beside the popularity-boosted top-5 (AFTER)."""
    # BEFORE: the pure recipe, via the shipped recommender (never scores popularity).
    pure_top = recommend_songs(PROFILE, songs, k=5)
    # AFTER: the same songs, scored with the popularity add-on at this weight.
    pop_top = rank_with_popularity(PROFILE, songs, pop_weight, k=5)

    pure_names = [song["title"] for (song, _s, _r) in pure_top]
    pop_names = [song["title"] for (song, _t, _p) in pop_top]

    print(f"--- POP_WEIGHT = {pop_weight}  (total = taste + {pop_weight} * popularity) ---")
    print(f"{'#':<3}{'BEFORE (pure taste)':<40}{'AFTER (+ popularity)':<40}")
    for i in range(5):
        b_song, b_score, _b_reasons = pure_top[i]
        a_song, a_total, a_pure = pop_top[i]
        before = f"{b_song['title']} ({b_score:.2f}, pop {b_song['popularity']})"
        after = f"{a_song['title']} ({a_total:.2f} = {a_pure:.2f} taste + pop {a_song['popularity']})"
        print(f"{i + 1:<3}{before:<40}{after:<40}")

    # Who moved: buried = fell out of the top-5; lifted = climbed into it.
    buried = [n for n in pure_names if n not in pop_names]
    lifted = [n for n in pop_names if n not in pure_names]
    print(f"  BURIED (dropped out of top-5): {', '.join(buried) if buried else '(none)'}")
    print(f"  LIFTED (climbed into top-5):   {', '.join(lifted) if lifted else '(none)'}")
    print()


def main() -> None:
    songs = load_songs(DATA_PATH)

    print("=" * 72)
    print("POPULARITY-BIAS EXPERIMENT")
    print(f"Profile: {PROFILE_LABEL}")
    print("The pure recipe in recommender.py is NOT modified; this is a side-car.")
    print("=" * 72)
    print()

    for weight in POP_WEIGHTS:
        _print_before_after(songs, weight)

    print("CONCLUSION")
    print("-" * 72)
    print(
        "Under the pure recipe the folk fan's #1 is Wandering Roads, a perfect\n"
        "genre+mood match AND the lowest-popularity song in the catalog (0.18) --\n"
        "the recommender surfaces a genuine hidden gem. Adding popularity does NOT\n"
        "dethrone it: here Wandering Roads (4.00) leads the next song by 2.15 points,\n"
        "and popularity (range 0.0-1.0) cannot climb that gap until the weight passes\n"
        "3.52. This is not just a lucky profile: sweeping every genre+mood match in\n"
        "the catalog, no non-matching song overtakes such a #1 below weight 2.73,\n"
        "above the aggressive 2.0 shown here. The moat is real for THIS catalog, but\n"
        "it is not guaranteed by the recipe -- a genre-only rival with a perfect\n"
        "energy fit reaches 3.0 and would merely tie a genre+mood match. The bias\n"
        "instead corrupts the ranks below #1, and it does so early. At weight 1.0 --\n"
        "the mild, defensible weight -- Summer Anthem, a pop/happy chart hit that\n"
        "shares NEITHER genre NOR mood with a folk fan, already crashes into the top\n"
        "5 (alongside Velvet Touch), burying genuine near-matches Rainy Day Blues and\n"
        "Acoustic Morning. The mood-match reorder (Golden Hour, pop 0.82, edging past\n"
        "Backroad Sunset, pop 0.58) is only the mildest symptom. At weight 2.0 the\n"
        "invaders are Summer Anthem and Sunshine Pop. The lesson: even a modest\n"
        "popularity thumb on the scale quietly trades the listener's real taste for\n"
        "whatever is already popular. That is why the shipped recipe stays pure."
    )


if __name__ == "__main__":
    main()

"""Brute-force profile sweeps that back the claims made in the two side-car
experiments (src/diversity.py and src/experiment_popularity.py).

WHY THIS FILE EXISTS
    Both side-cars used to assert broad, catalog-wide findings ("across all 231
    profiles...", "no non-matching song overtakes below weight 2.73") that were
    produced by a throwaway script nobody committed. When the catalog grew from
    20 songs to 46 those numbers went stale, and because the script was gone
    they could not be re-derived or even checked. That is the failure this file
    fixes: every catalog-wide number quoted in this project is now produced by
    code a reader can run.

    Run it with:  python -m src.sweep

WHAT A "PROFILE" IS HERE
    The sweep grid is the full cross product of:
        * every distinct genre present in the catalog,
        * every distinct mood present in the catalog,
        * eleven target-energy values, 0.0 to 1.0 in steps of 0.1.
    This is deliberately a SUPERSET of plausible listeners: it includes
    combinations no song actually has (a classical/energetic fan, say). That is
    the point. A claim of the form "this never happens" is only worth making if
    it was tested against the hostile corners of the space, not just the
    comfortable middle.

    The grid size therefore depends on the catalog, and it is printed with the
    results rather than hard-coded into any prose, so it cannot go stale again.
"""

from __future__ import annotations

import os
from collections import Counter

from src.recommender import load_songs, recommend_songs

# Eleven energy steps spanning the full 0.0-1.0 range. Built with integer
# arithmetic and rounded, because 0.1 has no exact binary representation and
# repeated float addition would drift (0.30000000000000004 and friends).
ENERGY_STEPS = [round(i / 10, 1) for i in range(11)]

# Both catalogs live in data/. songs.csv is the shipped 46-song catalog;
# songs_original.csv is the 20-song catalog the project started with. Sweeping
# both is what lets us say precisely WHICH findings were changed by the
# expansion rather than guessing.
_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
CATALOGS = {
    "46-song (shipped)": os.path.join(_DATA_DIR, "songs.csv"),
    "20-song (original)": os.path.join(_DATA_DIR, "songs_original.csv"),
}


def build_grid(songs: list[dict]) -> list[dict]:
    """Return every profile in the sweep grid for this catalog.

    Genres and moods are taken from the catalog itself (sorted, so the grid is
    deterministic across runs and machines) rather than from a hand-maintained
    list, which would be one more thing that could drift out of sync with the
    data.
    """
    genres = sorted({s["genre"] for s in songs})
    moods = sorted({s["mood"] for s in songs})
    return [
        {"favorite_genre": g, "favorite_mood": m, "target_energy": e}
        for g in genres
        for m in moods
        for e in ENERGY_STEPS
    ]


# ---------------------------------------------------------------------------
# Sweep 1: does a top-5 ever hold 3 songs of one genre?
# ---------------------------------------------------------------------------

def sweep_genre_concentration(songs: list[dict], k: int = 5) -> dict:
    """Measure how concentrated by genre a top-k list can get across the grid.

    This is what decides whether a max_per_genre cap of 2 is dead code. The cap
    can only ever fire on a list that holds 3 or more of a single genre, so if
    that never occurs the cap is unreachable no matter how it is implemented.

    Returns a summary dict rather than printing, so the numbers can be asserted
    in a test or reused by a caller.
    """
    profiles = build_grid(songs)
    worst = 0                      # highest same-genre count seen in any top-k
    hits_3_plus = 0                # profiles whose top-k holds 3+ of one genre
    example: dict | None = None    # first offending profile, for the report

    for prefs in profiles:
        ranked = recommend_songs(prefs, songs, k=k)
        # Counter over the genres of the k shown songs; most_common(1) gives the
        # single most repeated genre and how many times it appears.
        counts = Counter(song["genre"] for song, _score, _reasons in ranked)
        top_count = counts.most_common(1)[0][1] if counts else 0

        if top_count > worst:
            worst = top_count
        if top_count >= 3:
            hits_3_plus += 1
            if example is None:
                example = dict(prefs)

    return {
        "profiles": len(profiles),
        "max_same_genre_in_topk": worst,
        "profiles_with_3_plus": hits_3_plus,
        "example_profile": example,
    }


# ---------------------------------------------------------------------------
# Sweep 2: how heavy must a popularity thumb be to dethrone a perfect match?
# ---------------------------------------------------------------------------

def _overtake_weight(taste_1: float, pop_1: float,
                     taste_r: float, pop_r: float) -> float | None:
    """Smallest popularity weight at which rival r outscores the leader.

    Under the experiment's formula, total = taste + w * popularity. Rival r
    overtakes the leader when:

        taste_r + w * pop_r  >  taste_1 + w * pop_1
        w * (pop_r - pop_1)  >  taste_1 - taste_r
        w                    >  (taste_1 - taste_r) / (pop_r - pop_1)

    Returns that threshold, or None when no weight can ever do it. A rival that
    is no more popular than the leader (pop_r <= pop_1) never catches up by
    adding popularity: the term grows at least as fast for the leader, so the
    gap cannot close. Solving analytically instead of stepping w in a loop means
    the answer is exact rather than quantized to whatever step size we picked.
    """
    if pop_r <= pop_1:
        return None
    return (taste_1 - taste_r) / (pop_r - pop_1)


def sweep_popularity_moat(songs: list[dict]) -> dict:
    """Find the weakest popularity moat across every perfect-match profile.

    "Perfect match" means the profile's top-ranked song matches the listener on
    BOTH genre and mood (so it scores at least 3.0 before energy). The question
    the side-car asks is whether such a #1 is safe from popularity, and the
    honest way to answer it is to find the profile where it is LEAST safe.

    Only rivals that fail to match both dimensions count as usurpers: a second
    genre+mood match displacing the first is a tie-break between two songs the
    listener actually asked for, not the popularity bias we are hunting.
    """
    profiles = build_grid(songs)
    weakest: float | None = None
    weakest_profile: dict | None = None
    checked = 0

    for prefs in profiles:
        # Rank the WHOLE catalog so every possible rival is considered, not
        # just the ones that happened to make a top-5.
        ranked = recommend_songs(prefs, songs, k=len(songs))
        if not ranked:
            continue

        leader, taste_1, _reasons = ranked[0]
        matches_both = (leader["genre"] == prefs["favorite_genre"]
                        and leader["mood"] == prefs["favorite_mood"])
        if not matches_both:
            # No perfect match sits at #1 for this profile, so there is no moat
            # to measure here. Skip rather than counting it as safe.
            continue

        checked += 1
        # Popularity is read straight off the catalog row. Note for anyone
        # extending this: experiment_popularity.score_with_popularity returns
        # (total, PURE TASTE), not (total, popularity). Using its second value
        # here would silently compare taste against taste, and because `ranked`
        # is already sorted by taste every rival would look unable to overtake,
        # producing a confident and completely false "never dethroned" result.
        pop_1 = float(leader["popularity"])

        for rival, taste_r, _r in ranked[1:]:
            rival_matches_both = (rival["genre"] == prefs["favorite_genre"]
                                  and rival["mood"] == prefs["favorite_mood"])
            if rival_matches_both:
                continue
            pop_r = float(rival["popularity"])
            w = _overtake_weight(taste_1, pop_1, taste_r, pop_r)
            if w is None:
                continue
            # Track the global minimum: the single easiest dethroning anywhere
            # in the grid. That is the number a safety claim has to survive.
            if weakest is None or w < weakest:
                weakest = w
                weakest_profile = dict(prefs)
                weakest_profile["leader"] = leader["title"]
                weakest_profile["usurper"] = rival["title"]

    return {
        "profiles_checked": checked,
        "weakest_moat_weight": weakest,
        "weakest_case": weakest_profile,
    }


def main() -> None:
    """Print both sweeps for both catalogs."""
    print("=" * 72)
    print("PROFILE SWEEPS")
    print("Grid: every catalog genre x every catalog mood x energy 0.0-1.0 by 0.1")
    print("=" * 72)

    for label, path in CATALOGS.items():
        songs = load_songs(path)
        conc = sweep_genre_concentration(songs)
        moat = sweep_popularity_moat(songs)

        print(f"\n--- {label}: {len(songs)} songs ---")
        print(f"  profiles swept:                  {conc['profiles']}")
        print(f"  most same-genre songs in a top-5: {conc['max_same_genre_in_topk']}")
        print(f"  profiles whose top-5 holds 3+:    {conc['profiles_with_3_plus']}")
        if conc["example_profile"]:
            ex = conc["example_profile"]
            print(f"    example: {ex['favorite_genre']} / {ex['favorite_mood']}"
                  f" / energy {ex['target_energy']}")
        print(f"  perfect-match profiles checked:   {moat['profiles_checked']}")
        if moat["weakest_moat_weight"] is None:
            print("  weakest popularity moat:          none (never dethroned)")
        else:
            print(f"  weakest popularity moat:          weight"
                  f" {moat['weakest_moat_weight']:.2f}")
            wc = moat["weakest_case"]
            print(f"    {wc['usurper']} overtakes {wc['leader']}"
                  f" for a {wc['favorite_genre']} / {wc['favorite_mood']}"
                  f" / energy {wc['target_energy']} listener")


if __name__ == "__main__":
    main()

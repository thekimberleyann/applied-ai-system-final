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

RAG explanation layer (Project 5): the default run below now attaches a grounded
natural-language explanation to each recommendation via src/explain.py (retrieve a
factual note -> LLM/offline-stub phrases the "why"). It runs offline and
deterministically unless GEMINI_API_KEY is set. The scoring/ranking is unchanged;
the explainer only adds prose to songs the recipe already chose.
"""

from __future__ import annotations

import logging
import os

from src.explain import explain_recommendations, format_block, load_corpus
from src.llm_client import VibeExplainer
from src.recommender import load_songs, recommend_songs

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "songs.csv")

# Path to an OPTIONAL local .env at the repo root. It is gitignored, so a key put
# here is never committed. See _load_dotenv_if_present below.
ENV_PATH = os.path.join(os.path.dirname(__file__), "..", ".env")


def _load_dotenv_if_present() -> None:
    """Load KEY=VALUE lines from a local .env into the environment, if it exists.

    This lets the Gemini key live in a gitignored .env file instead of being
    retyped every session. Deliberately dependency-free: we parse the file
    ourselves rather than requiring python-dotenv, so the default offline path
    still needs zero third-party packages and stays reproducible.

    Behavior:
      * No .env file           -> no-op (the normal offline case).
      * `# comment` / blank     -> skipped.
      * `KEY=VALUE`             -> set only if KEY is not ALREADY in the real
                                   environment (os.environ.setdefault), so an
                                   explicit `set GEMINI_API_KEY=...` in the shell
                                   always wins over the file.
    Surrounding single/double quotes on the value are stripped for convenience.
    """
    if not os.path.exists(ENV_PATH):
        return
    with open(ENV_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key:
                # Do not clobber a value already exported in the shell.
                os.environ.setdefault(key, val)

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


def run_rag_block(header: str, prefs: dict, songs: list[dict],
                  notes: dict, client: VibeExplainer, k: int = 5) -> list[dict]:
    """Explain one profile's top-k via the RAG layer, print it, return the results.

    Returns the structured result list so main() can compute the reliability
    summary (how many recommendations were grounded on a note vs fell back).
    """
    results = explain_recommendations(prefs, songs, notes, client, k=k)
    print(format_block(header, results))
    return results


def main() -> None:
    # Configure logging for the whole run. The RAG orchestrator emits one INFO line
    # per recommendation (retrieval confidence, explainer mode, guardrail state);
    # sending it to stderr keeps stdout clean for the pasteable recommendation
    # output while still leaving an auditable trail.
    logging.basicConfig(
        level=logging.INFO,
        format="LOG %(levelname)s %(name)s: %(message)s",
    )

    # Pull in a local .env (if any) BEFORE constructing the explainer, so a key
    # stored there is visible when VibeExplainer decides live vs offline.
    _load_dotenv_if_present()

    songs = load_songs(DATA_PATH)
    print(f"Loaded songs: {len(songs)}")

    # Build the RAG pieces once: load the note corpus and construct the explainer.
    # The explainer picks live vs offline at construction; we report which so the
    # output is self-documenting about whether a key was present.
    notes = load_corpus()
    client = VibeExplainer()
    print(f"RAG explainer mode: {client.mode}  |  notes loaded: {len(notes)}")
    print()

    # 1. Default run, now WITH grounded RAG explanations (the AI feature in action).
    default_results = run_rag_block(
        "=== Recommendations for the default profile (pop / happy) [RAG] ===",
        DEFAULT_PROFILE,
        songs,
        notes,
        client,
    )

    # 2. A second explained profile so the README has multiple RAG interactions and
    #    a case where a whole scoring term is thin. Chill Lofi exercises a different
    #    corner of taste space than the default pop profile.
    lofi_results = run_rag_block(
        "=== Chill Lofi (lofi / chill / energy 0.30) [RAG] ===",
        {"favorite_genre": "lofi", "favorite_mood": "chill", "target_energy": 0.30},
        songs,
        notes,
        client,
    )

    # 3. Diverse / stress battery -- score-only, to keep the reliability picture of
    #    the raw recipe visible (no explanations needed here).
    print("### DIVERSE / STRESS PROFILES (score-only) ###")
    print()
    for label, prefs in DIVERSE_PROFILES:
        print_recommendations(f"=== {label} ===", prefs, songs)

    # 4. Adversarial battery -- score-only, probing the recipe edges.
    print("### ADVERSARIAL PROFILES (score-only) ###")
    print()
    for label, prefs in ADVERSARIAL_PROFILES:
        print_recommendations(f"=== {label} ===", prefs, songs)

    # 5. Reliability summary: across the two explained blocks, how many
    #    recommendations were grounded on a retrieved note vs. fell back to
    #    score-only. This one line is the guardrail/reliability evidence.
    explained = default_results + lofi_results
    grounded = sum(1 for r in explained if r["grounded"])
    total = len(explained)
    avg_conf = (
        sum(r["confidence"] for r in explained) / total if total else 0.0
    )
    print("### RELIABILITY SUMMARY (RAG layer) ###")
    print(
        f"{grounded}/{total} explained recommendations were grounded on a "
        f"retrieved note; average retrieval confidence {avg_conf:.2f}; "
        f"explainer mode = {client.mode}."
    )
    print(
        "Guardrail: any recommendation with no note above the confidence floor "
        "falls back to a score-only explanation instead of inventing details."
    )


if __name__ == "__main__":
    main()

"""VibeFinder RAG orchestration -- ties recommend -> retrieve -> explain together.

This is the module that makes the RAG feature part of the MAIN application flow
rather than a side script. Given a taste profile and the catalog, it:

  1. calls recommend_songs (deterministic scoring + ranking) -- unchanged,
  2. for each chosen song, retrieves the best factual note (src/retriever.py),
  3. asks the explainer for a grounded "why this fits you" (src/llm_client.py),
  4. logs the retrieval confidence, the explainer mode, and whether the guardrail
     fallback fired, so the run leaves an auditable trail.

The ranking that comes out is byte-for-byte the ranking recommend_songs produced;
this module only ATTACHES an explanation to each already-chosen song. It can never
reorder results -- a property the tests pin directly.
"""

from __future__ import annotations

import logging

from src.llm_client import VibeExplainer
from src.recommender import recommend_songs
from src.retriever import load_notes, retrieve_note

# Module logger. Configuration (level, handler) is the application's job in
# src/main.py; libraries should not configure logging for their importers. We add
# a NullHandler so importing this module never emits "No handler" warnings when the
# app has not configured logging (for example under pytest).
logger = logging.getLogger("vibefinder.rag")
logger.addHandler(logging.NullHandler())


def explain_recommendations(
    prefs: dict,
    songs: list[dict],
    notes: dict[str, str],
    client: VibeExplainer,
    k: int = 5,
) -> list[dict]:
    """Return the top-k recommendations, each with a grounded explanation attached.

    Each result is a dict:
        {
          "song":       the song dict,
          "score":      float score from the recipe,
          "reasons":    the deterministic per-term reason list,
          "note_title": title of the note retrieved (or None if none cleared floor),
          "confidence": retrieval confidence 0.0-1.0,
          "grounded":   True if a note was used, False if the fallback fired,
          "explanation":the natural-language text shown to the user,
        }

    The order of the list is exactly recommend_songs' order. `notes` and `client`
    are passed in (not built here) so the corpus is loaded once and the same
    explainer -- with its already-decided live/offline mode -- is reused per run.
    """
    # Retrieve first for every recommendation, then explain them all in ONE batched
    # call (a single API request in live mode, keeping multi-song queries under the
    # rate limit). The offline path is unaffected: the batch just calls the
    # deterministic stub per grounded song.
    ranked = recommend_songs(prefs, songs, k=k)
    retrieved = []
    for song, score, reasons in ranked:
        note, confidence, note_title = retrieve_note(song, notes)
        retrieved.append((song, score, reasons, note, confidence, note_title))

    items = [{"song": s, "score": sc, "reasons": r, "note": n}
             for (s, sc, r, n, c, nt) in retrieved]
    explanations, status = client.explain_batch(items, prefs)
    if status:
        logger.warning("live explainer status: %s", status)

    results: list[dict] = []
    for (song, score, reasons, note, confidence, note_title), explanation in zip(
            retrieved, explanations):
        grounded = note is not None
        logger.info(
            "rec=%r score=%.2f retrieved=%r confidence=%.2f mode=%s grounded=%s",
            song.get("title"), score, note_title, confidence, client.mode, grounded,
        )
        results.append({
            "song": song, "score": score, "reasons": reasons,
            "note_title": note_title, "confidence": confidence,
            "grounded": grounded, "explanation": explanation,
        })

    return results


def format_block(header: str, results: list[dict]) -> str:
    """Render one explained-recommendation block as text (for the CLI / logs).

    Kept separate from explain_recommendations so the data and its presentation do
    not entangle: tests check the structured dicts, while main.py prints this.
    """
    lines = [header]
    for rank, r in enumerate(results, start=1):
        song = r["song"]
        lines.append(f"{rank}. {song['title']}  (score {r['score']:.2f})")
        # Show the deterministic reasons (unchanged) ...
        for reason in r["reasons"]:
            lines.append(f"     - {reason}")
        # ... then the RAG explanation, tagged with its retrieval confidence and
        # whether it was grounded on a note or fell back to score-only.
        tag = (
            f"grounded on '{r['note_title']}', confidence {r['confidence']:.2f}"
            if r["grounded"]
            else "no note retrieved -- score-only fallback"
        )
        lines.append(f"     why: {r['explanation']}")
        lines.append(f"          [{tag}]")
    lines.append("")  # trailing blank line between blocks
    return "\n".join(lines)


def load_corpus():
    """Convenience wrapper so callers do not import load_notes separately."""
    return load_notes()

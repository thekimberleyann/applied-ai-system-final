"""Retrieval evaluation: measure the retriever instead of trusting it.

WHY THIS EXISTS
    Everything else in this project measures the RECOMMENDER. Nothing measured
    the RETRIEVER, which meant every claim about grounding rested on spot checks
    and on reading the code. This module scores retrieval the way information
    retrieval has always been scored, so a change to the corpus, the similarity
    metric, the stopword list, or the confidence floor produces a NUMBER that
    moves rather than a vibe that shifts.

    Run with:  python -m src.evaluate_retrieval

THE GOLD SET
    A gold set normally has to be written by hand: a list of queries paired with
    the document that should be retrieved. Here it is derived, because the corpus
    is keyed one note per song, so the correct note for a song is unambiguously
    the note carrying its title. That gives 46 query-and-answer pairs for free,
    with no judgement calls and nothing to maintain.

    The catch is worth stating plainly: a derived gold set can only measure
    whether retrieval finds the obviously-right document. It cannot measure
    whether a note is any good, and it cannot catch a corpus where two notes
    describe the same song. It is the cheap 80 percent, not the whole job.

THE TWO METRICS
    hit@k  -- the fraction of queries whose gold note appears in the top k.
              "Did the right document make it into the context window at all."
              If the answer is no, no amount of prompt tuning can save the
              generation, which is why this is the first thing to measure.
    MRR    -- mean reciprocal rank: average of 1/rank of the gold note. It
              rewards ranking the right note FIRST, not merely including it.
              hit@3 of 1.0 with an MRR of 0.6 means the right note is usually
              present but often beaten to the top by a wrong one.

THE THIRD MEASUREMENT, WHICH MATTERS MOST HERE
    leave-one-out: delete a song's own note, then ask what retrieval does. The
    confidence floor is supposed to answer "no usable note" and trigger the
    score-only fallback. Measuring it is how we learned that it does not, for
    any song in this catalog. See the docstring on leave_one_out below.
"""

from __future__ import annotations

import os

from src.recommender import load_songs
from src.retriever import (
    MIN_CONFIDENCE,
    load_notes,
    retrieve_note,
    score_all_notes,
)

_DATA = os.path.join(os.path.dirname(__file__), "..", "data")


def gold_pairs(songs: list[dict], notes: dict[str, str]) -> list[tuple[dict, str]]:
    """Derive (song, gold_note_title) pairs.

    A song only enters the gold set if a note actually carries its title. A song
    with no note has no correct answer, so scoring it would measure nothing;
    those are handled by leave_one_out instead.
    """
    return [(s, s["title"]) for s in songs if s["title"] in notes]


def hit_at_k(board: list[dict], gold_title: str, k: int) -> bool:
    """Did the gold note land in the top k of this ranked board?"""
    return any(row["title"] == gold_title for row in board[:k])


def reciprocal_rank(board: list[dict], gold_title: str) -> float:
    """1/rank of the gold note, or 0.0 if it is absent from the board."""
    for position, row in enumerate(board, start=1):
        if row["title"] == gold_title:
            return 1.0 / position
    return 0.0


def evaluate(songs: list[dict], notes: dict[str, str],
             use_tiebreak: bool = True) -> dict:
    """Score retrieval over the derived gold set.

    `use_tiebreak` selects what is being measured:
      True  -- the shipped retriever, exact-title tiebreak included. This is the
               system as it actually behaves.
      False -- pure token overlap, the tiebreak removed. This is what the
               retrieval would do on its own merits, and the gap between the two
               is exactly how much work the tiebreak is doing.

    score_all_notes orders by overlap alone, so the False case reads straight off
    the board. The True case asks retrieve_note, which is the real decision-maker.
    """
    pairs = gold_pairs(songs, notes)
    hits1 = hits3 = 0
    rr_total = 0.0

    for song, gold in pairs:
        board = score_all_notes(song, notes)

        if use_tiebreak:
            # Re-rank the board the way retrieve_note actually decides: an exact
            # title match wins outright, otherwise overlap order stands. This
            # mirrors retrieve_note's (exact, overlap) sort key rather than
            # reimplementing its arithmetic.
            board = sorted(board, key=lambda r: (not r["exact"], -r["overlap"], r["title"]))

        hits1 += hit_at_k(board, gold, 1)
        hits3 += hit_at_k(board, gold, 3)
        rr_total += reciprocal_rank(board, gold)

    n = len(pairs) or 1
    return {
        "queries": len(pairs),
        "hit@1": hits1 / n,
        "hit@3": hits3 / n,
        "mrr": rr_total / n,
    }


def leave_one_out(songs: list[dict], notes: dict[str, str]) -> dict:
    """Delete each song's own note and see whether the floor protects it.

    This is the guardrail's real test. The confidence floor exists so that a song
    with no relevant note falls back to a score-only explanation instead of being
    described using facts about a DIFFERENT song. The floor only does that job if
    an unrelated note scores below MIN_CONFIDENCE.

    On this corpus it does not. Sibling notes share genre and mood vocabulary, so
    with its own note removed a song's next-best match scores 0.60 to 0.80, far
    above the 0.15 floor. Every song in the catalog silently grounds on some
    other song's note.

    That is a live hazard for anyone extending this project: add a row to
    songs.csv, forget to write its note, and the system will confidently explain
    the new song using another song's facts. No warning, no fallback, high
    reported confidence. The floor only catches input that is alien to the whole
    corpus, which real catalog rows never are.

    Returns the count that leaked, the worst offenders, and the score the floor
    would have to exceed to actually stop them.
    """
    leaked: list[tuple[float, str, str]] = []

    for song in songs:
        # Rebuild the corpus without this song's own note. dict comprehension so
        # the shared corpus is never mutated.
        others = {k: v for k, v in notes.items() if k != song["title"]}
        _note, confidence, picked = retrieve_note(song, others)
        if picked is not None:
            leaked.append((confidence, song["title"], picked))

    leaked.sort(reverse=True)
    return {
        "songs": len(songs),
        "leaked": len(leaked),
        "worst": leaked[:5],
        # The floor would need to sit above the HIGHEST wrong match to stop them
        # all, which on this corpus would also reject many correct retrievals.
        "floor_needed": leaked[0][0] if leaked else 0.0,
    }


def genuine_confidence_range(songs: list[dict], notes: dict[str, str]) -> dict:
    """The spread of confidences on correct retrievals, versus the floor.

    Reported so the floor's headroom is a measured number rather than an
    assertion. If the lowest genuine retrieval sits just above MIN_CONFIDENCE,
    the floor is one corpus edit away from rejecting a correct note.
    """
    confidences = []
    for song in songs:
        _n, confidence, picked = retrieve_note(song, notes)
        if picked is not None:
            confidences.append((confidence, song["title"]))
    confidences.sort()
    return {
        "min": confidences[0] if confidences else (0.0, ""),
        "max": confidences[-1] if confidences else (0.0, ""),
        "headroom": (confidences[0][0] - MIN_CONFIDENCE) if confidences else 0.0,
    }


def main() -> None:
    songs = load_songs(os.path.join(_DATA, "songs.csv"))
    notes = load_notes(os.path.join(_DATA, "song_notes.md"))

    print("=" * 72)
    print("RETRIEVAL EVALUATION")
    print(f"gold set: {len(gold_pairs(songs, notes))} derived query/answer pairs")
    print("=" * 72)

    shipped = evaluate(songs, notes, use_tiebreak=True)
    overlap = evaluate(songs, notes, use_tiebreak=False)

    print(f"\n{'variant':<28}{'hit@1':>8}{'hit@3':>8}{'MRR':>8}")
    print(f"{'shipped (with tiebreak)':<28}{shipped['hit@1']:>8.3f}"
          f"{shipped['hit@3']:>8.3f}{shipped['mrr']:>8.3f}")
    print(f"{'pure overlap (no tiebreak)':<28}{overlap['hit@1']:>8.3f}"
          f"{overlap['hit@3']:>8.3f}{overlap['mrr']:>8.3f}")
    print(f"\n  The gap is how much work the exact-title tiebreak does. Without it,"
          f"\n  overlap alone puts the right note first {overlap['hit@1']:.0%} of the time.")

    rng = genuine_confidence_range(songs, notes)
    print(f"\nCONFIDENCE FLOOR = {MIN_CONFIDENCE}")
    print(f"  lowest correct retrieval:  {rng['min'][0]:.2f}  ({rng['min'][1]})")
    print(f"  highest correct retrieval: {rng['max'][0]:.2f}  ({rng['max'][1]})")
    print(f"  headroom above the floor:  {rng['headroom']:.2f}")

    loo = leave_one_out(songs, notes)
    print("\nLEAVE-ONE-OUT (each song's own note removed)")
    print(f"  {loo['leaked']} of {loo['songs']} songs ground on ANOTHER song's note.")

    if loo["leaked"] == 0:
        print("\n  The metadata filter is holding. Every song whose own note is")
        print("  missing now falls back to a score-only reason instead of being")
        print("  explained with a different song's facts.")
        print("\n  This was not always true. Before the filter, all 46 songs leaked,")
        print("  matching siblings at 0.60 to 0.80 against a floor of 0.15, because")
        print("  sibling notes share genre and mood vocabulary. No threshold could")
        print("  separate them: correct margins spanned 0.00 to 0.50 and wrong ones")
        print("  0.00 to 0.40, so 44 of 46 correct cases sat inside the wrong range.")
        print("  The fix was to stop asking the score a question it cannot answer.")
        print("  Similarity finds candidates; identity decides eligibility.")
    else:
        print(f"  The floor would have to exceed {loo['floor_needed']:.2f} to stop them,")
        print("  which is above most CORRECT retrievals, so raising it is not the fix.")
        for conf, song, picked in loo["worst"]:
            print(f"    {song:<22} -> {picked:<22} {conf:.2f}")
        print("\n  Meaning: the floor only rejects input alien to the whole corpus.")
        print("  A catalog row whose note was never written is NOT alien, so it is")
        print("  explained using another song's facts, with no warning.")


if __name__ == "__main__":
    main()

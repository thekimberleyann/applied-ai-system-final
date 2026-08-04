"""Retrieval evaluation: measure the retriever instead of trusting it.

WHY THIS EXISTS
    Everything else in this project measures the RECOMMENDER. Nothing measured
    the RETRIEVER, which meant every claim about grounding rested on spot checks
    and on reading the code. This module scores retrieval the way information
    retrieval has always been scored, so a change to the corpus, the similarity
    metric, the stopword list, or the confidence floor produces a NUMBER that
    moves rather than a vibe that shifts.

    Run with:  python -m src.evaluate_retrieval
               python -m src.evaluate_retrieval --compare

CHANGE A KNOB, WATCH THE METRIC MOVE
    --compare is the reason src/config.py exists. It runs the whole measurement
    under several configurations and prints them as one table, one knob changed
    per row, so the effect of each knob is a row you can read rather than an
    argument you have to follow. Turn the tiebreak off and hit@1 drops from 1.000
    to 0.674. Raise the floor past the lowest correct retrieval and grounded
    coverage falls from 46 songs to 14. Remove the metadata filter and the leak
    column goes from nothing to the entire catalog.

    The bare run (no flag) is deliberately left byte-identical to what it printed
    before the knobs existed, because assets/ evidence and the write-ups quote
    it. --compare is additive.

WHY THE TABLE HAS SIX COLUMNS AND NOT THREE
    hit@1, hit@3 and MRR score the RANKING, which is all they can score, and on
    this system they are not enough to see a knob move. Three problems, three
    extra columns:

      * The floor and the metadata filter act AFTER the board is ordered. They
        decide whether the winning note is ALLOWED to be used, so no ranking
        metric can see them at all. `grounded` counts the songs the system was
        willing to explain, which is what those two knobs actually move.
      * The metadata filter's failure is invisible on a complete corpus, because
        every song has its own note and the filter never fires. `leaked` runs
        leave-one-out, deleting each song's note, which is the only measurement
        that shows the bug.
      * The exact-title tiebreak is strong enough to hide damage done to the
        similarity metric underneath it: a knob can degrade the overlap badly and
        MRR still reads 1.000 because the tiebreak rescues the board. `ovMRR`
        re-scores with the tiebreak suppressed so that damage is visible. The
        stopword knob is exactly this case, and without ovMRR its row would have
        been five identical numbers.

    Between them every knob moves at least one column, which was the design
    target: a knob that moves nothing measurable is a knob nobody can reason
    about.

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

import argparse
import os
from dataclasses import replace

from src.config import DEFAULT_RETRIEVAL, RetrievalConfig, retrieval_or_default
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
             config: RetrievalConfig | None = None) -> dict:
    """Score retrieval over the derived gold set.

    `config` (optional, defaults to DEFAULT_RETRIEVAL) is the SINGLE source of
    truth for every knob, including whether the exact-title tiebreak applies.
    An earlier version also took a separate `use_tiebreak` argument and combined
    the two with AND, which meant the same question had two answers and a reader
    had to check both to know what was measured. To score pure token overlap,
    pass a config with the tiebreak switched off:

        replace(DEFAULT_RETRIEVAL, use_exact_title_tiebreak=False)

    That comparison is the interesting one: score_all_notes orders by overlap
    alone, so a tiebreak-off config shows what retrieval does on its own merits,
    and the gap against the default is how much work the tiebreak is doing.
    """
    cfg = retrieval_or_default(config)
    pairs = gold_pairs(songs, notes)
    hits1 = hits3 = 0
    rr_total = 0.0

    for song, gold in pairs:
        board = score_all_notes(song, notes, cfg)

        if cfg.use_exact_title_tiebreak:
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


def leave_one_out(songs: list[dict], notes: dict[str, str],
                  config: RetrievalConfig | None = None) -> dict:
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

    This is the measurement the metadata-filter knob moves, and the only one that
    does. With the filter on (the default) the leak count is 0. With it off, this
    number is the size of the catalog, which is what makes that knob a fault
    injection rather than a setting.
    """
    cfg = retrieval_or_default(config)
    leaked: list[tuple[float, str, str]] = []

    for song in songs:
        # Rebuild the corpus without this song's own note. dict comprehension so
        # the shared corpus is never mutated.
        others = {k: v for k, v in notes.items() if k != song["title"]}
        _note, confidence, picked = retrieve_note(song, others, cfg)
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


def genuine_confidence_range(songs: list[dict], notes: dict[str, str],
                             config: RetrievalConfig | None = None) -> dict:
    """The spread of confidences on correct retrievals, versus the floor.

    Reported so the floor's headroom is a measured number rather than an
    assertion. If the lowest genuine retrieval sits just above MIN_CONFIDENCE,
    the floor is one corpus edit away from rejecting a correct note.
    """
    cfg = retrieval_or_default(config)
    confidences = []
    for song in songs:
        _n, confidence, picked = retrieve_note(song, notes, cfg)
        if picked is not None:
            confidences.append((confidence, song["title"]))
    confidences.sort()
    return {
        "min": confidences[0] if confidences else (0.0, ""),
        "max": confidences[-1] if confidences else (0.0, ""),
        # Headroom is measured against the floor IN EFFECT, not the default one,
        # so raising the floor is visible here as the margin shrinking (and going
        # negative once the floor has climbed past a correct retrieval).
        "headroom": (confidences[0][0] - cfg.min_confidence) if confidences else 0.0,
    }


def grounded_count(songs: list[dict], notes: dict[str, str],
                   config: RetrievalConfig | None = None) -> int:
    """How many songs actually come back with a usable note.

    The ranking metrics cannot see this. hit@1 asks whether the right note was
    ranked first; this asks whether the system was then WILLING to use it, which
    is a separate decision made by the confidence floor and the metadata filter
    after ranking is over. On the shipped defaults the two agree (46 of 46), and
    the point of measuring both is to show what pulls them apart: raise the floor
    above a song's genuine confidence and its note is still ranked first and
    still refused.
    """
    cfg = retrieval_or_default(config)
    return sum(1 for song in songs if retrieve_note(song, notes, cfg)[2] is not None)


def metrics_for_config(songs: list[dict], notes: dict[str, str],
                       config: RetrievalConfig) -> dict:
    """Every headline number for ONE configuration, in a single dict.

    Bundled into one function so the comparison table cannot accidentally measure
    two different things in two different columns: every row of that table is one
    call to this, with only the config changing.
    """
    scores = evaluate(songs, notes, config)
    # The same gold set scored with the tiebreak suppressed, which exposes the
    # quality of the token overlap ITSELF. Without this column a knob that
    # degrades the similarity metric can hide completely, because the exact-title
    # tiebreak is strong enough to rescue a badly ranked board and hand back a
    # perfect hit@1 either way. The stopword knob is exactly that case on this
    # corpus, so the column is not hypothetical.
    raw = evaluate(songs, notes, replace(config, use_exact_title_tiebreak=False))
    return {
        "hit@1": scores["hit@1"],
        "hit@3": scores["hit@3"],
        "mrr": scores["mrr"],
        "overlap_mrr": raw["mrr"],
        "grounded": grounded_count(songs, notes, config),
        "leaked": leave_one_out(songs, notes, config)["leaked"],
    }


def comparison_variants() -> list[tuple[str, RetrievalConfig]]:
    """The configurations the comparison table walks, defaults first.

    One variant per knob, each changing exactly ONE field away from the defaults.
    That is the whole discipline of the table: if a row changed two things at
    once, a moved number could not be attributed to either of them.

    Built with dataclasses.replace off DEFAULT_RETRIEVAL rather than by
    constructing configs from scratch, so a future field added to RetrievalConfig
    is automatically held at its default in every row instead of silently
    reverting to the constructor default in some of them.

    The floor variant uses 0.60 because measurement puts the lowest correct
    retrieval on this corpus at 0.25: 0.60 is comfortably past it, so the row
    demonstrates a floor set too high rejecting notes that were correct, which is
    the failure mode worth showing. A floor of 0.20 would move nothing and teach
    nothing.
    """
    return [
        ("defaults (shipped)", DEFAULT_RETRIEVAL),
        ("no exact-title tiebreak", replace(DEFAULT_RETRIEVAL,
                                            use_exact_title_tiebreak=False)),
        ("no stopword filtering", replace(DEFAULT_RETRIEVAL, use_stopwords=False)),
        ("floor raised to 0.60", replace(DEFAULT_RETRIEVAL, min_confidence=0.60)),
        ("NO metadata filter (bug)", replace(DEFAULT_RETRIEVAL,
                                             use_metadata_filter=False)),
    ]


def render_comparison(songs: list[dict], notes: dict[str, str]) -> str:
    """The knob comparison table, as text.

    Returns a string rather than printing, so this can be asserted on in a test
    and captured as committed evidence the same way assets/sample_run.txt is.
    """
    total = len(songs)
    lines = [
        "=" * 78,
        "KNOB COMPARISON: what each configuration change actually costs",
        f"catalog {total} songs, corpus {len(notes)} notes, "
        f"gold set {len(gold_pairs(songs, notes))} pairs",
        "=" * 78,
        "",
        f"{'configuration':<26}{'hit@1':>7}{'hit@3':>7}{'MRR':>7}"
        f"{'ovMRR':>7}{'grounded':>11}{'leaked':>8}",
        "-" * 78,
    ]

    for label, config in comparison_variants():
        m = metrics_for_config(songs, notes, config)
        lines.append(
            f"{label:<26}{m['hit@1']:>7.3f}{m['hit@3']:>7.3f}{m['mrr']:>7.3f}"
            f"{m['overlap_mrr']:>7.3f}{m['grounded']:>8}/{total:<2}{m['leaked']:>8}"
        )

    lines += [
        "-" * 78,
        "",
        "  hit@1/hit@3/MRR  quality of the RANKING the system actually uses.",
        "  ovMRR            the same MRR with the exact-title tiebreak suppressed,",
        "                   so it scores the token overlap on its own merits. A",
        "                   knob can degrade the similarity badly and leave MRR at",
        "                   1.000, because the tiebreak rescues the board; ovMRR is",
        "                   where that damage shows.",
        "  grounded         songs the system was WILLING to explain from a note,",
        "                   out of the whole catalog. Decided after ranking, by the",
        "                   floor and the metadata filter.",
        "  leaked           leave-one-out: with a song's own note deleted, how many",
        "                   songs get explained using a DIFFERENT song's facts.",
        "                   This is the number that must stay at 0.",
        "",
        "READING THE ROWS",
        "  no tiebreak       hit@1 1.000 -> 0.674 and MRR -> 0.830. Token overlap",
        "                    alone cannot reliably put a song's own note first,",
        "                    because sibling notes share genre and mood vocabulary.",
        "                    This is the measurement that justifies the tiebreak.",
        "                    hit@3 stays 1.000, so it is a RANKING failure and not a",
        "                    recall failure, which is what says reranking is the fix",
        "                    and a better corpus is not. Grounded also falls to",
        "                    29/46: once the tiebreak stops forcing the own-note",
        "                    pick, the metadata filter rejects the 17 songs where a",
        "                    sibling note out-scored their own.",
        "",
        "  no stopwords      ovMRR 0.830 -> 0.826, and nothing else moves. This is",
        "                    the honest result and it is more interesting than the",
        "                    textbook answer. Stopwords cannot inflate a score here",
        "                    because _similarity divides by the QUERY tokens and",
        "                    counts only SHARED ones, and the query is built from",
        "                    title plus genre plus mood, which almost never contains",
        "                    a stopword. Exactly 3 of 46 songs have one in their",
        "                    query (Smoke and Brass, Dust and Diesel, Nocturne in",
        "                    Grey) and only Nocturne in Grey changes rank, 2nd to",
        "                    3rd. The lesson is that a preprocessing step matters in",
        "                    proportion to how much of the QUERY it touches, and on",
        "                    short structured queries that is nearly nothing. On",
        "                    natural-language queries this knob would dominate.",
        "",
        "  floor 0.60        every ranking column is untouched and grounded falls",
        "                    from 46 to 14. The floor cannot improve retrieval, it",
        "                    can only refuse it, and set above the lowest correct",
        "                    confidence (0.25, Delta Dust) it refuses notes that",
        "                    were retrieved perfectly well.",
        "",
        "  no metadata filt  every ranking column is perfect, grounded is a full",
        "                    46/46, and the leak column is the entire catalog. That",
        "                    combination is the point of this row: on a COMPLETE",
        "                    corpus the bug is invisible to every metric except",
        "                    leave-one-out, which is why the filter is pinned by a",
        "                    test rather than trusted to show up in hit@1.",
    ]
    return "\n".join(lines)


def main() -> None:
    # argparse rather than a bare sys.argv check so --help documents the flag.
    # The default (no flag) path below is unchanged from before the knobs
    # existed, deliberately: its output is quoted as evidence elsewhere in the
    # project, so the comparison table is additive and opt-in.
    parser = argparse.ArgumentParser(
        description="Measure VibeFinder's retrieval with hit@k, MRR and leave-one-out.")
    parser.add_argument(
        "--compare", action="store_true",
        help="Print the knob comparison table: the same measurements repeated "
             "under several configurations, one knob changed per row.")
    args = parser.parse_args()

    songs = load_songs(os.path.join(_DATA, "songs.csv"))
    notes = load_notes(os.path.join(_DATA, "song_notes.md"))

    if args.compare:
        print(render_comparison(songs, notes))
        return

    print("=" * 72)
    print("RETRIEVAL EVALUATION")
    print(f"gold set: {len(gold_pairs(songs, notes))} derived query/answer pairs")
    print("=" * 72)

    shipped = evaluate(songs, notes)
    overlap = evaluate(songs, notes,
                       replace(DEFAULT_RETRIEVAL, use_exact_title_tiebreak=False))

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

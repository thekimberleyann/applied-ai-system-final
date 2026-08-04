"""Glass box: make one VibeFinder run fully inspectable.

WHY THIS EXISTS
    VibeFinder answers "here are five songs" but not "why these five, and why
    was THAT note used to explain them". Both answers already exist inside the
    system; they were simply never surfaced. Every number this module reports is
    read from the same functions the real run uses. Nothing here re-implements
    scoring or retrieval, because a debugging view that computes its own answers
    can disagree with the system it claims to describe, which makes it worse than
    no view at all.

TWO SEPARATE "WHY" QUESTIONS
    It matters that these stay apart, because conflating them is exactly the
    confusion VibeFinder's central guardrail exists to prevent:

      1. Why did this song RANK here?   Answered by the deterministic recipe in
         recommender.score_song. No AI is involved at any point.
      2. Why was this NOTE retrieved to explain it?  Answered by the retriever.
         This is the retrieval-augmented half.

    The language model participates in neither. It receives the ranking and the
    retrieved note as fixed inputs and writes prose. inspect_run() therefore
    reports the ranking and the retrieval independently, and never attributes a
    ranking decision to the model.

DESIGN CONSTRAINT: OBSERVATION MUST NOT PERTURB
    Everything here is read-only with respect to a run. No function in this
    module mutates a song dict, a note, or a result. A test pins that a run's
    output is identical whether or not the glass box is used, which is the same
    shape as the guardrail pinning that the explainer never re-ranks.
"""

from __future__ import annotations

from src.llm_client import build_explain_prompt
from src.recommender import recommend_songs, score_song
from src.retriever import MIN_CONFIDENCE, retrieve_note, score_all_notes

# How many songs BELOW the shown cut to include in the ranking table. The near
# misses are where the insight is: seeing a 3.92 lose to a 3.95 teaches more
# about the recipe than the winners do. The full catalog stays available via
# rank_table(..., limit=None) for anyone who wants all of it.
NEAR_MISS_COUNT = 5


def score_breakdown(prefs: dict, song: dict) -> dict:
    """Itemize one song's score into its three terms.

    The terms are recovered by PARSING the reasons list that score_song already
    returns, rather than by recomputing the arithmetic here. That is deliberate:
    score_song guarantees its reasons sum to its score, so parsing them inherits
    that guarantee, while a second implementation of the recipe could drift away
    from the first and quietly display numbers the system never used.

    Returns a dict with the genre, mood and energy contributions, the total, and
    the raw reasons list.
    """
    score, reasons = score_song(prefs, song)

    # Default every term to 0.0, then fill in whichever reasons are present. A
    # non-matching dimension simply produces no reason string, which is why a
    # missing key here means "did not match" rather than "something went wrong".
    terms = {"genre": 0.0, "mood": 0.0, "energy": 0.0}
    for reason in reasons:
        # Each reason ends in "(+N.NN)". Pull the number back out of the string
        # the recipe itself produced.
        value = float(reason.rsplit("(+", 1)[1].rstrip(")"))
        if reason.startswith("genre"):
            terms["genre"] = value
        elif reason.startswith("mood"):
            terms["mood"] = value
        elif reason.startswith("energy"):
            terms["energy"] = value

    return {
        "title": song.get("title", ""),
        "genre": song.get("genre", ""),
        "mood": song.get("mood", ""),
        "energy": song.get("energy", ""),
        "terms": terms,
        "total": score,
        "reasons": reasons,
    }


def rank_table(prefs: dict, songs: list[dict], k: int = 5,
               limit: int | None = None) -> list[dict]:
    """Rank the WHOLE catalog and return breakdowns, marking the top-k cut.

    Answering "why this song over the rest" requires showing the rest, so this
    ranks the whole catalog and then marks which rows the user actually saw.

    `limit` caps how many rows come back. None (the default) means the k shown
    songs plus NEAR_MISS_COUNT near misses, which is the useful default view.
    Pass limit=len(songs) to get the entire ranking.

    Each row is a score_breakdown dict plus:
        rank   -- 1-based position in the full ranking
        shown  -- whether this row is inside the top-k the listener received
    """
    ranked = recommend_songs(prefs, songs, k=len(songs))

    rows: list[dict] = []
    for position, (song, _score, _reasons) in enumerate(ranked, start=1):
        row = score_breakdown(prefs, song)
        row["rank"] = position
        row["shown"] = position <= k
        rows.append(row)

    if limit is None:
        limit = k + NEAR_MISS_COUNT
    return rows[:limit]


def retrieval_board(song: dict, notes: dict[str, str]) -> dict:
    """Report the full retrieval competition for one song.

    This is the lecture's "print the retrieved chunks" step, which VibeFinder
    performed but only ever wrote to a log. Two rankings are reported, not one:

      * `board` is every note ordered by TOKEN OVERLAP alone, which is what a
        pure overlap retriever would have chosen.
      * `picked_title` is what retrieve_note actually chose, which can differ,
        because retrieve_note applies an exact-title tiebreak on top of overlap.

    When those two disagree, `tiebreak_overrode` is True. That case is worth
    surfacing rather than hiding: it is a real instance of lexical retrieval
    picking the wrong document (a sibling note that happens to share vocabulary),
    corrected by a hand-rolled reranking rule. Hiding it would waste the clearest
    retrieval lesson in this codebase.

    Note also that `confidence` is the overlap of the PICKED note, which is not
    necessarily the highest overlap on the board. The Inspector shows both
    columns so that discrepancy is visible instead of misleading.
    """
    board = score_all_notes(song, notes)
    note, confidence, picked_title = retrieve_note(song, notes)

    # The note overlap alone would have retrieved: the top of the board.
    overlap_winner = board[0]["title"] if board else None

    return {
        "song_title": song.get("title", ""),
        "board": board,
        "picked_title": picked_title,
        "picked_note": note,
        "confidence": confidence,
        "grounded": note is not None,
        "floor": MIN_CONFIDENCE,
        "overlap_winner": overlap_winner,
        # Only meaningful when something was actually picked. A song that fell
        # below the floor was not "overridden", it simply had no usable note.
        "tiebreak_overrode": (
            picked_title is not None
            and overlap_winner is not None
            and picked_title != overlap_winner
        ),
        # STRICT override: the tiebreak did not merely break a tie, it overturned
        # a note that genuinely scored HIGHER. This distinction matters and the
        # Inspector must not blur it. On the shipped catalog 15 songs trigger an
        # override but only 3 are strict (Heavy Riff, Delta Dust, Halcyon Drift);
        # the other 12 are equal-overlap ties where any tiebreak rule would have
        # to choose something. Reporting all 15 as retrieval failures would
        # overstate the problem by five times. The 3 strict cases are the real
        # evidence that token overlap alone mis-retrieves.
        "strict_override": (
            picked_title is not None
            and board
            and round(board[0]["overlap"], 2)
            > round(
                next(r["overlap"] for r in board if r["title"] == picked_title), 2
            )
        ),
    }


def inspect_song(prefs: dict, song: dict, notes: dict[str, str],
                 reasons: list[str] | None = None) -> dict:
    """Full glass-box record for a single recommended song.

    Bundles the three panels for one song: how it scored, what retrieval did,
    and the exact prompt the model would be handed. The prompt is built even in
    offline mode, because assembling it is pure and needs no key: a reviewer
    running without credentials should still see what retrieval feeds the model.
    """
    breakdown = score_breakdown(prefs, song)
    retrieval = retrieval_board(song, notes)

    # Use the caller's reasons when supplied (so the Inspector quotes the same
    # strings the run produced) and fall back to the freshly computed ones.
    reasons = reasons if reasons is not None else breakdown["reasons"]

    # A song with no retrieved note gets no prompt: there is nothing to ground
    # on, and the system falls back to a score-only explanation instead. Showing
    # a prompt here would misrepresent what the guardrail does.
    prompt = (
        build_explain_prompt(reasons, retrieval["picked_note"], prefs)
        if retrieval["grounded"]
        else None
    )

    # There are TWO distinct reasons a prompt can be withheld, and conflating
    # them would send a reader looking in the wrong place. Either nothing scored
    # above the confidence floor (an alien query), or something scored well but
    # was not this song's own note and the metadata filter rejected it (a corpus
    # gap). The second case can show a high confidence number, so reporting it as
    # a floor failure would be actively misleading.
    if retrieval["grounded"]:
        withheld = None
    elif retrieval["board"] and retrieval["board"][0]["above_floor"]:
        withheld = (
            f"the best match was '{retrieval['board'][0]['title']}' at "
            f"{retrieval['board'][0]['overlap']:.2f}, which is not this song's own "
            "note, so the metadata filter rejected it and the score-only fallback runs"
        )
    else:
        withheld = (
            "nothing cleared the confidence floor, so the score-only fallback "
            "runs and no prompt is built"
        )

    return {
        "breakdown": breakdown,
        "retrieval": retrieval,
        "prompt": prompt,
        "prompt_withheld_reason": withheld,
    }


def inspect_run(prefs: dict, songs: list[dict], notes: dict[str, str],
                k: int = 5) -> dict:
    """Glass-box record for a whole run: the ranking plus per-song detail.

    Read-only. Nothing here mutates the catalog, the notes, or any result, so
    inspecting a run cannot change what that run would have produced.
    """
    rows = rank_table(prefs, songs, k=k)
    ranked = recommend_songs(prefs, songs, k=k)

    return {
        "prefs": dict(prefs),
        "catalog_size": len(songs),
        "corpus_size": len(notes),
        "ranking": rows,
        "songs": [
            inspect_song(prefs, song, notes, reasons)
            for song, _score, reasons in ranked
        ],
    }

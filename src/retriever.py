"""VibeFinder retrieval layer -- the "R" in RAG.

This module is the retrieval half of VibeFinder's explanation feature. The
recommender (src/recommender.py) decides WHICH songs to suggest and in what order.
This retriever's only job is, for a song that was already chosen, to look up the
most relevant factual note about it from the local knowledge corpus in
data/song_notes.md. That retrieved note -- and nothing else -- is what the LLM
explainer (src/llm_client.py) is allowed to ground its wording on.

Why retrieval at all, when the notes are keyed by title?
    We could just do a dict lookup by title. Instead we score every note against a
    small query built from the song's own attributes (title, genre, mood) and
    return the best match with a confidence number. That does two useful things:
      1. It makes this a real, measurable retrieval step (a ranked similarity
         search) rather than an invisible lookup, which is the point of the RAG
         feature and gives us a confidence signal to log and test.
      2. It degrades gracefully: if a song has no good note (nothing clears the
         confidence floor), retrieve_note reports low confidence and the caller
         falls back to the rule-based reasons instead of letting the LLM invent
         facts. That fallback is the core guardrail of the whole feature.

The similarity metric is deliberately simple (token overlap). This is a small,
transparent project; embeddings would be gold plating at this catalog size (46).
"""

from __future__ import annotations

import os
import re

from src.config import DEFAULT_RETRIEVAL, RetrievalConfig, retrieval_or_default

# The retrieval knobs (the confidence floor, the stopword set, the exact-title
# tiebreak and the metadata filter) now live in RetrievalConfig in src/config.py,
# so they can be varied and MEASURED rather than only read. Every function below
# takes an optional config and falls back to DEFAULT_RETRIEVAL.
#
# These two module-level names are kept as aliases onto the defaults. They are
# not dead weight: the tests, src/glassbox.py and src/evaluate_retrieval.py all
# import MIN_CONFIDENCE by name, and it reads far better in an assertion than
# DEFAULT_RETRIEVAL.min_confidence does. Keeping the alias also means the config
# refactor did not touch a single existing import.
#
# A note must clear MIN_CONFIDENCE to count as a real match. Below it, the caller
# should NOT feed the note to the LLM -- it is treated as "no relevant note
# found" so the system falls back rather than grounding on a note that does not
# actually describe this song. Tuned so a song's own note (which shares its genre
# and mood words) clears it easily while an unrelated note does not.
MIN_CONFIDENCE = DEFAULT_RETRIEVAL.min_confidence

# Path to the corpus, resolved relative to this file so it works no matter what
# directory the program is launched from.
NOTES_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "song_notes.md")

# Very small stopword set. These words appear in almost every note ("a", "and",
# "the") so counting them would make every note look similar to every query and
# wash out the real signal (genre and mood words). Kept tiny on purpose.
_STOPWORDS = DEFAULT_RETRIEVAL.stopwords


def _tokenize(text: str, config: RetrievalConfig | None = None) -> set[str]:
    """Split text into a set of lowercased word tokens, stopwords removed.

    We return a SET (not a list) because the similarity below is overlap-based and
    only cares whether a word is present, not how many times. Non-letter/digit
    characters are treated as separators, so punctuation never sticks to a word.

    Stopword removal is a retrieval-quality decision, not a formatting detail, so
    it is a knob. config.active_stopwords() resolves the on/off flag and the word
    set together and returns an EMPTY set when filtering is disabled, which keeps
    this function down to a single code path: there is no `if filtering enabled`
    branch here that could drift from the one the config already made.
    """
    if not text:
        return set()
    stopwords = retrieval_or_default(config).active_stopwords()
    # \b word boundaries via findall of alphanumeric runs; lowercased for a
    # case-insensitive match against the (also lowercased) notes.
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w for w in words if w not in stopwords}


def load_notes(path: str = NOTES_PATH) -> dict[str, str]:
    """Parse data/song_notes.md into a {title: note_text} dictionary.

    Corpus format (see data/song_notes.md): each song's note starts with an H2
    header line `## <exact title>` followed by one or more lines of prose, until
    the next `## ` header or end of file. The top-of-file `# Song Notes` H1 and its
    intro paragraph sit before the first `## ` header and are therefore ignored.

    The returned dict is keyed by the title EXACTLY as written in the header (the
    same string as the song's `title` field in the catalog), so a caller can find
    a song's note directly, and retrieve_note can also search across all notes.

    Robustness: a missing corpus file raises FileNotFoundError (a broken install
    the caller should know about), but a malformed/empty section is simply skipped
    -- a header with no body just does not get added.
    """
    notes: dict[str, str] = {}
    current_title: str | None = None
    current_lines: list[str] = []

    def _flush() -> None:
        # Commit the note we have been accumulating, if it has a title and any
        # non-blank body. Defined as a closure so both the loop and the final
        # end-of-file flush use identical logic.
        if current_title is not None:
            body = "\n".join(current_lines).strip()
            if body:
                notes[current_title] = body

    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            # An H2 header opens a new song section. We flush the previous one
            # first so its accumulated body is saved before we switch titles.
            if line.startswith("## "):
                _flush()
                current_title = line[3:].strip()
                current_lines = []
            elif current_title is not None:
                # Body line of the current section (blank lines included; they are
                # trimmed by the .strip() in _flush).
                current_lines.append(line)
            # Lines before the first `## ` header (the H1 and intro) fall through
            # and are ignored, which is what we want.

    _flush()  # save the last section at end of file
    return notes


def _query_for_song(song: dict) -> str:
    """Build the retrieval query text for a song from its own attributes.

    We use title + genre + mood because those are the words most likely to also
    appear in the matching note, which is exactly what makes the song's own note
    win the similarity search. Energy/tempo are numbers, not words, so they do not
    help a token-overlap query and are left out.
    """
    parts = [
        str(song.get("title", "")),
        str(song.get("genre", "")),
        str(song.get("mood", "")),
    ]
    return " ".join(p for p in parts if p)


def _similarity(query_tokens: set[str], note_tokens: set[str]) -> float:
    """Overlap confidence in 0.0-1.0: shared tokens / query tokens.

    We divide by the number of QUERY tokens (not the union) so the score answers
    "how much of what I asked about is covered by this note," which stays high even
    though a note is longer than the query. Returns 0.0 for an empty query so an
    attribute-less song cannot divide by zero.
    """
    if not query_tokens:
        return 0.0
    shared = query_tokens & note_tokens
    return len(shared) / len(query_tokens)


def retrieve_note(song: dict, notes: dict[str, str],
                  config: RetrievalConfig | None = None) -> tuple[str | None, float, str | None]:
    """Retrieve the best-matching note for one song.

    Returns a 3-tuple `(note_text, confidence, matched_title)`:
      * note_text     -- the retrieved note, or None if nothing cleared the floor
      * confidence    -- the token-overlap similarity of the best match (0.0-1.0),
                         rounded to 2 decimals; useful to log and to test
      * matched_title -- the title of the note that won, or None on no match

    Algorithm: tokenize a query built from the song, score every note in the
    corpus by token overlap, and keep the highest. If the best score is below the
    confidence floor (or the corpus is empty), we return (None, best_score, None)
    so the caller treats it as "no relevant note" and falls back. Ties are broken
    by the corpus's iteration order, which is deterministic for a normal dict.

    `config` is optional and defaults to DEFAULT_RETRIEVAL, so the two-argument
    call every existing caller makes is unchanged. It controls four things, each
    marked at the line where it is read below: the stopword set, the confidence
    floor, whether the exact-title tiebreak applies, and whether the metadata
    filter applies. The RETURN CONTRACT does not vary with any of them: this is
    always a 3-tuple in the shape described above.
    """
    cfg = retrieval_or_default(config)
    query_tokens = _tokenize(_query_for_song(song), cfg)
    song_title = str(song.get("title", ""))

    best_title: str | None = None
    best_note: str | None = None
    best_conf = 0.0
    # Selection uses a two-part key: (exact-title-match, body-overlap). The exact
    # flag guarantees a song's OWN note wins even when a same-genre+mood sibling's
    # body scores higher on token overlap (e.g. Heavy Riff vs Concrete Anthem, both
    # rock/intense, where Concrete Anthem's note contains the word "heavy"). The
    # body-overlap alone would mis-retrieve there; the exact flag fixes it WITHOUT
    # saturating the confidence -- we still report the body overlap as the
    # confidence, so it stays a varied, meaningful signal rather than always 1.0.
    best_key = (0, 0.0)

    for title, note in notes.items():
        body_overlap = _similarity(query_tokens, _tokenize(note, cfg))
        # KNOB: the exact-title tiebreak. Pinning `exact` to 0 for every note
        # collapses the two-part key to plain overlap order, which is what a
        # pure lexical retriever would do. Expressed as a zeroed flag rather than
        # as a second sort path so both settings run the identical loop and the
        # only difference between them is the one value being measured.
        exact = 1 if (cfg.use_exact_title_tiebreak and title == song_title) else 0
        key = (exact, body_overlap)
        if key > best_key:
            best_key = key
            best_conf = body_overlap
            best_title = title
            best_note = note

    best_conf = round(best_conf, 2)
    # Enforce the confidence floor: below it we report NO usable note (the caller
    # will fall back), but we still return the score we saw so it can be logged.
    # An off-catalog song has no exact-title match and typically low body overlap,
    # so it falls here to the guardrail path.
    # KNOB: the confidence floor.
    if best_note is None or best_conf < cfg.min_confidence:
        return (None, best_conf, None)

    # METADATA FILTER. Similarity finds candidates; IDENTITY decides eligibility.
    #
    # This exists because measurement showed the floor could not do this job.
    # With a song's own note deleted, all 46 catalog songs still retrieved a
    # sibling's note at 0.60 to 0.80, because sibling notes share genre and mood
    # vocabulary. A confidence threshold cannot separate those cases: correct
    # retrievals span margins of 0.00 to 0.50 and wrong ones 0.00 to 0.40, so 44
    # of 46 correct cases sit inside the wrong-case range. There is no cutoff.
    # See src/evaluate_retrieval.py, which produces those numbers.
    #
    # The reason no threshold works is that a similarity score answers "is this
    # note similar" when the question is "is this note ABOUT this song". Those
    # are different questions, and the corpus already answers the second one: it
    # is keyed one note per song, so correctness IS title identity.
    #
    # So we filter on metadata rather than on the score, which is what a
    # production vector store does when it constrains retrieved candidates by
    # tenant, permission, or date. The ranked search above still does real work:
    # it produces the confidence number, and the full board that
    # score_all_notes exposes to the Inspector. It just no longer gets the final
    # say on whether a note is allowed to ground an explanation.
    #
    # Practical effect: with a complete corpus, none. Every song has its own
    # note, so this filter never fires and output is unchanged. It matters when
    # someone adds a row to songs.csv and forgets to write its note, which
    # previously produced a confident explanation built from a DIFFERENT song's
    # facts. Now that song falls back to a score-only reason, which is the
    # honest answer.
    #
    # KNOB, AND THE ONE KNOB THAT IS A FAULT INJECTION. cfg.use_metadata_filter
    # defaults to True and should stay True in any real use. Setting it False
    # does not "relax" this guardrail, it removes it, restoring the exact bug
    # described above. It is configurable only so that failure can be
    # demonstrated and MEASURED on demand (evaluate_retrieval's leave-one-out
    # count goes from zero leaks to the whole catalog) instead of being taken on
    # trust from this comment. Anything that exposes this to a user is required
    # to label it as a deliberate break-it switch, not as a normal setting.
    if cfg.use_metadata_filter and best_title != song_title:
        return (None, best_conf, None)

    return (best_note, best_conf, best_title)


def missing_notes(songs: list[dict], notes: dict[str, str]) -> list[str]:
    """Catalog songs that have no note of their own, in catalog order.

    The corpus is the retrieval system's entire knowledge, so a gap in it is a
    data problem, not a model problem. Callers use this at load time to say so
    out loud: a missing note is almost always an oversight (a song added to the
    CSV without a corresponding entry in song_notes.md), and it silently costs
    that song its grounded explanation.

    Kept separate from retrieval so it can be reported once at startup rather
    than discovered one song at a time, and so a caller can decide for itself
    whether a gap is a warning or a hard error.
    """
    return [s["title"] for s in songs if s.get("title") not in notes]


def score_all_notes(song: dict, notes: dict[str, str],
                    config: RetrievalConfig | None = None) -> list[dict]:
    """Score EVERY note against one song and return the whole ranked board.

    This is the observability twin of retrieve_note. retrieve_note answers "which
    note won"; this answers "what did the competition look like", which is what
    the glass-box Inspector displays. It is deliberately ADDITIVE: retrieve_note
    is untouched by this function and remains the single decision-maker, so the
    tests and documented claims resting on it cannot be disturbed by anything
    here. A test pins the two against each other so this board can never
    disagree with the pick the system actually made.

    Each entry is a dict with:
        title        -- the note's title
        overlap      -- token-overlap similarity, 0.0-1.0, rounded to 2dp, the
                        same number retrieve_note reports as `confidence`
        exact        -- True when the note's title equals the song's title, i.e.
                        this note wins the exact-title tiebreak. Reported as a
                        FACT about the titles, not as a prediction: it stays True
                        even when config.use_exact_title_tiebreak is off, because
                        the Inspector's job there is to show that an exact match
                        existed and was not acted on.
        above_floor  -- whether overlap clears config.min_confidence

    `config` is optional and defaults to DEFAULT_RETRIEVAL. It affects the
    tokenization (via the stopword knob) and the above_floor column (via the
    confidence floor), so a board rendered under a given config matches the
    decision retrieve_note makes under that same config.

    Ordering is by OVERLAP alone, descending. That is deliberate and is the whole
    point of the display: sorting by overlap shows what a pure token-overlap
    retriever would have returned, so when the exact-title tiebreak picks a
    different note the disagreement becomes visible instead of being silently
    resolved. Ties are broken by title so the order is stable across runs.
    """
    cfg = retrieval_or_default(config)
    query_tokens = _tokenize(_query_for_song(song), cfg)
    song_title = str(song.get("title", ""))

    board: list[dict] = []
    for title, note in notes.items():
        # Round ONCE and reuse, the same discipline score_song uses for its
        # energy term: computing the similarity twice invites the displayed
        # number and the floor comparison to disagree in the last decimal.
        overlap = round(_similarity(query_tokens, _tokenize(note, cfg)), 2)
        board.append({
            "title": title,
            "overlap": overlap,
            "exact": title == song_title,
            "above_floor": overlap >= cfg.min_confidence,
        })

    # Negate the score for a descending sort while keeping the title ascending,
    # which gives a deterministic total order without two separate sort passes.
    board.sort(key=lambda row: (-row["overlap"], row["title"]))
    return board

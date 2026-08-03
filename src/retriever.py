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
transparent project; embeddings would be gold plating for a 20-song catalog.
"""

from __future__ import annotations

import os
import re

# A note must clear this token-overlap confidence to count as a real match. Below
# it, the caller should NOT feed the note to the LLM -- it is treated as "no
# relevant note found" so the system falls back rather than grounding on a note
# that does not actually describe this song. Tuned so a song's own note (which
# shares its genre and mood words) clears it easily while an unrelated note does
# not. Exposed as a module constant so a test can pin it.
MIN_CONFIDENCE = 0.15

# Path to the corpus, resolved relative to this file so it works no matter what
# directory the program is launched from.
NOTES_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "song_notes.md")

# Very small stopword set. These words appear in almost every note ("a", "and",
# "the") so counting them would make every note look similar to every query and
# wash out the real signal (genre and mood words). Kept tiny on purpose.
_STOPWORDS = {
    "a", "an", "and", "the", "of", "to", "for", "it", "is", "at", "or", "on",
    "in", "by", "with", "without", "so", "as", "not", "this", "that",
}


def _tokenize(text: str) -> set[str]:
    """Split text into a set of lowercased word tokens, stopwords removed.

    We return a SET (not a list) because the similarity below is overlap-based and
    only cares whether a word is present, not how many times. Non-letter/digit
    characters are treated as separators, so punctuation never sticks to a word.
    """
    if not text:
        return set()
    # \b word boundaries via findall of alphanumeric runs; lowercased for a
    # case-insensitive match against the (also lowercased) notes.
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w for w in words if w not in _STOPWORDS}


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


def retrieve_note(song: dict, notes: dict[str, str]) -> tuple[str | None, float, str | None]:
    """Retrieve the best-matching note for one song.

    Returns a 3-tuple `(note_text, confidence, matched_title)`:
      * note_text     -- the retrieved note, or None if nothing cleared the floor
      * confidence    -- the token-overlap similarity of the best match (0.0-1.0),
                         rounded to 2 decimals; useful to log and to test
      * matched_title -- the title of the note that won, or None on no match

    Algorithm: tokenize a query built from the song, score every note in the
    corpus by token overlap, and keep the highest. If the best score is below
    MIN_CONFIDENCE (or the corpus is empty), we return (None, best_score, None) so
    the caller treats it as "no relevant note" and falls back. Ties are broken by
    the corpus's iteration order, which is deterministic for a normal dict.
    """
    query_tokens = _tokenize(_query_for_song(song))

    best_title: str | None = None
    best_note: str | None = None
    best_score = 0.0

    for title, note in notes.items():
        score = _similarity(query_tokens, _tokenize(note))
        if score > best_score:
            best_score = score
            best_title = title
            best_note = note

    best_score = round(best_score, 2)
    # Enforce the confidence floor: below it we report NO usable note (the caller
    # will fall back), but we still return the score we saw so it can be logged.
    if best_note is None or best_score < MIN_CONFIDENCE:
        return (None, best_score, None)
    return (best_note, best_score, best_title)

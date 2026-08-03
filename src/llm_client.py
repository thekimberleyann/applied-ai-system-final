"""VibeFinder LLM client -- the "AG" (augmented generation) in RAG.

Given a song, its deterministic score/reasons, and the factual note retrieved for
it (src/retriever.py), this client produces the short natural-language "why this
fits you" explanation shown to the user. It has two modes:

  * OFFLINE STUB (the default): a deterministic, template-based explanation built
    only from the retrieved note and the score reasons. No network, no API key, no
    external package. This is what makes VibeFinder reproducible -- `python -m
    src.main` and the whole test suite run identically on any machine, and a grader
    never needs a key. The wording is fixed, so tests can assert on it exactly.

  * LIVE (opt-in): if the GEMINI_API_KEY environment variable is set, the client
    calls Google's Gemini to phrase the explanation. It reuses the same client
    pattern as the Module 4 DocuBot project. The prompt hard-constrains the model
    to the retrieved note only and forbids inventing facts.

Design rule enforced everywhere in this file: the LLM EXPLAINS, it never RANKS.
Nothing here can change which songs were chosen or their order -- the score from
recommender.py is passed in already decided and is only ever read, never altered.
That separation is the feature's central reliability guarantee.
"""

from __future__ import annotations

import os
import re
import textwrap

# Central model pin, mirroring DocuBot. Only consulted in live mode; the offline
# stub ignores it entirely. gemini-flash-latest tracks Google's current flash
# model so it will not retire out from under this project.
GEMINI_MODEL_NAME = "gemini-flash-latest"


class VibeExplainer:
    """Turns a chosen song + its retrieved note into a grounded explanation.

    Usage:
        client = VibeExplainer()          # offline stub unless GEMINI_API_KEY set
        text = client.explain(song, score, reasons, note, prefs)

    The constructor NEVER raises on a missing key: absence of a key is the normal,
    reproducible path (offline stub), not an error. `self.mode` is "live" or
    "offline" so callers and logs can report which path ran.
    """

    def __init__(self, force_offline: bool = False):
        # force_offline lets tests pin the deterministic path even on a machine
        # that happens to have a key in its environment.
        api_key = os.getenv("GEMINI_API_KEY")
        if force_offline or not api_key:
            self.mode = "offline"
            self._client = None
            return

        # Live mode. Import google-genai LAZILY, only here, so the package is NOT a
        # requirement for the default offline path -- importing it at module top
        # would break `import src.llm_client` on any machine without it installed.
        try:
            from google import genai  # type: ignore

            self._client = genai.Client(api_key=api_key)
            self.mode = "live"
        except Exception:
            # google-genai not installed, or client construction failed. Fall back
            # to the offline stub rather than crashing -- the system still works,
            # just deterministically. (Construction makes no network call, so a
            # bad key is not detected here; that surfaces at the first call.)
            self._client = None
            self.mode = "offline"

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def explain(
        self,
        song: dict,
        score: float,
        reasons: list[str],
        note: str | None,
        prefs: dict,
    ) -> str:
        """Return a one-paragraph grounded explanation for a single recommendation.

        `note` is the text retrieved for this song, or None when retrieval found
        nothing relevant. When it is None we DO NOT call the LLM at all: with no
        grounding text there is nothing to be faithful to, so we return a plain
        fallback built from the deterministic reasons. This is the guardrail that
        stops the model from inventing details about a song it has no note for.
        """
        if not note:
            return self._fallback(song, reasons)

        if self.mode == "live":
            return self._explain_live(song, score, reasons, note, prefs)
        return self._explain_offline(song, reasons, note)

    # ------------------------------------------------------------------
    # Offline deterministic stub
    # ------------------------------------------------------------------

    def _explain_offline(self, song: dict, reasons: list[str], note: str) -> str:
        """Deterministic explanation: the note's first sentence + why it matched.

        Grounding: the descriptive clause is taken verbatim from the retrieved
        note (its first sentence), so the stub can only say what the corpus says.
        The match clause is derived from `reasons`, which come straight from the
        deterministic score. Nothing is invented, and the output is byte-for-byte
        stable for a given (note, reasons), which is what the tests assert on.
        """
        first_sentence = self._first_sentence(note)
        match_clause = self._match_clause(reasons)
        title = song.get("title", "This song")
        return f"{title}: {first_sentence}. {match_clause}"

    @staticmethod
    def _first_sentence(note: str) -> str:
        """Return the note's first sentence, without splitting on decimal points.

        A naive note.split('.')[0] truncates 'high energy at 0.85 ...' at '0'
        because the decimal point looks like a sentence end. We instead match up to
        the first period that is followed by whitespace or end-of-string, so a
        period inside a number (no following space) is not treated as a boundary.
        """
        text = note.strip()
        m = re.match(r".*?[.](?=\s|$)", text, re.S)
        # Strip the trailing period so the caller can add its own '. '.
        return (m.group(0).rstrip(".").strip() if m else text.rstrip("."))

    # ------------------------------------------------------------------
    # Live Gemini path
    # ------------------------------------------------------------------

    def _explain_live(
        self,
        song: dict,
        score: float,
        reasons: list[str],
        note: str,
        prefs: dict,
    ) -> str:
        """Ask Gemini to phrase the explanation, grounded ONLY in the note.

        The prompt hands the model exactly three things -- the retrieved note, the
        listener's stated preferences, and the deterministic match reasons -- and
        forbids it from adding any fact not in the note. On any API error we return
        the same deterministic fallback used elsewhere, so a live failure never
        crashes the run or blocks a recommendation.
        """
        prompt = textwrap.dedent(
            f"""
            You explain, in two sentences, why a song was recommended to a listener.

            The listener's taste profile:
              favorite genre: {prefs.get('favorite_genre')}
              favorite mood:  {prefs.get('favorite_mood')}
              target energy:  {prefs.get('target_energy')}

            The only facts you may use about the song are in this note:
            \"\"\"{note}\"\"\"

            Why our recommender matched it (already decided, do not re-rank):
            {', '.join(reasons)}

            Rules:
            - Use ONLY facts stated in the note. Do not invent artists, awards,
              lyrics, chart positions, or anything not written above.
            - Do not claim the song is objectively good; frame it as a fit for THIS
              listener's stated taste.
            - Keep it to two sentences, plain and warm.
            """
        ).strip()

        try:
            response = self._client.models.generate_content(
                model=GEMINI_MODEL_NAME,
                contents=prompt,
            )
            text = (response.text or "").strip()
            # An empty model response is itself a failure to explain; fall back
            # rather than returning a blank line.
            return text or self._fallback(song, reasons)
        except Exception as e:
            # Network/quota/model errors degrade to the deterministic fallback,
            # tagged so it is visible in output/logs that live generation failed.
            return (
                self._fallback(song, reasons)
                + f"  (live explanation unavailable: {type(e).__name__})"
            )

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _match_clause(reasons: list[str]) -> str:
        """Turn the raw reason strings into a short 'why it matched' sentence.

        Reads the deterministic reasons (e.g. 'genre match (+2.0)') and names the
        dimensions that fired. The energy reason is always present, so we always
        have at least one dimension to report.
        """
        hits = []
        for r in reasons:
            if r.startswith("genre match"):
                hits.append("your favorite genre")
            elif r.startswith("mood match"):
                hits.append("the mood you asked for")
            elif r.startswith("energy close"):
                hits.append("your target energy")
        if not hits:
            return "It surfaced on the energy match alone."
        if len(hits) == 1:
            return f"It matched on {hits[0]}."
        return "It matched on " + ", ".join(hits[:-1]) + f", and {hits[-1]}."

    @staticmethod
    def _fallback(song: dict, reasons: list[str]) -> str:
        """Plain, note-free explanation used when there is no grounding text.

        Built only from the deterministic reasons so it is always safe: it can only
        restate why the score chose the song, never describe the song itself.
        """
        title = song.get("title", "This song")
        return f"{title}: recommended on the score alone ({'; '.join(reasons)})."

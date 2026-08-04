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


def build_explain_prompt(reasons: list[str], note: str, prefs: dict) -> str:
    """Assemble the single-song explanation prompt. Pure: no I/O, no API call.

    Lifted out of the live explainer so the glass-box Inspector can DISPLAY the
    prompt without a key and without spending a request. Building the string has
    no side effects, so the panel that demonstrates what retrieval actually does
    (it pastes the retrieved text into the prompt for you) stays visible in the
    default offline configuration, which is the one every reviewer runs.

    The prompt hands the model exactly three things: the retrieved note, the
    listener's stated preferences, and the deterministic match reasons. It then
    forbids any fact not present in the note. Note what is NOT here: the score's
    authority. The reasons are labelled as already decided precisely so the model
    treats the ranking as fixed input rather than something to re-litigate.
    """
    return textwrap.dedent(
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

        Two traps a naive note.split('.')[0] falls into, both handled here:
          * decimals: 'high energy at 0.85' would truncate at '0'. We only treat a
            period as a boundary when whitespace or end-of-string follows it, so a
            period inside a number (followed by a digit) is never a boundary.
          * initials: 'the A. Keys Trio' would truncate at 'A'. We skip any period
            whose preceding token is a single uppercase letter (an initial) and
            take the next real sentence end instead.
        """
        text = note.strip()
        for m in re.finditer(r"[.](?=\s|$)", text):
            preceding = re.search(r"(\S+)$", text[: m.start()])
            token = preceding.group(1) if preceding else ""
            if len(token) == 1 and token.isalpha() and token.isupper():
                # A single-letter initial (e.g. "A." in "A. Keys Trio"); not a
                # sentence end -- keep scanning for the next boundary.
                continue
            return text[: m.start()].strip()
        # No usable boundary found: return the whole note, trailing period removed.
        return text.rstrip(".")

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
        prompt = build_explain_prompt(reasons, note, prefs)

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
            # Network/quota/model errors degrade gracefully. Because we have the
            # retrieved note here, we fall back to the GROUNDED offline stub (not the
            # bare score-only line) and tag it so the reason is visible -- and the tag
            # names a rate limit explicitly when that is what happened.
            return self._explain_offline(song, reasons, note) + f"  ({self._short_tag(e)})"

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

    # ------------------------------------------------------------------
    # Error classification (so the UI can tell the user WHY live failed)
    # ------------------------------------------------------------------

    @staticmethod
    def _is_rate_limit(e: Exception) -> bool:
        """True when an exception looks like a quota / rate-limit (HTTP 429)."""
        msg = str(e).lower()
        return ("429" in msg or "resource_exhausted" in msg
                or "quota" in msg or "rate limit" in msg)

    @staticmethod
    def _short_tag(e: Exception) -> str:
        """Short inline tag appended to a single fallback explanation."""
        if VibeExplainer._is_rate_limit(e):
            return "live rate limit reached; showing offline explanation"
        return f"live unavailable: {type(e).__name__}"

    @staticmethod
    def _status_message(e: Exception) -> str:
        """One-line human status the UI can show as a banner when live fell back."""
        if VibeExplainer._is_rate_limit(e):
            return ("Live AI phrasing hit the Gemini free-tier rate limit (about 20 "
                    "requests per minute). Showing the offline explanations instead; "
                    "try again in a minute, or use fewer songs.")
        return (f"Live AI phrasing was unavailable ({type(e).__name__}). Showing the "
                "offline explanations instead.")

    # ------------------------------------------------------------------
    # Batched explanation: one API call for a whole result list
    # ------------------------------------------------------------------

    def explain_batch(self, items: list[dict], prefs: dict) -> tuple[list[str], str | None]:
        """Explain a whole result list, returning (explanations, status).

        `items` is a list of dicts, each with keys: song, score, reasons, note.
        Explanations are returned aligned to `items`. `status` is None on success, or
        a one-line human message when LIVE phrasing failed (e.g. rate limit) and we
        fell back to the offline explanations.

        Why batch: in live mode this sends ONE API call for the whole list instead of
        one call per song, which keeps a multi-song query well under the free-tier
        rate limit. Songs with no retrieved note never go to the model (the guardrail):
        they get the score-only fallback directly.
        """
        explanations: list[str | None] = [None] * len(items)

        # No-note songs: score-only fallback, never sent to the model.
        for i, it in enumerate(items):
            if not it.get("note"):
                explanations[i] = self._fallback(it["song"], it["reasons"])
        grounded = [i for i, it in enumerate(items) if it.get("note")]

        # Offline (or nothing to ground): deterministic stub per grounded song.
        if self.mode != "live" or not grounded:
            for i in grounded:
                it = items[i]
                explanations[i] = self._explain_offline(
                    it["song"], it["reasons"], it["note"])
            return [e for e in explanations], None  # type: ignore

        # Live: a single call for all grounded songs.
        try:
            text = self._batch_live_call(grounded, items, prefs)
            parsed = self._parse_numbered(text, len(grounded))
            for n, i in enumerate(grounded):
                it = items[i]
                # If the model skipped an item, fall back to its offline stub.
                explanations[i] = parsed[n] or self._explain_offline(
                    it["song"], it["reasons"], it["note"])
            return [e for e in explanations], None  # type: ignore
        except Exception as e:
            # Whole-batch failure (e.g. rate limit): grounded offline stubs for all,
            # plus a single status message the UI shows once.
            for i in grounded:
                it = items[i]
                explanations[i] = self._explain_offline(
                    it["song"], it["reasons"], it["note"])
            return [e for e in explanations], self._status_message(e)  # type: ignore

    def _batch_live_call(self, grounded: list[int], items: list[dict], prefs: dict) -> str:
        """Build one prompt covering every grounded song and call Gemini once.

        The numbers 1..len(grounded) in the prompt are positions within the
        GROUNDED subset, not positions in `items`. `grounded` holds the original
        indices, so explain_batch maps each parsed entry back with
        `grounded[n]`. A no-note song is absent from the prompt entirely, which
        is the guardrail: the model is never shown a song it has no facts for.
        """
        blocks = []
        for n, i in enumerate(grounded, start=1):
            it = items[i]
            blocks.append(
                f'{n}. "{it["song"].get("title", "")}"\n'
                f'   note: """{it["note"]}"""\n'
                f'   why our recommender matched it: {", ".join(it["reasons"])}'
            )
        songs_block = "\n\n".join(blocks)

        prompt = textwrap.dedent(
            f"""
            You explain, in two sentences each, why several songs were recommended to
            a listener.

            The listener's taste profile:
              favorite genre: {prefs.get('favorite_genre')}
              favorite mood:  {prefs.get('favorite_mood')}
              target energy:  {prefs.get('target_energy')}

            Rules:
            - For each song, use ONLY the facts in that song's note. Do not invent
              artists, awards, lyrics, chart positions, or anything not in the note.
            - Frame it as a fit for THIS listener's stated taste, not as objectively good.
            - Two sentences per song, plain and warm.

            Return a numbered list with EXACTLY one entry per song, matching the numbers
            below, in this format:
            1. <explanation for song 1>
            2. <explanation for song 2>

            Songs:
            {songs_block}
            """
        ).strip()

        response = self._client.models.generate_content(
            model=GEMINI_MODEL_NAME, contents=prompt)
        text = (response.text or "").strip()
        if not text:
            raise RuntimeError("empty response from model")
        return text

    @staticmethod
    def _parse_numbered(text: str, n: int) -> list[str | None]:
        """Parse a numbered list into a list of n explanations (None if missing).

        Matches entries that begin a line with 'N.' and captures everything up to the
        next numbered entry, so a two-sentence explanation spanning lines is kept whole.

        The entry is placed by the number the MODEL wrote, not by match order, so a
        response that renumbers or omits an entry cannot shift the others out of
        alignment; the range check discards any number outside 1..n. Slots the model
        never produced stay None, which is why explain_batch treats None as "fall
        back to the offline stub for this song".
        """
        result: list[str | None] = [None] * n
        # re.S makes `.` span newlines so a multi-line entry is captured whole; the
        # lookahead stops the capture at the next 'N.' line or end of text, and the
        # non-greedy `+?` keeps it from swallowing the rest of the response.
        for m in re.finditer(r"(?m)^\s*(\d+)\.\s*(.+?)(?=\n\s*\d+\.\s|\Z)", text, re.S):
            idx = int(m.group(1)) - 1
            if 0 <= idx < n:
                result[idx] = " ".join(m.group(2).split())
        return result

"""Every tunable knob in VibeFinder, in one file.

WHY THIS EXISTS
    Before this module the system's parameters were scattered and, worse, most
    of them were not parameters at all. The scoring weights were three numeric
    literals buried in the body of score_song. The stopword list, the confidence
    floor, the exact-title tiebreak and the metadata filter were each a fixed
    decision expressed as code. Every one of those is a CHOICE that the project's
    documentation defends with measurements, and a choice you cannot vary is a
    choice you cannot check. Someone who forks this repo should be able to move a
    knob and watch hit@1 move, rather than take the write-up's word for it.

    So the knobs live here, as two frozen dataclasses with documented defaults,
    and every function that consumes one takes it as an OPTIONAL argument that
    falls back to the module-level default. That shape matters: it means nothing
    downstream had to change, existing call sites still work untouched, and the
    default path through the system is byte-for-byte what it was before.

THE ONE RULE
    The defaults in this file ARE the graded system. README.md, DESIGN.md,
    EVALUATION.md and model_card.md all describe the behavior these exact values
    produce. Changing a default here silently invalidates those documents, so
    treat the default values as pinned (a test in tests/test_config.py pins them
    explicitly) and express experiments by constructing a NEW config instead.

    The Streamlit Inspector honors that rule too: its controls build a throwaway
    config for one render and never write back here or to disk.

WHY TWO DATACLASSES AND NOT ONE
    Scoring and retrieval are separate subsystems that happen to sit in the same
    pipeline. The recommender ranks songs and has never known that a retriever
    exists; the retriever explains songs that were already chosen and has no say
    in the ranking. Keeping their knobs in two objects preserves that separation
    at the type level: you cannot accidentally hand score_song something that
    changes retrieval, which is the same boundary the whole project's "the model
    phrases, it never judges" guardrail rests on.

WHY FROZEN
    frozen=True makes these immutable and hashable. Immutable because a config
    is passed down through several layers (app -> glassbox -> recommender and
    retriever) and a mutable one could be edited mid-run by any of them, which
    would make a reported number and the number actually used disagree. Hashable
    because Streamlit's st.cache_data keys on its arguments, so a hashable config
    can safely become part of a cache key later without a custom hash function.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

# The stopword set the shipped system uses. Defined at module level rather than
# inline in the dataclass because a mutable default (a set) cannot be a dataclass
# default at all, and because naming it lets a caller build a variant from it
# (DEFAULT_STOPWORDS | {"remix"}) without retyping the list.
#
# frozenset, not set: the dataclass is frozen and hashable, and a plain set is
# neither, so a set here would break hashing the moment anything tried to cache
# on a config.
#
# Kept deliberately tiny. These words appear in nearly every note ("a", "and",
# "the"), so counting them makes every note look similar to every query and
# washes out the signal that actually discriminates (genre and mood words).
DEFAULT_STOPWORDS = frozenset({
    "a", "an", "and", "the", "of", "to", "for", "it", "is", "at", "or", "on",
    "in", "by", "with", "without", "so", "as", "not", "this", "that",
})


@dataclass(frozen=True)
class ScoringConfig:
    """Weights for the recommender's three-term scoring recipe.

    The recipe is score = genre_weight*genre_hit + mood_weight*mood_hit +
    energy_weight*closeness, where closeness is max(0, 1 - |song - target|).

    THE SCALE MOVES WITH THE WEIGHTS, AND THAT IS NOT A BUG
        The documented 0.0 to 4.0 score scale is not a normalization applied
        anywhere in the code. It is simply what 2.0 + 1.0 + 1.0 adds up to. Set
        genre_weight to 5.0 and the maximum becomes 7.0; every score printed,
        every threshold a reader has memorized, and every figure in the write-up
        is now on a different scale.

        We deliberately do NOT renormalize back to 4.0. Renormalizing would hide
        the very thing the knob is for: seeing that weighting genre more heavily
        pushes genre matches up the ranking. A rescaled score would make a
        doubled genre weight look like it changed nothing. The honest answer is
        that the scale is a consequence of the weights, so it is stated here and
        the Inspector shows the live maximum alongside the scores.

        A test pins that the DEFAULTS still top out at exactly 4.00, so the
        documented scale cannot drift by accident.

    THE SUM GUARANTEE SURVIVES ANY WEIGHTING
        score_song promises that the numbers inside its reason strings add up to
        exactly the score it returns. That promise is weight-independent: the
        genre and mood terms print the exact float they contribute, and the
        energy term is rounded ONCE (after the weight is applied) and that single
        rounded value is both added and printed. See score_song's docstring.

    Attributes:
        genre_weight:  added when the song's genre equals the user's favorite.
                       Default 2.0, the largest term, because genre is the
                       coarsest and most reliable taste signal in the catalog.
        mood_weight:   added when the song's mood matches. Default 1.0, half of
                       genre, because mood labels are more subjective.
        energy_weight: multiplies the 0.0-1.0 energy closeness. Default 1.0. This
                       is the only continuous term, which is what makes it the
                       natural tiebreaker between songs matching on both labels.
    """

    genre_weight: float = 2.0
    mood_weight: float = 1.0
    energy_weight: float = 1.0

    @property
    def max_score(self) -> float:
        """The best score any song can reach under these weights.

        Reported rather than enforced. The Inspector shows it so a user who has
        moved a weight can see immediately that 4.00 is no longer the ceiling,
        instead of comparing new scores against a remembered old scale.
        """
        return self.genre_weight + self.mood_weight + self.energy_weight


@dataclass(frozen=True)
class RetrievalConfig:
    """Knobs for the retrieval half of the RAG explanation layer.

    Four of these five are ordinary settings. The fifth (use_metadata_filter) is
    a deliberate break-it switch and is documented as such below.

    Attributes:
        min_confidence:
            Token-overlap floor a note must clear to count as a real match.
            Default 0.15. Below it the caller is told "no usable note" and falls
            back to score-only reasons rather than letting the model phrase
            around a note that does not describe this song. Measurement (see
            src/evaluate_retrieval.py) puts the lowest CORRECT retrieval on the
            shipped corpus at 0.25, so 0.15 leaves real but modest headroom.
            Raise it past 0.25 and correct retrievals start being rejected, which
            is exactly what the comparison table in evaluate_retrieval shows.

        use_exact_title_tiebreak:
            Default True. Retrieval selects on a two-part key,
            (exact-title-match, body-overlap), so a song's own note wins even
            when a same-genre sibling's note scores higher on raw token overlap.
            Turn it off to see what pure lexical retrieval does on its own
            merits: hit@1 and MRR both fall, which is the measurement that
            justifies the tiebreak existing at all.

        use_metadata_filter:
            Default True. THIS IS A BREAK-IT SWITCH, NOT A SETTING. It gates the
            identity check that rejects a note whose title is not this song's
            title. With a complete corpus it never fires and changes nothing.
            Turning it OFF reproduces a real, fixed bug: a song with no note of
            its own gets confidently explained using a DIFFERENT song's facts, at
            high reported confidence and with no warning. Leave-one-out goes from
            0 leaks to every song in the catalog leaking. It is exposed only so
            that failure can be demonstrated on demand rather than described, and
            anything that surfaces it to a user must label it as a fault
            injection.

        use_stopwords:
            Default True. When False, tokenization keeps every word including
            "a", "and", "the". Common words then inflate the overlap between a
            query and every long note, so the ranking flattens and the metrics
            move. This is the cheapest demonstration in the project that a
            preprocessing choice is a retrieval-quality choice.

        stopwords:
            The set used when use_stopwords is True. Defaults to
            DEFAULT_STOPWORDS. Separate from the on/off flag so a caller can
            swap the vocabulary without losing the ability to disable filtering
            entirely, and so turning filtering off and back on cannot lose the
            custom list.
    """

    min_confidence: float = 0.15
    use_exact_title_tiebreak: bool = True
    use_metadata_filter: bool = True
    use_stopwords: bool = True
    # default_factory rather than a bare default so the frozenset is built per
    # instance; frozensets are immutable so sharing would be safe here, but the
    # factory keeps the pattern correct if this ever becomes a mutable type.
    stopwords: frozenset[str] = field(default_factory=lambda: DEFAULT_STOPWORDS)

    def active_stopwords(self) -> frozenset[str]:
        """The stopword set actually applied, honoring the on/off flag.

        Exists so the caller (retriever._tokenize) never has to remember to check
        the flag and the set separately. Filtering disabled is expressed as an
        empty set, which makes the tokenizer's inner loop identical in both
        cases: one code path, no branch that could drift.
        """
        return self.stopwords if self.use_stopwords else frozenset()


# The module-level defaults every function falls back to when handed no config.
#
# These two objects are what "default behavior" means throughout this project.
# Nothing in the codebase mutates them (they are frozen, so nothing can), and
# nothing writes them to disk. The Streamlit UI builds a fresh config per render
# and discards it; it never touches these.
DEFAULT_SCORING = ScoringConfig()
DEFAULT_RETRIEVAL = RetrievalConfig()


def scoring_or_default(config: ScoringConfig | None) -> ScoringConfig:
    """Resolve an optional scoring config to a concrete one.

    A one-line helper repeated in several modules otherwise. Having it named in
    one place means the "None means defaults" contract is defined once rather
    than re-implemented at each call site, where one of them would eventually get
    it subtly wrong (an `or` instead of an `is None`, say, which would silently
    replace a legitimately falsy config).
    """
    return DEFAULT_SCORING if config is None else config


def retrieval_or_default(config: RetrievalConfig | None) -> RetrievalConfig:
    """Resolve an optional retrieval config to a concrete one."""
    return DEFAULT_RETRIEVAL if config is None else config


def describe(config: ScoringConfig | RetrievalConfig) -> str:
    """One-line summary naming only what DIFFERS from the defaults.

    Used by the Inspector and by evaluate_retrieval's comparison table. Printing
    every field would bury the one value that was changed among six that were
    not, and the interesting question is always "what is different about this
    run", never "what is this run".
    """
    baseline = DEFAULT_SCORING if isinstance(config, ScoringConfig) else DEFAULT_RETRIEVAL

    changes = []
    for name in config.__dataclass_fields__:
        current, original = getattr(config, name), getattr(baseline, name)
        if current != original:
            # Stopword sets print as a size, not as 21 words on one line.
            if isinstance(current, frozenset):
                changes.append(f"{name}={len(current)} words")
            else:
                changes.append(f"{name}={current}")

    return ", ".join(changes) if changes else "defaults"


def reset_to_defaults() -> tuple[ScoringConfig, RetrievalConfig]:
    """Fresh copies of both default configs, for a UI "reset" control.

    Returns new instances rather than the module-level singletons. The objects
    are frozen so handing back the singletons would be harmless today, but a
    reset that returns the shared default invites a future caller to store it
    somewhere that expects to own its config, and this costs nothing.
    """
    return (replace(DEFAULT_SCORING), replace(DEFAULT_RETRIEVAL))

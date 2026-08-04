# VibeFinder Evaluation Notes

This document holds the evaluation material that used to sit at the bottom of the
README: the biases predicted from the scoring recipe and from the catalog (including
the original 20-song versus expanded 46-song catalog history), and the full inventory
of what the automated test suite covers. The README keeps the short Testing Summary;
this is the section-by-section detail behind it. The project overview, setup and run
instructions, and the reliability evidence stay in [README.md](README.md); the scoring
recipe these biases follow from is walked through in [DESIGN.md](DESIGN.md).

---

### Expected Biases

Bias can enter from two places: the scoring rule itself, and the songs we chose
to score. The four biases below are predictions we make from the design and the
catalog, stated up front. Each is a hypothesis that Phase 4 tests directly, where
the measured results and any surprises are reported.

**Biases from the scoring recipe (the math)**

- **Genre dominance.** Genre is worth +2.0, double the weight of mood (+1.0) or a
  perfect energy match (+1.0). A song that matches your genre usually outranks a
  song that misses genre but matches mood and energy. In the closest case a genre
  match scores at least 2.0, while the best a non-genre song can reach (perfect
  mood +1.0 plus perfect energy +1.0) is also 2.0, so the genre song ties at
  worst and wins whenever its energy is even slightly close to your target. We
  expect genre to dominate the rankings; Phase 4 will measure how often the top
  result simply shares the profile's genre.
- **Popularity bias (held out by design).** Popularity is a column in the catalog
  but is deliberately excluded from the shipped recipe (the three terms are genre,
  mood, and energy only, maxing at 4.0). We designed it out on purpose, and we
  gave several niche perfect-match songs a low popularity, so a popularity term
  would bury exactly the songs a content-based recommender should surface (a
  filter-bubble, rich-get-richer effect). Phase 4 switches popularity on inside a
  controlled experiment to demonstrate this bias, measures how far the niche
  matches drop, then reverts it so the final product stays popularity-free.

**Biases from the catalog (the data)**

> Note: the two data biases below described the ORIGINAL 20-song catalog. Project 5
> expanded the catalog to 46 songs, rebalancing genres (every genre now has 2-3
> songs, all 10 GTZAN genres covered) and giving every mood at least 3 songs. Both
> data biases are therefore largely resolved; they are kept here as the baseline the
> expansion addressed.

- **Composition skew (original catalog).** The original 20 songs were not evenly
  balanced -- they skewed toward pop and high-energy tracks. We expected popular,
  high-energy profiles to get richer results than niche profiles simply because
  there were more songs to match. (Note this is a property of the data, not the
  recipe: the energy term still rewards closeness to your target, not high energy.)
  The 46-song catalog spreads genres and energy more evenly, so this skew is largely
  corrected.
- **Thin-mood coverage (original catalog).** In the original 20 songs, four moods
  appeared on only one song each: dreamy, intense, mellow, and sad. A profile asking
  for one of those had almost nothing to match on. The expansion gives every mood at
  least 3 songs, so this thin coverage is resolved.

## Testing

```bash
python -m pytest
```

The test suite is a quality add -- the assignment does not require tests, but they
act as a reproducibility and regression guard and double as an executable
specification of the recipe. There are 138 tests across eight files. `tests/`
`test_recommender.py` covers the core recipe, `tests/test_evaluation.py` covers
the Phase 4 evaluation profiles and the popularity experiment,
`tests/test_diversity.py` covers the genre diversity re-ranking side-car, and
`tests/test_retriever.py` and `tests/test_explain.py` cover the Project 5 RAG layer
(retrieval, grounding, the no-note guardrail, and the never-re-rank guarantee), and
`tests/test_glassbox.py` covers the Inspector (the scoreboard agreeing with the
retriever, inspection not perturbing a run, and prompt assembly without a key),
`tests/test_evaluate_retrieval.py` covers the retrieval metrics themselves plus the
identity filter that stops a song being explained with another song's facts, and
`tests/test_config.py` pins the editable knobs: that the defaults are exactly the
shipped values, that the reasons-sum-to-the-score guarantee survives ANY weighting
and not just 2/1/1, and that UI edits never write back to those defaults.
Together they cover:

- **Loading:** the real catalog loads exactly 46 rows with the right types;
  genre and mood are lower-cased; and malformed rows (a non-numeric cell, a short
  row, a blank line) are skipped rather than crashing the load.
- **Scoring:** a perfect match scores 4.00; matching is case-insensitive; the
  energy term is symmetric around the target; a genre match (+2.0) outranks a
  mood-only match (+1.0); missing fields and unknown genres degrade gracefully
  instead of raising.
- **The explainability guarantee:** the numeric values in the reasons list always
  sum to the total score, checked across many song and profile combinations
  (including an off-round energy value).
- **Ranking:** `recommend_songs` returns at most k, in non-increasing score
  order, handles an empty catalog and an empty-genre profile, and is
  deterministic -- exact score ties keep the catalog's original order, and the
  caller's catalog is never reordered.
- **Evaluation and experiment:** the energy-ceiling winner flip, the ghost-genre
  term going dead, the conflicted profile still ranking the unique categorical
  match first, and three popularity-experiment guards (the #1 is never dethroned,
  niche near-matches are buried while pop hits are lifted, and the pure recipe is
  never touched or the catalog mutated).
- **Diversity re-ranking:** the exact default-profile BEFORE/AFTER at cap 1;
  scores and reasons pass through as the same objects; neither the input list nor
  any song dict is mutated; the dead-cap no-op (cap 2 is byte-for-byte the
  baseline, pinned so nobody quietly re-defaults it); the empty-result edge cases
  (`k <= 0`, `max_per_genre <= 0`); an unreachable k returns fewer than k rather
  than relaxing the cap; a missing `genre` key does not crash; and stability
  (kept songs preserve their relative order).

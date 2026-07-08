# Model Card: VibeFinder 1.0

<!-- You (Kim) write the narrative. Agents will supply raw material: dataset stats,
tested profiles, experiment results, and observed biases. Keep sentences short and plain. -->

## Model Name

_e.g., "VibeFinder 1.0"_

## Goal / Task

### Who uses it, and why

VibeFinder is for a listener who can describe the vibe they want right now -- a
genre, a mood, and an energy level -- and wants a few songs from the catalog that
fit that vibe, each with a plain reason so they can trust the pick. The primary
user goal is mood and taste matching ("give me songs that fit this vibe"), not
discovery of unfamiliar music. VibeFinder does not track what the user has
already heard and does not reward novelty, so it optimizes for fit, not for
surfacing new artists. If discovery were the goal, the scoring would need a
novelty term that lowers the rank of already-heard songs, which is out of scope
here.

### What it does (main success path)

Given one taste profile (favorite_genre, favorite_mood, target_energy),
VibeFinder scores every song in the catalog, ranks them, and returns the top-k
(default 5) highest-scoring songs, each with a short reason.

### What "transparent" and "explainable" mean here (concrete and testable)

These are quality goals, so we pin them to specific, checkable behavior rather
than leaving them subjective:

- **Transparent:** every recommendation shows its numeric match score on a fixed
  0.0 to 4.0 scale, so the user can see how strong a match is and how picks
  compare to each other.
- **Explainable:** every recommendation lists the reasons that produced the
  score, one line per contributing term, for example "genre match (+2.0)",
  "mood match (+1.0)", "energy close to target (+0.94)". A reason appears only
  when that term actually fired. Acceptance check (verified by a Phase 3 test):
  the component values in the reasons list add up to the displayed total score.

### Constraints and non-goals (what VibeFinder will NOT do)

Documented up front to keep scope tight and avoid gold plating:

- Does not predict popularity or "hits."
- Does not learn from other users or from listening history (no collaborative
  filtering).
- Uses one static profile per run, defined in code. There is no live slider,
  per-request UI, login, or user account.
- Reads a fixed, hand-authored CSV catalog. There is no admin tool or
  data-ingestion pipeline for adding songs at runtime; the catalog is edited
  directly in `data/songs.csv`.
- Always returns a top-k list even when the best matches are weak. There is no
  minimum-score threshold that would instead report "nothing fits your vibe."
  (Edge cases such as an unknown genre or an energy target no song can reach are
  examined in the Phase 4 evaluation.)

<!-- Kim: this is the neutral factual stub, now reframed around user goals,
concrete explainability, and explicit constraints. Reword in your own voice. -->

## Data Used

The catalog is a small synthetic dataset of 10 songs stored in `data/songs.csv`.
Each song has six features: title, artist, genre, mood, energy (a 0.0 to 1.0
float), and tempo_bpm (an integer). Recommendations are made against a user
profile with three fields: favorite_genre, favorite_mood, and target_energy.

Known limits of this data:

- The catalog is tiny (10 songs) and hand-authored, not drawn from real
  listening data, so results will not generalize.
- There is no popularity, play-count, rating, or user-history data, so
  collaborative filtering is not possible.
- There is no temporal data (no release dates or timestamps), so the system
  cannot account for recency or trends.
- Genre, mood, and energy values are assigned by hand and may carry the
  author's own labeling bias.

<!-- Phase 2 will expand the catalog to ~20 songs; update the size and
distribution notes here when that happens. -->


## Algorithm Summary

_Your scoring rules in plain language (no code)._

## Observed Behavior / Biases

_At least one pattern, limitation, or imbalance (Phase 4 findings)._

## Limitations and Bias

_3-5 sentences on one weakness discovered during experiments (Phase 4 Step 4)._

## Evaluation

<!-- Phase 4 Step 5: which profiles you tested, what surprised you, and a per-pair
comparison of outputs (what changed and why it makes sense). Paste terminal output
for each profile as fenced code blocks. -->

## Intended Use and Non-Intended Use

_What it is for, and what it should NOT be used for._

## Ideas for Improvement

_2-3 things you would change if you kept developing this._

## Personal Reflection

<!-- Kim writes this: biggest learning moment; how AI helped and when you double-checked
it; what surprised you about simple algorithms; what you'd try next. -->

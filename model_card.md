# Model Card: VibeFinder 1.0

<!-- You (Kim) write the narrative. Agents will supply raw material: dataset stats,
tested profiles, experiment results, and observed biases. Keep sentences short and plain. -->

## Model Name

_e.g., "VibeFinder 1.0"_

## Goal / Task

VibeFinder recommends songs from a fixed catalog that fit a single user's stated
taste profile. For each song it compares the song's genre, mood, and energy
against the user's favorite genre, favorite mood, and target energy, produces a
match score, and returns a ranked top-k list with a short reason for each pick.
The goal is a transparent, explainable recommendation rather than a black-box
prediction. It does not predict hits or learn from other users.

<!-- Kim: this is the neutral factual stub. Reword in your own voice if you like. -->

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

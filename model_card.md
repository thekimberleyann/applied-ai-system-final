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
here. Framing the goal around why the user asks for a recommendation, rather than
around the software's mechanics, follows the user-story emphasis on user
intent over feature lists (Cohn, 2004).

### What it does (main success path)

Given one taste profile (favorite_genre, favorite_mood, target_energy),
VibeFinder scores every song in the catalog, ranks them, and returns the top-k
(default 5) highest-scoring songs, each with a short reason.

### What "transparent" and "explainable" mean here (concrete and testable)

These are quality attributes (nonfunctional requirements). Like the word
"user-friendly," they are too subjective to build against until they have
measurable acceptance criteria, so we pin them to specific, checkable behavior
(Wiegers & Beatty, 2013):

- **Transparent:** every recommendation shows its numeric match score on a fixed
  0.0 to 4.0 scale, so the user can see how strong a match is and how picks
  compare to each other.
- **Explainable:** every recommendation lists the reasons that produced the
  score, one line per contributing term, for example "genre match (+2.0)",
  "mood match (+1.0)", "energy close to target (+0.94)". A reason appears only
  when that term actually fired. Acceptance check (verified by a Phase 3 test):
  the component values in the reasons list add up to the displayed total score.

### Constraints and non-goals (what VibeFinder will NOT do)

Documenting what the system will not do keeps scope tight and helps prevent
gold plating, where developers add unrequested features they assume the user
wants (Wiegers & Beatty, 2013):

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

The catalog is a small synthetic dataset of 20 songs stored in `data/songs.csv`.
Each song has seven features: title, artist, genre, mood, energy (a 0.0 to 1.0
float), tempo_bpm (an integer), and popularity (a 0.0 to 1.0 float). Popularity
is data-only: it is recorded for every song but is excluded from the scoring
recipe by design, and is used only in the Phase 4 bias experiment (see the
Algorithm Summary). Recommendations are made against a user profile with three
fields: favorite_genre, favorite_mood, and target_energy.

Catalog make-up (the baseline for the Phase 4 bias study):

- The 20 songs skew toward pop and high-energy tracks, and one cluster of
  electronic-family genres (synthwave, edm, electronic, dreampop) makes up about
  20% of the catalog.
- Several moods are thinly covered: dreamy, intense, mellow, and sad each appear
  on only one song.
- Some niche, perfect-match songs were deliberately given a low popularity value,
  so the Phase 4 popularity-bias experiment has something vivid to surface.

Known limits of this data:

- The catalog is tiny (20 songs) and hand-authored, not drawn from real
  listening data, so results will not generalize.
- There is no play-count, rating, or user-history data, so collaborative
  filtering is not possible. The popularity value is a single static number per
  song, not a record of interactions, so it does not enable collaborative
  filtering either.
- There is no temporal data (no release dates or timestamps), so the system
  cannot account for recency or trends.
- Genre, mood, and energy values are assigned by hand and may carry the
  author's own labeling bias.


## Algorithm Summary

VibeFinder is a content-based recommender: it scores every song against your
stated tastes -- favorite genre, favorite mood, and a target energy level -- and
returns the songs that fit best. This section describes the scoring design; the
implementation is built in Phase 3.

A song earns up to four points in total, from three rules:

- **Genre match (2 points, all or nothing).** A song earns two points when its
  genre is exactly your favorite genre, and nothing otherwise. Genre is treated
  as the strongest signal of fit, so it is weighted twice as heavily as the other
  two rules.
- **Mood match (1 point, all or nothing).** A song earns one point when its mood
  is exactly your favorite mood, and nothing otherwise.
- **Energy closeness (up to 1 point, graduated).** This rule rewards how close a
  song's energy is to the level you asked for, not how high its energy is. A song
  sitting right on your target earns the full point, and the reward shrinks as the
  gap grows in either direction -- a song calmer than you asked for is penalized
  just as much as one that is more energetic by the same amount -- reaching zero
  once the gap is large.

Adding the three rules gives a maximum total of 4.0 (2.0 + 1.0 + 1.0). VibeFinder
ranks every song by this total, highest first, and returns the top few (five by
default). When two songs tie on the total score, the one appearing earlier in the
catalog is listed first. Each recommendation comes with a short list of reasons
showing where its points came from, and those reason values always add up to the
total score, which is what makes the score transparent and explainable as defined
under Goal / Task.

These three rules are the entire recipe. The catalog also records each song's
popularity, but popularity is excluded by design from scoring; it is kept only
for a separate Phase 4 experiment and has no effect on the recommendations shown
today.

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

## References

Cohn, M. (2004). *User stories applied: For agile software development*.
Addison-Wesley.

Wiegers, K. E., & Beatty, J. (2013). *Software requirements* (3rd ed.).
Microsoft Press.


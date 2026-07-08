# Model Card: VibeFinder 1.0

<!-- You (Kim) write the narrative. Agents will supply raw material: dataset stats,
tested profiles, experiment results, and observed biases. Keep sentences short and plain. -->

## Model Name

VibeFinder 1.0 -- a content-based music recommender that scores a small fixed
catalog against a described genre, mood, and energy profile and returns the top
matches with plain-language reasons.

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
intent over feature lists.

### What it does (main success path)

Given one taste profile (favorite_genre, favorite_mood, target_energy),
VibeFinder scores every song in the catalog, ranks them, and returns the top-k
(default 5) highest-scoring songs, each with a short reason.

### What "transparent" and "explainable" mean here (concrete and testable)

These are quality attributes (nonfunctional requirements). Like the word
"user-friendly," they are too subjective to build against until they have
measurable acceptance criteria, so we pin them to specific, checkable behavior:

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
wants:

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

<!-- Kim: this is the neutral factual write-up of the Phase 4 findings. Reword in
your own voice; the "what surprised me" reaction belongs in the Personal Reflection. -->

Running the recipe across many taste profiles surfaced three consistent patterns:

- **Genre dominance / a categorical moat.** Because a genre match is +2.0 and a
  mood match is +1.0, any song that matches both starts at 3.0 before the energy
  term is counted. That is a roughly two-point lead over any song matching only
  one field, so a genuine genre-plus-mood match almost always takes the top
  spot. It is robust at the top, but it also means the whole ranking is decided
  by genre first, everything else second.
- **Energy is only a weak tiebreaker.** The energy term (0.0 to 1.0) matters when
  two songs already tie on genre and mood, but it is easily swamped by a single
  categorical match. In the Conflicted profile below, a song with a large energy
  mismatch still wins comfortably because it is the only genre-plus-mood match.
- **A pop / high-energy catalog skew.** The catalog leans toward pop and
  high-energy songs, so mainstream, upbeat profiles get several strong matches
  while niche profiles (for example a single-song mood like dreamy or sad) fall
  back to weak energy-only matches.

## Limitations and Bias

<!-- Kim: the assignment asks for 3-5 sentences on ONE weakness found during the
experiments. This is a neutral draft of the popularity finding; put it in your voice. -->

The clearest weakness is how fragile the ranking becomes below the top match, and
how easily a popularity signal would corrupt it. The popularity experiment
(`python -m src.experiment_popularity`) added a popularity term on top of the pure
recipe for a folk / nostalgic listener. The deserved number one, Wandering Roads,
survived because a genre-plus-mood match is structurally hard to unseat, but the
ranks below it did not: at a modest weight the more popular of two genuine mood
matches jumped ahead of the less popular one, and at a higher weight two pop chart
hits that share neither genre nor mood with a folk fan pushed real near-matches
out of the top five. This is the classic popularity-bias / filter-bubble failure,
where a crowd signal quietly overrides personal fit, and it is exactly why the
shipped recipe scores taste only and leaves popularity out.

## Evaluation

<!-- Kim: the profiles tested and the factual comparisons are below with real
terminal output. The one thing left for you is the "what surprised me" line in
each comparison and in the Personal Reflection. -->

Seven profiles were tested beyond the default: four diverse (High-Energy Pop,
Chill Lofi, Deep Intense Rock, Romantic R&B) and three adversarial (Conflicted,
Ghost Genre, Energy Ceiling), plus the popularity experiment. Full output comes
from `python -m src.main` and `python -m src.experiment_popularity`. Three
comparisons tell the story.

**Comparison 1 -- the energy tiebreak flips a winner (default vs Energy Ceiling).**
For a pop / happy listener, changing only the target energy changes the number
one song. At target 0.80 Summer Anthem (energy 0.80) wins; at target 1.0 (a
ceiling no song reaches) Sunshine Pop (energy 0.85, closer to 1.0) wins. A tiny
number decides the order.

```
Default (pop / happy / 0.80)          Energy Ceiling (pop / happy / 1.0)
1. Summer Anthem   (score 4.00)        1. Sunshine Pop   (score 3.85)
2. Sunshine Pop    (score 3.95)        2. Summer Anthem  (score 3.80)
```

**Comparison 2 -- graceful degradation (Ghost Genre vs a normal pop run).** When
the requested genre (kpop) is not in the catalog, the +2.0 genre term is dead for
every song, so the best possible score drops from 4.0 to 2.0 and the system ranks
on mood and energy alone. It does not crash; it just quietly loses a scoring term.

```
Ghost Genre (kpop / happy / 0.80)      High-Energy Pop (pop / happy / 0.95)
1. Summer Anthem   (score 2.00)        1. Sunshine Pop   (score 3.90)
2. Sunshine Pop    (score 1.95)        2. Summer Anthem  (score 3.85)
```

**Comparison 3 -- the popularity experiment (before vs after, folk / nostalgic /
0.40).** With popularity switched on, the low-popularity hidden gem stays at
number one, but popular non-matches invade the ranks below it.

```
POP_WEIGHT = 2.0
#  BEFORE (pure taste)                 AFTER (+ popularity)
1  Wandering Roads (4.00, pop 0.18)    Wandering Roads (4.36)
2  Backroad Sunset (1.85, pop 0.58)    Golden Hour     (3.39)
3  Golden Hour     (1.75, pop 0.82)    Backroad Sunset (3.01)
4  Rainy Day Blues (1.00, pop 0.25)    Summer Anthem   (2.50)   <- pop hit, no genre/mood match
5  Acoustic Morning(0.95, pop 0.40)    Sunshine Pop    (2.35)   <- pop hit, no genre/mood match
```

_What surprised me (Kim to write): ____._

## Intended Use and Non-Intended Use

<!-- Kim: neutral factual draft; reword in your voice. Kept consistent with the
non-goals already listed under Goal / Task. -->

**Intended use.** VibeFinder is a teaching and demonstration tool for
content-based recommendation. It takes one listener's described taste -- a genre,
a mood, and a target energy level -- and returns a short, ranked list of songs
from a small, fixed, hand-authored catalog, with a plain-language reason for
every match, so a person can see exactly why each song was picked. Good fits
include learning how content-based scoring works, showing how a transparent
scoring recipe behaves, and giving a concrete, inspectable example of how
recommendation biases arise.

**Non-intended use.** VibeFinder is not built for and should not be used for:

- Real-world or production music recommendation. The catalog is 20 hand-authored
  songs, not a live library, and the profile is set once in code with no login,
  interface, or feedback loop -- consistent with the constraints under Goal / Task.
- Anything needing collaborative filtering or listening history. VibeFinder never
  looks at what other users liked or at a listener's past plays; with no such data
  collaborative filtering is not possible here.
- Music discovery of unheard tracks. It optimizes for fit, not novelty, and does
  not reward or surface unfamiliar songs.
- Predicting hits, popularity, or commercial success. The catalog records a
  popularity value, but the shipped recipe never scores it; it is data only.
- Fairness-sensitive, high-stakes, or otherwise consequential decisions.
- Any claim that a VibeFinder score is an objective measure of a song's quality. A
  score reflects only how closely a song's tagged attributes match the described
  profile under one fixed recipe, not whether the song is good. Note also that it
  always returns a top-k list even when every match is weak (there is no
  minimum-score threshold).

## Ideas for Improvement

<!-- Kim: neutral factual draft; reword in your voice. Each idea traces to a bias
documented in Observed Behavior/Biases, Limitations, or the Expected Biases. -->

1. **Add a diversity or anti-popularity guard to soften genre dominance.** Because
   an exact genre-plus-mood match reaches 3.0 before energy is counted, one genre
   can hold the top ranks almost unbeatably, and the popularity experiment showed
   popular non-matches colonizing ranks 2 through 5. A re-balanced genre weight or
   a rule limiting how many same-genre (or high-popularity) songs fill the list
   would directly counter both the categorical-moat bias and the filter-bubble
   risk. (This would be added on top of the recipe; the base recipe stays three
   terms and popularity stays out of scoring.)
2. **Expand the catalog for the thin moods.** Four moods -- dreamy, intense,
   mellow, and sad -- have a single song each, so those profiles get little real
   choice and the mood term barely differentiates results. Adding songs across
   these underrepresented moods would give niche profiles genuine matches and
   reduce the pop and high-energy skew of the current catalog.
3. **Add a lightweight feedback loop.** The model runs one static profile with no
   way for a listener to react, documented as an honest non-goal and an
   expectation gap. A simple rate-or-skip signal, or a target-energy slider to
   adjust the profile between runs, would let results respond to the listener
   instead of being fixed in code.

## Personal Reflection

<!-- Kim writes this: biggest learning moment; how AI helped and when you double-checked
it; what surprised you about simple algorithms; what you'd try next. -->


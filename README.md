# VibeFinder - Music Recommender Simulation

A simple content-based music recommender. It scores each song in a catalog against
a user's "taste profile" (favorite genre, mood, target energy) and returns a ranked,
explained list of suggestions.

## How The System Works

### What a recommender does

A recommender system suggests items a person is likely to enjoy typically based on 
prior likes or interactions. Streaming services like Spotify and Netflix do this constantly: out of large libraries they surface the handful of songs or shows most relevant to you. VibeFinder is a small, transparent version of the same idea, built for a fixed catalog of
songs.

### Two common approaches

Real-world recommenders are usually built one of two ways.

- **Collaborative filtering** learns from the behavior of many users. It looks
  at what large numbers of people liked, skipped, replayed, or added to
  playlists, and finds patterns across those users. The core idea is "people
  who behaved like you also enjoyed this." For example, Spotify's Discover
  Weekly can recommend a track simply because listeners with taste similar to
  yours keep saving it, even without knowing anything about how the song
  sounds. This approach needs a large history of user interactions to work.
- **Content-based filtering** matches the features of the items themselves to a
  user's stated preferences. It does not need other users at all. The core idea
  is "this item's attributes line up with what you said you want." For example,
  you tell a service you like calm acoustic music, and it scores each song by
  how well its genre, mood, and energy fit that description. This approach needs
  good item features and a clear preference to compare against.

### Improving either approach (a requirements lens)

Both descriptions above focus on how the software works: one tracks user
behavior, the other matches item attributes. From a requirements point of view,
that is only half the picture. Three principles from software requirements
practice show how either approach can be improved, and they also explain why
VibeFinder is intentionally simple.

- **Start from the user's goal, not the mechanics.** A recommender is only truly
  complete when it serves the user's actual objective, not just a list of
  system behaviors. The same engine should prioritize differently
  depending on why the person wants a recommendation right now -- for example
  "help me focus while I study" versus "show me new artists I have not heard."
  Defining that goal first is what tells the algorithm what to optimize.
- **Close the expectation gap with feedback.** An algorithm can be
  mathematically optimal and still miss what the user actually wanted, which
  leaves an expectation gap. Real systems narrow it
  with frequent contact points: letting users rate or skip results, adjust
  parameters (such as a target-energy slider), or react to a prototype, then
  feeding that back in. VibeFinder deliberately does not do this yet -- it runs
  once from a static profile with no feedback loop -- so this is an honest
  limitation and a clear direction for improvement rather than something the
  current version claims.
- **Separate attractive features from real value.** A recommendation engine is a
  product feature, and every mechanism should trace back to a validated user
  task and a justification. A complex collaborative
  filtering model is not automatically more valuable; building one the user did
  not need is gold plating. When the user's goal is quick, explainable
  vibe-matching, a simple content-based score delivers more value at far less
  cost. That trade-off is the reason VibeFinder's simple design is a deliberate
  choice, not a shortcut.

### Which approach VibeFinder uses, and why

VibeFinder uses **content-based filtering**.

This is a deliberate choice forced by the data we have. VibeFinder has no record
of how anyone has ever listened -- there are no likes, skips, play counts,
ratings, or playlists to learn from. Collaborative filtering is therefore not
possible here, because there is no crowd of user behavior to find patterns in.
What VibeFinder does have is a catalog where every song is described by concrete
features, plus a single user's stated taste profile. It compares the two
directly: for each song it measures how well the song's features match the
profile, produces a score, ranks the songs by that score, and returns a short
list of the best matches with a plain-language reason for each.

### Song features (what VibeFinder knows about each song)

Each song in the catalog is described by these features:

- **title** -- the song's name.
- **artist** -- the performer.
- **genre** -- the musical category (for example pop, rock, lofi, jazz).
- **mood** -- the emotional feel (for example happy, chill, intense, calm).
- **energy** -- how energetic the track is, on a 0.0 to 1.0 scale, where higher
  means more energetic.
- **tempo_bpm** -- the tempo in beats per minute (a whole number).
- **popularity** -- a crowd-popularity value on a 0.0 to 1.0 scale, where higher
  means more widely popular. It is recorded for every song but is deliberately
  NOT scored by the recipe (see the note under Algorithm Recipe).

### UserProfile features (what VibeFinder knows about you)

A user's taste profile has three preferences, which songs are matched against:

- **favorite_genre** -- the genre the listener most wants to hear.
- **favorite_mood** -- the mood the listener is in the mood for.
- **target_energy** -- the listener's preferred energy level, on the same 0.0
  to 1.0 scale as a song's energy.

### Algorithm Recipe (how the score is calculated)

VibeFinder scores every song against your taste profile (favorite genre,
favorite mood, and a target energy from 0.0 to 1.0), then ranks the highest
scorers. A song's score is the sum of exactly three terms, for a maximum of
**4.0 points** (2.0 + 1.0 + 1.0):

- **Genre match (+2.0).** The song's genre must exactly equal your
  `favorite_genre`. It is all-or-nothing: +2.0 on an exact match, otherwise 0.
  Genre is weighted twice as heavily as the other terms because it is the
  strongest single signal of whether a song fits the vibe you asked for.
- **Mood match (+1.0).** The song's mood must exactly equal your
  `favorite_mood`. Also all-or-nothing: +1.0 on an exact match, otherwise 0.
- **Energy closeness (up to +1.0).** This term rewards how CLOSE a song's energy
  is to your target energy, not how high its energy is. It is computed as
  `1.0 * max(0, 1 - |song_energy - target_energy|)`. A song sitting right on
  your target earns the full +1.0; the score shrinks as the gap widens and
  reaches 0 once the difference is 1.0 or more. The direction does not matter --
  a low target-energy rewards calm songs exactly as much as a high target-energy
  rewards intense ones. Because energy is continuous, this term almost always
  contributes something, so it acts as the natural tie-breaker between songs
  that match on genre and mood.

The `tempo_bpm` feature is recorded for every song but is likewise not scored: it
correlates closely with energy, so scoring it would double-count that same signal.

**Worked example.** Using the default profile (genre `pop`, mood `happy`,
target energy `0.8`), two songs both match perfectly on genre and mood, so
energy closeness alone decides the order:

```
Summer Anthem  genre +2.00 | mood +1.00 | energy +1.00  (|0.80 - 0.80| = 0.00) = 4.00
Sunshine Pop   genre +2.00 | mood +1.00 | energy +0.95  (|0.85 - 0.80| = 0.05) = 3.95
```

"Summer Anthem" wins by 0.05 purely because its energy lands exactly on the
target. A tiny number decides the ranking. When two songs tie on the total
score, VibeFinder keeps the catalog's original order (a stable sort), so the
ranking is deterministic.

**How a recommendation is explained.** Each result carries a short reasons list
naming only the terms that fired, for example `genre match (+2.0)`,
`mood match (+1.0)`, `energy close to target (+0.94)`. The energy reason always
appears; the genre and mood reasons appear only on an exact match. By design the
component values in the reasons list always add up to the displayed total score,
so every recommendation's explanation adds up to the number you see. (This
summing guarantee is enforced by a Phase 3 test.)

> **Note -- popularity is deliberately NOT scored.** The catalog carries a
> `popularity` value (0.0 to 1.0) per song, but it is excluded from the shipped
> recipe above by design. VibeFinder's job is to match one listener's taste and
> mood, and popularity is a crowd signal that says nothing about whether a song
> fits THIS user; scoring on it would bury niche, perfect-fit songs under chart
> hits (a filter-bubble, rich-get-richer effect). The column is kept in the data
> on purpose so Phase 4 can switch it on inside a controlled experiment, measure
> that bias directly, and then revert it. See the Phase 4 bias study.

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

- **Composition skew.** The 20 songs are not evenly balanced -- they skew toward
  pop and high-energy tracks, and one cluster of electronic-family genres
  (synthwave, edm, electronic, dreampop) makes up about 20% of the catalog. We
  expect popular, high-energy profiles to get richer and more varied results than
  niche profiles simply because there are more songs to match. Phase 4 will
  compare result quality across different profile types. (Note this is a property
  of the data, not the recipe: the energy term still rewards closeness to your
  target, not high energy.)
- **Thin-mood coverage.** Four moods appear on only one song each: dreamy,
  intense, mellow, and sad. For a profile asking for one of those moods there is
  almost nothing to match on, so the mood term can fire at most once and the
  ranking falls back to genre and energy. Phase 4 will check which mood profiles
  collapse to genre-plus-energy in practice.

## Run it

```bash
pip install -r requirements.txt
python -m src.main
```

## Sample Recommendation Output

Running `python -m src.main` against the default profile (genre pop, mood happy,
target energy 0.8) produces this ranking. Note how the two pop/happy songs tie on
genre and mood, so the energy-closeness term alone decides that Summer Anthem
(energy 0.80, right on the target) edges out Sunshine Pop (energy 0.85):

```
Loaded songs: 20

=== Recommendations for the default profile (pop / happy) ===
1. Summer Anthem  (score 4.00)
     - genre match (+2.0)
     - mood match (+1.0)
     - energy close to target (+1.00)
2. Sunshine Pop  (score 3.95)
     - genre match (+2.0)
     - mood match (+1.0)
     - energy close to target (+0.95)
3. Midnight Drive  (score 0.95)
     - energy close to target (+0.95)
4. Crown Season  (score 0.95)
     - energy close to target (+0.95)
5. Power Up  (score 0.92)
     - energy close to target (+0.92)
```

Songs 3 to 5 match neither genre nor mood, so their whole score is the energy
term. This is the genre-dominance effect described under Expected Biases: any
pop/happy match jumps far ahead of songs that only happen to sit near the target
energy.

## Optional Extension: Genre Diversity Re-Ranking

This is an optional extension, kept deliberately OUTSIDE the shipped recipe. It
targets the genre-dominance bias documented under Expected Biases -- two
near-identical pop hits crowding the top of a pop/happy ranking -- and asks a
different question than the recommender itself: instead of "what fits my vibe,"
it asks "show me a spread of genres."

**What it does.** `src/diversity.py` takes the already-ranked
`(song, score, reasons)` list from `recommend_songs`, walks it top to bottom, and
keeps a song only while its genre has been kept fewer than `max_per_genre` times.
It is a post-ranking SELECTION step, a side-car that sits beside the recipe
exactly as the popularity experiment does. Scores and reasons pass through
completely unmodified; `src/recommender.py` is never touched, so the extension
deletes cleanly -- remove the file and the recommender is exactly as it was.

**Why it is NOT a scoring term.** Diversity could not be folded into the score
without breaking a guarantee the model card defines as the testable meaning of
"transparent." A diversity bonus would push a score above the fixed 0.0 to 4.0
scale, and a penalty would subtract points that no reason string accounts for,
breaking the "the reasons always sum to the score" guarantee. The only honest
place for it is a selection step layered on top of the finished ranking, where it
never goes near a score.

**How to run it.**

```bash
python -m src.diversity
```

**BEFORE / AFTER (default profile, pop / happy / 0.80, max_per_genre=1).**

```
#  BEFORE (pure recipe)              AFTER (one per genre)
1  Summer Anthem [pop] 4.00          Summer Anthem [pop] 4.00
2  Sunshine Pop [pop] 3.95           Midnight Drive [synthwave] 0.95
3  Midnight Drive [synthwave] 0.95   Crown Season [hip-hop] 0.95
4  Crown Season [hip-hop] 0.95       Power Up [electronic] 0.92
5  Power Up [electronic] 0.92        Dance All Night [edm] 0.90
```

**Two honest findings.** Both argue for keeping the extension out of the shipped
recipe.

- **A cap of 2 is dead code on this catalog.** There are 20 songs with at most 2
  of any one genre (pop x2, hip-hop x2, everything else x1), and across all 231
  (genre, mood, energy) profiles no top-5 ever contains 3 songs of a single
  genre. A cap of 2 can therefore never fire; only a cap of 1 changes anything,
  which is why 1 is the default. This echoes the earlier popularity tie-breaker
  that was rejected for the same reason: a knob that almost never fires is not
  worth shipping.
- **A cap of 1 is not free.** On the default profile it demotes Sunshine Pop, a
  genuine 3.95 pop/happy match, and promotes Dance All Night at 0.90 -- an edm
  song that matches NEITHER the listener's genre NOR their mood. That is a
  3.05-point quality cost for one slot of genre breadth. It does curb the
  genre-dominance bias, but it spends the listener's stated taste on variety they
  did not ask for. That trade is why the shipped `recommend_songs` is left
  unchanged and diversity stays a separate, optional module.

## Testing

```bash
python -m pytest
```

The test suite is a quality add -- the assignment does not require tests, but they
act as a reproducibility and regression guard and double as an executable
specification of the recipe. There are 50 tests across three files. `tests/`
`test_recommender.py` covers the core recipe, `tests/test_evaluation.py` covers
the Phase 4 evaluation profiles and the popularity experiment, and
`tests/test_diversity.py` covers the genre diversity re-ranking side-car. Together
they cover:

- **Loading:** the real catalog loads exactly 20 rows with the right types;
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

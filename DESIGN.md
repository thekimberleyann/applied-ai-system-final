# VibeFinder Design Notes

This document holds the deeper design material that used to sit at the bottom of the
README: what a recommender does and the two common approaches to building one, why
VibeFinder is content-based, the feature inventories for a song and for a taste
profile, the scoring recipe walked through term by term, and the optional
genre-diversity re-ranking extension. The project overview, setup and run
instructions, architecture, and design trade-offs stay in
[README.md](README.md). The bias predictions and the detailed test inventory are in
[EVALUATION.md](EVALUATION.md), which is where the "Expected Biases" section referred
to below now lives.

---

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
**4.0 points** (2.0 + 1.0 + 1.0).

The three weights below are the shipped defaults, and since Project 5 they live in
`ScoringConfig` in [`src/config.py`](src/config.py) rather than as literals inside
`score_song`. They are editable at runtime from the Inspector's knob panel in the
Streamlit app, which never writes them back. Note that the 0.0 to 4.0 scale is simply
what 2.0 + 1.0 + 1.0 adds up to and nothing is renormalized, so changing a weight
changes the ceiling; the reasons-sum-to-the-score guarantee below holds under any
weighting, and a test pins that. The terms:

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

## Run it

```bash
pip install -r requirements.txt
python -m src.main
```

> The rest of this section documents the **core recipe** in isolation (the Module 3
> behavior). Since Project 5, `python -m src.main` also attaches the RAG explanations
> shown in the Project 5 section above; the ranking below is unchanged -- the
> explainer only adds prose on top of it.

## Sample Recommendation Output (core recipe, score-only)

The default profile (genre pop, mood happy, target energy 0.8) produces this ranking.
Three pop/happy songs tie on genre and mood, so the energy-closeness term alone orders
them: Summer Anthem (energy 0.80, right on the target) edges out Sunshine Pop (0.85)
and Confetti Skies (0.72). Since Project 5, `python -m src.main` prints this block
tagged `[RAG]` with an explanation line under each song; to see the same ranking
score-only, itemized term by term, run `python -m src.inspect_cli` and read Panel 1:

```
Loaded songs: 46

=== Recommendations for the default profile (pop / happy) ===
1. Summer Anthem  (score 4.00)
     - genre match (+2.0)
     - mood match (+1.0)
     - energy close to target (+1.00)
2. Sunshine Pop  (score 3.95)
     - genre match (+2.0)
     - mood match (+1.0)
     - energy close to target (+0.95)
3. Confetti Skies  (score 3.92)
     - genre match (+2.0)
     - mood match (+1.0)
     - energy close to target (+0.92)
4. Velvet Hustle  (score 2.00)
     - mood match (+1.0)
     - energy close to target (+1.00)
5. Mirrorball Fever  (score 1.95)
     - mood match (+1.0)
     - energy close to target (+0.95)
```

The three pop/happy songs (each 3.9+) sit far ahead of songs 4 to 5, which are
disco/happy tracks matching the mood but not the genre (so no +2.0 term). This is
the genre-dominance effect described under Expected Biases: any full genre+mood match
jumps far ahead of a mood-only or energy-only match.

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
2  Sunshine Pop [pop] 3.95           Velvet Hustle [disco] 2.00
3  Confetti Skies [pop] 3.92         Midnight Drive [synthwave] 0.95
4  Velvet Hustle [disco] 2.00        Crown Season [hip-hop] 0.95
5  Mirrorball Fever [disco] 1.95     Static Rebellion [rock] 0.95
```

**Two honest findings.** Both argue for keeping the extension out of the shipped
recipe.

- **A cap of 2 was dead code on the original catalog, and the catalog SIZE is what
  changed that.** On the original 20-song catalog every genre had at most 2 songs, so
  across all 2178 swept (genre, mood, energy) profiles no top-5 ever held 3 of one
  genre and a cap of 2 could never fire -- it was dead code, and only a cap of 1 did
  anything. After Project 5 expanded the catalog to 46 songs, eight genres carry 3
  entries and 968 of the 2299 swept profiles produce a top-5 holding 3 of one genre,
  so the default pop/happy top-5 now holds THREE pop songs and a cap of 2 fires (it
  drops the third pop song). The lesson is that the knob's usefulness was gated by
  catalog size, not by the algorithm -- which is exactly why a bigger, balanced catalog
  matters. Both sweep numbers come from `python -m src.sweep`, which prints its grid
  size with the results: an earlier hand-counted figure here went stale the moment the
  catalog grew, and could not be re-derived because the script that produced it was
  never committed.
- **A cap of 1 is not free.** On the default profile it demotes Sunshine Pop (3.95)
  and Confetti Skies (3.92), two genuine pop/happy matches, and promotes Velvet Hustle
  at 2.00 -- a disco song that matches the listener's mood but NOT their genre. That is
  a ~1.95-point quality cost at slot 2 for one extra genre. It does curb the
  genre-dominance bias, but it spends the listener's stated taste on variety they did
  not ask for. That trade is why the shipped `recommend_songs` is left unchanged and
  diversity stays a separate, optional module.

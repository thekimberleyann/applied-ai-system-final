# VibeFinder — Music Recommender Simulation

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
  system behaviors (Cohn, 2004). The same engine should prioritize differently
  depending on why the person wants a recommendation right now -- for example
  "help me focus while I study" versus "show me new artists I have not heard."
  Defining that goal first is what tells the algorithm what to optimize.
- **Close the expectation gap with feedback.** An algorithm can be
  mathematically optimal and still miss what the user actually wanted, which
  leaves an expectation gap (Wiegers & Beatty, 2013). Real systems narrow it
  with frequent contact points: letting users rate or skip results, adjust
  parameters (such as a target-energy slider), or react to a prototype, then
  feeding that back in. VibeFinder deliberately does not do this yet -- it runs
  once from a static profile with no feedback loop -- so this is an honest
  limitation and a clear direction for improvement rather than something the
  current version claims.
- **Separate attractive features from real value.** A recommendation engine is a
  product feature, and every mechanism should trace back to a validated user
  task and a justification (Wiegers & Beatty, 2013). A complex collaborative
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

<!-- Phase 2 (next commit): add the expected-biases paragraph here. -->

_Expected biases: TODO (Phase 2)._

## Run it

```bash
pip install -r requirements.txt
python -m src.main
```

## Sample Recommendation Output

<!-- Phase 3: paste the terminal output (titles, scores, reasons) as a fenced block. -->

_TODO (Phase 3)._

## Testing

```bash
python -m pytest
```

_TODO (Phase 3/quality): describe what the tests cover._

## References

Cohn, M. (2004). *User stories applied: For agile software development*.
Addison-Wesley.

Wiegers, K. E., & Beatty, J. (2013). *Software requirements* (3rd ed.).
Microsoft Press.

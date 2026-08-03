# Model Card: VibeFinder 1.0

## Model Name

VibeFinder 1.0 is a content-based music recommender. It scores a small fixed
catalog against a described genre, mood, and energy profile, then returns the top
matches with plain-language reasons.

## Goal / Task

### Who uses it, and why

VibeFinder is for a listener who can describe the vibe they want right now: a
genre, a mood, and an energy level. They want a few songs from the catalog that
fit that vibe, each with a reason they can check, so they can trust the pick. The
goal is mood and taste matching, not discovery of unfamiliar music. VibeFinder
does not track what the listener has already heard and does not reward novelty, so
it aims for fit rather than for surfacing new artists. If discovery were the goal,
the scoring would need a novelty term that pushes already-heard songs down the
list, and that is out of scope here. Framing the goal around why someone asks for
a recommendation, rather than around what the software does, follows the
user-story emphasis on user intent over feature lists.

### What it does (main success path)

Given one taste profile (favorite_genre, favorite_mood, target_energy),
VibeFinder scores every song in the catalog, ranks them, and returns the top-k
(5 by default) highest-scoring songs, each with a short reason.

### What "transparent" and "explainable" mean here (concrete and testable)

These are quality attributes. Like the word "user-friendly," they are too vague to
build against until they have acceptance criteria you can actually check, so each
one is pinned to specific behavior:

- **Transparent:** every recommendation shows its numeric match score on a fixed
  0.0 to 4.0 scale, so the listener can see how strong a match is and how the
  picks compare to each other.
- **Explainable:** every recommendation lists the reasons behind its score, one
  line per term that fired, for example "genre match (+2.0)", "mood match (+1.0)",
  "energy close to target (+0.94)". A reason appears only when that term actually
  contributed. Acceptance check, verified by a Phase 3 test: the values in the
  reasons list add up to the displayed total score.

### Constraints and non-goals (what VibeFinder will NOT do)

Writing down what the system will not do keeps the scope tight. It also guards
against gold plating, where a developer adds features nobody asked for:

- Does not predict popularity or "hits."
- Does not learn from other users or from listening history, so no collaborative
  filtering.
- Uses one static profile per run, defined in code. There is no live slider,
  per-request interface, login, or user account.
- Reads a fixed, hand-authored CSV catalog. There is no admin tool or
  data-ingestion pipeline for adding songs at runtime. The catalog is edited
  directly in `data/songs.csv`.
- Always returns a top-k list even when the best matches are weak. There is no
  minimum-score threshold that would instead report "nothing fits your vibe."
  Edge cases such as an unknown genre, or an energy target no song can reach, are
  examined in the Phase 4 evaluation.

## Data Used

The catalog is a small synthetic dataset of 20 songs stored in `data/songs.csv`.
Each song has seven features: title, artist, genre, mood, energy (a 0.0 to 1.0
float), tempo_bpm (an integer), and popularity (a 0.0 to 1.0 float). Popularity is
data only. It is recorded for every song but left out of the scoring recipe by
design, and it is used only in the Phase 4 bias experiment. See the Algorithm
Summary. Recommendations are made against a user profile with three fields:
favorite_genre, favorite_mood, and target_energy.

Catalog make-up, which is the baseline for the Phase 4 bias study:

- The 20 songs skew toward pop and high-energy tracks, and one cluster of
  electronic-family genres (synthwave, edm, electronic, dreampop) makes up about
  20% of the catalog.
- Several moods are thinly covered. Dreamy, intense, mellow, and sad each appear
  on only one song.
- Some niche, perfect-match songs were deliberately given a low popularity value,
  so the Phase 4 popularity experiment has something vivid to surface.

Known limits of this data:

- The catalog is tiny at 20 songs, and hand-authored rather than drawn from real
  listening data, so the results will not generalize.
- There is no play-count, rating, or user-history data, so collaborative filtering
  is not possible. The popularity value is a single static number per song, not a
  record of interactions, so it does not enable collaborative filtering either.
- There is no temporal data, meaning no release dates or timestamps, so the system
  cannot account for recency or trends.
- Genre, mood, and energy values are assigned by hand and may carry the author's
  own labeling bias.


## Algorithm Summary

VibeFinder is a content-based recommender. It scores every song against your
stated tastes, meaning your favorite genre, your favorite mood, and a target
energy level, and returns the songs that fit best. This section describes the
scoring design. The implementation is built in Phase 3.

A song earns up to four points in total, from three rules:

- **Genre match (2 points, all or nothing).** A song earns two points when its
  genre is exactly your favorite genre, and nothing otherwise. Genre is treated as
  the strongest signal of fit, so it is weighted twice as heavily as the other two
  rules.
- **Mood match (1 point, all or nothing).** A song earns one point when its mood
  is exactly your favorite mood, and nothing otherwise.
- **Energy closeness (up to 1 point, graduated).** This rule rewards how close a
  song's energy is to the level you asked for, not how high its energy is. A song
  sitting right on your target earns the full point, and the reward shrinks as the
  gap grows in either direction, reaching zero once the gap is large. A song
  calmer than you asked for loses just as much as one that is more energetic by
  the same amount.

Adding the three rules gives a maximum total of 4.0 (2.0 + 1.0 + 1.0). VibeFinder
ranks every song by this total, highest first, and returns the top few, five by
default. When two songs tie on the total, the one appearing earlier in the catalog
is listed first. Each recommendation comes with a short list of reasons showing
where its points came from, and those reason values always add up to the total
score. That is what makes the score transparent and explainable as defined under
Goal / Task.

These three rules are the entire recipe. The catalog also records each song's
popularity, but popularity is left out of scoring by design. It is kept only for a
separate Phase 4 experiment and has no effect on the recommendations shown today.

## Observed Behavior / Biases

Running the recipe across many taste profiles surfaced three consistent patterns:

- **Genre dominance, or a categorical moat.** A genre match is worth 2.0 and a
  mood match 1.0, so any song matching both starts at 3.0 before the energy term
  is counted. A genuine genre-plus-mood match almost always takes the top spot.
  The size of its lead depends on the profile rather than on a fixed rule. In the
  folk / nostalgic profile demonstrated below, the number one banks a 2.15-point
  lead (Wandering Roads 4.00 against Backroad Sunset 1.85), but the recipe does
  not guarantee that. A mood-only rival with a perfect energy fit reaches 2.0, and
  a genre-only rival with a perfect energy fit reaches 3.0, which is enough to tie
  a genre-plus-mood match whose own energy fit is poor. That tie is then broken
  only by catalog order. The moat holds up in practice for this catalog, but it is
  a property of these particular numbers rather than a theorem. Either way, the
  ranking is decided by genre first and everything else second.
- **Energy is only a weak tiebreaker.** The energy term runs from 0.0 to 1.0, so
  it matters when two songs already tie on genre and mood, but a single
  categorical match easily swamps it. In the Conflicted profile, a song with a
  large energy mismatch still wins comfortably because it is the only
  genre-plus-mood match.
- **A pop and high-energy catalog skew.** The catalog leans toward pop and
  high-energy songs, so mainstream, upbeat profiles get several strong matches
  while niche profiles, for example a single-song mood like dreamy or sad, fall
  back to weak energy-only matches.

## Limitations and Bias

The clearest weakness is how fragile the ranking becomes below the top match, and
how easily a popularity signal would corrupt it. The popularity experiment
(`python -m src.experiment_popularity`) adds a popularity term on top of the pure
recipe for a folk / nostalgic listener. The deserved number one, Wandering Roads,
survives. It holds a 2.15-point lead here, and popularity, which only ranges from
0.0 to 1.0, cannot close that gap until the weight passes 3.52. Sweeping every
genre-plus-mood match in the catalog, no non-matching song overtakes such a number
one below weight 2.73, well above the aggressive 2.0 the experiment uses, so the
top spot is safe at every weight shown. That moat is still a property of this
catalog's numbers rather than a guarantee of the recipe, since a genre-only rival
with a perfect energy fit can tie a genre-plus-mood match. The ranks below number
one had no such protection. Even at the mild, defensible weight of 1.0, Summer
Anthem, a pop chart hit sharing neither genre nor mood with a folk fan, climbed
into the top five and buried real near-matches, and at weight 2.0 both Summer
Anthem and Sunshine Pop did. This is the classic popularity bias and filter bubble
failure, where a crowd signal quietly overrides personal fit, and it is exactly
why the shipped recipe scores taste only and leaves popularity out.

## Evaluation

Seven profiles were tested beyond the default: four diverse (High-Energy Pop,
Chill Lofi, Deep Intense Rock, Romantic R&B) and three adversarial (Conflicted,
Ghost Genre, Energy Ceiling), plus the popularity experiment. Full output comes
from `python -m src.main` and `python -m src.experiment_popularity`. Three
comparisons tell the story.

**Comparison 1, the energy tiebreak flips a winner (default against Energy
Ceiling).** For a pop / happy listener, changing only the target energy changes
the number one song. At target 0.80 Summer Anthem (energy 0.80) wins. At target
1.0, a ceiling no song reaches, Sunshine Pop (energy 0.85, closer to 1.0) wins. A
tiny number decides the order.

```
Default (pop / happy / 0.80)          Energy Ceiling (pop / happy / 1.0)
1. Summer Anthem   (score 4.00)        1. Sunshine Pop   (score 3.85)
2. Sunshine Pop    (score 3.95)        2. Summer Anthem  (score 3.80)
```

**Comparison 2, graceful degradation (Ghost Genre against a normal pop run).**
When the requested genre, kpop, is not in the catalog, the +2.0 genre term is dead
for every song. The best possible score drops from 4.0 to 2.0 and the system ranks
on mood and energy alone. It does not crash. It just quietly loses a scoring term.

```
Ghost Genre (kpop / happy / 0.80)      High-Energy Pop (pop / happy / 0.95)
1. Summer Anthem   (score 2.00)        1. Sunshine Pop   (score 3.90)
2. Sunshine Pop    (score 1.95)        2. Summer Anthem  (score 3.85)
```

**Comparison 3, the popularity experiment (before and after, folk / nostalgic /
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

_What surprised me: how little it takes to move the number one song. A 0.05 gap in
energy is the entire reason Summer Anthem beats Sunshine Pop, and nudging the target
up to 1.0 flips the order, with no machine learning anywhere to credit or blame._

## Intended Use and Non-Intended Use

**Intended use.** VibeFinder is a teaching and demonstration tool for
content-based recommendation. It takes one listener's described taste, meaning a
genre, a mood, and a target energy level, and returns a short ranked list of songs
from a small fixed hand-authored catalog. Every match comes with a plain-language
reason, so a person can see exactly why each song was picked. Good fits include
learning how content-based scoring works, showing how a transparent scoring recipe
behaves, and giving a concrete, inspectable example of how recommendation biases
arise.

**Non-intended use.** VibeFinder is not built for and should not be used for:

- Real-world or production music recommendation. The catalog is 20 hand-authored
  songs rather than a live library, and the profile is set once in code with no
  login, interface, or feedback loop. This matches the constraints under Goal /
  Task.
- Anything needing collaborative filtering or listening history. VibeFinder never
  looks at what other users liked or at a listener's past plays, and with no such
  data collaborative filtering is not possible here.
- Music discovery of unheard tracks. It aims for fit rather than novelty, and does
  not reward or surface unfamiliar songs.
- Predicting hits, popularity, or commercial success. The catalog records a
  popularity value, but the shipped recipe never scores it. It is data only.
- Fairness-sensitive, high-stakes, or otherwise consequential decisions.
- Any claim that a VibeFinder score measures a song's quality. A score reflects
  only how closely a song's tagged attributes match the described profile under
  one fixed recipe, not whether the song is any good. Note also that it always
  returns a top-k list even when every match is weak, since there is no
  minimum-score threshold.

## Ideas for Improvement

1. **Add a diversity or anti-popularity guard to soften genre dominance.** An
   exact genre-plus-mood match reaches 3.0 before energy is counted, so one genre
   can hold the top ranks almost unbeatably, and the popularity experiment showed
   popular non-matches colonizing ranks 2 through 5. The diversity half of this
   idea is now implemented as an optional extension in `src/diversity.py`. It is a
   post-ranking selection step that caps how many same-genre songs fill the list,
   and it is kept deliberately out of the shipped recipe. Measuring it produced two
   findings that made keeping it out the right call. First, the obvious cap of no
   more than 2 per genre is dead code on this catalog. At most 2 songs share any
   genre, and no top-5 across all 231 profiles ever holds 3, so a cap of 2 can
   never fire. Only a cap of 1 does anything. Second, a cap of 1 is not free. On
   the default profile it demotes a genuine 3.95 pop/happy match and promotes a
   0.90 song matching neither the listener's genre nor mood, a measured 3.05-point
   quality cost for one slot of breadth. The anti-popularity guard remains future
   work. Either guard is a selection step layered on top of the recipe, so the base
   recipe stays three terms and popularity stays out of scoring.
2. **Expand the catalog for the thin moods.** Four moods, dreamy, intense, mellow,
   and sad, have a single song each, so those profiles get little real choice and
   the mood term barely differentiates results. Adding songs across these
   underrepresented moods would give niche profiles genuine matches and reduce the
   pop and high-energy skew of the current catalog.
3. **Add a lightweight feedback loop.** The model runs one static profile with no
   way for a listener to react, which is documented as an honest non-goal and an
   expectation gap. A simple rate-or-skip signal, or a target-energy slider to
   adjust the profile between runs, would let results respond to the listener
   instead of being fixed in code.

## Project 5 Reflection: Applied AI System (RAG Extension)

This section is my graded responsible-AI reflection for the Project 5 extension --
the RAG explanation layer I added on top of the original recommender.

### Limitations and biases in the system

The RAG layer inherits every bias of the recommender underneath it -- genre
dominance, the pop-and-high-energy skew of the catalog, the four moods that appear
on only one song -- and then adds its own. The explanation is only ever as good as
the note it retrieves: if a note is thin or slightly off, the explanation inherits
that, and my notes are hand-written, so my own wording choices are a bias baked into
the corpus. There is also a tone bias worth naming -- a fluent "why this fits you"
can sound more confident than a 0.90 energy-only match deserves, which is why every
explanation is printed next to its real score and reasons rather than replacing them.
And the retrieval itself is plain token overlap, so it would not scale past a small,
well-labeled catalog without something smarter.

### Could the AI be misused, and how I prevent it

The realistic misuse is not dramatic -- it is someone reading the generated
explanation as a factual claim about a song ("this won awards," "everyone loves
this") when it is really a vibe match for one listener's stated taste. I designed
against that three ways. First, the model is only ever allowed to ground on the
retrieved note, and the live prompt explicitly forbids inventing artists, awards,
lyrics, or chart positions. Second, when no note clears the confidence floor the
system refuses to describe the song at all and falls back to a score-only line --
no note, no claims. Third, the score and its reasons are always shown alongside the
prose, so the explanation can never be the only thing a reader sees. The LLM never
ranks, so it can never be used to quietly promote a song for a reason it will not
state.

### What surprised me while testing reliability

Two things. The one I keep coming back to: code that runs is not code that is right.
My offline explainer ran with zero errors and still produced "A classical piece by
the A." because it split the note on the first period and hit an artist's initial --
and earlier, "high energy at 0" because it split on a decimal point. Nothing crashed.
I only caught both by reading the actual output, and it made me trust green checks a
little less and my own eyes a little more. The second surprise was how clean the
"never re-rank" guarantee turned out to be once I wrote a test for it: because the
ranking is decided before the explainer ever runs, proving the AI cannot change it
was a three-line assertion, not a hope.

### My collaboration with AI (one helpful, one flawed)

**Helpful.** When I worried the project would be unreproducible if it needed an API
key, the AI suggested making the explainer default to a deterministic offline stub
and only call the live model when a key is present. That one decision is what lets
`python -m src.main` and all 62 tests run identically on any machine with no key and
no network -- it is the reason a grader can actually run this. I kept it exactly.

**Flawed.** The same AI wrote the first offline explainer using
`note.split(".")[0]` to grab the note's first sentence. It looked reasonable and ran
fine, but my notes contain decimals like "high energy at 0.85," so it truncated the
sentence at "0" and printed "high energy at 0." I caught it by running the program
and reading the output, not from any error. I replaced it with a splitter that only
treats a period as a sentence end when a space or line-end follows (and that also
skips single-letter initials like "A. Keys Trio"), and I pinned the fix with a test
that asserts the full "0.80" sentence survives. The lesson stuck: I check the AI's
output against reality rather than trusting that "it ran" means "it is correct."

## Personal Reflection

### Biggest learning moment

The biggest shift happened across the whole project rather than in one sitting,
and the clearest way to see it is to line up three moments.

Early on, deciding what to do with popularity, the AI proposed a tie-breaker.
Popularity would only matter when two songs scored exactly the same. Both debating
agents settled on that as the safe middle ground, and then both admitted it would
almost never do anything, because once the energy term is continuous, exact ties
are rare. They caught that, not me. I took the point and chose data-only instead,
adding the popularity column to the catalog without ever scoring on it.

Much later, building the diversity extension, I proposed my own rule: no more than
2 songs of any one genre in the list I show. It sounded sensible. This time,
though, I asked the question the agents had asked me. Can it ever fire? So we
measured. The catalog holds 20 songs with at most 2 of any single genre, and
across all 231 possible genre, mood, and energy profiles, no top-5 anywhere ever
contains 3 songs of one genre. A cap of 2 could never fire once. Only a cap of 1 does anything, so 1
became the default, and a test now pins that so nobody quietly changes it back.

That is the learning moment. In the first case an AI caught a dead feature for me.
In the third I caught my own. Somewhere in between I stopped asking whether an idea
sounded reasonable and started asking whether I could show it ever does anything.

The other thing that set this up was rewriting my goal statement. My first version
described what the software does: it compares genre, mood, and energy, produces a
score, returns a ranked list, and it is transparent and explainable. The problem is
that the two words carrying the most weight, transparent and explainable, had no
test attached. Anyone could disagree with me and neither of us could settle it. So
I rewrote the goal around who uses it and why, and turned those words into things I
could check. Transparent means the 0.0 to 4.0 score is shown. Explainable means the
per-term reasons must add up to that score, which became an actual test in Phase 3.

### How AI helped, and where I checked it

I ran the project with the AI working as two roles instead of one. An implementer
proposed something, an adversarial reviewer tried to break it, then they converged.
That meant I was never choosing between accepting a suggestion and writing it
myself, which is a bad choice to be handed. I was choosing between two arguments,
which is a much better place to think from.

The reviewer earned its keep. In Phase 3 it found that the energy term was being
added to the score at full precision but displayed rounded, which would have
broken the reasons-sum-to-score guarantee I had just spent the goal rewrite
defining. The fix was to round once and reuse that value, and a test guards it now.

The clearest place I overruled the AI was the popularity tie-breaker. Choosing
data-only instead meant the shipped recommender stays a pure three-term recipe
capped at 4.0, and popularity switches on only inside one controlled Phase 4
experiment that then reverts. I liked that answer because it let me demonstrate a
real bias without shipping it, where the tie-breaker version would have looked like
a decision while doing nothing.

I also caught a real bug in the agents' Phase 4 code. Their profile dictionaries
used the keys genre, mood, and energy, but score_song reads favorite_genre,
favorite_mood, and target_energy. Their profiles would have matched nothing at all,
and the experiment would have produced confident output about a catalog it was
never querying correctly.

The more honest thing to write about is where it went the other way. After I
thought the project was finished, I had a fresh reviewer audit the whole thing with
instructions not to trust any prior work and to run the code rather than read it.
It checked me, and it found three real defects.

The one that stung was this. I had written, in the popularity experiment's
conclusion and again in an earlier draft of this model card, that popular
non-matches only invade the
top 5 at the aggressive weight of 2.0. My own program's printed output, four lines
above that conclusion, already showed two songs climbing into the top 5 at weight
1.0, which the file itself calls the mild and realistic setting. The reviewer found
it starts even earlier, at 0.5. I had written that narrative from what I expected
the mild weight to do, and I had not re-read my own output. A few sections earlier
I had congratulated myself for following the numbers instead of my intuition, so
the lesson clearly had not landed as evenly as I thought.

What makes it bearable is that the honest version is the stronger result. "Even a
mild, defensible popularity weight lets chart hits into the top five" is worse for
the product and better for the report than what I originally claimed.

The same review also stress-tested my claim about a two-point moat protecting the
number one song. My headline was right and my reasoning was wrong. I had
generalized a 2.15-point gap from one profile into a rule that does not follow from
the recipe. Rather than delete the claim, the reviewer swept the 209 of those
profiles that have an exact genre-and-mood match, at 21 energy targets each, and
found the cheapest
weight at which any non-matching song unseats the pure number one is 2.73 across
the whole catalog. The finding survives, but it is now a measured property of these
20 songs instead of something I asserted.

### What surprised me about simple algorithms

A green test suite can manufacture confidence it has not earned.

load_songs crashed with an AttributeError on a CSV row cut short before the genre
and mood columns, because csv.DictReader does not drop missing trailing fields, it
fills them with None, and None.strip() raises. The row-skipping guard caught
ValueError, TypeError, and KeyError but not AttributeError. One stray line would
kill the entire catalog load.

Here is the part that got me. There was a test for exactly this case, called
test_load_songs_skips_malformed_rows, and its fixture row had 5 of the 7 columns,
so the only missing fields were numeric. float(None) raises TypeError, which was
caught. The test passed, its docstring promised short rows were handled, the README
repeated the promise, and the bug sat underneath all of it. The test was named
after a case it never actually exercised.

Early in this project I was learning to tell apart three things: I typed the
command wrong, the code is not written yet, and something is actually broken. This
added a fourth category I had not considered, which is broken while the tests
insist otherwise. That one is harder, because nothing prompts you to go looking.

Two smaller surprises, both about how visible everything is when there is no
machine learning involved. On the default pop and happy profile, Summer Anthem
beats Sunshine Pop 4.00 to 3.95, and the entire reason is that its energy of 0.80
sits one notch closer to my target than 0.85 does. Push the target to 1.0 and the
order flips. And the diversity cap surprised me in the other direction, because a
feature can be worse than useless. My cap of 2 would have passed code review,
passed every test, been documented as a bias guard, and changed nothing, ever.

### What I would try next

The anti-popularity guard is the obvious next piece, and what I would do
differently is evaluate it before writing it. Measure whether it can fire at all,
then measure what it costs when it does. I have that number for diversity. At a cap
of 1 on the default profile it evicts Sunshine Pop, a genuine 3.95 pop and happy
match, to promote an edm song at 0.90 matching neither my genre nor my mood. That
is 3.05 points of match quality spent on one slot of variety the listener never
asked for, which is why it ships as an optional side-car and stays out of the
recommender.

I would also expand the catalog. Four moods, dreamy, intense, mellow, and sad, have
only one song each, so any profile asking for them is choosing from almost nothing.
Adding songs there would do more for real output quality than any algorithm change
I could make, and it would let me test the thin-mood behavior properly instead of
documenting it as a limitation.

The recipe here is four lines of arithmetic. Genre match is worth 2.0, mood match
1.0, energy closeness up to 1.0, capped at 4.0. No training, no model, nothing
hidden. And I still managed to ship a claim contradicting my own printed output,
write a test named for a case it did not cover, and design a guard that could never
trigger. Every one of those was caught by running something and reading the number,
never by looking at the code and deciding it seemed right. If simple algorithms can
hide that much from me, I want to be a lot more suspicious of the ones I cannot
read.


# VibeFinder - Applied AI System (RAG-Extended Music Recommender)

A content-based music recommender that scores each song in a catalog against a
user's "taste profile" (favorite genre, mood, target energy) and returns a ranked
list of suggestions, each with a grounded, natural-language explanation of why it
fits you.

---

# Project 5: Applied AI System

## Original project (Modules 1-3)

This system extends **VibeFinder**, my Module 3 Music Recommender. The original
project was a content-based recommender: it loaded a 20-song catalog, scored every
song against a listener's stated taste profile using a transparent three-term recipe
(genre +2.0, mood +1.0, energy closeness up to +1.0), and returned a ranked top-5
with a rule-based reason for each pick. Its whole point was explainability -- every
number in a recommendation could be traced back to the recipe.

## Summary: what the extended system does and why it matters

For Project 5 I added a **Retrieval-Augmented Generation (RAG)** layer on top of that
recommender. The recommender still decides which songs to suggest and in what order.
The new layer then, for each chosen song, **retrieves** a factual note about it from a
local knowledge corpus and uses a language model to **generate** a short "why this
fits you" that is grounded in that retrieved note. A ranked list with "+2.0 genre
match" is correct but cold; the RAG layer turns it into an explanation a person can
actually read, without letting the model make things up.

The required AI feature is RAG, and it is **fully integrated into the main flow**:
`python -m src.main` produces the explanations by default. The generation runs
**offline and deterministically** with no API key (so it is reproducible for any
reviewer) and upgrades to a live model only when `GEMINI_API_KEY` is set.

## AI feature: Retrieval-Augmented Generation

- **Retrieve** (`src/retriever.py`): a token-overlap search over `data/song_notes.md`
  returns the best-matching note for a song plus a confidence score (0.0-1.0).
- **Augment + Generate** (`src/llm_client.py`): the retrieved note is the ONLY factual
  context handed to the explainer. In offline mode a deterministic stub composes the
  explanation from the note's first sentence plus the match reasons; in live mode a
  Gemini prompt is hard-constrained to the note and told to refuse rather than invent.
- **Orchestrate** (`src/explain.py`): ties recommend -> retrieve -> explain together,
  logs one line per recommendation (confidence, mode, whether it was grounded), and
  returns structured results.

**The central guardrail: the LLM explains, it never re-ranks.** The deterministic
score is decided before the explainer ever runs and is only read, never changed. If
retrieval finds no note above the confidence floor, the system falls back to a
score-only explanation instead of describing a song it has no facts for. Both
properties are pinned by tests.

## Architecture Overview

The system is two layers. The **deterministic core** (unchanged from Module 3) loads
`data/songs.csv`, scores and ranks the songs, and produces the final ordering. The
**RAG layer** takes that already-ranked list and attaches an explanation to each pick:
the retriever pulls the relevant note from `data/song_notes.md`, and the explainer
(offline stub or live Gemini) phrases a grounded "why," falling back to score-only if
no note is confident enough. Automated tests and human review sit on the output to
confirm the explainer never changed the ranking and never invented facts. The full
diagram source is in [`diagrams/architecture.mmd`](diagrams/architecture.mmd)
(rendered below).

![VibeFinder architecture](assets/architecture.png)

## Setup and Run

```bash
pip install -r requirements.txt

# Default: runs fully offline, deterministic, no API key needed.
python -m src.main

# Run the tests (138 tests, all offline).
python -m pytest

# Optional live mode: set a key to have Gemini phrase the explanations.
# (Offline stub is used automatically if this is unset or google-genai is absent.)
pip install google-genai

# Provide the key either as an environment variable ...
export GEMINI_API_KEY=your_key_here      # PowerShell: $env:GEMINI_API_KEY="..."
                                         # Command Prompt: set GEMINI_API_KEY=...
# ... or, to avoid retyping it, copy .env.example to .env and put the key there.
# .env is gitignored, so the key is never committed; main.py loads it automatically.
python -m src.main
```

## Optional: Web UI (Streamlit)

A small Streamlit front-end (`app.py`) is included for a point-and-click experience.
It is optional polish -- the CLI above is the graded, reproducible path -- and it adds
no new logic: it collects a taste profile from dropdowns and a slider and calls the
same `recommend` / `retrieve` / `explain` code, showing each ranked song with its
grounded explanation. It also offers a "genre variety" toggle (the diversity re-rank).

```bash
pip install streamlit
streamlit run app.py
```

Like the CLI, it runs offline by default and uses live Gemini automatically if a key
is present (shell env var or a local `.env`). A mode banner shows which is active.

It has two views. **Single** runs the finished system. **Compare** is a build-your-own
A/B lab: the same taste profile is run through two independently-configured pipelines
side by side -- each side toggles the catalog (Original 20 vs Expanded 46), RAG on/off
(grounded explanations vs original score-only reasons), live vs offline phrasing, and
genre variety. It makes the effect of each Project 5 change visible at a glance (for
example, a `metal / intense` profile has no real match on the 20-song catalog but a
full 3.95 match on the 46-song one). The comparison is authentic, not mocked: the
score-only path is the untouched Module 3 recommender and the 20-song catalog is the
original data from git history.

## The Inspector: showing the work

A recommendation that says "trust me" teaches nothing. The Inspector opens the system
up so a reader can see *why* it did what it did, and so someone who forks it can tell
whether a change they made was an improvement or a regression.

It answers two questions that are easy to confuse, and keeps them deliberately apart:

1. **Why did this song rank here?** The deterministic recipe decided that, before any
   model ran. No AI is involved.
2. **Why was *this note* retrieved to explain it?** That is the retrieval half of RAG,
   and it was previously only written to a log.

Run it in the browser (`streamlit run app.py`, then pick **Inspector**), or in the
terminal with no extra dependencies:

```bash
python -m src.inspect_cli
python -m src.inspect_cli --song "Heavy Riff"
python -m src.inspect_cli --genre metal --mood intense
```

**Panel 1, the ranking.** Every song scored, itemized into its three terms, with the
top-k cut drawn in and the near misses below it. Answering "why this one over the
rest" requires showing the rest, and the near misses are where the recipe is easiest
to read: a 3.92 losing to a 3.95 says more about the weights than the winner does.

**Panel 2, the retrieval scoreboard.** Every note scored against the song, ordered by
raw token overlap, with the `MIN_CONFIDENCE` floor marked. This is the debugging step
the RAG literature insists on: print the retrieved chunks before blaming the model.

The scoreboard is ordered by overlap rather than by what the retriever actually chose,
and that is the point. `retrieve_note` applies an exact-title tiebreak on top of
overlap, so the two orderings can disagree, and the Inspector shows when they do. It
distinguishes two cases that look alike and are not:

- a **tie** broken by title, which any tiebreak rule would have to resolve somehow
- a **strict override**, where a different note genuinely scored higher and the song's
  own note would have lost

On the shipped catalog 15 of 46 songs trigger an override but only 3 are strict
(Heavy Riff, Halcyon Drift, Delta Dust). Reporting all 15 as retrieval failures would
overstate the problem fivefold. The 3 strict cases are the honest evidence that token
overlap alone mis-retrieves: Heavy Riff's own note scores 0.50 while Concrete Anthem's
scores 0.75, because that note happens to contain the word "heavy". The exact-title
tiebreak is what rescues it, which makes that tiebreak a hand-rolled reranker.

**Panel 3, the prompt.** The exact string the model would receive. It is built even
with no API key, because assembling it is a pure function with no side effects, so
this panel stays visible in the offline configuration every reviewer runs. Seeing it
makes one thing concrete that no diagram does: retrieval's whole job is to paste the
right text into the prompt for you, on every call.

**Design constraints.** The Inspector reads the same functions the real run uses and
recomputes nothing, so it cannot disagree with the system it describes: a test pins
the scoreboard's winner against `retrieve_note` across all 46 songs. It is read-only,
and another test pins that a run's output is identical whether or not it was
inspected, which is the same shape as the guardrail that the explainer never re-ranks.
`retrieve_note` itself was not modified; `score_all_notes` was added alongside it.

**It found a real bug on its first run.** The prompt panel revealed that every live
call this project had ever made was sending a raggedly indented prompt.
`textwrap.dedent` was running *after* f-string interpolation, and since every corpus
note is two lines whose second line is unindented, dedent computed a common prefix of
nothing and stripped nothing. A single-line note dedented correctly, which is why it
went unnoticed. Templates are now dedented once at import, before substitution, and a
regression test pins the layout against a multi-line note. That is the argument for
this whole feature in one incident: the defect was invisible until the prompt was
printed.

## Sample Interactions (RAG output, captured from `python -m src.main`)

Full captured run: [`assets/sample_run.txt`](assets/sample_run.txt).

**Example 1 -- default profile (pop / happy / energy 0.8).** Both pop/happy songs
match on all three terms; the explanation is grounded in each song's note:

```
=== Recommendations for the default profile (pop / happy) [RAG] ===
1. Summer Anthem  (score 4.00)
     - genre match (+2.0)
     - mood match (+1.0)
     - energy close to target (+1.00)
     why: Summer Anthem: An upbeat pop anthem by Coast Kids, high energy at 0.80 and a danceable 120 BPM. It matched on your favorite genre, the mood you asked for, and your target energy.
          [grounded on 'Summer Anthem', confidence 1.00]
2. Sunshine Pop  (score 3.95)
     - genre match (+2.0)
     - mood match (+1.0)
     - energy close to target (+0.95)
     why: Sunshine Pop: A bright, upbeat pop track by The Brights. It matched on your favorite genre, the mood you asked for, and your target energy.
          [grounded on 'Sunshine Pop', confidence 0.67]
```

**Example 2 -- Chill Lofi (lofi / chill / energy 0.30).** A different corner of taste
space; note how the two partial matches below are explained honestly -- #2 matches
genre but not mood, #3 matches mood but not genre:

```
=== Chill Lofi (lofi / chill / energy 0.30) [RAG] ===
1. Lofi Rain  (score 4.00)
     - genre match (+2.0)
     - mood match (+1.0)
     - energy close to target (+1.00)
     why: Lofi Rain: A calm lofi beat by Study Cat, low energy at 0.30 and a slow 72 BPM. It matched on your favorite genre, the mood you asked for, and your target energy.
          [grounded on 'Lofi Rain', confidence 0.67]
2. Study Fog  (score 2.98)
     - genre match (+2.0)
     - energy close to target (+0.98)
     why: Study Fog: A lofi track built for the background, mellow and low-key at 0.28 energy over a slow 74 BPM. It matched on your favorite genre, and your target energy.
          [grounded on 'Study Fog', confidence 0.50]
3. Underwater Bloom  (score 1.90)
     - mood match (+1.0)
     - energy close to target (+0.90)
     why: Underwater Bloom: A dreampop track with a chill mood, gentle at 0.40 energy and a 100 BPM drift. It matched on the mood you asked for, and your target energy.
          [grounded on 'Underwater Bloom', confidence 0.50]
```

**Example 3 -- the guardrail firing (song with no note).** When retrieval finds no
note above the confidence floor, the system refuses to describe the song and falls
back to a score-only line (captured in [`assets/guardrail_demo.txt`](assets/guardrail_demo.txt)):

```
Retrieval for a song with no note:
  note found: False   confidence: 0.0   matched: None
  explanation: Untitled Demo: recommended on the score alone (energy close to target (+0.50)).
```

## Reliability and Guardrail Evidence

The RAG run ends with a reliability summary, and the test suite pins the guarantees:

```
### RELIABILITY SUMMARY (RAG layer) ###
10/10 explained recommendations were grounded on a retrieved note; average retrieval confidence 0.58; explainer mode = offline.
Guardrail: any recommendation with no note above the confidence floor falls back to a score-only explanation instead of inventing details.
```

```
$ python -m pytest -q
138 passed
```

| What is tested | Where | Result |
| --- | --- | --- |
| Every catalog song has a note and retrieves it | `test_retriever.py` | Pass |
| A song with no note falls back (guardrail) | `test_retriever.py`, `test_explain.py` | Pass |
| Offline explanation is deterministic | `test_explain.py` | Pass |
| Explanation is grounded in the note (no decimal/initial truncation) | `test_explain.py` | Pass |
| LLM layer never re-ranks (order + scores unchanged) | `test_explain.py` | Pass |

Test log: [`assets/pytest_summary.txt`](assets/pytest_summary.txt).

## Design Decisions and Trade-offs

- **RAG instead of a chatbot.** The recommender is the product; the AI's job is to
  explain its output trustworthily, not to replace the scoring. So the LLM sits
  downstream of a fixed ranking rather than driving it.
- **Offline stub by default.** Requiring an API key would make the project
  unreproducible for a grader. The deterministic stub means the system, its output,
  and its tests are identical on any machine; live Gemini is a strict upgrade, not a
  dependency. Trade-off: the offline wording is templated rather than fluent.
- **Token-overlap retrieval, not embeddings.** For a 20-song catalog, embeddings would
  be gold plating. A transparent overlap score is easy to log, test, and reason about.
- **Explain, never re-rank.** Keeping the LLM strictly downstream is what makes the
  system auditable: the ranking is always the deterministic recipe, and a test proves
  the explainer cannot change it.

### How the song categories are grounded

The catalog's `genre / mood / energy` schema is a deliberate, principled simplification
of how the music industry and music-information-retrieval (MIR) research categorize
tracks, not an ad-hoc choice:

- **Genre** follows the standard "one label from a bounded list" pattern. The canonical
  MIR benchmark, the GTZAN genre collection, uses a fixed set of 10 genres (blues,
  classical, country, disco, hip-hop, jazz, metal, pop, reggae, rock); this catalog
  covers all 10 plus a few adjacent labels (synthwave, lofi, edm, r&b, and others).
- **Energy** (0.0-1.0) matches Spotify's `energy` audio feature exactly in both concept
  ("perceptual intensity and activity") and scale, so this dimension mirrors a
  production system rather than inventing a metric.
- **Mood** is a single word from the common vocabulary seen in mood-tagged datasets
  (happy, sad, calm, energetic, chill, romantic...). This is a documented simplification:
  Spotify has no single mood field and instead derives mood from `valence` + `energy`,
  a 2-D model (Russell's valence-arousal circumplex). A single mood word collapses that
  plane to one point, so, for example, "sad" (low energy, low valence) and "angry" (high
  energy, low valence) are not cleanly separated. The natural upgrade -- out of this
  project's scope -- is to add a `valence` 0.0-1.0 field to recover the mood quadrant.

In short, `energy` is modeled the industry-standard way, `genre` mirrors the most-cited
MIR benchmark, and `mood` is a lightweight, interpretable stand-in for the valence axis.

Sources: GTZAN genre collection (Tzanetakis & Cook, 2002); Spotify Web API audio-features
reference (`energy`, `valence` definitions); Russell's circumplex model of affect (1980,
the valence-arousal basis for the mood quadrant).

## Testing Summary

62 automated tests pass (up from 50 in Module 3): the original 50 recipe/evaluation/
diversity tests plus 12 new ones for retrieval, grounding, the guardrail fallback, and
the no-re-rank guarantee. What worked: the offline stub made the whole feature testable
without a network, and the no-re-rank test caught exactly the risk that worried me.
What did not, at first: the offline explainer truncated notes on decimal points and on
an artist's initial ("A. Keys Trio") -- it ran without error but produced wrong text,
which I only caught by reading the output. Both are now fixed and pinned by a test.

## Reflection

My graded responsible-AI reflection -- how I collaborated with AI (one helpful and one
flawed suggestion), the system's limitations and biases, misuse and prevention, and
what surprised me in testing -- is in [`model_card.md`](model_card.md).

---

## Further reading

The deeper background material lives in two companion documents so this README stays
focused on what the system is, how to run it, and how it was decided.

- [DESIGN.md](DESIGN.md) -- how a recommender works, why VibeFinder is content-based,
  the song and taste-profile feature inventories, the scoring recipe walked through
  term by term, and the optional genre-diversity re-ranking extension.
- [EVALUATION.md](EVALUATION.md) -- the biases predicted from the recipe and from the
  catalog (including the original 20-song versus expanded 46-song history), and the
  full inventory of what the automated test suite covers.

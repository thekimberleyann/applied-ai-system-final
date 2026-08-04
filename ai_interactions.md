# AI Interactions Log -- VibeFinder

This is a curated record of the most notable interactions I had with an AI
assistant while building VibeFinder, a content-based music recommender. It is not
the full running log; it collects the interactions that best show where the AI
helped, where I verified or changed its work, and where I made the final call. For
each entry I note what I asked, what the AI produced, how I checked it, and whether
I kept, rejected, or modified the result.

Throughout the project I used a deliberate human-in-the-loop process: the AI
drafted and critiqued, and I decided.

---

## 1. Two-agent debate as the working method

**What I asked:** For each phase, I had the AI work as two roles instead of one. This
included an implementer that proposed a solution and an adversarial reviewer that tried to
break it and then converge, with the work integrated only after I reviewed it.

**What the AI produced:** Paired proposals and critiques at every phase. The
implementer drafted the recipe, code, or wording; the reviewer attacked edge
cases, hidden assumptions, and biases; the two narrowed to a recommendation.

**My verification and decision:** I read both sides each phase rather than
accepting a first draft. Keeping the reviewer role honest is what surfaced several
of the issues below.

**Decision:** Kept, as the standing method for the whole project.

---

## 2. Reframing the Goal as requirements engineering

**What I asked:** I directed the AI to rewrite the project Goal in usage-centric
terms rather than as a vague "recommend songs" statement -- to say who uses it,
what a good result looks like, how "transparent" and "explainable" would be
tested, and what the explicit non-goals were.

**What the AI produced:** A restated Goal centered on one listener getting
explainable vibe matches, with testable transparency (every score traceable to its
reasons) and a list of non-goals: no login, no live catalog, no collaborative
filtering, no feedback loop.

**My verification and decision:** I confirmed the non-goals matched the scope I
wanted and would keep the project from gold-plating. This reframe was my
direction; the AI drafted to it.

**Decision:** Kept.

---

## 3. Popularity: I overruled the AI's compromise

**What I asked:** Whether the catalog's popularity value should influence the
ranking.

**What the AI produced:** In debate, the two agents converged on a compromise --
use popularity as a small tie-breaker so that, all else equal, the more popular
song ranks higher. Both agents also admitted the tie-breaker would almost never
fire, since exact score ties are rare once the energy term is continuous.

**My verification and decision:** I rejected the compromise. Letting popularity
into the score would quietly undercut the whole point of a transparent,
content-based recipe, and it buys almost nothing. Instead I decided popularity
would be data only: keep the column in the catalog, never score it in the shipped
recipe, and use it only in a separate Phase 4 experiment to demonstrate the bias
it would introduce.

**Decision:** Rejected the AI's compromise; adopted my data-only approach.

---

## 4. Adversarial review caught a real scoring bug

**What I asked:** I had the reviewer role check whether the printed reasons would
always add up to the displayed score (the transparency guarantee).

**What the AI produced:** The reviewer found a latent bug. The energy-closeness
term was being added into the total at full floating-point precision but shown to
the listener rounded to two decimals. For some energy values the rounded reasons
would not sum to the score, which would silently break the guarantee that every
point is explained.

**My verification and decision:** I reproduced the mismatch, confirmed it was
real, and adopted the fix of rounding the energy term once and reusing that single
rounded value in both the total and the displayed reason, so the numbers always
reconcile. A test now enforces this.

**Decision:** Kept the fix (round once, reuse).

---

## 5. The Phase 4 popularity experiment: honest, not rigged

**What I asked:** To test the intuition that a niche, perfect-match song would get
buried by popular songs once popularity was allowed to matter.

**What the AI produced:** The debate showed my intuition was arithmetically wrong
for the number-one slot. Because an exact genre-plus-mood match creates a roughly
two-point lead (the "categorical moat"), the true best match still wins rank one
even under popularity pressure -- it would take an absurd popularity weight to
unseat it. The stronger, more honest finding was different: popular non-matching
songs colonize ranks 2 through 5 while the hidden gem survives at the top. The AI
ran the experiment at two different popularity weights so the result would not look
cherry-picked.

**My verification and decision:** I checked the arithmetic behind the categorical
moat and confirmed the two-weight presentation was there to keep the finding
honest rather than to manufacture a dramatic result. I kept the corrected, more
accurate framing instead of my original intuition.

**Decision:** Kept, with the finding corrected to what the numbers actually show.

---

## 6. I directed removal of the APA citations

**What I asked:** The AI had included APA-style citations in the draft materials. I
judged they were not needed for this project.

**What the AI produced:** Initially, formatted APA in-text citations and reference
lists in both the README and the model card.

**My verification and decision:** I decided the citations added overhead without
serving the project's goal, and directed their removal from both files. I confirmed
afterward that no citation text remained.

**Decision:** Rejected; removed at my direction.

---

## 7. An independent adversarial review of the finished project

**What I asked:** After the project was built, I brought in a fresh AI reviewer
and told it explicitly not to trust any of the earlier work, to verify everything
by running it rather than reading it, and to try to break the code. I wanted a
second opinion, not a rubber stamp.

**What the AI produced:** Three real defects and two inaccurate claims in my own
documentation.

1. A crash in `load_songs`. `csv.DictReader` fills a short row's missing trailing
   fields with `None`, so a row truncated before the genre or mood column made the
   code call `None.strip()` and raise `AttributeError` -- a type the row-skipping
   guard did not catch. One bad line killed the whole catalog load. What made this
   worth finding is why it survived: the test named `test_load_songs_skips_malformed_rows`
   used a fixture row with 5 of the 7 columns, so only the numeric columns were
   missing, and `float(None)` raises `TypeError`, which WAS caught. The test passed
   while the bug it was named for was live.
2. My popularity experiment's written conclusion contradicted the experiment's own
   printed output. I had written that popular non-matches invade the top five only
   at the aggressive weight 2.0. The program printed, four lines above that
   conclusion, that Summer Anthem and Velvet Touch already climb in at the mild
   weight 1.0.
3. My "roughly two-point categorical moat" did not follow from the recipe. A
   mood-only rival with a perfect energy fit reaches 2.0 and a genre-only rival
   reaches 3.0, which merely ties a genre-plus-mood match with a poor energy fit.

**My verification and decision:** I had each finding reproduced in front of me
before accepting it. The crash was demonstrated on a two-column CSV row; the
contradiction was demonstrated against the program's real terminal output; and the
moat claim was not simply deleted but stress-tested. The reviewer swept all 209
profiles in the catalog that have an exact genre-plus-mood match, at 21 energy
targets each, and computed the cheapest popularity weight at which a non-matching
song can unseat the pure number one. The answer, 2.73, sits comfortably above the
aggressive demonstration weight of 2.0, so the moat finding survives everywhere in
this catalog and was not cherry-picked. Only the justification was wrong, not the
headline. Each fix was committed separately after I confirmed the tests passed and
that the experiment's printed tables were byte-for-byte unchanged, so every number
quoted in the model card remains accurate. The suite went from 35 to 40 tests.

**Decision:** Kept all findings and all fixes. The most valuable one was not a
line of code. It was learning that a passing test can be worse than no test when
it is named after a case it does not actually exercise.

> Note (added 2026-08-04): the popularity figures in this entry were measured on
> the original 20-song catalog and were correct then. The catalog expansion the
> day before submission invalidated them without any scoring code changing. The
> gap behind the folk number one is 1.06, not 2.15. The cheapest dethroning
> weight is 1.63, not 2.73, which now sits BELOW the weight of 2.0 my own
> experiment demonstrates, so the "safe at every weight shown" claim no longer
> holds. I left the entry as written because it records what I believed at the
> time, and re-derived the current numbers with `python -m src.sweep`.

---

## 8. A diversity extension, measured before it was built

**What I asked:** I asked for a diversity guard as an optional extension, to
mitigate the genre-dominance bias I had already documented: two near-identical
pop hits crowding the top of a pop/happy ranking. My first instinct was a simple
cap: no more than 2 songs of any one genre in the shown list.

**What the AI produced:** Before writing the feature, I made the AI measure
whether my instinct would even do anything. It did not. This catalog has 20 songs
with at most 2 of any single genre, and brute-forcing all 231 (genre, mood,
energy) profiles, no top-5 anywhere ever holds 3 songs of one genre. A cap of 2
can never fire -- it would change nothing, ever. Only a cap of 1 actually alters a
result. The AI then built `src/diversity.py` as a post-ranking selection side-car,
not a scoring term: I required that, because a diversity bonus would push a score
above the fixed 0.0 to 4.0 scale and a penalty would subtract points no reason
string accounts for, breaking the reasons-sum-to-the-score guarantee. It had to
sit beside the recipe, the same shape as the popularity experiment, and pass every
score and reason through untouched.

**My verification and decision:** That dead cap was the third time this same trap
showed up in this project. The AI's popularity tie-breaker back in entry 3 would
almost never fire, and here my own diversity cap of 2 would never fire at all. I
rejected the cap of 2 and set the default to 1. Then I made the AI measure what a
cap of 1 actually costs, because it is not free. On the default profile it demotes
Sunshine Pop, a real 3.95 pop/happy match, and promotes Dance All Night at 0.90,
an edm song matching neither my genre nor my mood. That is a 3.05-point quality
cost to buy one slot of genre variety. I confirmed the numbers by running
`python -m src.diversity` myself and reading the BEFORE/AFTER. The suite went from
40 to 50 tests, and I made sure one of them pins the dead-cap finding as an
executable fact, so nobody can quietly "fix" the default back to 2 without a test
failing. I also confirmed `python -m src.main` and `python -m src.experiment_popularity`
were unchanged and that `src/recommender.py` was never modified.

**Decision:** Kept, as an optional extension explicitly OUTSIDE the shipped
recipe. Measuring the cost, demoting a 3.95 real match for a 0.90 non-match,
showed that diversity answers a different question than the one VibeFinder was
built to answer. The shipped recommender answers "what fits my vibe"; this side-car answers
"give me a spread of genres." Different question, different module.

> Note (added later): this entry records the diversity work on the ORIGINAL 20-song
> catalog. The Project 5 catalog expansion (entry 10) changed two of these numbers --
> the cap-2 "dead code" finding no longer holds (it fires on 46 songs) and the cap-1
> cost is now ~1.95 points, not 3.05. Kept as-is for the honest history; see entry 10.

---

## 9. Project 5: the RAG explanation layer (helpful design, flawed code)

**What I asked:** For the applied-AI project I asked to extend VibeFinder with a
RAG layer: retrieve a factual note about each recommended song and have a model
write a grounded "why this fits you." My one hard rule up front was that the LLM
must explain, never re-rank -- the deterministic score stays the source of truth.

**What the AI produced (helpful):** When I raised that requiring a Gemini key would
make the project unreproducible for a grader, the AI proposed defaulting to a
deterministic offline stub and only calling the live model when GEMINI_API_KEY is
set. That is the reason `python -m src.main` and all 62 tests run identically on any
machine with no key and no network. I kept it as-is.

**What the AI produced (flawed):** The first offline explainer grabbed the note's
first sentence with `note.split(".")[0]`. It ran without error but my notes contain
decimals like "high energy at 0.85," so it truncated the explanation to "high energy
at 0." A related case truncated "the A. Keys Trio" at the initial.

**My verification and decision:** I caught both by running the program and reading
the actual output, not from any error or failing check. I replaced the split with a
sentence finder that only treats a period as a boundary when a space or line-end
follows it, and that skips single-letter initials. I pinned the fix with a test
(`tests/test_explain.py::test_explanation_is_grounded_in_the_note`) that asserts the
full "0.80" sentence survives, and added tests for the no-note guardrail and for the
never-re-rank guarantee. I ran `python -m pytest` (62 passed) and re-read the
captured run in `assets/sample_run.txt` before trusting it.

**Decision:** Kept the offline-stub design and the corrected sentence handling. The
episode is the clearest example in this project of "it runs" not meaning "it is
right," and of me checking the AI's output against reality.

---

## 10. Project 5: expanding the catalog to fix its own limitations

**What I asked:** My model card documented two data biases -- a pop/high-energy
composition skew and four moods (dreamy, intense, mellow, sad) with a single song
each. Rather than just describe them, I asked an AI to design a catalog expansion
that fixes them, grounded in the categorization research (GTZAN genres, common mood
vocabulary, Spotify-style energy values).

**What the AI produced:** A proposal of 26 new songs (46 total) that rebalances
every genre to 2-3 songs, adds disco to complete all 10 GTZAN genres, gives every
mood at least 3 songs, widens the energy spread, and keeps ~11 niche low-popularity
strong-matches for the popularity experiment. It also produced a matching factual
note for each new song and a before/after balance table, and it flagged the
downstream files the change would break.

**My verification and decision:** I did not take the data as-is. Two catches: (1) the
proposed pop/happy song "Confetti Skies" had energy 0.80, identical to my default
profile, which would tie Summer Anthem at 4.00 and destroy my signature "Summer
Anthem edges Sunshine Pop by 0.05" example -- I nudged it to 0.72 to preserve that.
(2) The bigger catalog exposed a real retrieval bug: "Heavy Riff" started retrieving
"Concrete Anthem"'s note because both are rock/intense and Concrete Anthem's note
contains the word "heavy." I fixed the retriever to guarantee a song's own note wins
(exact-title tiebreaker) while still reporting body-overlap as a varied confidence. I
re-derived every affected test against the real output rather than guessing, and the
suite stayed green at 62.

**Decision:** Integrated. Importantly, the expansion SUPERSEDED the earlier
"cap of 2 is dead code" finding from entry 8: on 46 songs the default top-5 holds
three pop songs, so a cap of 2 now fires. I reframed that across the docs as a size
insight -- the diversity knob's usefulness was gated by catalog size, not by the
algorithm -- and updated the test to pin the new behavior. The catalog biases the
model card used to merely describe are now actually fixed.

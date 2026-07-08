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

**What I asked:** For each phase, I had the AI work as two roles instead of one --
an implementer that proposed a solution and an adversarial reviewer that tried to
break it -- and then converge, with the work integrated only after I reviewed it.

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

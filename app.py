"""VibeFinder -- Streamlit UI.

A thin web front-end over the SAME logic the CLI uses (src/recommender.py,
src/retriever.py, src/llm_client.py). It adds no recommendation logic of its own: it
collects a taste profile from form controls, calls the existing functions, and
renders the ranked songs with their grounded RAG explanations. The CLI
(`python -m src.main`) remains the graded, reproducible path; this is optional polish.

Two views:
- Single  -- one configuration (the finished system).
- Compare -- a "build your own model" A/B lab: the same taste profile run through two
  independently-configured pipelines side by side (catalog size, RAG on/off, live vs
  offline, genre variety), to show what each change actually did.

Run it from the repo root:

    pip install streamlit
    streamlit run app.py

Performance: defaults to the OFFLINE deterministic explainer, so first load is instant
(no network, no google-genai import). Turn on live phrasing to use Gemini (needs
GEMINI_API_KEY; one batched API call per run, subject to rate limits). Results are cached
per (profile, options) so repeats are instant.
"""

from __future__ import annotations

import os

import streamlit as st

from src.diversity import diversify
from src.glassbox import inspect_song, rank_table
from src.llm_client import VibeExplainer
from src.main import _load_dotenv_if_present
from src.recommender import load_songs, recommend_songs
from src.retriever import load_notes, missing_notes, retrieve_note

_HERE = os.path.dirname(__file__)

# The two selectable catalogs. "Original (20)" is the authentic original catalog
# pulled from git history; "Expanded (46)" is the rebalanced catalog.
# Both share the SINGLE note corpus in data/song_notes.md: every title in the
# 20-song file also appears in the 46-song file, so the corpus covers both and
# retrieval behaves the same whichever catalog a Compare side selects.
CATALOGS = {
    "Expanded (46)": os.path.join(_HERE, "data", "songs.csv"),
    "Original (20)": os.path.join(_HERE, "data", "songs_original.csv"),
}


# ----------------------------------------------------------------------------
# Cached loaders. Streamlit re-runs the whole script on every interaction, so we
# cache file loads and the explainer to keep it snappy.
# ----------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def _load_catalog(catalog_key: str) -> list[dict]:
    return load_songs(CATALOGS[catalog_key])


@st.cache_data(show_spinner=False)
def _load_corpus() -> dict:
    return load_notes()


@st.cache_resource(show_spinner=False)
def _get_explainer(force_offline: bool) -> VibeExplainer:
    """One explainer per mode, built lazily. Offline never imports google-genai.

    cache_resource (not cache_data) because a VibeExplainer holds a live client
    object: cache_data would try to serialize the return value, while
    cache_resource hands back the same instance. Keying on force_offline means
    the live and offline explainers are two separate cached instances.

    The .env load is deliberately inside the not-force_offline branch, so the
    offline path never touches the filesystem looking for a key. VibeExplainer
    reads GEMINI_API_KEY in its constructor, so the load must happen first.
    """
    if not force_offline:
        _load_dotenv_if_present()
    return VibeExplainer(force_offline=force_offline)


@st.cache_data(show_spinner=False)
def _compute(genre: str, mood: str, energy: float, k: int, catalog_key: str,
             rag_on: bool, use_live: bool, one_per_genre: bool) -> tuple[list[dict], str, int, str | None]:
    """Run one fully-configured pipeline; cached on its plain inputs.

    Returns (results, explainer_mode, catalog_size, status). When rag_on is False we
    skip retrieval/generation and return the raw recommender output (score + rule-
    based reasons only). `status` is None unless live phrasing failed (e.g. a rate
    limit) and fell back to offline, in which case it is a one-line message to show.

    This function repeats the retrieve-then-explain sequence that
    src/explain.py's explain_recommendations performs, rather than calling it,
    because the UI needs two things that function does not offer: the optional
    diversify step between ranking and explaining, and a flattened result dict
    (title/artist/genre pulled up to the top level) for the card renderer.

    Every parameter is a plain scalar or bool so st.cache_data can hash the call
    and reuse a previous run's result.
    """
    songs = _load_catalog(catalog_key)
    prefs = {"favorite_genre": genre, "favorite_mood": mood, "target_energy": energy}

    # Rank the WHOLE catalog, not just the top k. diversify drops songs whose
    # genre is already full, so it needs the ranked tail below position k to
    # backfill from; a pre-truncated top-k would leave holes instead. max()
    # keeps this correct if a caller ever asks for more songs than the catalog
    # holds (recommend_songs slices safely past the end either way).
    pool = recommend_songs(prefs, songs, k=max(k, len(songs)))
    # The chosen set is fixed HERE, before any explanation exists. Everything
    # below only attaches prose to these already-decided picks: neither
    # retrieval nor the explainer can add, drop, or reorder a song.
    chosen = diversify(pool, k=k, max_per_genre=1) if one_per_genre else pool[:k]

    if not rag_on:
        results = [{
            "title": s["title"], "artist": s["artist"], "genre": s["genre"],
            "score": sc, "reasons": r, "explanation": None,
        } for s, sc, r in chosen]
        return results, "score-only", len(songs), None

    notes = _load_corpus()
    client = _get_explainer(force_offline=not use_live)

    # Retrieve for every pick, then explain them all in ONE batched call (a single
    # API request in live mode, so a multi-song query stays under the rate limit).
    retrieved = []
    for song, score, reasons in chosen:
        note, confidence, note_title = retrieve_note(song, notes)
        retrieved.append((song, score, reasons, note, confidence, note_title))
    items = [{"song": s, "score": sc, "reasons": r, "note": n}
             for (s, sc, r, n, c, nt) in retrieved]
    explanations, status = client.explain_batch(items, prefs)

    # explain_batch returns explanations positionally aligned to `items`, so
    # zipping them back against `retrieved` pairs each song with its own text.
    results = []
    for (song, score, reasons, note, confidence, note_title), explanation in zip(
            retrieved, explanations):
        results.append({
            "title": song["title"], "artist": song["artist"], "genre": song["genre"],
            "score": score, "reasons": reasons, "explanation": explanation,
            "confidence": confidence, "grounded": note is not None,
            "note_title": note_title,
        })
    return results, client.mode, len(songs), status


# ----------------------------------------------------------------------------
# Rendering
# ----------------------------------------------------------------------------

def _render_card(rank: int, r: dict) -> None:
    """Render one result card (with or without a RAG explanation)."""
    with st.container(border=True):
        head = st.columns([0.7, 0.3])
        head[0].markdown(f"**{rank}. {r['title']}**  ·  {r['artist']}")
        head[1].markdown(f"score **{r['score']:.2f}**")
        st.caption("  ".join(f"`{reason}`" for reason in r["reasons"]))
        # RAG mode carries an explanation; score-only mode does not.
        if r.get("explanation"):
            st.write(f"_{r['explanation']}_")
            if r.get("grounded"):
                st.caption(
                    f"grounded on note '{r['note_title']}' "
                    f"(retrieval confidence {r['confidence']:.2f})"
                )
            else:
                st.caption("no note retrieved, score-only fallback (guardrail)")


def _render_results(results: list[dict]) -> None:
    """Render a stacked list of result cards (used in Single view)."""
    if not results:
        st.warning("No songs to show.")
        return
    for rank, r in enumerate(results, start=1):
        _render_card(rank, r)


def _render_compare(res_a: list[dict], res_b: list[dict]) -> None:
    """Render two result lists side by side, ROW BY ROW so rank 1 lines up with
    rank 1, etc. Paired cards in a row stretch to equal height (via CSS), so the
    two columns stay visually even even when one side's card is taller."""
    if not res_a and not res_b:
        st.warning("No songs to show.")
        return
    for i in range(max(len(res_a), len(res_b))):
        row = st.columns(2)
        with row[0]:
            if i < len(res_a):
                _render_card(i + 1, res_a[i])
        with row[1]:
            if i < len(res_b):
                _render_card(i + 1, res_b[i])


def _config_summary(cfg: dict, mode: str) -> str:
    """Short human-readable label for a side's configuration."""
    parts = ["RAG" if cfg["rag_on"] else "Score-only", cfg["catalog_key"]]
    if cfg["rag_on"]:
        parts.append("Live" if mode == "live" else "Offline")
    if cfg["one_per_genre"]:
        parts.append("Genre variety")
    return "  ·  ".join(parts)


def _side_controls(label: str, catalog_keys: list[str], key_prefix: str) -> dict:
    """Render one side's independent pipeline controls; return its config dict.

    key_prefix ("a" or "b") is folded into every widget key. Streamlit keys must
    be unique across the page, so without the prefix the two Compare sides would
    resolve to the same widget and always report identical settings.
    """
    st.markdown(f"**{label}**")
    catalog_key = st.selectbox("Catalog", catalog_keys, key=f"{key_prefix}_cat")
    rag_on = st.checkbox("RAG explanations", value=True, key=f"{key_prefix}_rag",
                         help="On: grounded natural-language 'why'. Off: the original "
                              "score-only rule reasons.")
    use_live = st.checkbox("Live AI phrasing", value=False, key=f"{key_prefix}_live",
                           disabled=not rag_on,
                           help="Only when RAG is on. Uses Gemini (needs a key; slower).")
    one_per_genre = st.checkbox("Genre variety", value=False, key=f"{key_prefix}_div",
                                help="Caps the list to ONE song per genre: only each "
                                     "genre's single top-scoring song is kept, and any "
                                     "other songs of that genre are dropped (even ones "
                                     "that would otherwise rank higher overall). Trades "
                                     "some taste-match for a wider spread of genres.")
    return {"catalog_key": catalog_key, "rag_on": rag_on,
            "use_live": use_live, "one_per_genre": one_per_genre}


# CSS to match Kim's portfolio (Blush + Lavender, IBM Plex fonts, soft gradient).
_PORTFOLIO_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Serif:wght@500;600&display=swap');

:root {
  --cream:#FDEEF1; --paper:#FFF7F9; --ink:#3A1F33; --muted:#7A5768;
  --border:#F3D6DE; --rose:#D97A8C; --rose-soft:#FBDCE3; --sage:#B08FB5;
}

html, body, [data-testid="stAppViewContainer"], [data-testid="stSidebar"],
.stMarkdown, p, div, span, label, input, button, select, textarea {
  font-family: 'IBM Plex Sans', sans-serif;
}
h1, h2, h3, h4 {
  font-family: 'IBM Plex Serif', serif !important;
  color: var(--ink); letter-spacing: -0.01em;
}
h1 { font-weight: 600; }

[data-testid="stAppViewContainer"] {
  background-color: var(--cream);
  background-image:
    radial-gradient(circle at 10% 0%, rgba(217,122,140,0.07), transparent 50%),
    radial-gradient(circle at 90% 20%, rgba(176,143,181,0.07), transparent 55%);
  background-attachment: fixed;
}

code {
  background: #F7D0D9 !important;
  color: #3A1F33 !important;
  border: 1px solid #D97A8C !important;
  border-radius: 999px; padding: 2px 11px;
  font-size: 0.82rem; font-weight: 600;
  font-family: 'IBM Plex Sans', sans-serif !important;
  white-space: nowrap;
}

[data-testid="stVerticalBlockBorderWrapper"] {
  background: var(--paper);
  border: 1px solid var(--border) !important;
  border-radius: 14px;
  box-shadow: 0 1px 3px rgba(58,31,51,0.04);
}

/* In Compare mode, paired cards sit in a two-column row; stretch them to equal
   height so the left and right cards line up evenly regardless of content length. */
[data-testid="stHorizontalBlock"] { align-items: stretch; }
[data-testid="stHorizontalBlock"] [data-testid="stVerticalBlockBorderWrapper"] {
  height: 100%;
}

[data-testid="stFormSubmitButton"] button {
  background: var(--rose); color: #fff; border: none; border-radius: 10px;
  font-weight: 500;
}
[data-testid="stFormSubmitButton"] button:hover { background: #cf6b7e; color:#fff; }

[data-testid="stAlert"] {
  background: var(--rose) !important; border-radius: 10px; border: none;
}
[data-testid="stAlert"] * { color: #fff !important; fill: #fff !important; }

::selection { background: var(--rose-soft); color: var(--ink); }
</style>
"""


def _warn_missing_notes(songs: list[dict], notes: dict) -> None:
    """Announce catalog songs that have no note of their own.

    The corpus is the retrieval system's whole knowledge, so a gap in it is a
    data problem. Those songs still get recommended and still get score-only
    reasons; they simply cannot be grounded. Saying so here is cheaper than a
    user wondering why one card reads differently from the others.
    """
    gaps = missing_notes(songs, notes)
    if gaps:
        st.warning(
            f"{len(gaps)} song(s) have no note and cannot be grounded: "
            f"{', '.join(gaps)}. They will fall back to score-only reasons."
        )


def _render_inspector(genre: str, mood: str, energy: float, k: int) -> None:
    """The glass box: show the work behind one run.

    Three panels answering three separate questions, deliberately kept apart
    because conflating them is the confusion VibeFinder's guardrail exists to
    prevent:

      1. Why did this song RANK here? The deterministic recipe, no AI involved.
      2. Why was THIS NOTE retrieved? The retrieval half of RAG.
      3. What exactly would the model be handed? The assembled prompt.

    All numbers come from src/glassbox.py, which reads the same functions the
    real run uses. Nothing is recomputed here, so this view cannot disagree with
    the system it describes.
    """
    prefs = {"favorite_genre": genre, "favorite_mood": mood, "target_energy": energy}
    songs = _load_catalog("Expanded (46)")
    notes = _load_corpus()
    _warn_missing_notes(songs, notes)

    # --- Panel 1: the ranking ------------------------------------------------
    st.subheader("Why this order")
    st.caption(
        "No AI here. This is the deterministic recipe, and it alone decides the "
        "ranking. The rows below the cut are the near misses, which is where the "
        "recipe is easiest to understand: they show what the shown songs beat."
    )

    rows = rank_table(prefs, songs, k=k)
    st.dataframe(
        [
            {
                "#": r["rank"],
                "shown": "yes" if r["shown"] else "",
                "song": r["title"],
                "genre": r["genre"],
                "mood": r["mood"],
                "total": round(r["total"], 2),
                "+genre": r["terms"]["genre"],
                "+mood": r["terms"]["mood"],
                "+energy": r["terms"]["energy"],
            }
            for r in rows
        ],
        hide_index=True,
        use_container_width=True,
    )

    with st.expander(f"Show the full ranking (all {len(songs)} songs)"):
        full = rank_table(prefs, songs, k=k, limit=len(songs))
        st.dataframe(
            [
                {"#": r["rank"], "shown": "yes" if r["shown"] else "",
                 "song": r["title"], "total": round(r["total"], 2)}
                for r in full
            ],
            hide_index=True, use_container_width=True,
        )

    # --- Panel 2 and 3: retrieval and the prompt, for one chosen song --------
    st.divider()
    shown_titles = [r["title"] for r in rows if r["shown"]]
    choice = st.selectbox(
        "Inspect the retrieval for", shown_titles,
        help="Pick any of the songs the recommender returned.",
    )
    song = next(s for s in songs if s["title"] == choice)
    record = inspect_song(prefs, song, notes)
    board = record["retrieval"]

    st.subheader("Retrieval scoreboard")
    st.caption(
        "\"Print the retrieved chunks.\" This is the first step in debugging any "
        "RAG system, and until now VibeFinder only wrote it to a log. Every note "
        "in the corpus is scored against this song; the winner grounds the "
        "explanation."
    )

    # Ordered by overlap alone, which is what a pure token-overlap retriever
    # would have returned. Showing that ordering (rather than the tiebreak-
    # adjusted one) is what makes a disagreement between the two visible.
    top_rows = board["board"][:10]
    st.dataframe(
        [
            {
                "note": row["title"],
                "overlap": row["overlap"],
                "exact title": "yes" if row["exact"] else "",
                "picked": "PICKED" if row["title"] == board["picked_title"] else "",
                "above floor": "yes" if row["above_floor"] else "no",
            }
            for row in top_rows
        ],
        hide_index=True, use_container_width=True,
    )
    st.caption(
        f"Confidence floor is {board['floor']:.2f}. Below it the system reports no "
        "usable note and falls back to a score-only explanation rather than letting "
        "the model invent facts."
    )

    if not board["grounded"]:
        st.warning(
            "Nothing cleared the floor, so the score-only fallback ran. That is the "
            "guardrail: no facts means no grounded claim."
        )
    elif board["strict_override"]:
        st.error(
            f"Token overlap alone would have retrieved **{board['overlap_winner']}** at "
            f"{board['board'][0]['overlap']:.2f}, beating this song's own note at "
            f"{board['confidence']:.2f}. The exact-title tiebreak overrode it. That "
            "tiebreak is a hand-rolled reranker, and this is a genuine case of "
            "keyword retrieval fetching the wrong document."
        )
    elif board["tiebreak_overrode"]:
        st.info(
            f"Tied with **{board['overlap_winner']}** on overlap; the exact-title "
            "tiebreak chose this song's own note. A tie, not a mis-retrieval."
        )

    st.subheader("The prompt that would be sent")
    st.caption(
        "\"RAG is automated paste.\" Retrieval's whole job is to put the right text "
        "into the prompt for you, on every call. Building this string needs no API "
        "key, so it is shown in offline mode too."
    )
    if record["prompt"] is None:
        st.warning(f"No prompt built: {record['prompt_withheld_reason']}.")
    else:
        st.code(record["prompt"], language="text")
        st.caption(
            "The note above is the ONLY song fact the model receives. The match "
            "reasons are passed in as already decided, which is how the ranking "
            "stays authoritative and the model is left to phrase, not to judge."
        )


def main() -> None:
    st.set_page_config(page_title="VibeFinder", layout="wide")
    st.markdown(_PORTFOLIO_CSS, unsafe_allow_html=True)

    # A representative catalog just to populate the genre/mood dropdowns.
    ref_songs = _load_catalog("Expanded (46)")
    genres = sorted({s["genre"] for s in ref_songs})
    moods = sorted({s["mood"] for s in ref_songs})

    # View mode lives OUTSIDE the form so switching it re-renders the controls
    # immediately; everything else is inside a form so it only runs on submit.
    with st.sidebar:
        st.header("VibeFinder")
        view = st.radio(
            "View", ["Single", "Compare", "Inspector"], horizontal=True,
            help="Single runs the finished system (recommender + RAG explanations). "
                 "Compare lets you build two pipelines from the same taste profile and "
                 "see them side by side, to show what each change actually did. "
                 "Inspector opens the glass box: the score breakdown, the full "
                 "retrieval scoreboard, and the exact prompt the model would receive.",
        )

        with st.form("controls"):
            st.subheader("Taste profile")
            genre = st.selectbox("Favorite genre", genres,
                                 index=genres.index("pop") if "pop" in genres else 0)
            mood = st.selectbox("Favorite mood", moods,
                                index=moods.index("happy") if "happy" in moods else 0)
            energy = st.slider("Target energy", 0.0, 1.0, 0.80, 0.05,
                               help="0.0 = very calm, 1.0 = very energetic")
            k = st.slider("How many songs", 1, 10, 5)

            if view in ("Single", "Inspector"):
                st.divider()
                # Single view has no RAG toggle: it always runs the finished
                # system with explanations on. Turning RAG off is a Compare-view
                # experiment, so the flag is hard-coded True rather than exposed.
                single_rag = True
                single_live = st.checkbox("Use live AI phrasing (slower)", value=False,
                                          help="Off: instant offline explanations. On: "
                                               "Gemini phrases each one (needs a key).")
                single_div = st.checkbox("Genre variety (one per genre)", value=False,
                                         help="Caps the list to ONE song per genre: only "
                                              "each genre's single top-scoring song is "
                                              "kept, and any other songs of that genre "
                                              "are dropped (even ones that would "
                                              "otherwise rank higher overall). Trades "
                                              "some taste-match for a wider spread of "
                                              "genres.")
                cfg_a = cfg_b = None
            else:
                st.divider()
                st.caption("Configure each side independently:")
                cfg_a = _side_controls("Side A", list(CATALOGS.keys()), "a")
                st.divider()
                cfg_b = _side_controls("Side B", list(CATALOGS.keys()), "b")
                single_rag = single_live = single_div = None

            submitted = st.form_submit_button(
                "Compare" if view == "Compare" else "Find songs",
                use_container_width=True, type="primary")

    # --- Main content -----------------------------------------------------
    st.title("VibeFinder")
    st.caption(
        "A content-based music recommender with grounded, plain-language "
        "explanations. Build a taste profile and see what fits your vibe, and why."
    )

    # Collapsible explainer, open by default. Explains both views and what each
    # toggle in Compare mode actually changes, so a first-time viewer understands
    # what is being compared and why it matters.
    with st.expander("About VibeFinder: what you're looking at", expanded=True):
        st.markdown(
            "**VibeFinder** started as a simple music recommender (it scores each song "
            "on genre, mood, and energy, and returns a ranked list with terse rule-based "
            "reasons). It was then extended with a **RAG explanation layer** that "
            "retrieves a factual note about each pick and writes a grounded plain-language "
            "*why this fits you*, plus an expanded and rebalanced song catalog.\n\n"
            "- **Single view** runs the finished system: the recommender plus RAG "
            "explanations, on the expanded 46-song catalog.\n"
            "- **Compare view** is a build-your-own A/B lab. The same taste profile is "
            "run through **two pipelines side by side**, and you flip each change "
            "independently on each side to see what it did:\n"
            "    - **Catalog:** Original 20 vs Expanded 46 (rebalanced). Shows the "
            "effect of fixing the pop/high-energy skew and the thin moods. For example, "
            "a *metal / intense* profile has no real match on 20 songs but a full match "
            "on 46.\n"
            "    - **RAG explanations:** off gives the terse score-only reasons; on "
            "gives the grounded natural-language explanation.\n"
            "    - **Live AI phrasing:** offline deterministic wording vs Gemini-written "
            "(needs a key).\n"
            "    - **Genre variety:** cap the list to one song per genre.\n\n"
            "The comparison is authentic: the score-only path is the untouched original "
            "recommender, and the 20-song catalog is the original data."
        )

    st.subheader(f"{genre} / {mood} / energy {energy:.2f}")
    if view == "Compare":
        st.caption("Same taste profile, two pipelines. Configure each side in the sidebar.")

    if view == "Inspector":
        _render_inspector(genre, mood, energy, k)
        return

    if view == "Single":
        with st.spinner("Finding your vibe..."):
            results, mode, size, status = _compute(genre, mood, energy, k,
                                                   "Expanded (46)", single_rag,
                                                   single_live, single_div)
        mode_label = "Live (Gemini)" if mode == "live" else "Offline (deterministic)"
        st.info(f"Explainer mode: **{mode_label}**  |  catalog: {size} songs")
        _warn_missing_notes(_load_catalog("Expanded (46)"), _load_corpus())
        if status:
            st.warning(status)
        # Full-width results, spanning the screen like the banner above.
        _render_results(results)
        return

    # Compare view: two independently-configured pipelines, same profile.
    with st.spinner("Running both pipelines..."):
        res_a, mode_a, size_a, status_a = _compute(genre, mood, energy, k,
                                                   cfg_a["catalog_key"], cfg_a["rag_on"],
                                                   cfg_a["use_live"], cfg_a["one_per_genre"])
        res_b, mode_b, size_b, status_b = _compute(genre, mood, energy, k,
                                                   cfg_b["catalog_key"], cfg_b["rag_on"],
                                                   cfg_b["use_live"], cfg_b["one_per_genre"])

    # Show any live-fallback status once (both sides usually share the same message).
    # dict.fromkeys drops duplicate strings while keeping first-seen order, so two
    # sides that hit the same rate limit produce one banner, not two identical ones.
    for msg in dict.fromkeys(s for s in (status_a, status_b) if s):
        st.warning(msg)

    # Config banners as a paired header row, then the results row by row so the
    # two columns line up rank for rank with matching card heights.
    head = st.columns(2)
    head[0].info(_config_summary(cfg_a, mode_a) + f"  ·  {size_a} songs")
    head[1].info(_config_summary(cfg_b, mode_b) + f"  ·  {size_b} songs")
    _render_compare(res_a, res_b)


if __name__ == "__main__":
    main()

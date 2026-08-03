"""VibeFinder -- Streamlit UI.

A thin web front-end over the SAME logic the CLI uses (src/recommender.py,
src/retriever.py, src/llm_client.py). It adds no recommendation logic of its own: it
collects a taste profile from form controls, calls the existing functions, and
renders the ranked songs with their grounded RAG explanations. The CLI
(`python -m src.main`) remains the graded, reproducible path; this is optional polish.

Two views:
- Single  -- one configuration (the finished Project 5 system).
- Compare -- a "build your own model" A/B lab: the same taste profile run through two
  independently-configured pipelines side by side (catalog size, RAG on/off, live vs
  offline, genre variety), to show what each Project 5 change actually did.

Run it from the repo root:

    pip install streamlit
    streamlit run app.py

Performance: defaults to the OFFLINE deterministic explainer, so first load is instant
(no network, no google-genai import). Turn on live phrasing to use Gemini (needs
GEMINI_API_KEY; one API call per song, subject to rate limits). Results are cached
per (profile, options) so repeats are instant.
"""

from __future__ import annotations

import os

import streamlit as st

from src.diversity import diversify
from src.llm_client import VibeExplainer
from src.main import _load_dotenv_if_present
from src.recommender import load_songs, recommend_songs
from src.retriever import load_notes, retrieve_note

_HERE = os.path.dirname(__file__)

# The two selectable catalogs. "Original (20)" is the authentic Module 3 catalog
# pulled from git history; "Expanded (46)" is the rebalanced Project 5 catalog.
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
    """One explainer per mode, built lazily. Offline never imports google-genai."""
    if not force_offline:
        _load_dotenv_if_present()
    return VibeExplainer(force_offline=force_offline)


@st.cache_data(show_spinner=False)
def _compute(genre: str, mood: str, energy: float, k: int, catalog_key: str,
             rag_on: bool, use_live: bool, one_per_genre: bool) -> tuple[list[dict], str, int]:
    """Run one fully-configured pipeline; cached on its plain inputs.

    Returns (results, explainer_mode, catalog_size). When rag_on is False we skip
    retrieval/generation entirely and return the raw recommender output (the
    original Module 3 behavior: score + rule-based reasons only).
    """
    songs = _load_catalog(catalog_key)
    prefs = {"favorite_genre": genre, "favorite_mood": mood, "target_energy": energy}

    pool = recommend_songs(prefs, songs, k=max(k, len(songs)))
    chosen = diversify(pool, k=k, max_per_genre=1) if one_per_genre else pool[:k]

    if not rag_on:
        results = [{
            "title": s["title"], "artist": s["artist"], "genre": s["genre"],
            "score": sc, "reasons": r, "explanation": None,
        } for s, sc, r in chosen]
        return results, "score-only", len(songs)

    notes = _load_corpus()
    client = _get_explainer(force_offline=not use_live)
    results = []
    for song, score, reasons in chosen:
        note, confidence, note_title = retrieve_note(song, notes)
        results.append({
            "title": song["title"], "artist": song["artist"], "genre": song["genre"],
            "score": score, "reasons": reasons, "explanation": client.explain(
                song, score, reasons, note, prefs),
            "confidence": confidence, "grounded": note is not None,
            "note_title": note_title,
        })
    return results, client.mode, len(songs)


# ----------------------------------------------------------------------------
# Rendering
# ----------------------------------------------------------------------------

def _render_results(results: list[dict]) -> None:
    """Render a list of result cards (with or without RAG explanations)."""
    if not results:
        st.warning("No songs to show.")
        return
    for rank, r in enumerate(results, start=1):
        with st.container(border=True):
            head = st.columns([0.7, 0.3])
            head[0].markdown(f"**{rank}. {r['title']}** — {r['artist']}")
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
                    st.caption("no note retrieved — score-only fallback (guardrail)")


def _config_summary(cfg: dict, mode: str) -> str:
    """Short human-readable label for a side's configuration."""
    parts = ["RAG" if cfg["rag_on"] else "Score-only", cfg["catalog_key"]]
    if cfg["rag_on"]:
        parts.append("Live" if mode == "live" else "Offline")
    if cfg["one_per_genre"]:
        parts.append("Genre variety")
    return "  ·  ".join(parts)


def _side_controls(label: str, catalog_keys: list[str], key_prefix: str) -> dict:
    """Render one side's independent pipeline controls; return its config dict."""
    st.markdown(f"**{label}**")
    catalog_key = st.selectbox("Catalog", catalog_keys, key=f"{key_prefix}_cat")
    rag_on = st.checkbox("RAG explanations", value=True, key=f"{key_prefix}_rag",
                         help="On: grounded natural-language 'why'. Off: the original "
                              "score-only rule reasons.")
    use_live = st.checkbox("Live AI phrasing", value=False, key=f"{key_prefix}_live",
                           disabled=not rag_on,
                           help="Only when RAG is on. Uses Gemini (needs a key; slower).")
    one_per_genre = st.checkbox("Genre variety", value=False, key=f"{key_prefix}_div",
                                help="Mix up the results so you don't get several "
                                     "songs from the same genre.")
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
            "View", ["Single", "Compare"], horizontal=True,
            help="Single runs the finished system (recommender + RAG explanations). "
                 "Compare lets you build two pipelines from the same taste profile and "
                 "see them side by side, to show what each change actually did.",
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

            if view == "Single":
                st.divider()
                single_rag = True
                single_live = st.checkbox("Use live AI phrasing (slower)", value=False,
                                          help="Off: instant offline explanations. On: "
                                               "Gemini phrases each one (needs a key).")
                single_div = st.checkbox("Genre variety (one per genre)", value=False,
                                         help="Mix up the results so you don't get "
                                              "several songs from the same genre.")
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
    with st.expander("About VibeFinder — what you're looking at", expanded=True):
        st.markdown(
            "**VibeFinder** started as a simple music recommender -- score each song on "
            "genre, mood, and energy, and return a ranked list with terse rule-based "
            "reasons -- and was extended with a **RAG explanation layer** that retrieves "
            "a factual note about each pick and writes a grounded plain-language *why "
            "this fits you*, plus an expanded and rebalanced song catalog.\n\n"
            "- **Single view** runs the finished system: the recommender plus RAG "
            "explanations, on the expanded 46-song catalog.\n"
            "- **Compare view** is a build-your-own A/B lab. The same taste profile is "
            "run through **two pipelines side by side**, and you flip each change "
            "independently on each side to see what it did:\n"
            "    - **Catalog** — Original 20 vs Expanded 46 (rebalanced). Shows the "
            "effect of fixing the pop/high-energy skew and the thin moods (e.g. a "
            "*metal / intense* profile has no real match on 20 songs but a full match "
            "on 46).\n"
            "    - **RAG explanations** — off gives the terse score-only reasons; on "
            "gives the grounded natural-language explanation.\n"
            "    - **Live AI phrasing** — offline deterministic wording vs Gemini-"
            "written (needs a key).\n"
            "    - **Genre variety** — cap the list to one song per genre.\n\n"
            "The comparison is authentic: the score-only path is the untouched original "
            "recommender, and the 20-song catalog is the original data."
        )

    st.subheader(f"{genre} / {mood} / energy {energy:.2f}")
    if view == "Compare":
        st.caption("Same taste profile, two pipelines. Configure each side in the sidebar.")

    if view == "Single":
        with st.spinner("Finding your vibe..."):
            results, mode, size = _compute(genre, mood, energy, k, "Expanded (46)",
                                           single_rag, single_live, single_div)
        mode_label = "Live (Gemini)" if mode == "live" else "Offline (deterministic)"
        st.info(f"Explainer mode: **{mode_label}**  |  catalog: {size} songs")
        # Full-width results, spanning the screen like the banner above.
        _render_results(results)
        return

    # Compare view: two independently-configured pipelines, same profile.
    with st.spinner("Running both pipelines..."):
        res_a, mode_a, size_a = _compute(genre, mood, energy, k,
                                         cfg_a["catalog_key"], cfg_a["rag_on"],
                                         cfg_a["use_live"], cfg_a["one_per_genre"])
        res_b, mode_b, size_b = _compute(genre, mood, energy, k,
                                         cfg_b["catalog_key"], cfg_b["rag_on"],
                                         cfg_b["use_live"], cfg_b["one_per_genre"])

    col_a, col_b = st.columns(2)
    with col_a:
        st.info(_config_summary(cfg_a, mode_a) + f"  ·  {size_a} songs")
        _render_results(res_a)
    with col_b:
        st.info(_config_summary(cfg_b, mode_b) + f"  ·  {size_b} songs")
        _render_results(res_b)


if __name__ == "__main__":
    main()

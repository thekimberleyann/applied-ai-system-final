"""VibeFinder -- Streamlit UI.

A thin web front-end over the SAME logic the CLI uses (src/recommender.py,
src/retriever.py, src/llm_client.py). It adds no recommendation logic of its own: it
collects a taste profile from form controls, calls the existing functions, and
renders the ranked songs with their grounded RAG explanations. The CLI
(`python -m src.main`) remains the graded, reproducible path; this is optional polish.

Run it from the repo root:

    pip install streamlit
    streamlit run app.py

Performance notes:
- The UI defaults to the OFFLINE deterministic explainer, so first load is instant --
  no network and no google-genai import. Turn on "Use live AI phrasing" in the sidebar
  to have Gemini phrase the explanations (needs GEMINI_API_KEY; slower, one API call
  per song, and subject to rate limits).
- Results are cached per (profile, options, mode), so repeating a query is instant.
"""

from __future__ import annotations

import os

import streamlit as st

from src.diversity import diversify
from src.llm_client import VibeExplainer
from src.main import _load_dotenv_if_present
from src.recommender import load_songs, recommend_songs
from src.retriever import load_notes, retrieve_note

DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "songs.csv")


# ----------------------------------------------------------------------------
# Cached loaders. Streamlit re-runs this whole script on every interaction, so we
# cache the catalog, the note corpus, and the explainer to avoid reloading files
# and re-constructing the client on each click.
# ----------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def _load_catalog() -> list[dict]:
    return load_songs(DATA_PATH)


@st.cache_data(show_spinner=False)
def _load_corpus() -> dict:
    return load_notes()


@st.cache_resource(show_spinner=False)
def _get_explainer(force_offline: bool) -> VibeExplainer:
    """One explainer per mode, built lazily.

    force_offline=True (the default UI mode) never imports google-genai or touches
    the network, so the first render is instant. Only when the user opts into live
    phrasing do we load a .env and construct a live client.
    """
    if not force_offline:
        _load_dotenv_if_present()
    return VibeExplainer(force_offline=force_offline)


@st.cache_data(show_spinner=False)
def _compute(genre: str, mood: str, energy: float, k: int,
             one_per_genre: bool, use_live: bool) -> tuple[list[dict], str]:
    """Recommend -> (optionally diversify) -> retrieve -> explain, cached.

    Cached on the plain, hashable inputs so re-selecting the same query returns
    instantly instead of recomputing (and, in live mode, re-calling the API).
    Returns (results, explainer_mode). Mirrors src/explain.py plus the optional
    genre-diversity selection; the ranking is still the deterministic recipe and the
    explainer only adds prose.
    """
    songs = _load_catalog()
    notes = _load_corpus()
    client = _get_explainer(force_offline=not use_live)

    prefs = {"favorite_genre": genre, "favorite_mood": mood, "target_energy": energy}

    # Ask for a generous pool so the diversity cap has room to backfill across genres.
    pool = recommend_songs(prefs, songs, k=max(k, len(songs)))
    chosen = diversify(pool, k=k, max_per_genre=1) if one_per_genre else pool[:k]

    results = []
    for song, score, reasons in chosen:
        note, confidence, note_title = retrieve_note(song, notes)
        explanation = client.explain(song, score, reasons, note, prefs)
        results.append({
            "title": song["title"], "artist": song["artist"], "genre": song["genre"],
            "score": score, "reasons": reasons, "confidence": confidence,
            "grounded": note is not None, "note_title": note_title,
            "explanation": explanation,
        })
    return results, client.mode


# CSS to match Kim's portfolio (Blush + Lavender, IBM Plex fonts, soft gradient).
# Base colors come from .streamlit/config.toml; this adds the web fonts, the gradient
# background, and chip/card polish that config alone cannot express.
_PORTFOLIO_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Serif:wght@500;600&display=swap');

:root {
  --cream:#FDEEF1; --paper:#FFF7F9; --ink:#3A1F33; --muted:#7A5768;
  --border:#F3D6DE; --rose:#D97A8C; --rose-soft:#FBDCE3; --sage:#B08FB5;
}

/* Body font: IBM Plex Sans everywhere. */
html, body, [data-testid="stAppViewContainer"], [data-testid="stSidebar"],
.stMarkdown, p, div, span, label, input, button, select, textarea {
  font-family: 'IBM Plex Sans', sans-serif;
}
/* Display font: IBM Plex Serif for headings, in deep-plum ink. */
h1, h2, h3, h4 {
  font-family: 'IBM Plex Serif', serif !important;
  color: var(--ink); letter-spacing: -0.01em;
}
h1 { font-weight: 600; }

/* Blush page with the portfolio's soft radial gradients. */
[data-testid="stAppViewContainer"] {
  background-color: var(--cream);
  background-image:
    radial-gradient(circle at 10% 0%, rgba(217,122,140,0.07), transparent 50%),
    radial-gradient(circle at 90% 20%, rgba(176,143,181,0.07), transparent 55%);
  background-attachment: fixed;
}

/* Reason tags render as inline <code>; style them as rose chips. */
code {
  background: var(--rose-soft) !important; color: var(--ink) !important;
  border-radius: 6px; padding: 1px 7px; font-size: 0.8rem;
  font-family: 'IBM Plex Sans', sans-serif !important;
}

/* Recommendation cards: paper surface, soft rose hairline, rounded. */
[data-testid="stVerticalBlockBorderWrapper"] {
  background: var(--paper);
  border: 1px solid var(--border) !important;
  border-radius: 14px;
  box-shadow: 0 1px 3px rgba(58,31,51,0.04);
}

/* Rose primary button. */
[data-testid="stFormSubmitButton"] button {
  background: var(--rose); color: #fff; border: none; border-radius: 10px;
  font-weight: 500;
}
[data-testid="stFormSubmitButton"] button:hover { background: #cf6b7e; color:#fff; }

/* Info banner tinted lavender rather than default blue. */
[data-testid="stAlert"] {
  background: #ECDCEF; color: var(--ink); border-radius: 10px;
}

::selection { background: var(--rose-soft); color: var(--ink); }
</style>
"""


def main() -> None:
    # Wide layout so the app uses the full window and scales with the screen; the
    # content is then held in a responsive centered column below.
    st.set_page_config(page_title="VibeFinder", layout="wide")
    st.markdown(_PORTFOLIO_CSS, unsafe_allow_html=True)

    songs = _load_catalog()
    genres = sorted({s["genre"] for s in songs})
    moods = sorted({s["mood"] for s in songs})

    # --- Sidebar controls -------------------------------------------------
    # Everything lives inside a FORM, so changing a dropdown or slider does NOT
    # recompute -- the app only re-runs when the user clicks "Find songs". This
    # keeps it from re-querying (and, in live mode, re-calling the API) on every keystroke.
    with st.sidebar:
        st.header("Your taste profile")
        with st.form("profile_form"):
            genre = st.selectbox("Favorite genre", genres,
                                 index=genres.index("pop") if "pop" in genres else 0)
            mood = st.selectbox("Favorite mood", moods,
                                index=moods.index("happy") if "happy" in moods else 0)
            energy = st.slider("Target energy", 0.0, 1.0, 0.80, 0.05,
                               help="0.0 = very calm, 1.0 = very energetic")
            k = st.slider("How many songs", 1, 10, 5)
            one_per_genre = st.checkbox(
                "Genre variety (one per genre)",
                value=False,
                help="Optional diversity re-ranking: show a spread of genres instead "
                     "of letting one genre dominate. Trades some taste-match for variety.",
            )
            use_live = st.checkbox(
                "Use live AI phrasing (slower)",
                value=False,
                help="Off: instant, deterministic offline explanations. On: Gemini "
                     "phrases each explanation (needs GEMINI_API_KEY; one API call per "
                     "song, and subject to rate limits).",
            )
            # No rerun happens until this is clicked; on first load it renders with
            # the defaults above and shows a default set of recommendations.
            st.form_submit_button("Find songs", use_container_width=True, type="primary")

    # --- Main content, held in a responsive centered column ---------------
    # The middle column carries the content; the side spacers keep line length
    # comfortable on very wide screens while everything still scales with the window.
    left, center, right = st.columns([1, 4, 1])
    with center:
        st.title("VibeFinder")
        st.caption(
            "A content-based music recommender with grounded, plain-language "
            "explanations. Pick a taste profile and see what fits your vibe, and why."
        )

        with st.spinner("Finding your vibe..."):
            results, mode = _compute(genre, mood, energy, k, one_per_genre, use_live)

        mode_label = "Live (Gemini)" if mode == "live" else "Offline (deterministic)"
        st.info(f"Explainer mode: **{mode_label}**  |  catalog: {len(songs)} songs")

        st.subheader(f"Recommendations for {genre} / {mood} / energy {energy:.2f}")

        if not results:
            st.warning("No songs to show.")
            return

        for rank, r in enumerate(results, start=1):
            with st.container(border=True):
                head = st.columns([0.72, 0.28])
                head[0].markdown(f"**{rank}. {r['title']}** — {r['artist']}")
                head[1].markdown(f"score **{r['score']:.2f}**")
                st.caption("  ".join(f"`{reason}`" for reason in r["reasons"]))
                st.write(f"_{r['explanation']}_")
                if r["grounded"]:
                    st.caption(
                        f"grounded on note '{r['note_title']}' "
                        f"(retrieval confidence {r['confidence']:.2f})"
                    )
                else:
                    st.caption("no note retrieved — score-only fallback (guardrail)")


if __name__ == "__main__":
    main()

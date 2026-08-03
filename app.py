"""VibeFinder -- Streamlit UI.

A thin web front-end over the SAME logic the CLI uses (src/recommender.py,
src/retriever.py, src/llm_client.py). It adds no recommendation logic of its own: it
collects a taste profile from form controls, calls the existing functions, and
renders the ranked songs with their grounded RAG explanations. The CLI
(`python -m src.main`) remains the graded, reproducible path; this is optional polish.

Run it from the repo root:

    pip install streamlit
    streamlit run app.py

Offline by default (deterministic, no key). If GEMINI_API_KEY is set (in the shell
or a local .env), the explanations are phrased live by Gemini instead.
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

@st.cache_data
def _load_catalog() -> list[dict]:
    return load_songs(DATA_PATH)


@st.cache_data
def _load_corpus() -> dict:
    return load_notes()


@st.cache_resource
def _get_explainer() -> VibeExplainer:
    # Pull in a local .env first so a key stored there enables live mode, exactly
    # as the CLI does. cache_resource keeps a single explainer for the session.
    _load_dotenv_if_present()
    return VibeExplainer()


def _recommend(prefs: dict, songs: list[dict], notes: dict, client: VibeExplainer,
               k: int, one_per_genre: bool) -> list[dict]:
    """Recommend -> (optionally diversify) -> retrieve -> explain.

    Mirrors src/explain.py but adds the optional genre-diversity selection so the UI
    can offer it as a toggle. The ranking still comes from the deterministic recipe;
    diversify only drops same-genre repeats, and the explainer only adds prose.
    """
    # Ask for a generous pool so the diversity cap has room to backfill across genres.
    pool = recommend_songs(prefs, songs, k=max(k, len(songs)))
    if one_per_genre:
        chosen = diversify(pool, k=k, max_per_genre=1)
    else:
        chosen = pool[:k]

    results = []
    for song, score, reasons in chosen:
        note, confidence, note_title = retrieve_note(song, notes)
        explanation = client.explain(song, score, reasons, note, prefs)
        results.append({
            "song": song, "score": score, "reasons": reasons,
            "confidence": confidence, "grounded": note is not None,
            "note_title": note_title, "explanation": explanation,
        })
    return results


def main() -> None:
    st.set_page_config(page_title="VibeFinder", page_icon="🎵", layout="centered")

    songs = _load_catalog()
    notes = _load_corpus()
    client = _get_explainer()

    st.title("🎵 VibeFinder")
    st.caption(
        "A content-based music recommender with grounded, plain-language "
        "explanations. Pick a taste profile and see what fits your vibe -- and why."
    )

    # Distinct, sorted option lists straight from the catalog, so the dropdowns can
    # only offer genres/moods that actually exist in the data.
    genres = sorted({s["genre"] for s in songs})
    moods = sorted({s["mood"] for s in songs})

    # --- Controls ---------------------------------------------------------
    with st.sidebar:
        st.header("Your taste profile")
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
            help="Optional diversity re-ranking: show a spread of genres instead of "
                 "letting one genre dominate. Trades some taste-match for variety.",
        )

    # A small banner so it is always clear whether prose is live or offline.
    mode_label = ("Live (Gemini)" if client.mode == "live"
                  else "Offline (deterministic stub)")
    st.info(f"Explainer mode: **{mode_label}**  |  catalog: {len(songs)} songs")

    prefs = {"favorite_genre": genre, "favorite_mood": mood, "target_energy": energy}
    results = _recommend(prefs, songs, notes, client, k, one_per_genre)

    st.subheader(f"Recommendations for {genre} / {mood} / energy {energy:.2f}")

    if not results:
        st.warning("No songs to show.")
        return

    for rank, r in enumerate(results, start=1):
        song = r["song"]
        with st.container(border=True):
            top = st.columns([0.75, 0.25])
            top[0].markdown(f"**{rank}. {song['title']}** — {song['artist']}")
            top[1].markdown(f"score **{r['score']:.2f}**")
            # The deterministic reasons as small tags.
            st.caption("  ".join(f"`{reason}`" for reason in r["reasons"]))
            # The RAG explanation.
            st.write(f"_{r['explanation']}_")
            # Provenance: grounded on which note, and how confident retrieval was.
            if r["grounded"]:
                st.caption(
                    f"grounded on note '{r['note_title']}' "
                    f"(retrieval confidence {r['confidence']:.2f})"
                )
            else:
                st.caption("no note retrieved — score-only fallback (guardrail)")


if __name__ == "__main__":
    main()

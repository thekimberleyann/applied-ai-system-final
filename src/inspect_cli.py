"""Text rendering of the glass box, so it runs without Streamlit.

The inspection LOGIC lives in src/glassbox.py and returns plain data structures.
This module only turns that data into text. Keeping the two apart buys three
things: the lab works for anyone who does not install the web UI, the logic is
testable without driving a UI harness, and this output can be committed as
execution evidence in the same way assets/sample_run.txt already is.

Run with:  python -m src.inspect_cli
           python -m src.inspect_cli --song "Heavy Riff"
"""

from __future__ import annotations

import argparse
import os

from src.glassbox import inspect_run, retrieval_board
from src.recommender import load_songs
from src.retriever import load_notes

_DATA = os.path.join(os.path.dirname(__file__), "..", "data")

# Caption text tying each panel to the concept it demonstrates, so someone who
# forks this can see which part of a RAG system they are looking at.
CAPTIONS = {
    "ranking": "no AI here: this is the deterministic recipe, and it alone decides order",
    "board": "\"print the retrieved chunks\": the first step in debugging any RAG system",
    "prompt": "\"RAG is automated paste\": retrieval just puts the right text in the prompt",
}


def _rule(char: str = "-", width: int = 74) -> str:
    return char * width


def render_ranking(record: dict) -> str:
    """The score recipe, itemized, with the top-k cut drawn in."""
    prefs = record["prefs"]
    lines = [
        _rule("="),
        f"WHY THIS ORDER      {prefs['favorite_genre']} / {prefs['favorite_mood']}"
        f" / energy {prefs['target_energy']}",
        f"  {CAPTIONS['ranking']}",
        _rule("="),
        f"{'#':>3}  {'song':<22}{'total':>7}   genre   mood   energy",
    ]

    cut_drawn = False
    for row in record["ranking"]:
        # Draw the cut line once, at the boundary between what the listener saw
        # and what they did not. The near misses below it are the point of this
        # table: they show what the shown songs actually beat.
        if not row["shown"] and not cut_drawn:
            lines.append(f"{_rule('.')}  top {sum(r['shown'] for r in record['ranking'])} cut")
            cut_drawn = True

        t = row["terms"]
        lines.append(
            f"{row['rank']:>3}  {row['title'][:22]:<22}{row['total']:>7.2f}"
            f"   {t['genre']:>5.1f}  {t['mood']:>5.1f}   {t['energy']:>5.2f}"
        )
    return "\n".join(lines)


def render_board(board: dict, top: int = 8) -> str:
    """The retrieval competition, with the floor and any override marked."""
    lines = [
        "",
        _rule("="),
        f"RETRIEVAL SCOREBOARD   {board['song_title']}",
        f"  {CAPTIONS['board']}",
        _rule("="),
        f"  {'note':<24}{'overlap':>8}  {'exact':>5}  picked",
    ]

    floor_drawn = False
    for row in board["board"][:top]:
        if not row["above_floor"] and not floor_drawn:
            lines.append(f"  {_rule('.', 30)} floor {board['floor']:.2f}")
            floor_drawn = True
        lines.append(
            f"  {row['title'][:24]:<24}{row['overlap']:>8.2f}"
            f"  {'*' if row['exact'] else '-':>5}"
            f"  {'*' if row['title'] == board['picked_title'] else ''}"
        )

    if len(board["board"]) > top:
        lines.append(f"  ... {len(board['board']) - top} more notes scored")

    if not board["grounded"]:
        lines.append("")
        lines.append("  ! nothing cleared the floor. The score-only fallback runs,")
        lines.append("    which is the guardrail against explaining a song we have")
        lines.append("    no facts about.")
    elif board["strict_override"]:
        lines.append("")
        lines.append(f"  ! overlap alone would have retrieved '{board['overlap_winner']}'")
        lines.append(f"    at {board['board'][0]['overlap']:.2f}, beating this song's own note")
        lines.append(f"    at {board['confidence']:.2f}. The exact-title tiebreak overrode it.")
        lines.append("    That tiebreak is a hand-rolled reranker, and this row is")
        lines.append("    a real case of token overlap retrieving the wrong document.")
    elif board["tiebreak_overrode"]:
        lines.append("")
        lines.append(f"  ! tied with '{board['overlap_winner']}' on overlap; the exact-title")
        lines.append("    tiebreak chose this song's own note. A tie, not a mis-retrieval.")

    return "\n".join(lines)


def render_prompt(record: dict) -> str:
    """The assembled prompt, shown whether or not a key is present."""
    lines = ["", _rule("="), "PROMPT THAT WOULD BE SENT", f"  {CAPTIONS['prompt']}", _rule("=")]

    if record["prompt"] is None:
        lines.append(f"  (no prompt built: {record['prompt_withheld_reason']})")
        return "\n".join(lines)

    for line in record["prompt"].splitlines():
        lines.append(f"  {line}")
    lines.append("")
    lines.append("  ^ Building this string needs no API key, so it is shown in offline")
    lines.append("    mode too. The note above is the ONLY song fact the model receives.")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect a VibeFinder run.")
    parser.add_argument("--genre", default="pop")
    parser.add_argument("--mood", default="happy")
    parser.add_argument("--energy", type=float, default=0.80)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument(
        "--song",
        help="Show the retrieval board for one song by title, instead of a full run.",
    )
    args = parser.parse_args()

    songs = load_songs(os.path.join(_DATA, "songs.csv"))
    notes = load_notes(os.path.join(_DATA, "song_notes.md"))
    prefs = {
        "favorite_genre": args.genre,
        "favorite_mood": args.mood,
        "target_energy": args.energy,
    }

    if args.song:
        match = next((s for s in songs if s["title"].lower() == args.song.lower()), None)
        if match is None:
            raise SystemExit(f"No song titled {args.song!r} in the catalog.")
        print(render_board(retrieval_board(match, notes)))
        return

    record = inspect_run(prefs, songs, notes, k=args.k)
    print(render_ranking(record))
    # Detail for the top pick only, so the default output stays readable. Use
    # --song to inspect any other title's retrieval.
    if record["songs"]:
        print(render_board(record["songs"][0]["retrieval"]))
        print(render_prompt(record["songs"][0]))


if __name__ == "__main__":
    main()

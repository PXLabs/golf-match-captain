"""
08_Scorecards.py — Match Play Scorecard Generator
Golf Match Captain

Generate and download a PDF scorecard pack for any round.
One scorecard per match. Each card contains:
  - Match ID (for AI photo scanning)
  - Pre-printed stroke dots in the top-right corner of each score box
  - Open dot = half stroke (9-hole only)
  - Two dots = 2 strokes (very high HC players)
  - Team-coloured player rows (Celtic Tigers green / The Hurleys red)
  - Short player codes for AI row identification (CT-P1, TH-P1, etc.)
  - Hole result and match status rows
  - Circle-the-result footer with signature lines

PDF is one scorecard per page, portrait letter.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
from database.db import initialise_database, fetchone
from modules.events import list_events, list_rounds
from modules.scorecard_pdf import generate_round_scorecards
from modules.handicap import FORMAT_LABELS

initialise_database()

st.title("🃏 Scorecards")
st.caption(
    "Generate a printable PDF scorecard pack for any round. "
    "Stroke dots are pre-calculated and printed on each card."
)
st.markdown("---")

# ── Event selector ────────────────────────────────────────────────
events = list_events(status="ACTIVE")
if not events:
    st.info("No active events found. Create an event in Event Setup first.")
    st.stop()

if len(events) == 1:
    event = events[0]
else:
    emap = {e["event_id"]: e["name"] for e in events}
    eid  = st.selectbox("Event", list(emap.keys()), format_func=lambda i: emap[i])
    event = next(e for e in events if e["event_id"] == eid)

eid = event["event_id"]

# ── Round selector ────────────────────────────────────────────────
rounds = list_rounds(eid)
if not rounds:
    st.info("No rounds configured for this event.")
    st.stop()

rmap = {
    r["round_id"]: (
        f"Round {r['round_number']}  —  {r['date']}"
        f"  ·  {r['holes']} holes"
        f"  ·  {FORMAT_LABELS.get(r['format_code'], r['format_code'])}"
    )
    for r in rounds
}
rid = st.selectbox("Round", list(rmap.keys()), format_func=lambda i: rmap[i])
sel_round = next(r for r in rounds if r["round_id"] == rid)

st.markdown("---")

# ── Round summary ─────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)
c1.metric("Round", sel_round["round_number"])
c2.metric("Holes", sel_round["holes"])
c3.metric("Format", FORMAT_LABELS.get(sel_round["format_code"], sel_round["format_code"]))
c4.metric("Date", sel_round["date"])

# ── Tee deck check ────────────────────────────────────────────────
tee_check = fetchone(
    "SELECT tee_id_a, tee_id_b FROM round WHERE round_id = %s", (rid,)
)
has_tee = tee_check and (tee_check.get("tee_id_a") or tee_check.get("tee_id_b"))

if not has_tee:
    st.warning(
        "No tee deck assigned to this round. Stroke dots cannot be calculated. "
        "Assign a tee deck in Event Setup → Rounds before generating scorecards."
    )

# ── Match count check ─────────────────────────────────────────────
from database.db import fetchall
match_count = fetchall(
    "SELECT match_id FROM match WHERE round_id = %s", (rid,)
)

if not match_count:
    st.warning(
        "No matches in the draw for this round yet. "
        "Add the draw in Results Entry before generating scorecards."
    )

st.markdown("---")

# ── Stroke rules explainer ────────────────────────────────────────
with st.expander("How strokes are calculated", expanded=False):
    if sel_round["holes"] == 9:
        st.markdown(
            "**9-hole match — halved handicap:**\n\n"
            "1. Full WHS course handicaps are calculated for each player using the round's tee deck.\n"
            "2. PLAY_OFF_LOW is applied — the lowest handicap plays scratch, others receive the difference.\n"
            "3. The difference is **halved** (e.g. a difference of 7 → 3 full strokes + 1 half stroke).\n"
            "4. Full strokes are allocated from the lowest stroke-index holes first.\n"
            "5. A half stroke (if any) is allocated to the next stroke-index hole.\n\n"
            "On the card: filled dot ● = full stroke · open dot ○ = half stroke (wins a tied hole)."
        )
    else:
        st.markdown(
            "**18-hole match — full handicap:**\n\n"
            "1. Full WHS course handicaps are calculated using the round's tee deck.\n"
            "2. PLAY_OFF_LOW is applied — the lowest handicap plays scratch, others receive the difference.\n"
            "3. Strokes are allocated from the lowest stroke-index holes first.\n"
            "4. Players with a handicap difference > 18 receive 2 strokes on some holes.\n\n"
            "On the card: filled dot ● = 1 stroke · two dots ●● = 2 strokes on that hole."
        )

# ── Generate button ───────────────────────────────────────────────
st.subheader("Generate PDF")

compact = st.checkbox(
    "Compact mode — 2 cards per page (caddie / rain size)",
    value=True,
    help=(
        "Fits two scorecards on one portrait letter sheet, each roughly half-page. "
        "Ideal for wet weather or caddie use. Un-check for a full-size card per page."
    ),
)

col_btn, col_info = st.columns([2, 3])
with col_btn:
    generate = st.button(
        "📄 Generate Scorecards",
        type="primary",
        use_container_width=True,
        disabled=(not match_count),
    )
with col_info:
    if compact:
        st.caption(
            f"{len(match_count)} match card(s) · 2 per page · portrait letter · "
            "compact caddie size"
        )
    else:
        st.caption(
            f"{len(match_count)} match card(s) · 1 per page · portrait letter · "
            "full size"
        )

if generate:
    with st.spinner("Calculating strokes and building PDF…"):
        try:
            pdf_bytes = generate_round_scorecards(rid, compact=compact)
            kb = len(pdf_bytes) // 1024
            size_tag = "COMPACT" if compact else "FULL"
            fname = (
                f"scorecards_R{sel_round['round_number']}_"
                f"{size_tag}_"
                f"{sel_round['date'].replace('-', '')}.pdf"
            )
            st.success(
                f"PDF ready — {len(match_count)} scorecard(s) · {kb} KB · {size_tag}"
            )
            st.download_button(
                label="⬇️ Download Scorecards PDF",
                data=pdf_bytes,
                file_name=fname,
                mime="application/pdf",
                use_container_width=True,
                type="primary",
            )
        except Exception as e:
            st.error(f"Could not generate scorecards: {e}")
            st.caption(
                "Common causes: tee deck not assigned to this round, "
                "or players missing from the draw."
            )

st.markdown("---")
st.caption(
    "Golf Match Captain · Scorecards  ·  "
    "Cards include AI scan reference ID — photograph the completed card "
    "to auto-enter results (coming soon)."
)

"""
10_Scorecard.py — Scorecard Photo Upload
Golf Match Captain | Scorecard Feature

Four-step wizard:
  Step 1 — Select event, round, and match
  Step 2 — Upload scorecard photo → Vision extraction
  Step 3 — Review & correct extracted scores, map names to players
  Step 4 — Preview hole-by-hole results → Confirm & save
"""

import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
from database.db import initialise_database
from modules.events import list_events, get_event, list_rounds, get_event_players_by_team
from modules.results import get_matches_with_players, list_matches
from modules.roster import get_player
from modules.handicap import FORMAT_LABELS
from modules.scorecard import (
    extract_scorecard_vision,
    calculate_match,
    save_scorecard_result,
    get_hole_scores,
    ExtractedPlayer,
    ExtractionResult,
    image_bytes_to_media_type,
    ANTHROPIC_AVAILABLE,
)

initialise_database()

st.title("📷 Scorecard Upload")
st.caption("Photograph a scorecard to extract scores and update match results.")
st.markdown("---")

if not ANTHROPIC_AVAILABLE:
    st.error(
        "The `anthropic` package is not installed.\n\n"
        "Run: `pip install anthropic`"
    )
    st.stop()

# ---------------------------------------------------------------
# Session state keys
# ---------------------------------------------------------------
SS_STEP        = "sc_step"
SS_EVENT       = "sc_event_id"
SS_ROUND       = "sc_round_id"
SS_MATCH       = "sc_match_id"
SS_EXTRACTION  = "sc_extraction"
SS_CORRECTIONS = "sc_corrections"   # {player_idx: [scores]}
SS_MAPPING     = "sc_mapping"       # {"A1": player_id, "A2":..., "B1":..., "B2":...}
SS_CALC        = "sc_calculation"
SS_IMAGE_BYTES = "sc_image_bytes"
SS_IMAGE_TYPE  = "sc_image_type"

for key, default in [
    (SS_STEP, 1), (SS_EVENT, None), (SS_ROUND, None), (SS_MATCH, None),
    (SS_EXTRACTION, None), (SS_CORRECTIONS, {}), (SS_MAPPING, {}),
    (SS_CALC, None), (SS_IMAGE_BYTES, None), (SS_IMAGE_TYPE, "image/jpeg"),
]:
    if key not in st.session_state:
        st.session_state[key] = default


def _reset():
    for k in [SS_STEP, SS_EVENT, SS_ROUND, SS_MATCH, SS_EXTRACTION,
              SS_CORRECTIONS, SS_MAPPING, SS_CALC, SS_IMAGE_BYTES, SS_IMAGE_TYPE]:
        st.session_state[k] = 1 if k == SS_STEP else (
            {} if k in (SS_CORRECTIONS, SS_MAPPING) else None
        )

# ---------------------------------------------------------------
# Formatting Helpers
# ---------------------------------------------------------------

def _pair(n1, n2):
    if n1 and n2:
        return f"{n1} & {n2}"
    return n1 or "TBD"

def _gross_cell(g1, g2):
    if g1 and g2:
        return f"{g1} / {g2}"
    if g1:
        return str(g1)
    return "—"

def _net_cell(net):
    if net is None:
        return "—"
    return f"{net:.0f}"


# ---------------------------------------------------------------
# Progress indicator
# ---------------------------------------------------------------
step = st.session_state[SS_STEP]
step_labels = ["1 Select", "2 Upload", "3 Review", "4 Confirm"]
prog_cols = st.columns(4)
for i, (col, lbl) in enumerate(zip(prog_cols, step_labels), 1):
    if i < step:
        col.markdown(f"✅ ~~{lbl}~~")
    elif i == step:
        col.markdown(f"**▶ {lbl}**")
    else:
        col.markdown(f"· {lbl}")

st.markdown("---")

# ==============================================================
# STEP 1 — Select event, round, match
# ==============================================================
if step == 1:
    st.subheader("Step 1 — Select Match")

    events = list_events(status="ACTIVE")
    if not events:
        st.info("No active events. Create one in Event Setup.")
        st.stop()

    event_map    = {e["event_id"]: e["name"] for e in events}
    selected_eid = st.selectbox("Event", list(event_map),
                                 format_func=lambda i: event_map[i])
    event  = get_event(selected_eid)
    rounds = list_rounds(selected_eid)

    if not rounds:
        st.warning("No rounds configured for this event.")
        st.stop()

    round_map    = {
        r["round_id"]: (
            f"Round {r['round_number']} — {r['date']}  |  "
            f"{FORMAT_LABELS.get(r['format_code'], r['format_code'])}"
        )
        for r in rounds
    }
    selected_rid = st.selectbox("Round", list(round_map),
                                 format_func=lambda i: round_map[i])
    sel_round    = next(r for r in rounds if r["round_id"] == selected_rid)

    fmt = sel_round["format_code"]
    st.caption(
        f"Format: **{FORMAT_LABELS.get(fmt, fmt)}**  |  "
        f"Holes: **{sel_round['holes']}**"
    )

    # Match selector
    matches = get_matches_with_players(selected_rid)
    if not matches:
        st.warning("No matches in the draw for this round. Add them in Results Entry first.")
        st.stop()

    def _match_label(m):
        a = _pair(m["a1_name"], m["a2_name"])
        b = _pair(m["b1_name"], m["b2_name"])
        done = " ✅" if m["result"] else ""
        scored = " 📊" if m.get("hole_scores") else ""
        return f"Match {m['match_order']}: {a}  vs  {b}{done}{scored}"

    match_map    = {m["match_id"]: _match_label(m) for m in matches}
    selected_mid = st.selectbox("Match", list(match_map),
                                 format_func=lambda i: match_map[i])
    sel_match    = next(m for m in matches if m["match_id"] == selected_mid)

    # Show existing hole scores if any
    existing = get_hole_scores(selected_mid)
    if existing:
        st.info(
            f"📊 This match already has hole scores recorded "
            f"(confidence: {existing.get('confidence','?')}). "
            "Continuing will overwrite them."
        )

    if st.button("Next →", type="primary", use_container_width=True):
        st.session_state[SS_EVENT] = selected_eid
        st.session_state[SS_ROUND] = selected_rid
        st.session_state[SS_MATCH] = selected_mid
        st.session_state[SS_STEP]  = 2
        st.rerun()


# ==============================================================
# STEP 2 — Upload photo → Vision extraction
# ==============================================================
elif step == 2:
    st.subheader("Step 2 — Upload Scorecard Photo")

    event  = get_event(st.session_state[SS_EVENT])
    rounds = list_rounds(st.session_state[SS_EVENT])
    sel_rnd = next(r for r in rounds if r["round_id"] == st.session_state[SS_ROUND])
    holes   = int(sel_rnd["holes"])

    st.caption(
        f"Event: **{event['name']}**  |  "
        f"Round {sel_rnd['round_number']} — {sel_rnd['date']}  |  "
        f"{holes} holes"
    )
    st.markdown(
        "Take a clear, straight-on photo of the scorecard in good light. "
        "All score boxes should be visible. JPEG or PNG recommended."
    )

    uploaded = st.file_uploader(
        "Upload scorecard photo",
        type=["jpg", "jpeg", "png", "webp"],
        key="sc_upload",
    )

    col_back, col_next = st.columns([1, 3])
    if col_back.button("← Back"):
        st.session_state[SS_STEP] = 1
        st.rerun()

    if uploaded:
        st.image(uploaded, caption="Uploaded scorecard", use_container_width=True)

        if col_next.button("🔍 Extract Scores", type="primary",
                            use_container_width=True):
            image_bytes = uploaded.read()
            media_type  = image_bytes_to_media_type(uploaded.name)

            with st.spinner("Reading scorecard with Claude Vision…"):
                result = extract_scorecard_vision(image_bytes, holes, media_type)

            if not result.success:
                st.error(f"Extraction failed: {result.error}")
            else:
                st.session_state[SS_EXTRACTION]  = result
                st.session_state[SS_IMAGE_BYTES] = image_bytes
                st.session_state[SS_IMAGE_TYPE]  = media_type
                # Initialise corrections with extracted scores
                st.session_state[SS_CORRECTIONS] = {
                    i: list(p.scores)
                    for i, p in enumerate(result.players)
                }
                st.session_state[SS_STEP] = 3
                st.rerun()
    else:
        col_next.button("🔍 Extract Scores", disabled=True,
                         use_container_width=True)


# ==============================================================
# STEP 3 — Review, correct, and map players
# ==============================================================
elif step == 3:
    st.subheader("Step 3 — Review & Map Players")

    extraction: ExtractionResult = st.session_state[SS_EXTRACTION]
    event = get_event(st.session_state[SS_EVENT])
    rounds = list_rounds(st.session_state[SS_EVENT])
    sel_rnd = next(r for r in rounds if r["round_id"] == st.session_state[SS_ROUND])
    holes   = int(sel_rnd["holes"])
    fmt     = sel_rnd["format_code"]

    is_pairs = fmt in ("FOURBALL_MP", "FOURSOMES_MP")
    sides    = ["A1", "B1", "A2", "B2"] if is_pairs else ["A1", "B1"]

    # Confidence banner
    conf_colors = {"high": "success", "medium": "warning", "low": "error"}
    conf_fn = getattr(st, conf_colors.get(extraction.confidence, "info"))
    conf_fn(
        f"Extraction confidence: **{extraction.confidence.upper()}**"
        + (f"  |  {extraction.course_name}" if extraction.course_name else "")
        + (f"\n\n⚠️ {extraction.notes}" if extraction.notes else "")
    )

    st.markdown("---")

    # ---- Player name → roster mapping -------------------------
    st.markdown("**Map extracted names to your roster players**")

    matches     = get_matches_with_players(st.session_state[SS_ROUND])
    sel_match   = next(m for m in matches
                       if m["match_id"] == st.session_state[SS_MATCH])
    teams       = get_event_players_by_team(st.session_state[SS_EVENT])
    ev_ta       = event["team_a_name"]
    ev_tb       = event["team_b_name"]

    # Build the pool of players in this match
    match_players = {}
    for field_name, label in [
        ("a1_id", f"{ev_ta} — Player 1"),
        ("a2_id", f"{ev_ta} — Player 2"),
        ("b1_id", f"{ev_tb} — Player 1"),
        ("b2_id", f"{ev_tb} — Player 2"),
    ]:
        pid = sel_match.get(field_name)
        if pid:
            p = get_player(pid)
            if p:
                match_players[pid] = p["name"]

    extracted_names = [p.raw_name for p in extraction.players]
    mapping         = st.session_state.get(SS_MAPPING, {})

    # One row per extracted player
    st.caption(
        f"{len(extracted_names)} player(s) extracted from photo. "
        "Assign each to a side."
    )

    new_mapping = {}
    for i, ep in enumerate(extraction.players):
        mc1, mc2, mc3 = st.columns([2, 3, 2])
        mc1.markdown(f"**'{ep.raw_name}'**")

        pid_opts   = [None] + list(match_players.keys())
        pid_labels = ["— unassigned —"] + list(match_players.values())
        cur_pid    = mapping.get(str(i))
        cur_idx    = pid_opts.index(cur_pid) if cur_pid in pid_opts else 0

        chosen_pid = mc2.selectbox(
            f"Roster player for '{ep.raw_name}'",
            pid_opts,
            index=cur_idx,
            format_func=lambda x: match_players.get(x, "— unassigned —"),
            key=f"map_pid_{i}",
            label_visibility="collapsed",
        )

        side_opts  = ["—"] + sides
        cur_side   = mapping.get(f"side_{i}", "—")
        cur_side_i = side_opts.index(cur_side) if cur_side in side_opts else 0
        chosen_side = mc3.selectbox(
            "Side",
            side_opts,
            index=cur_side_i,
            key=f"map_side_{i}",
            label_visibility="collapsed",
        )

        new_mapping[str(i)]        = chosen_pid
        new_mapping[f"side_{i}"]   = chosen_side

    st.session_state[SS_MAPPING] = new_mapping

    st.markdown("---")

    # ---- Score correction grid --------------------------------
    st.markdown("**Review and correct extracted scores**")
    st.caption("Click any cell to edit. Red cells = 0 (unread by Vision).")

    corrections = st.session_state[SS_CORRECTIONS]
    hole_nums   = list(range(1, holes + 1))

    for i, ep in enumerate(extraction.players):
        side_label = new_mapping.get(f"side_{i}", "—")
        pid        = new_mapping.get(str(i))
        name_label = match_players.get(pid, ep.raw_name) if pid else ep.raw_name

        st.markdown(f"*{name_label} ({side_label})*")
        curr_scores = corrections.get(i, list(ep.scores))

        # Display as two rows of 9 for 18-hole, one row for 9-hole
        row_ranges = [range(9), range(9, holes)] if holes == 18 else [range(holes)]
        new_scores = list(curr_scores)

        for row_range in row_ranges:
            cols = st.columns(len(list(row_range)))
            for j, hole_idx in enumerate(row_range):
                val = curr_scores[hole_idx] if hole_idx < len(curr_scores) else 0
                cell_label = f"H{hole_idx+1}"
                new_val = cols[j].number_input(
                    cell_label,
                    min_value=0, max_value=20,
                    value=int(val),
                    step=1,
                    key=f"score_{i}_{hole_idx}",
                    label_visibility="visible",
                )
                if hole_idx < len(new_scores):
                    new_scores[hole_idx] = new_val

        corrections[i] = new_scores
        total = sum(s for s in new_scores if s > 0)
        zeros = sum(1 for s in new_scores if s == 0)
        st.caption(
            f"Total: **{total}**"
            + (f"  ·  ⚠️ {zeros} hole(s) unread" if zeros else "  ·  ✅ All holes read")
        )

    st.session_state[SS_CORRECTIONS] = corrections

    st.markdown("---")
    col_back, col_next = st.columns([1, 3])
    if col_back.button("← Back"):
        st.session_state[SS_STEP] = 2
        st.rerun()

    if col_next.button("Calculate Results →", type="primary",
                        use_container_width=True):
        # Apply corrections to extraction
        for i, ep in enumerate(extraction.players):
            ep.scores    = corrections.get(i, ep.scores)
            ep.player_id = new_mapping.get(str(i))
            ep.side      = new_mapping.get(f"side_{i}", "—")

        # Resolve side assignments
        def _pid_for_side(side):
            for i, ep in enumerate(extraction.players):
                if new_mapping.get(f"side_{i}") == side:
                    return ep.player_id
            return None

        pid_a1 = _pid_for_side("A1") or sel_match.get("a1_id")
        pid_b1 = _pid_for_side("B1") or sel_match.get("b1_id")
        pid_a2 = _pid_for_side("A2") if is_pairs else None
        pid_b2 = _pid_for_side("B2") if is_pairs else None

        if not pid_a1 or not pid_b1:
            st.error("Please map at least one player to A1 and one to B1.")
            st.stop()

        event_full = get_event(st.session_state[SS_EVENT])
        allowance  = float(event_full["allowance_pct"]) / 100.0

        with st.spinner("Calculating hole-by-hole results…"):
            calc = calculate_match(
                extraction=extraction,
                player_a1_id=pid_a1,
                player_b1_id=pid_b1,
                player_a2_id=pid_a2,
                player_b2_id=pid_b2,
                round_id=st.session_state[SS_ROUND],
                format_code=fmt,
                handicap_mode=event_full["handicap_mode"],
                allowance_pct=allowance,
            )

        if calc is None:
            st.error(
                "Could not calculate results. "
                "Check that tee decks are assigned to this round."
            )
        else:
            st.session_state[SS_CALC] = calc
            st.session_state[SS_STEP] = 4
            st.rerun()


# ==============================================================
# STEP 4 — Preview results → Confirm & save
# ==============================================================
elif step == 4:
    st.subheader("Step 4 — Confirm & Save")

    calc: MatchCalculation = st.session_state[SS_CALC]
    extraction: ExtractionResult = st.session_state[SS_EXTRACTION]
    event  = get_event(st.session_state[SS_EVENT])
    ev_ta  = event["team_a_name"]
    ev_tb  = event["team_b_name"]

    # Result banner
    result_colors = {"A": "success", "B": "error", "HALVED": "warning"}
    result_fn = getattr(st, result_colors.get(calc.final_result, "info"))
    winner_name = ev_ta if calc.final_result == "A" else (
        ev_tb if calc.final_result == "B" else "Halved"
    )
    result_fn(
        f"**Result: {winner_name} — {calc.result_detail}**  |  "
        f"Holes: {ev_ta} {calc.holes_won_a} / {ev_tb} {calc.holes_won_b} / "
        f"Halved {calc.holes_halved}"
    )

    # Running score sparkline
    st.markdown("**Running match score** (positive = Team A leading)")
    running_df = pd.DataFrame({
        "Hole":  [h.hole for h in calc.hole_results],
        "Score": calc.running_score,
    })
    st.line_chart(running_df.set_index("Hole"), height=180)

    # Hole-by-hole table
    st.markdown("**Hole-by-hole breakdown**")
    rows = []
    for h in calc.hole_results:
        winner_icon = {"A": f"✅ {ev_ta}", "B": f"✅ {ev_tb}", "H": "🤝 Half"}.get(
            h.winner, "—"
        )
        rows.append({
            "Hole":       h.hole,
            "Par":        h.par or "—",
            f"{ev_ta} Gross": _gross_cell(h.gross_a1, h.gross_a2),
            f"{ev_ta} Net":   _net_cell(h.best_net_a),
            f"{ev_tb} Gross": _gross_cell(h.gross_b1, h.gross_b2),
            f"{ev_tb} Net":   _net_cell(h.best_net_b),
            "Winner":     winner_icon,
        })

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.markdown("---")
    col_back, col_save = st.columns([1, 3])
    if col_back.button("← Back"):
        st.session_state[SS_STEP] = 3
        st.rerun()

    if col_save.button("💾 Save Scorecard Results", type="primary",
                        use_container_width=True):
        save_scorecard_result(
            match_id=st.session_state[SS_MATCH],
            calculation=calc,
            extraction=extraction,
        )
        st.success(
            f"✅ Scorecard saved. Match result: **{winner_name} — {calc.result_detail}**"
        )
        st.balloons()

        if st.button("📷 Upload Another Scorecard", use_container_width=True):
            _reset()
            st.rerun()




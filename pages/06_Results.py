"""
06_Results.py — Results Entry
Golf Match Captain | Phase 1E

Covers:
  - Build the draw for a round (set pairings)
  - Record match results (win / loss / halved + margin detail)
  - Running team scoreboard across all rounds
  - Player form table
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
from database.db import initialise_database
from modules.events import (
    list_events, get_event, list_rounds, get_event_players_by_team,
)
from modules.results import (
    create_match, list_matches, update_match_players, record_result,
    clear_result, delete_match, get_round_score, get_event_score,
    get_player_results, get_matches_with_players, format_results_for_llm,
    RESULT_OPTIONS,
)
from modules.handicap import FORMAT_LABELS

initialise_database()

st.title("✅ Results Entry")
st.caption("Build the draw, record results, and track the running score.")
st.markdown("---")

def _pair_label(name1: str | None, name2: str | None) -> str:
    """Format one or two player names as a match label."""
    if name1 and name2:
        return f"{name1} & {name2}"
    if name1:
        return name1
    return "TBD"

# ---------------------------------------------------------------
# Event selector
# ---------------------------------------------------------------
events = list_events(status="ACTIVE")
if not events:
    st.info("No active events. Create one in Event Setup.")
    st.stop()

event_map    = {e["event_id"]: e["name"] for e in events}
selected_eid = st.selectbox(
    "Select Event",
    list(event_map.keys()),
    format_func=lambda i: event_map[i],
)
event    = get_event(selected_eid)
ev_ta    = event["team_a_name"]
ev_tb    = event["team_b_name"]
rounds   = list_rounds(selected_eid)

if not rounds:
    st.warning("No rounds configured. Go to Event Setup to add rounds.")
    st.stop()

# ---------------------------------------------------------------
# Running scoreboard (always visible at top)
# ---------------------------------------------------------------
score = get_event_score(selected_eid)

st.subheader("🏆 Running Score")
sc1, sc2, sc3 = st.columns(3)
sc1.metric(ev_ta, f"{score['total_points_a']:.1f} pts",
            delta=f"{score['total_points_a'] - score['total_points_b']:+.1f} vs {ev_tb}")
sc2.metric(ev_tb, f"{score['total_points_b']:.1f} pts")
sc3.metric("Rounds complete", f"{score['rounds_completed']} / {len(rounds)}")

# Per-round breakdown
if score["per_round"]:
    import pandas as pd
    rnd_rows = []
    for r in score["per_round"]:
        played_str = (
            f"{r['points_a']:.1f} – {r['points_b']:.1f}"
            if r["matches_played"] > 0
            else "—"
        )
        winner = (
            ev_ta if r["points_a"] > r["points_b"]
            else ev_tb if r["points_b"] > r["points_a"]
            else "Tied" if r["matches_played"] > 0
            else "—"
        )
        rnd_rows.append({
            "Round":   r["round_number"],
            "Date":    r["date"],
            "Format":  FORMAT_LABELS.get(r["format_code"], r["format_code"]),
            "Score":   played_str,
            "Winner":  winner,
            "Pending": r["matches_pending"],
        })
    st.dataframe(pd.DataFrame(rnd_rows), use_container_width=True, hide_index=True)

st.markdown("---")

# ---------------------------------------------------------------
# Round tabs
# ---------------------------------------------------------------
st.subheader("📋 Draw & Results by Round")
round_tab_labels = [
    f"R{r['round_number']} — {r['date']}" for r in rounds
]
tabs = st.tabs(round_tab_labels)

for tab, rnd in zip(tabs, rounds):
    rid    = rnd["round_id"]
    fmt    = rnd["format_code"]
    is_singles = fmt in ("SINGLES_MP", "SINGLES_STROKE")
    teams  = get_event_players_by_team(selected_eid)
    ta_players = teams["A"]
    tb_players = teams["B"]

    with tab:
        st.caption(
            f"{FORMAT_LABELS.get(fmt, fmt)}  |  "
            f"{rnd['holes']} holes  |  {rnd['course_name']}"
        )

        matches = get_matches_with_players(rid)

        # -------------------------------------------------------
        # Draw builder — add a new match
        # -------------------------------------------------------
        with st.expander("➕ Add a Match to Draw", expanded=len(matches) == 0):
            with st.form(f"add_match_{rid}", clear_on_submit=True):
                st.markdown(f"**{ev_ta} side**")
                a_col1, a_col2 = st.columns(2)
                a1_opts  = [None] + [p["player_id"] for p in ta_players]
                a1_names = ["— select —"] + [f"{p['name']} ({p['current_index']:.1f})"
                                               for p in ta_players]
                a1_idx = a_col1.selectbox(
                    "Player 1 *" if is_singles else "Partner 1 *",
                    range(len(a1_opts)), format_func=lambda i: a1_names[i],
                    key=f"a1_{rid}",
                )
                a2_idx = a_col2.selectbox(
                    "— (singles)" if is_singles else "Partner 2",
                    range(len(a1_opts)),
                    format_func=lambda i: a1_names[i],
                    key=f"a2_{rid}",
                    disabled=is_singles,
                )

                st.markdown(f"**{ev_tb} side**")
                b_col1, b_col2 = st.columns(2)
                b1_opts  = [None] + [p["player_id"] for p in tb_players]
                b1_names = ["— select —"] + [f"{p['name']} ({p['current_index']:.1f})"
                                               for p in tb_players]
                b1_idx = b_col1.selectbox(
                    "Player 1 *" if is_singles else "Partner 1 *",
                    range(len(b1_opts)), format_func=lambda i: b1_names[i],
                    key=f"b1_{rid}",
                )
                b2_idx = b_col2.selectbox(
                    "— (singles)" if is_singles else "Partner 2",
                    range(len(b1_opts)),
                    format_func=lambda i: b1_names[i],
                    key=f"b2_{rid}",
                    disabled=is_singles,
                )

                m_notes   = st.text_input("Match notes (optional)", key=f"mnotes_{rid}")
                m_order   = len(matches) + 1

                if st.form_submit_button("Add to Draw", type="primary"):
                    a1 = a1_opts[a1_idx]
                    b1 = b1_opts[b1_idx]
                    if not a1 or not b1:
                        st.error("Select at least one player from each team.")
                    else:
                        a2 = None if is_singles else a1_opts[a2_idx]
                        b2 = None if is_singles else b1_opts[b2_idx]
                        create_match(rid, m_order, a1, a2, b1, b2, m_notes)
                        st.success("Match added to draw.")
                        st.rerun()

        # -------------------------------------------------------
        # Match cards — result entry
        # -------------------------------------------------------
        if not matches:
            st.info("No matches in the draw yet. Add one above.")
        else:
            round_score = get_round_score(rid)
            rc1, rc2, rc3 = st.columns(3)
            rc1.metric(ev_ta, f"{round_score['points_a']:.1f} pts")
            rc2.metric(ev_tb, f"{round_score['points_b']:.1f} pts")
            rc3.metric("Pending", round_score["matches_pending"])

            st.markdown("---")

            for m in matches:
                mid = m["match_id"]

                # Build display names
                a_name = _pair_label(m["a1_name"], m["a2_name"])
                b_name = _pair_label(m["b1_name"], m["b2_name"])

                result     = m["result"]
                pts_a      = m["pts_a"]
                pts_b      = m["pts_b"]

                # Colour the card border by result
                if result == "A":
                    border_colour = "#2980b9"
                elif result == "B":
                    border_colour = "#e74c3c"
                elif result == "HALVED":
                    border_colour = "#27ae60"
                else:
                    border_colour = "#888"

                with st.container(border=True):
                    h1, h2, h3, h4 = st.columns([3, 3, 2, 1])
                    h1.markdown(f"**{a_name}**")
                    h2.markdown(f"**{b_name}**")

                    if result:
                        result_display = RESULT_OPTIONS.get(result, result)
                        detail_str     = f" ({m['result_detail']})" if m["result_detail"] else ""
                        h3.markdown(f"✔ {result_display}{detail_str}")
                        h4.markdown(f"**{pts_a:.1f}–{pts_b:.1f}**")
                    else:
                        h3.caption("Pending")
                        h4.caption("—")

                    # Notes
                    if m["notes"]:
                        st.caption(f"📝 {m['notes']}")

                    # Result entry form
                    with st.form(f"result_{mid}"):
                        r_col1, r_col2, r_col3 = st.columns([2, 2, 1])
                        result_keys    = list(RESULT_OPTIONS.keys())
                        result_labels  = list(RESULT_OPTIONS.values())
                        cur_result_idx = result_keys.index(result) if result in result_keys else 0

                        chosen_result = r_col1.selectbox(
                            "Result",
                            range(len(result_keys)),
                            index=cur_result_idx,
                            format_func=lambda i: result_labels[i],
                            key=f"res_sel_{mid}",
                        )
                        result_detail = r_col2.text_input(
                            "Margin (e.g. 3&2, 1 UP)",
                            value=m["result_detail"] or "",
                            key=f"res_det_{mid}",
                        )

                        fc1, fc2, fc3 = st.columns([2, 1, 1])
                        if fc1.form_submit_button("💾 Save Result", type="primary",
                                                   use_container_width=True):
                            record_result(mid, result_keys[chosen_result], result_detail)
                            st.success("Result saved.")
                            st.rerun()

                        if result and fc2.form_submit_button("↩ Clear", use_container_width=True):
                            clear_result(mid)
                            st.info("Result cleared.")
                            st.rerun()

                        if fc3.form_submit_button("🗑️ Delete", use_container_width=True):
                            delete_match(mid)
                            st.warning("Match removed.")
                            st.rerun()

# ---------------------------------------------------------------
# Player form table
# ---------------------------------------------------------------
st.markdown("---")
st.subheader("👤 Player Form")

p_stats  = get_player_results(selected_eid)
all_players_map = {
    p["player_id"]: p
    for p in (get_event_players_by_team(selected_eid)["A"] +
              get_event_players_by_team(selected_eid)["B"])
}

if not p_stats:
    st.caption("No results recorded yet.")
else:
    import pandas as pd
    form_rows = []
    for s in sorted(p_stats, key=lambda x: -x["pts"]):
        pid     = s["player_id"]
        p_info  = all_players_map.get(pid)
        name    = p_info["name"] if p_info else f"Player {pid}"
        team    = (ev_ta if p_info and p_info["team"] == "A" else ev_tb) if p_info else "—"
        played  = s["W"] + s["L"] + s["H"]
        form_rows.append({
            "Player":  name,
            "Team":    team,
            "Played":  played,
            "W":       s["W"],
            "L":       s["L"],
            "H":       s["H"],
            "Points":  s["pts"],
        })
    st.dataframe(pd.DataFrame(form_rows), use_container_width=True, hide_index=True)

# ---------------------------------------------------------------
# LLM context preview
# ---------------------------------------------------------------
st.markdown("---")
with st.expander("📋 Results Context for AI Advisor", expanded=False):
    llm_results = format_results_for_llm(selected_eid, ev_ta, ev_tb)
    st.code(llm_results, language=None)
    st.caption("This will be included in the AI Advisor context packet in Phase 1F.")




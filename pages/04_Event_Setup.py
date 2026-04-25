"""
04_Event_Setup.py — Event Setup
Golf Match Captain | Phase 1C

Covers:
  - Create / edit events (name, dates, team names, handicap mode, allowance %)
  - Assign players to Team A or Team B
  - Add / edit / delete rounds (course, tee decks, format, holes, date)
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
from database.db import initialise_database
from modules.events import (
    create_event, get_event, list_events, update_event, delete_event,
    assign_player, remove_player_from_event, set_player_role,
    get_event_players, get_event_players_by_team, get_unassigned_players,
    add_round, get_round, list_rounds, update_round, delete_round,
    get_event_summary, HANDICAP_MODES, EVENT_STATUSES,
)
from modules.courses import list_courses, list_tee_decks
from modules.roster import list_players
from modules.handicap import FORMAT_LABELS

initialise_database()

st.title("📅 Event Setup")
st.caption("Create events, build your rosters, and configure rounds.")
st.markdown("---")

FORMAT_OPTIONS = list(FORMAT_LABELS.keys())
FORMAT_DISPLAY = [FORMAT_LABELS[f] for f in FORMAT_OPTIONS]

def _parse_date(date_str: str):
    """Parse a date string to a date object for date_input."""
    from datetime import date
    try:
        return date.fromisoformat(str(date_str))
    except (ValueError, TypeError):
        return date.today()

# ---------------------------------------------------------------
# Sub-renders for round forms
# ---------------------------------------------------------------

def _render_round_add_form(event_id, courses, ta_name, tb_name, next_round_num):
    course_map = {c["course_id"]: c["name"] for c in courses}
    course_ids = list(course_map.keys())

    with st.form(f"add_round_{event_id}", clear_on_submit=True):
        r_col1, r_col2 = st.columns(2)
        r_num    = r_col1.number_input("Round Number", min_value=1, step=1,
                                        value=next_round_num)
        r_date   = r_col2.date_input("Date")
        r_course_idx = st.selectbox(
            "Course *", range(len(course_ids)),
            format_func=lambda i: course_map[course_ids[i]],
        )
        r_course_id  = course_ids[r_course_idx]

        decks = list_tee_decks(r_course_id)
        deck_opts = {d["tee_id"]: f"{d['name']} (Rating {d['rating']}, Slope {d['slope']})"
                     for d in decks}
        deck_ids  = [None] + list(deck_opts.keys())
        deck_labels = ["— same tee for both teams —"] + list(deck_opts.values())

        r_col3, r_col4 = st.columns(2)
        tee_a_idx = r_col3.selectbox(f"Tee — {ta_name}", range(len(deck_ids)),
                                      format_func=lambda i: deck_labels[i],
                                      key=f"add_tee_a_{event_id}")
        tee_b_idx = r_col4.selectbox(f"Tee — {tb_name}", range(len(deck_ids)),
                                      format_func=lambda i: deck_labels[i],
                                      key=f"add_tee_b_{event_id}")

        fmt_idx  = st.selectbox("Format", range(len(FORMAT_OPTIONS)),
                                  format_func=lambda i: FORMAT_DISPLAY[i])
        r_holes  = st.radio("Holes", [18, 9], horizontal=True)

        add_rnd = st.form_submit_button("Add Round", type="primary")
        if add_rnd:
            tee_a = deck_ids[tee_a_idx]
            tee_b = deck_ids[tee_b_idx]
            # If both None, leave as None (no tee deck specified yet)
            add_round(
                event_id=event_id,
                course_id=r_course_id,
                date=str(r_date),
                format_code=FORMAT_OPTIONS[fmt_idx],
                round_number=int(r_num),
                holes=r_holes,
                tee_id_a=tee_a,
                tee_id_b=tee_b,
            )
            st.success("Round added.")
            st.rerun()


def _render_round_edit_form(round_id, rnd, courses, event_id, ta_name, tb_name):
    course_map = {c["course_id"]: c["name"] for c in courses}
    course_ids = list(course_map.keys())

    with st.form(f"edit_round_{round_id}"):
        r_col1, r_col2 = st.columns(2)
        r_num  = r_col1.number_input("Round Number", min_value=1, step=1,
                                      value=int(rnd["round_number"]))
        r_date = r_col2.date_input("Date", value=_parse_date(rnd["date"]))

        cur_course_idx = course_ids.index(rnd["course_id"]) \
                         if rnd["course_id"] in course_ids else 0
        r_course_idx   = st.selectbox(
            "Course", range(len(course_ids)),
            index=cur_course_idx,
            format_func=lambda i: course_map[course_ids[i]],
        )
        r_course_id = course_ids[r_course_idx]

        decks      = list_tee_decks(r_course_id)
        deck_ids   = [None] + [d["tee_id"] for d in decks]
        deck_labels = ["— not set —"] + \
                      [f"{d['name']} (Rating {d['rating']}, Slope {d['slope']})"
                       for d in decks]

        cur_tee_a = rnd["tee_id_a"]
        cur_tee_b = rnd["tee_id_b"]
        tee_a_idx = deck_ids.index(cur_tee_a) if cur_tee_a in deck_ids else 0
        tee_b_idx = deck_ids.index(cur_tee_b) if cur_tee_b in deck_ids else 0

        r_col3, r_col4 = st.columns(2)
        new_tee_a_idx = r_col3.selectbox(f"Tee — {ta_name}", range(len(deck_ids)),
                                          index=tee_a_idx,
                                          format_func=lambda i: deck_labels[i],
                                          key=f"edit_tee_a_{round_id}")
        new_tee_b_idx = r_col4.selectbox(f"Tee — {tb_name}", range(len(deck_ids)),
                                          index=tee_b_idx,
                                          format_func=lambda i: deck_labels[i],
                                          key=f"edit_tee_b_{round_id}")

        cur_fmt_idx = FORMAT_OPTIONS.index(rnd["format_code"]) \
                      if rnd["format_code"] in FORMAT_OPTIONS else 0
        fmt_idx = st.selectbox("Format", range(len(FORMAT_OPTIONS)),
                                index=cur_fmt_idx,
                                format_func=lambda i: FORMAT_DISPLAY[i])

        r_holes = st.radio("Holes", [18, 9],
                            index=0 if int(rnd["holes"]) == 18 else 1,
                            horizontal=True)

        col_s, col_d = st.columns([3, 1])
        save_rnd = col_s.form_submit_button("💾 Save Round", use_container_width=True,
                                              type="primary")
        del_rnd  = col_d.form_submit_button("🗑️ Delete", use_container_width=True)

        if save_rnd:
            update_round(
                round_id=round_id,
                course_id=r_course_id,
                date=str(r_date),
                format_code=FORMAT_OPTIONS[fmt_idx],
                round_number=int(r_num),
                holes=r_holes,
                tee_id_a=deck_ids[new_tee_a_idx],
                tee_id_b=deck_ids[new_tee_b_idx],
            )
            st.success("Round updated.")
            st.rerun()
        if del_rnd:
            delete_round(round_id)
            st.warning("Round deleted.")
            st.rerun()


# ---------------------------------------------------------------
# Sidebar — create new event
# ---------------------------------------------------------------
with st.sidebar:
    st.header("➕ Create New Event")
    with st.form("create_event_form", clear_on_submit=True):
        ev_name   = st.text_input("Event Name *", placeholder="e.g. Heron Point Cup 2025")
        ev_date   = st.date_input("Start Date *")
        ev_ta     = st.text_input("Team A Name", value="Team A")
        ev_tb     = st.text_input("Team B Name", value="Team B")
        ev_mode   = st.selectbox("Handicap Mode", list(HANDICAP_MODES.keys()),
                                  format_func=lambda k: HANDICAP_MODES[k].split("—")[0].strip())
        ev_pct    = st.number_input("Allowance % (if applicable)",
                                     min_value=50, max_value=100, step=5, value=100)
        submitted = st.form_submit_button("Create Event", use_container_width=True,
                                           type="primary")
        if submitted:
            if not ev_name.strip():
                st.error("Event name is required.")
            else:
                eid = create_event(
                    name=ev_name,
                    start_date=str(ev_date),
                    team_a_name=ev_ta or "Team A",
                    team_b_name=ev_tb or "Team B",
                    handicap_mode=ev_mode,
                    allowance_pct=float(ev_pct),
                )
                st.success(f"✅ {ev_name.strip()} created.")
                st.rerun()

# ---------------------------------------------------------------
# Event list
# ---------------------------------------------------------------
events = list_events()

if not events:
    st.info("No events yet. Create your first event using the sidebar.")
    st.stop()

# Status filter
status_filter = st.selectbox("Filter by status", ["All"] + EVENT_STATUSES, index=0)
filtered = [e for e in events if status_filter == "All" or e["status"] == status_filter]

st.markdown(f"**{len(filtered)} event(s)**")
st.markdown("---")

for event in filtered:
    eid     = event["event_id"]
    summary = get_event_summary(eid)
    rounds  = list_rounds(eid)
    players = get_event_players(eid)

    label = (
        f"**{event['name']}**  |  {event['start_date']}  |  "
        f"{event['status']}  |  "
        f"{summary['team_a_count']}v{summary['team_b_count']} players  |  "
        f"{len(rounds)} round(s)"
    )

    with st.expander(label, expanded=False):
        tab_ev, tab_roster, tab_rounds = st.tabs(
            ["📋 Event Details", "👥 Team Roster", "📅 Rounds"]
        )

        # -------------------------------------------------------
        # Tab 1 — Event details / edit
        # -------------------------------------------------------
        with tab_ev:
            with st.form(f"edit_event_{eid}"):
                e_col1, e_col2 = st.columns(2)
                e_name  = e_col1.text_input("Event Name *", value=event["name"])
                e_date  = e_col2.date_input("Start Date",
                                              value=_parse_date(event["start_date"]))
                e_ta    = e_col1.text_input("Team A Name", value=event["team_a_name"])
                e_tb    = e_col2.text_input("Team B Name", value=event["team_b_name"])

                mode_keys    = list(HANDICAP_MODES.keys())
                mode_idx     = mode_keys.index(event["handicap_mode"]) \
                               if event["handicap_mode"] in mode_keys else 0
                e_mode  = st.selectbox(
                    "Handicap Mode",
                    mode_keys,
                    index=mode_idx,
                    format_func=lambda k: HANDICAP_MODES[k].split("—")[0].strip(),
                )
                e_pct   = st.number_input("Allowance %",
                                           min_value=50, max_value=100, step=5,
                                           value=int(event["allowance_pct"]))
                e_status = st.selectbox(
                    "Status", EVENT_STATUSES,
                    index=EVENT_STATUSES.index(event["status"])
                    if event["status"] in EVENT_STATUSES else 0,
                )

                col_s, col_d = st.columns([3, 1])
                save_ev = col_s.form_submit_button("💾 Save Changes",
                                                    use_container_width=True,
                                                    type="primary")
                del_ev  = col_d.form_submit_button("🗑️ Delete Event",
                                                    use_container_width=True)

                if save_ev:
                    if not e_name.strip():
                        st.error("Event name required.")
                    else:
                        update_event(eid, e_name, str(e_date), e_ta, e_tb,
                                     e_mode, float(e_pct), e_status)
                        st.success("Event updated.")
                        st.rerun()
                if del_ev:
                    delete_event(eid)
                    st.warning("Event deleted.")
                    st.rerun()

            # Handicap mode explanation
            st.info(f"ℹ️  {HANDICAP_MODES.get(event['handicap_mode'], '')}")

        # -------------------------------------------------------
        # Tab 2 — Team roster assignment
        # -------------------------------------------------------
        with tab_roster:
            teams = get_event_players_by_team(eid)
            ta_name = event["team_a_name"]
            tb_name = event["team_b_name"]

            with st.form(f"roster_form_{eid}"):
                col_a, col_b = st.columns(2)

                with col_a:
                    st.markdown(f"**{ta_name}**")
                    team_a_players = teams["A"]
                    if team_a_players:
                        for p in team_a_players:
                            role_str = p["role"] if "role" in p.keys() else "Player"
                            rc1, rc2, rc3 = st.columns([5, 4, 3])
                            role_badge = "🎖️" if role_str == "Captain" else ("🏅" if role_str == "Alternate Captain" else "•")
                            rc1.markdown(f"{role_badge} {p['name']} ({p['current_index']:.1f})")
                            
                            roles = ["Player", "Captain", "Alternate Captain"]
                            cur_idx = roles.index(role_str) if role_str in roles else 0
                            rc2.selectbox("Role", roles, index=cur_idx, key=f"role_a_{eid}_{p['player_id']}", label_visibility="collapsed")
                            rc3.checkbox("Remove", key=f"rm_a_{eid}_{p['player_id']}")
                    else:
                        st.caption("No players assigned yet.")

                with col_b:
                    st.markdown(f"**{tb_name}**")
                    team_b_players = teams["B"]
                    if team_b_players:
                        for p in team_b_players:
                            role_str = p["role"] if "role" in p.keys() else "Player"
                            rc1, rc2, rc3 = st.columns([5, 4, 3])
                            role_badge = "🎖️" if role_str == "Captain" else ("🏅" if role_str == "Alternate Captain" else "•")
                            rc1.markdown(f"{role_badge} {p['name']} ({p['current_index']:.1f})")
                            
                            roles = ["Player", "Captain", "Alternate Captain"]
                            cur_idx = roles.index(role_str) if role_str in roles else 0
                            rc2.selectbox("Role", roles, index=cur_idx, key=f"role_b_{eid}_{p['player_id']}", label_visibility="collapsed")
                            rc3.checkbox("Remove", key=f"rm_b_{eid}_{p['player_id']}")
                    else:
                        st.caption("No players assigned yet.")
                
                if st.form_submit_button("Save Roster Changes", type="primary", use_container_width=True):
                    # Process team A
                    for p in team_a_players:
                        pid = p["player_id"]
                        if st.session_state.get(f"rm_a_{eid}_{pid}"):
                            remove_player_from_event(eid, pid)
                        else:
                            new_r = st.session_state.get(f"role_a_{eid}_{pid}")
                            old_r = p["role"] if "role" in p.keys() else "Player"
                            if new_r and new_r != old_r:
                                set_player_role(eid, pid, new_r)
                    
                    # Process team B
                    for p in team_b_players:
                        pid = p["player_id"]
                        if st.session_state.get(f"rm_b_{eid}_{pid}"):
                            remove_player_from_event(eid, pid)
                        else:
                            new_r = st.session_state.get(f"role_b_{eid}_{pid}")
                            old_r = p["role"] if "role" in p.keys() else "Player"
                            if new_r and new_r != old_r:
                                set_player_role(eid, pid, new_r)
                    
                    st.success("Roster updated.")
                    st.rerun()

            st.markdown("---")
            st.markdown("**Assign a Player**")
            unassigned = get_unassigned_players(eid)

            if not unassigned:
                st.caption("All roster players are assigned to this event.")
            else:
                with st.form(f"assign_player_{eid}", clear_on_submit=True):
                    player_names = [f"{p['name']} ({p['current_index']:.1f})"
                                    for p in unassigned]
                    chosen_idx  = st.selectbox("Player", range(len(player_names)),
                                                format_func=lambda i: player_names[i])
                    chosen_team = st.radio("Assign to Team",
                                           [f"Team A — {ta_name}", f"Team B — {tb_name}"],
                                           horizontal=True)
                    team_letter = "A" if "Team A" in chosen_team else "B"

                    assign_btn = st.form_submit_button("Assign Player", type="primary")
                    if assign_btn:
                        chosen_player = unassigned[chosen_idx]
                        assign_player(eid, chosen_player["player_id"], team_letter)
                        st.success(
                            f"{chosen_player['name']} assigned to "
                            f"{'Team A — ' + ta_name if team_letter == 'A' else 'Team B — ' + tb_name}."
                        )
                        st.rerun()

        # -------------------------------------------------------
        # Tab 3 — Rounds
        # -------------------------------------------------------
        with tab_rounds:
            courses = list_courses()

            if not courses:
                st.warning("⚠️ No courses in the library. Add a course first.")
            else:
                # Display existing rounds
                if rounds:
                    st.markdown("**Scheduled Rounds**")
                    for rnd in rounds:
                        rid = rnd["round_id"]
                        rnd_label = (
                            f"Round {rnd['round_number']} — {rnd['date']}  |  "
                            f"{rnd['course_name']}  |  "
                            f"{FORMAT_LABELS.get(rnd['format_code'], rnd['format_code'])}  |  "
                            f"{rnd['holes']} holes"
                        )
                        with st.expander(rnd_label, expanded=False):
                            _render_round_edit_form(rid, rnd, courses, eid,
                                                     event["team_a_name"],
                                                     event["team_b_name"])
                else:
                    st.caption("No rounds yet. Add the first round below.")

                st.markdown("---")
                st.markdown("**Add a Round**")
                _render_round_add_form(eid, courses, event["team_a_name"],
                                       event["team_b_name"], len(rounds) + 1)


# ---------------------------------------------------------------
# Utility
# ---------------------------------------------------------------

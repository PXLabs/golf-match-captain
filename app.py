"""
app.py — Golf Match Captain
Streamlit entry point with live Dashboard.
Phase 1E: Dashboard shows live event score, round status, player form.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st
from database.db import initialise_database

st.set_page_config(
    page_title="Golf Match Captain",
    page_icon="⛳",
    layout="wide",
    initial_sidebar_state="expanded",
)

initialise_database()


def _show_welcome():
    st.markdown(
        """
        **Welcome to Golf Match Captain.** Use the sidebar to navigate.

        | Screen | Purpose |
        |---|---|
        | 👥 Roster Manager | Add players, enter score history, view intelligence signals |
        | ⛳ Course Library | Add courses and tee decks with stroke index |
        | 📅 Event Setup | Create events, assign teams, configure rounds |
        | 📊 Match Analysis | Pre-round handicap view and AI context |
        | ✅ Results Entry | Record match results and track the running score |

        *Start by adding players in Roster Manager, then create an event.*
        """
    )




st.title("⛳ Golf Match Captain")
st.caption("AI-Powered Pairing & Analysis Tool")
st.markdown("---")

try:
    from modules.events import list_events, list_rounds, get_event_players
    from modules.results import get_event_score, get_player_results
    from modules.handicap import FORMAT_LABELS

    events = list_events(status="ACTIVE")

    if not events:
        _show_welcome()
    else:
        event  = events[0]
        eid    = event["event_id"]
        ev_ta  = event["team_a_name"]
        ev_tb  = event["team_b_name"]
        score  = get_event_score(eid)
        rounds = list_rounds(eid)

        st.subheader(f"🏆 {event['name']}")
        st.caption(
            f"Started {event['start_date']}  |  "
            f"{event['handicap_mode'].replace('_', ' ').title()}"
        )

        # Score banner
        s1, s2, s3, s4 = st.columns(4)
        s1.metric(ev_ta, f"{score['total_points_a']:.1f} pts")
        s2.metric(ev_tb, f"{score['total_points_b']:.1f} pts")
        s3.metric("Rounds", f"{score['rounds_completed']} of {len(rounds)} done")
        gap    = score["total_points_a"] - score["total_points_b"]
        leader = ev_ta if gap > 0 else ev_tb if gap < 0 else "Level"
        s4.metric("Standing", leader,
                   delta=f"{abs(gap):.1f} pts ahead" if gap != 0 else "All square")

        st.markdown("---")

        # Round breakdown
        st.markdown("**Round Summary**")
        for r in score["per_round"]:
            col_r, col_s, col_f = st.columns([2, 4, 3])
            col_r.markdown(f"**Round {r['round_number']}** — {r['date']}")
            col_f.caption(FORMAT_LABELS.get(r["format_code"], r["format_code"]))
            if r["matches_played"] > 0:
                pending_note = (f" *({r['matches_pending']} pending)*"
                                if r["matches_pending"] else "")
                col_s.markdown(
                    f"{ev_ta} **{r['points_a']:.1f}** – **{r['points_b']:.1f}** "
                    f"{ev_tb}{pending_note}"
                )
            else:
                col_s.caption("Not started")

        # Player form
        p_stats = get_player_results(eid)
        played_stats = [s for s in p_stats if s["W"] + s["L"] + s["H"] > 0]
        if played_stats:
            players_map = {p["player_id"]: p for p in get_event_players(eid)}
            top = sorted(played_stats, key=lambda x: -x["pts"])[:6]

            st.markdown("---")
            st.markdown("**Player Form**")
            cols = st.columns(min(len(top), 3))
            for i, s in enumerate(top):
                pinfo = players_map.get(s["player_id"])
                name  = pinfo["name"] if pinfo else f"Player {s['player_id']}"
                team  = (ev_ta if pinfo and pinfo["team"] == "A"
                          else ev_tb) if pinfo else "—"
                cols[i % 3].metric(
                    f"{name} ({team})",
                    f"{s['pts']:.1f} pts",
                    f"{s['W']}W / {s['L']}L / {s['H']}H",
                )

        st.markdown("---")
        st.markdown("**Quick Links**")
        ql1, ql2, ql3 = st.columns(3)
        ql1.page_link("pages/05_Match_Analysis.py", label="📊 Match Analysis", icon="📊")
        ql2.page_link("pages/06_Results.py",        label="✅ Results Entry",  icon="✅")
        ql3.page_link("pages/02_Roster.py",         label="👥 Roster Manager", icon="👥")

        if len(events) > 1:
            st.markdown("---")
            st.caption("Other active events: "
                        + ", ".join(e["name"] for e in events[1:]))

except Exception as exc:
    _show_welcome()
    st.caption(f"_(Dashboard unavailable: {exc})_")

"""
07_Scoreboard.py — Read-Only Shared Scoreboard (Phase 2B)
Golf Match Captain

A password-protected read-only view for players and other captains.
Shows the running team score, round-by-round breakdown, match results,
and player form — without exposing any captain-only data (intelligence
flags, sandbagging signals, advisor, settings).

Password is set in .env or .streamlit/secrets.toml:
    SCOREBOARD_PASSWORD=yourpassword

If no password is configured, the page is open to anyone on the
same machine (appropriate for local use on a shared laptop).
"""

import sys, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
from database.db import initialise_database
from modules.events import list_events, get_event, list_rounds, get_event_players_by_team
from modules.results import (
    get_event_score, get_player_results, get_matches_with_players,
)
from modules.handicap import FORMAT_LABELS

initialise_database()

# ---------------------------------------------------------------
# Password gate
# ---------------------------------------------------------------

def _get_scoreboard_password() -> str | None:
    """Return the configured scoreboard password, or None if not set."""
    # Check Streamlit secrets
    try:
        return st.secrets.get("SCOREBOARD_PASSWORD", None)
    except Exception:
        pass
    # Check environment
    return os.environ.get("SCOREBOARD_PASSWORD", None) or None


def _check_access() -> bool:
    """
    Return True if the user has access.
    If no password is configured, always grants access.
    Tracks auth state in st.session_state.
    """
    required_pw = _get_scoreboard_password()
    if not required_pw:
        return True  # Open access — no password configured

    if st.session_state.get("scoreboard_authed"):
        return True

    st.markdown("### 🔒 Scoreboard Access")
    st.caption("Enter the event password to view the scoreboard.")
    entered = st.text_input("Password", type="password", key="sb_pw_input")
    if st.button("View Scoreboard", type="primary"):
        if entered == required_pw:
            st.session_state["scoreboard_authed"] = True
            st.rerun()
        else:
            st.error("Incorrect password.")
    return False


# ---------------------------------------------------------------
# Page
# ---------------------------------------------------------------

st.title("⛳ Golf Match Captain — Scoreboard")
st.caption("Live event scores and results.")

if not _check_access():
    st.stop()

st.markdown("---")

# Event selector — show active events only
events = list_events(status="ACTIVE")
if not events:
    st.info("No active events at the moment.")
    st.stop()

if len(events) == 1:
    selected_event = events[0]
else:
    event_map = {e["event_id"]: e["name"] for e in events}
    eid = st.selectbox("Event", list(event_map.keys()),
                        format_func=lambda i: event_map[i])
    selected_event = next(e for e in events if e["event_id"] == eid)

eid   = selected_event["event_id"]
ev_ta = selected_event["team_a_name"]
ev_tb = selected_event["team_b_name"]
score = get_event_score(eid)
rounds = list_rounds(eid)

# ---------------------------------------------------------------
# Score banner
# ---------------------------------------------------------------
st.subheader(f"🏆 {selected_event['name']}")
st.caption(f"Started {selected_event['start_date']}")

s1, s2, s3 = st.columns(3)
s1.metric(ev_ta, f"{score['total_points_a']:.1f} pts")
s2.metric(ev_tb, f"{score['total_points_b']:.1f} pts")
gap    = score["total_points_a"] - score["total_points_b"]
leader = ev_ta if gap > 0 else ev_tb if gap < 0 else "Level"
s3.metric(
    "Standing", leader,
    delta=f"{abs(gap):.1f} ahead" if gap != 0 else "All square",
)

st.markdown("---")

# ---------------------------------------------------------------
# Round-by-round breakdown
# ---------------------------------------------------------------
st.subheader("📋 Round Scores")

for r in score["per_round"]:
    c1, c2, c3 = st.columns([2, 4, 3])
    c1.markdown(f"**Round {r['round_number']}** — {r['date']}")
    c3.caption(FORMAT_LABELS.get(r["format_code"], r["format_code"]))
    if r["matches_played"] > 0:
        pending = f" *({r['matches_pending']} pending)*" if r["matches_pending"] else ""
        c2.markdown(
            f"{ev_ta} **{r['points_a']:.1f}** – **{r['points_b']:.1f}** {ev_tb}{pending}"
        )
    else:
        c2.caption("Not yet played")

st.markdown("---")

# ---------------------------------------------------------------
# Match results — expandable per round
# ---------------------------------------------------------------
st.subheader("🏌️ Match Results")

for rnd in rounds:
    rid     = rnd["round_id"]
    matches = get_matches_with_players(rid)
    played  = [m for m in matches if m["result"]]
    pending = [m for m in matches if not m["result"]]

    label = (
        f"Round {rnd['round_number']} — {rnd['date']}  |  "
        f"{FORMAT_LABELS.get(rnd['format_code'], rnd['format_code'])}  |  "
        f"{len(played)} result(s)"
        + (f" · {len(pending)} pending" if pending else "")
    )

    with st.expander(label, expanded=False):
        if not matches:
            st.caption("Draw not yet published.")
            continue

        for m in matches:
            a_name = _pair_label(m["a1_name"], m["a2_name"])
            b_name = _pair_label(m["b1_name"], m["b2_name"])

            mc1, mc2, mc3 = st.columns([3, 3, 3])
            mc1.markdown(f"**{a_name}**")
            mc3.markdown(f"**{b_name}**")

            if m["result"]:
                result_str = {
                    "A":      f"✅ {ev_ta} win",
                    "B":      f"✅ {ev_tb} win",
                    "HALVED": "🤝 Halved",
                }.get(m["result"], m["result"])
                detail = f" ({m['result_detail']})" if m.get("result_detail") else ""
                mc2.markdown(f"*{result_str}{detail}*")
            else:
                mc2.caption("—  pending  —")

st.markdown("---")

# ---------------------------------------------------------------
# Player form table
# ---------------------------------------------------------------
st.subheader("👤 Player Form")

p_stats = get_player_results(eid)
teams   = get_event_players_by_team(eid)
all_players = {
    p["player_id"]: p
    for p in teams["A"] + teams["B"]
}

played_stats = [s for s in p_stats if s["W"] + s["L"] + s["H"] > 0]
if not played_stats:
    st.caption("No results recorded yet.")
else:
    import pandas as pd
    rows = []
    for s in sorted(played_stats, key=lambda x: -x["pts"]):
        pinfo  = all_players.get(s["player_id"])
        name   = pinfo["name"] if pinfo else f"Player {s['player_id']}"
        team   = (ev_ta if pinfo and pinfo["team"] == "A" else ev_tb) if pinfo else "—"
        played = s["W"] + s["L"] + s["H"]
        rows.append({
            "Player": name,
            "Team":   team,
            "W":      s["W"],
            "L":      s["L"],
            "H":      s["H"],
            "Points": s["pts"],
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ---------------------------------------------------------------
# Upcoming / next round
# ---------------------------------------------------------------
upcoming = [r for r in rounds if not any(
    m["result"] for m in get_matches_with_players(r["round_id"])
)]
if upcoming:
    next_rnd = upcoming[0]
    st.markdown("---")
    st.subheader("📅 Next Round")
    st.markdown(
        f"**Round {next_rnd['round_number']}** — {next_rnd['date']}  |  "
        f"{FORMAT_LABELS.get(next_rnd['format_code'], next_rnd['format_code'])}  |  "
        f"{next_rnd['holes']} holes  |  {next_rnd['course_name']}"
    )

st.markdown("---")
st.caption("Golf Match Captain · Read-only view · Scores update in real time.")


def _pair_label(n1, n2):
    if n1 and n2:
        return f"{n1} & {n2}"
    return n1 or "TBD"

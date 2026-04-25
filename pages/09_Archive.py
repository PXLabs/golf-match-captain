"""
09_Archive.py — Event Archive & Career Stats
Golf Match Captain

Read-only view of completed and archived events:
  - Full results per event
  - Year-over-year career stats per player
  - Per-event scoreboard
  - CSV download of archive data
"""

import sys
from pathlib import Path
from datetime import datetime
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
from database.db import initialise_database, fetchall
from modules.events import list_events, get_event, list_rounds, get_event_players_by_team
from modules.results import get_event_score, get_player_results, get_matches_with_players
from modules.handicap import FORMAT_LABELS

initialise_database()

def _pair(n1, n2):
    if n1 and n2:
        return f"{n1} & {n2}"
    return n1 or "TBD"

st.title("🗄️ Event Archive")
st.caption("Historical results and career performance across all events.")
st.markdown("---")

# ---------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------
tab_archive, tab_career = st.tabs(["📋 Event Archive", "🏆 Career Stats"])

# ==============================================================
# Tab 1 — Event Archive
# ==============================================================
with tab_archive:

    all_events = list_events()
    if not all_events:
        st.info("No events in the database yet.")
        st.stop()

    # Filter controls
    status_filter = st.selectbox(
        "Show", ["All Events", "Completed", "Active", "Archived"],
        index=0,
    )
    status_map = {
        "All Events": None,
        "Completed":  "COMPLETED",
        "Active":     "ACTIVE",
        "Archived":   "ARCHIVED",
    }
    filter_val = status_map[status_filter]
    filtered   = [e for e in all_events
                  if filter_val is None or e["status"] == filter_val]

    st.markdown(f"**{len(filtered)} event(s)**")

    for event in filtered:
        eid   = event["event_id"]
        ev_ta = event["team_a_name"]
        ev_tb = event["team_b_name"]
        score = get_event_score(eid)
        rounds = list_rounds(eid)

        gap    = score["total_points_a"] - score["total_points_b"]
        winner = ev_ta if gap > 0 else ev_tb if gap < 0 else "Tied"

        status_badge = {"ACTIVE": "🟢", "COMPLETED": "✅", "ARCHIVED": "📦"}.get(
            event["status"], "❓"
        )

        label = (
            f"{status_badge} **{event['name']}**  |  "
            f"{event['start_date']}  |  "
            f"{ev_ta} {score['total_points_a']:.1f} – "
            f"{score['total_points_b']:.1f} {ev_tb}  |  "
            f"{'Winner: ' + winner if gap != 0 else 'Tied'}"
        )

        with st.expander(label, expanded=False):

            # Score summary
            sc1, sc2, sc3, sc4 = st.columns(4)
            sc1.metric(ev_ta,    f"{score['total_points_a']:.1f} pts")
            sc2.metric(ev_tb,    f"{score['total_points_b']:.1f} pts")
            sc3.metric("Winner", winner)
            sc4.metric("Rounds", len(rounds))

            st.markdown("---")

            # Round-by-round
            st.markdown("**Round Scores**")
            for r in score["per_round"]:
                rc1, rc2, rc3 = st.columns([2, 4, 3])
                rc1.markdown(f"Round {r['round_number']} — {r['date']}")
                rc3.caption(FORMAT_LABELS.get(r["format_code"], r["format_code"]))
                if r["matches_played"] > 0:
                    rc2.markdown(
                        f"{ev_ta} **{r['points_a']:.1f}** – "
                        f"**{r['points_b']:.1f}** {ev_tb}"
                    )
                else:
                    rc2.caption("No results")

            # Match results per round
            st.markdown("---")
            st.markdown("**Match Results**")
            for rnd in rounds:
                st.markdown(
                    f"*Round {rnd['round_number']} — "
                    f"{FORMAT_LABELS.get(rnd['format_code'], rnd['format_code'])}*"
                )
                matches = get_matches_with_players(rnd["round_id"])
                if not matches:
                    st.caption("No matches recorded.")
                    continue

                for m in matches:
                    a_label = _pair(m["a1_name"], m["a2_name"])
                    b_label = _pair(m["b1_name"], m["b2_name"])
                    result  = m["result"] or "—"
                    detail  = m.get("result_detail") or ""

                    result_str = {
                        "A":      f"✅ {ev_ta}",
                        "B":      f"✅ {ev_tb}",
                        "HALVED": "🤝 Halved",
                        "—":      "Pending",
                    }.get(result, result)

                    mc1, mc2, mc3 = st.columns([3, 3, 3])
                    mc1.caption(a_label)
                    mc2.caption(f"{result_str}{' (' + detail + ')' if detail else ''}")
                    mc3.caption(b_label)

            # Player form for this event
            st.markdown("---")
            st.markdown("**Player Form**")
            p_stats = get_player_results(eid)
            teams   = get_event_players_by_team(eid)
            p_map   = {p["player_id"]: p
                       for p in teams["A"] + teams["B"]}
            played_stats = [s for s in p_stats
                            if s["W"] + s["L"] + s["H"] > 0]

            if played_stats:
                form_rows = []
                for s in sorted(played_stats, key=lambda x: -x["pts"]):
                    pinfo = p_map.get(s["player_id"])
                    name  = pinfo["name"] if pinfo else f"#{s['player_id']}"
                    team  = (ev_ta if pinfo and pinfo["team"] == "A"
                              else ev_tb) if pinfo else "—"
                    form_rows.append({
                        "Player": name, "Team": team,
                        "W": s["W"], "L": s["L"], "H": s["H"],
                        "Points": s["pts"],
                    })
                st.dataframe(
                    pd.DataFrame(form_rows),
                    use_container_width=True, hide_index=True,
                )
            else:
                st.caption("No individual results recorded.")

    # CSV export of all archived results
    st.markdown("---")
    result_rows = fetchall("""
        SELECT e.name AS event, e.start_date,
               ep_a.name AS team_a, ep_b.name AS team_b,
               r.round_number, r.date AS round_date,
               r.format_code, m.match_order,
               COALESCE(pa1.name,'—') AS a_p1,
               COALESCE(pa2.name,'') AS a_p2,
               COALESCE(pb1.name,'—') AS b_p1,
               COALESCE(pb2.name,'') AS b_p2,
               m.result, m.result_detail
        FROM match m
        JOIN round r  ON r.round_id = m.round_id
        JOIN event e  ON e.event_id = r.event_id
        JOIN event ep_a ON ep_a.event_id = e.event_id
        JOIN event ep_b ON ep_b.event_id = e.event_id
        LEFT JOIN player pa1 ON pa1.player_id = m.team_a_player1_id
        LEFT JOIN player pa2 ON pa2.player_id = m.team_a_player2_id
        LEFT JOIN player pb1 ON pb1.player_id = m.team_b_player1_id
        LEFT JOIN player pb2 ON pb2.player_id = m.team_b_player2_id
        WHERE m.result IS NOT NULL
        ORDER BY e.start_date DESC, r.round_number, m.match_order
    """)

    if result_rows:
        df_export = pd.DataFrame([dict(r) for r in result_rows])
        ts = datetime.now().strftime("%Y%m%d")
        st.download_button(
            "⬇️ Download Full Archive CSV",
            df_export.to_csv(index=False).encode("utf-8"),
            f"gmc_archive_{ts}.csv",
            "text/csv",
            use_container_width=True,
        )


# ==============================================================
# Tab 2 — Career Stats
# ==============================================================
with tab_career:
    st.markdown(
        "Career performance across all recorded events. "
        "Only players who have appeared in at least one match are shown."
    )

    career_rows = fetchall("""
        SELECT
            p.name                                          AS player,
            COUNT(DISTINCT ep.event_id)                     AS events,
            SUM(CASE
                WHEN ep.team='A' AND m.result='A' THEN 1
                WHEN ep.team='B' AND m.result='B' THEN 1
                ELSE 0 END)                                 AS wins,
            SUM(CASE
                WHEN ep.team='A' AND m.result='B' THEN 1
                WHEN ep.team='B' AND m.result='A' THEN 1
                ELSE 0 END)                                 AS losses,
            SUM(CASE WHEN m.result='HALVED' THEN 1 ELSE 0 END) AS halved,
            ROUND(SUM(CASE
                WHEN ep.team='A' AND m.result='A' THEN 1.0
                WHEN ep.team='B' AND m.result='B' THEN 1.0
                WHEN m.result='HALVED'             THEN 0.5
                ELSE 0 END), 1)                             AS points,
            MIN(e.start_date)                               AS first_event,
            MAX(e.start_date)                               AS last_event,
            p.current_index                                 AS current_index
        FROM event_player ep
        JOIN player p ON p.player_id = ep.player_id
        JOIN event  e ON e.event_id  = ep.event_id
        LEFT JOIN match m ON m.round_id IN (
            SELECT round_id FROM round WHERE event_id = ep.event_id
        ) AND (
            m.team_a_player1_id = ep.player_id OR
            m.team_a_player2_id = ep.player_id OR
            m.team_b_player1_id = ep.player_id OR
            m.team_b_player2_id = ep.player_id
        ) AND m.result IS NOT NULL
        GROUP BY p.player_id
        HAVING wins + losses + halved > 0
        ORDER BY points DESC, wins DESC
    """)

    if not career_rows:
        st.info("No match results recorded yet. Complete an event to see career stats.")
    else:
        career_data = [dict(r) for r in career_rows]
        for row in career_data:
            played = row["wins"] + row["losses"] + row["halved"]
            row["W/L/H"]   = f"{row['wins']}/{row['losses']}/{row['halved']}"
            row["Played"]  = played
            row["Win %"]   = f"{row['wins']/played*100:.0f}%" if played else "—"

        df = pd.DataFrame(career_data)
        display_cols = ["player", "events", "Played", "W/L/H", "Win %",
                         "points", "current_index", "first_event", "last_event"]
        display_cols = [c for c in display_cols if c in df.columns]
        df_display = df[display_cols].copy()
        df_display.columns = ["Player", "Events", "Played", "W/L/H", "Win %",
                                "Points", "Current Index",
                                "First Event", "Last Event"]

        # Highlight the leaderboard
        st.dataframe(df_display, use_container_width=True, hide_index=True)

        # Summary metrics
        st.markdown("---")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Players tracked", len(career_data))
        m2.metric("Total matches",   sum(r["Played"] for r in
                                         df_display.rename(
                                             columns={"Played":"P"}).to_dict("records")))
        top = career_data[0]
        m3.metric("Points leader",   top["player"], f"{top['points']:.1f} pts")
        best_wr = max(career_data,
                      key=lambda r: r["wins"]/(r["wins"]+r["losses"]+r["halved"])
                      if r["wins"]+r["losses"]+r["halved"] > 0 else 0)
        played_best = best_wr["wins"] + best_wr["losses"] + best_wr["halved"]
        m4.metric("Best win rate",
                   best_wr["player"],
                   f"{best_wr['wins']/played_best*100:.0f}%"
                   if played_best else "—")

        ts = datetime.now().strftime("%Y%m%d")
        st.download_button(
            "⬇️ Download Career Stats CSV",
            df_display.to_csv(index=False).encode("utf-8"),
            f"gmc_career_{ts}.csv",
            "text/csv",
        )


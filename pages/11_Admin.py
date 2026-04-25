"""
08_Data_Management.py — Data Management
Golf Match Captain

Covers:
  - Load test/demo data
  - Clear all data (with confirmation)
  - Download SQLite database backup
  - Export data to CSV (players, events, results, career stats)
"""

import sys, io, csv, json
from pathlib import Path
from datetime import datetime
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
from database.db import initialise_database, DB_PATH, fetchall
from modules.seed_data import seed_all, clear_all_data, is_seeded
from modules.verma_cup_seed import load_verma_cup

initialise_database()

st.title("⚙️ Admin & Archive")
st.caption("Seed demo data, clear the database, backup, restore, and raw table export/import.")
st.markdown("---")

# ---------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------
def _df_to_csv(df: pd.DataFrame) -> bytes:
    """Convert a DataFrame to CSV bytes."""
    return df.to_csv(index=False).encode("utf-8")

# ---------------------------------------------------------------
# Section 0 — Verma Cup 2026 Setup
# ---------------------------------------------------------------
st.subheader("⛳ Verma Cup 2026 — Load Real Data")

st.markdown(
    "Loads the real Verma Cup 2026 data — 12 players, 7 courses with full tee decks, "
    "and the Verma Cup event with all 7 rounds configured."
)

seeded = is_seeded()
vc_col1, vc_col2 = st.columns([3, 1])
with vc_col1:
    clear_first = st.checkbox(
        "Clear existing data first (replaces test data with real Verma Cup data)",
        value=True,
        key="vc_clear_first",
    )
with vc_col2:
    if st.button("⛳ Load Verma Cup Data", type="primary", use_container_width=True):
        with st.spinner("Loading Verma Cup 2026 data…"):
            result = load_verma_cup(force=clear_first)
        if result["success"]:
            st.success(result["message"])
            st.rerun()
        else:
            st.error(result["message"])

st.markdown("---")

# ---------------------------------------------------------------
# Section 1 — Test / Demo Data
# ---------------------------------------------------------------
st.subheader("🌱 Demo Data")

seeded = is_seeded()

col1, col2 = st.columns(2)
with col1:
    st.markdown(
        "Load a complete realistic demo dataset:\n"
        "- 8 players (4 per team) with varied intelligence profiles\n"
        "- 2 courses (Heron Point GC, Cobble Beach GC)\n"
        "- 1 completed 3-round event with full results\n"
        "- Score history producing 🔴 🟡 🟢 signals"
    )

with col2:
    if seeded:
        st.info("⚠️ Data already exists in the database.")

    load_mode = st.radio(
        "Load mode",
        ["Add to existing data", "Clear first, then load"],
        index=1 if not seeded else 0,
    )
    force = (load_mode == "Clear first, then load")

    if st.button("🌱 Load Demo Data", type="primary", use_container_width=True):
        with st.spinner("Loading demo data…"):
            result = seed_all(force=force)
        if result.get("skipped"):
            st.warning(result["reason"])
        else:
            st.success(
                f"✅ Demo data loaded: "
                f"{result['players']} players, "
                f"{result['courses']} courses, "
                f"{result['events']} event."
            )
            st.rerun()

st.markdown("---")

# ---------------------------------------------------------------
# Section 2 — Clear All Data
# ---------------------------------------------------------------
st.subheader("🗑️ Clear All Data")

st.warning(
    "**This permanently deletes all players, courses, events, results, "
    "and score history.** The database schema is preserved — the app "
    "will still work, just with no data."
)

with st.form("clear_confirm_form"):
    confirm_text = st.text_input(
        "Type **CLEAR** to confirm",
        placeholder="CLEAR",
    )
    clear_btn = st.form_submit_button("🗑️ Clear All Data", type="secondary",
                                       use_container_width=True)
    if clear_btn:
        if confirm_text.strip().upper() == "CLEAR":
            clear_all_data()
            st.success("✅ All data cleared. The database is now empty.")
            st.rerun()
        else:
            st.error("Type CLEAR (all caps) to confirm.")

st.markdown("---")

# ---------------------------------------------------------------
# Section 3 — Database Archive Restore
# ---------------------------------------------------------------
st.subheader("💾 Database Archive Restore")

st.markdown(
    "Download a complete snapshot of the database, or upload an existing `.db` file to completely overwrite the current system state."
)

col_bkp, col_rst = st.columns(2)

with col_bkp:
    st.markdown("**Download Snapshot (.db)**")
    if DB_PATH.exists():
        db_bytes  = DB_PATH.read_bytes()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        st.download_button(
            label="⬇️ Download golf_captain.db",
            data=db_bytes,
            file_name=f"golf_captain_backup_{timestamp}.db",
            mime="application/octet-stream",
            use_container_width=True,
        )
        db_size = DB_PATH.stat().st_size
        st.caption(f"Database size: {db_size / 1024:.1f} KB")
    else:
        st.info("Database file not found.")

with col_rst:
    st.markdown("**Upload & Restore Snapshot (.db)**")
    uploaded_db = st.file_uploader("Replace database with snapshot", type=["db", "sqlite", "sqlite3"], label_visibility="collapsed")
    if uploaded_db:
        if st.button("⚠️ Restore Database File (Irreversible)", type="primary", use_container_width=True):
            DB_PATH.write_bytes(uploaded_db.getvalue())
            initialise_database()
            st.success("✅ Database restored successfully! The app will now reload.")
            st.rerun()

st.markdown("---")

# ---------------------------------------------------------------
# Section 4 — CSV Exports
# ---------------------------------------------------------------
st.subheader("📥 Export to CSV")

export_tab1, export_tab2, export_tab3, export_tab4 = st.tabs([
    "👥 Players & Scores",
    "📅 Events & Rounds",
    "✅ Match Results",
    "🏆 Career Stats",
])

# ---- Tab 1: Players & Scores ----
with export_tab1:
    st.markdown("**Player roster with intelligence summary and score history.**")

    players_rows = fetchall("""
        SELECT p.player_id, p.name, p.cpga_id, p.current_index,
               p.tee_preference, p.notes
        FROM player p
        ORDER BY p.name
    """)

    if not players_rows:
        st.caption("No players in the database.")
    else:
        # Roster summary
        roster_df = pd.DataFrame([dict(r) for r in players_rows])
        roster_df.columns = ["ID", "Name", "CPGA ID", "Index",
                               "Tee Preference", "Notes"]
        st.dataframe(roster_df, use_container_width=True, hide_index=True)

        roster_csv = _df_to_csv(roster_df)
        ts = datetime.now().strftime("%Y%m%d")
        st.download_button(
            "⬇️ Download Roster CSV",
            roster_csv,
            f"gmc_roster_{ts}.csv",
            "text/csv",
        )

        st.markdown("---")
        st.markdown("**Score History (all players)**")

        score_rows = fetchall("""
            SELECT p.name as player, s.date, s.course, s.tee_deck,
                   s.posted_score, s.differential
            FROM score_record s
            JOIN player p ON p.player_id = s.player_id
            ORDER BY p.name, s.date DESC
        """)
        if score_rows:
            score_df = pd.DataFrame([dict(r) for r in score_rows])
            score_df.columns = ["Player", "Date", "Course", "Tee",
                                  "Posted Score", "Differential"]
            st.dataframe(score_df, use_container_width=True, hide_index=True)
            st.download_button(
                "⬇️ Download Score History CSV",
                _df_to_csv(score_df),
                f"gmc_scores_{ts}.csv",
                "text/csv",
            )
        else:
            st.caption("No score records.")

# ---- Tab 2: Events & Rounds ----
with export_tab2:
    st.markdown("**All events and their configured rounds.**")

    event_rows = fetchall("""
        SELECT e.event_id, e.name, e.start_date, e.status,
               e.team_a_name, e.team_b_name,
               e.handicap_mode, e.allowance_pct
        FROM event e
        ORDER BY e.start_date DESC
    """)

    if not event_rows:
        st.caption("No events in the database.")
    else:
        event_df = pd.DataFrame([dict(r) for r in event_rows])
        event_df.columns = ["ID", "Event", "Start Date", "Status",
                              "Team A", "Team B", "HC Mode", "Allowance %"]
        st.dataframe(event_df, use_container_width=True, hide_index=True)

        round_rows = fetchall("""
            SELECT e.name as event, r.round_number, r.date,
                   c.name as course, r.format_code, r.holes
            FROM round r
            JOIN event e ON e.event_id = r.event_id
            JOIN course c ON c.course_id = r.course_id
            ORDER BY e.start_date DESC, r.round_number
        """)
        if round_rows:
            round_df = pd.DataFrame([dict(r) for r in round_rows])
            round_df.columns = ["Event", "Round", "Date",
                                  "Course", "Format", "Holes"]
            st.dataframe(round_df, use_container_width=True, hide_index=True)

        ts = datetime.now().strftime("%Y%m%d")
        combined = pd.concat([event_df.assign(Sheet="Events"),
                               round_df.assign(Sheet="Rounds")
                               if round_rows else pd.DataFrame()],
                              ignore_index=True)
        st.download_button(
            "⬇️ Download Events & Rounds CSV",
            _df_to_csv(combined),
            f"gmc_events_{ts}.csv",
            "text/csv",
        )

# ---- Tab 3: Match Results ----
with export_tab3:
    st.markdown("**All match results across all events.**")

    result_rows = fetchall("""
        SELECT
            e.name          AS event,
            r.round_number  AS round,
            r.date,
            r.format_code   AS format,
            m.match_order   AS match_no,
            COALESCE(pa1.name, '—') AS team_a_p1,
            COALESCE(pa2.name, '')  AS team_a_p2,
            COALESCE(pb1.name, '—') AS team_b_p1,
            COALESCE(pb2.name, '')  AS team_b_p2,
            m.result,
            m.result_detail AS margin,
            m.notes
        FROM match m
        JOIN round r  ON r.round_id  = m.round_id
        JOIN event e  ON e.event_id  = r.event_id
        LEFT JOIN player pa1 ON pa1.player_id = m.team_a_player1_id
        LEFT JOIN player pa2 ON pa2.player_id = m.team_a_player2_id
        LEFT JOIN player pb1 ON pb1.player_id = m.team_b_player1_id
        LEFT JOIN player pb2 ON pb2.player_id = m.team_b_player2_id
        ORDER BY e.start_date DESC, r.round_number, m.match_order
    """)

    if not result_rows:
        st.caption("No match results recorded.")
    else:
        result_df = pd.DataFrame([dict(r) for r in result_rows])
        result_df.columns = ["Event", "Round", "Date", "Format", "Match #",
                               "Team A P1", "Team A P2",
                               "Team B P1", "Team B P2",
                               "Result", "Margin", "Notes"]
        st.dataframe(result_df, use_container_width=True, hide_index=True)
        ts = datetime.now().strftime("%Y%m%d")
        st.download_button(
            "⬇️ Download Match Results CSV",
            _df_to_csv(result_df),
            f"gmc_results_{ts}.csv",
            "text/csv",
        )

# ---- Tab 4: Career Stats ----
with export_tab4:
    st.markdown(
        "**Year-over-year career performance per player across all events.**"
    )

    career_rows = fetchall("""
        SELECT
            p.name                          AS player,
            e.name                          AS event,
            e.start_date,
            ep.team,
            -- Count wins for team A players
            SUM(CASE
                WHEN ep.team = 'A' AND m.result = 'A' THEN 1
                WHEN ep.team = 'B' AND m.result = 'B' THEN 1
                ELSE 0 END)                 AS wins,
            SUM(CASE
                WHEN ep.team = 'A' AND m.result = 'B' THEN 1
                WHEN ep.team = 'B' AND m.result = 'A' THEN 1
                ELSE 0 END)                 AS losses,
            SUM(CASE WHEN m.result = 'HALVED' THEN 1 ELSE 0 END) AS halved,
            SUM(CASE
                WHEN ep.team = 'A' AND m.result = 'A' THEN 1.0
                WHEN ep.team = 'B' AND m.result = 'B' THEN 1.0
                WHEN m.result = 'HALVED'               THEN 0.5
                ELSE 0 END)                 AS points
        FROM event_player ep
        JOIN player p  ON p.player_id  = ep.player_id
        JOIN event  e  ON e.event_id   = ep.event_id
        LEFT JOIN match m ON m.round_id IN (
            SELECT round_id FROM round WHERE event_id = ep.event_id
        ) AND (
            m.team_a_player1_id = ep.player_id OR
            m.team_a_player2_id = ep.player_id OR
            m.team_b_player1_id = ep.player_id OR
            m.team_b_player2_id = ep.player_id
        ) AND m.result IS NOT NULL
        GROUP BY p.player_id, e.event_id
        ORDER BY p.name, e.start_date
    """)

    if not career_rows:
        st.caption("No career data yet — complete an event to see stats here.")
    else:
        career_df = pd.DataFrame([dict(r) for r in career_rows])
        career_df.columns = ["Player", "Event", "Date", "Team",
                               "W", "L", "H", "Points"]

        # Aggregate totals per player
        totals = (
            career_df.groupby("Player")
            .agg(Events=("Event", "count"),
                 W=("W", "sum"),
                 L=("L", "sum"),
                 H=("H", "sum"),
                 Points=("Points", "sum"))
            .reset_index()
            .sort_values("Points", ascending=False)
        )
        totals["Win %"] = (
            (totals["W"] / (totals["W"] + totals["L"] + totals["H"]))
            .fillna(0)
            .mul(100)
            .round(1)
            .astype(str) + "%"
        )

        st.markdown("**Career Totals**")
        st.dataframe(totals, use_container_width=True, hide_index=True)

        st.markdown("**Per-Event Breakdown**")
        st.dataframe(career_df, use_container_width=True, hide_index=True)

        ts = datetime.now().strftime("%Y%m%d")
        st.download_button(
            "⬇️ Download Career Stats CSV",
            _df_to_csv(career_df),
            f"gmc_career_stats_{ts}.csv",
            "text/csv",
        )

# ---------------------------------------------------------------
# Section 5 — Raw Table Management
# ---------------------------------------------------------------
st.markdown("---")
st.subheader("🗄️ Raw Table Management")

st.markdown(
    "Import and export raw database tables via CSV. "
    "**Note:** Replacing a table deletes all existing rows, which may cascade to dependent records."
)

TABLES = [
    "player", "course", "tee_deck", "event", 
    "event_player", "round", "match", "score_record", "player_tag"
]

sel_table = st.selectbox("Select Table", TABLES)

table_rows = fetchall(f"SELECT * FROM {sel_table}")
if table_rows:
    table_df = pd.DataFrame([dict(r) for r in table_rows])
    st.dataframe(table_df, use_container_width=True, hide_index=True)
    
    st.download_button(
        label=f"⬇️ Download {sel_table}.csv",
        data=_df_to_csv(table_df),
        file_name=f"{sel_table}_export.csv",
        mime="text/csv",
    )
else:
    table_df = pd.DataFrame()
    st.caption(f"Table '{sel_table}' is currently empty.")

st.markdown("**📤 Upload CSV to Table**")
up_csv = st.file_uploader(f"Upload CSV to {sel_table}", type=["csv"], label_visibility="collapsed")
mode = st.radio("Upload Mode", ["Add / Upsert (Keep existing data)", "Replace (Delete existing data)"], horizontal=True)

if up_csv:
    if st.button("Commit CSV Upload", type="primary"):
        import sqlite3
        conn = sqlite3.connect(str(DB_PATH))
        new_df = pd.read_csv(up_csv)
        try:
            if "Replace" in mode:
                conn.execute(f"DELETE FROM {sel_table}")
                conn.commit()
            
            new_df.to_sql(sel_table, conn, if_exists="append", index=False)
            conn.commit()
            st.success(f"Successfully loaded {len(new_df)} rows into {sel_table}!")
            st.rerun()
        except sqlite3.IntegrityError as e:
            st.error(f"Integrity Error (Duplicate unique ID or missing dependency): {e}")
        except Exception as e:
            st.error(f"Error loading CSV: {e}")
        finally:
            conn.close()




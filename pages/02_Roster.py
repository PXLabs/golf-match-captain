"""
02_Roster.py — Roster Manager (Phase 2A update)
Golf Match Captain

Phase 2A adds: Golf Canada Score Centre sync button per player.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
from database.db import initialise_database
from modules.roster import (
    add_player, get_player, list_players, update_player, delete_player,
    add_tag, remove_tag, get_tags_grouped,
    get_score_records, add_score_record, delete_score_record,
    get_differentials,
    TAG_CATEGORIES, TAG_CATEGORY_LABELS, MAX_SCORE_RECORDS,
)
from modules.intelligence import build_player_intelligence
from modules.golf_canada import (
    PLAYWRIGHT_AVAILABLE,
    sync_player_scores,
    sync_player_scores_mock,
)

initialise_database()

SIGNAL_BADGE = {
    "RED":   ("🔴", "Sandbagging signal"),
    "AMBER": ("🟡", "Watch closely"),
    "GREEN": ("🟢", "Reliable index"),
    "NONE":  ("⚪", "Insufficient data"),
}
TREND_ARROW = {"IMPROVING": "📈", "DECLINING": "📉", "STABLE": "➡️"}

st.title("👥 Roster Manager")
st.caption("Manage players, tags, score history, and intelligence signals.")
st.markdown("---")

# ---------------------------------------------------------------
# Sidebar — add new player
# ---------------------------------------------------------------
with st.sidebar:
    st.header("➕ Add New Player")
    with st.form("add_player_form", clear_on_submit=True):
        new_name  = st.text_input("Name *", placeholder="e.g. Tom MacKay")
        new_index = st.number_input("Handicap Index *", min_value=0.0,
                                    max_value=54.0, step=0.1, value=18.0)
        new_cpga  = st.text_input("CPGA ID", placeholder="Optional")
        new_tee   = st.selectbox("Tee Preference",
                                  ["", "Blue", "White", "Yellow", "Red", "Gold"])
        new_notes = st.text_area("Notes", height=80)
        submitted = st.form_submit_button("Add Player", use_container_width=True,
                                          type="primary")
        if submitted:
            if not new_name.strip():
                st.error("Name is required.")
            else:
                add_player(new_name, new_index, new_cpga, new_tee, new_notes)
                st.success(f"✅ {new_name.strip()} added.")
                st.rerun()

# ---------------------------------------------------------------
# Main roster
# ---------------------------------------------------------------
players = list_players()

if not players:
    st.info("No players yet. Add your first player using the sidebar.")
    st.stop()

# Build intelligence profiles for all players upfront
all_profiles = []
for p in players:
    diffs   = get_differentials(p["player_id"])
    recs    = get_score_records(p["player_id"])
    dates   = [r["date"] for r in recs]
    profile = build_player_intelligence(diffs, p["current_index"], dates)
    all_profiles.append(profile)

col1, col2, col3 = st.columns(3)
col1.metric("Players", len(players))
col2.metric("Avg Index",
            round(sum(p["current_index"] for p in players) / len(players), 1))
col3.metric("🔴 Signals",
            sum(1 for pr in all_profiles if pr["signal"] == "RED"),
            help="Players with sandbagging flags")

st.markdown("---")

# ---------------------------------------------------------------
# Player cards
# ---------------------------------------------------------------
for idx, player in enumerate(players):
    pid     = player["player_id"]
    profile = all_profiles[idx]
    records = get_score_records(pid)

    signal_emoji, signal_label = SIGNAL_BADGE[profile["signal"]]
    trend_arrow  = TREND_ARROW[profile["trend_direction"]]
    tags_grouped = get_tags_grouped(pid)
    tag_count    = sum(len(v) for v in tags_grouped.values())

    label = (
        f"{signal_emoji}  **{player['name']}**  |  "
        f"Index: {player['current_index']:.1f}  |  "
        f"{trend_arrow} {profile['trend_label']}  |  "
        f"{len(records)} score(s)  |  {tag_count} tag(s)"
    )

    with st.expander(label, expanded=False):
        tab_intel, tab_details, tab_tags, tab_scores = st.tabs(
            ["🧠 Intelligence", "📋 Details", "🏷️ Tags", "📈 Scores"]
        )

        # Intelligence tab
        with tab_intel:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Official Index", f"{profile['current_index']:.1f}")
            c2.metric("Derived Index",
                       f"{profile['derived_index']:.1f}" if profile["derived_index"] else "N/A")
            c3.metric("Volatility SD", f"{profile['volatility']:.1f}")
            c4.metric("Best-3 Gap", f"{profile['best3_gap']:+.1f}",
                       help="Positive = plays better than index")

            st.markdown("---")

            if profile["signal"] == "RED":
                st.error(f"🔴 **{signal_label}**")
            elif profile["signal"] == "AMBER":
                st.warning(f"🟡 **{signal_label}**")
            elif profile["signal"] == "GREEN":
                st.success(f"🟢 **{signal_label}**")
            else:
                st.info("⚪ Insufficient data for signals.")

            for msg in profile["flag_messages"]:
                st.caption(f"→ {msg}")

            if profile["n_rounds"] >= 2:
                st.markdown("---")
                import pandas as pd
                import plotly.express as px

                recs_asc = list(reversed(records))
                df = pd.DataFrame({
                    "Round":        range(1, len(recs_asc) + 1),
                    "Differential": [r["differential"] for r in recs_asc],
                })
                fig = px.line(df, x="Round", y="Differential", markers=True,
                               title=f"{player['name']} — Differential Trend")
                fig.add_hline(y=player["current_index"], line_dash="dash",
                               line_color="red",
                               annotation_text=f"Index {player['current_index']:.1f}")
                fig.update_layout(height=260, margin=dict(t=40, b=10))
                st.plotly_chart(fig, use_container_width=True)

        # Details tab
        with tab_details:
            with st.form(f"edit_player_{pid}"):
                e_name  = st.text_input("Name *", value=player["name"])
                e_index = st.number_input("Handicap Index *", min_value=0.0,
                                          max_value=54.0, step=0.1,
                                          value=float(player["current_index"]))
                e_cpga  = st.text_input("CPGA ID", value=player["cpga_id"] or "")
                tee_opts = ["", "Blue", "White", "Yellow", "Red", "Gold"]
                cur_tee  = player["tee_preference"] if player["tee_preference"] in tee_opts else ""
                e_tee   = st.selectbox("Tee Preference", tee_opts,
                                        index=tee_opts.index(cur_tee))
                e_notes = st.text_area("Notes", value=player["notes"] or "", height=80)
                c_s, c_d = st.columns([3, 1])
                if c_s.form_submit_button("💾 Save", use_container_width=True,
                                           type="primary"):
                    if not e_name.strip():
                        st.error("Name required.")
                    else:
                        update_player(pid, e_name, e_index, e_cpga, e_tee, e_notes)
                        st.success("Saved.")
                        st.rerun()
                if c_d.form_submit_button("🗑️ Delete", use_container_width=True):
                    delete_player(pid)
                    st.warning(f"{player['name']} removed.")
                    st.rerun()

        # Tags tab
        with tab_tags:
            if tag_count == 0:
                st.caption("No tags yet.")
            else:
                for cat_key, cat_label in TAG_CATEGORY_LABELS.items():
                    cat_tags = tags_grouped.get(cat_key, [])
                    if cat_tags:
                        st.markdown(f"*{cat_label}*")
                        for t in cat_tags:
                            tc1, tc2 = st.columns([5, 1])
                            tc1.markdown(f"• {t['value']}")
                            if tc2.button("✕", key=f"rem_tag_{t['tag_id']}"):
                                remove_tag(t["tag_id"])
                                st.rerun()

            st.markdown("---")
            with st.form(f"add_tag_{pid}", clear_on_submit=True):
                cat_opts  = list(TAG_CATEGORY_LABELS.values())
                cat_keys  = list(TAG_CATEGORY_LABELS.keys())
                chosen_lbl = st.selectbox("Category", cat_opts)
                chosen_key = cat_keys[cat_opts.index(chosen_lbl)]
                source = st.radio("Source", ["Choose preset", "Custom"], horizontal=True)
                if source == "Choose preset":
                    chosen_tag = st.selectbox("Tag", TAG_CATEGORIES[chosen_key])
                else:
                    chosen_tag = st.text_input("Custom tag")
                if st.form_submit_button("Add Tag", type="primary"):
                    if chosen_tag and chosen_tag.strip():
                        add_tag(pid, chosen_key, chosen_tag.strip())
                        st.success("Tag added.")
                        st.rerun()

        # Scores tab
        with tab_scores:
            # ---- Golf Canada sync --------------------------------
            cpga_id = player["cpga_id"] or ""
            with st.expander("🍁 Sync from Golf Canada Score Centre", expanded=False):
                if cpga_id:
                    st.caption(f"CPGA ID on file: **{cpga_id}**")
                else:
                    st.caption("No CPGA ID stored. Add one in the Details tab first.")

                sync_col1, sync_col2 = st.columns(2)

                if PLAYWRIGHT_AVAILABLE:
                    sync_label = "🔄 Sync from Golf Canada"
                    sync_help  = ("Fetches the player's 20 most recent score "
                                  "differentials from Golf Canada Score Centre. "
                                  "This will replace all existing records.")
                else:
                    sync_label = "🔄 Sync (Demo — Playwright not installed)"
                    sync_help  = ("Playwright is not installed, so this will load "
                                  "synthetic demo data. Install playwright for live sync.")

                if sync_col1.button(
                    sync_label, key=f"sync_{pid}",
                    disabled=not cpga_id,
                    help=sync_help,
                    use_container_width=True,
                ):
                    with st.spinner("Fetching scores from Golf Canada…"):
                        try:
                            if PLAYWRIGHT_AVAILABLE:
                                result = sync_player_scores(pid, cpga_id)
                            else:
                                result = sync_player_scores_mock(
                                    pid, cpga_id,
                                    base_index=float(player["current_index"]),
                                )

                            if result.success:
                                st.success(
                                    f"✅ Synced {result.rows_imported} records "
                                    + (f"for **{result.player_name}**." if result.player_name else ".")
                                    + (f" Index updated to **{result.current_index:.1f}**."
                                       if result.current_index else "")
                                )
                                st.rerun()
                            else:
                                st.error(
                                    f"Sync failed: {result.error or 'Unknown error. Check CPGA ID and internet connection.'}"
                                )
                        except Exception as exc:
                            st.error(f"Sync error: {exc}")

                if not PLAYWRIGHT_AVAILABLE:
                    st.info(
                        "💡 To enable live Golf Canada sync, install Playwright:\n"
                        "```\npip install playwright\nplaywright install chromium\n```"
                    )

            st.markdown("---")

            # ---- Stored score records ----------------------------
            st.markdown(f"**{len(records)}/{MAX_SCORE_RECORDS} records stored (newest first)**")
            if records:
                for rec in records:
                    c = st.columns([2, 3, 2, 1.5, 1.5, 0.8])
                    c[0].caption(rec["date"])
                    c[1].caption(rec["course"])
                    c[2].caption(rec["tee_deck"] or "—")
                    c[3].caption(str(rec["posted_score"]) if rec["posted_score"] else "—")
                    c[4].caption(f"**{rec['differential']:.1f}**")
                    if c[5].button("✕", key=f"del_rec_{rec['record_id']}"):
                        delete_score_record(rec["record_id"])
                        st.rerun()

            st.markdown("---")
            remaining = MAX_SCORE_RECORDS - len(records)
            if remaining > 0:
                st.markdown("**Add a record manually**")
                with st.form(f"add_score_{pid}", clear_on_submit=True):
                    s1, s2 = st.columns(2)
                    s_date   = s1.date_input("Date *")
                    s_diff   = s2.number_input("Differential *", min_value=-10.0,
                                                max_value=60.0, step=0.1, value=18.0)
                    s_course = st.text_input("Course *")
                    s3, s4   = st.columns(2)
                    s_tee    = s3.text_input("Tee Deck")
                    s_score  = s4.number_input("Posted Score", min_value=0,
                                                max_value=200, step=1, value=0)
                    if st.form_submit_button("Add Record", type="primary"):
                        if not s_course.strip():
                            st.error("Course required.")
                        else:
                            add_score_record(pid, str(s_date), s_course, s_diff,
                                             s_score or None, s_tee)
                            st.success("Record added.")
                            st.rerun()
            else:
                st.info(f"Maximum {MAX_SCORE_RECORDS} records reached.")

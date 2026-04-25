"""
05_Match_Analysis.py — Match Analysis + AI Advisor
Golf Match Captain | Phase 1F

Two-column layout:
  Left:  Player handicap cards + intelligence signals
  Right: Streaming AI Advisor chat panel
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
from database.db import initialise_database
from modules.events import (
    list_events, get_event, list_rounds, get_event_players_by_team,
)
from modules.courses import get_tee_deck_for_handicap, get_tee_deck
from modules.roster import get_differentials, get_score_records, get_tags_grouped
from modules.handicap import (
    playing_handicap_for_format, apply_handicap_mode,
    stroke_allocation_detail, FORMAT_LABELS,
)
from modules.intelligence import build_player_intelligence
from modules.advisor import (
    build_context_packet, stream_advisor_response,
    append_user_message, append_assistant_message, trim_history,
    STARTER_PROMPTS, AVAILABLE_MODELS, DEFAULT_MODEL,
)

initialise_database()

SIGNAL_BADGE = {"RED": "🔴", "AMBER": "🟡", "GREEN": "🟢", "NONE": "⚪"}
TREND_ARROW  = {"IMPROVING": "📈", "DECLINING": "📉", "STABLE": "➡️"}

st.title("📊 Match Analysis & AI Advisor")
st.caption("Pre-round captain's view — handicaps, intelligence, and your AI analyst.")
st.markdown("---")

# ---------------------------------------------------------------
# Event + round selectors
# ---------------------------------------------------------------
events = list_events(status="ACTIVE")
if not events:
    st.info("No active events. Create one in Event Setup.")
    st.stop()

event_map    = {e["event_id"]: e["name"] for e in events}
selected_eid = st.selectbox(
    "Event", list(event_map.keys()), format_func=lambda i: event_map[i]
)
event  = get_event(selected_eid)
rounds = list_rounds(selected_eid)

if not rounds:
    st.warning("No rounds configured. Go to Event Setup.")
    st.stop()

round_map    = {
    r["round_id"]: (
        f"Round {r['round_number']} — {r['date']}  |  "
        f"{r['course_name']}  |  "
        f"{FORMAT_LABELS.get(r['format_code'], r['format_code'])}"
    )
    for r in rounds
}
selected_rid   = st.selectbox(
    "Round", list(round_map.keys()), format_func=lambda i: round_map[i]
)
selected_round = next(r for r in rounds if r["round_id"] == selected_rid)

st.markdown("---")

# Shared values
ev_ta         = event["team_a_name"]
ev_tb         = event["team_b_name"]
fmt           = selected_round["format_code"]
holes         = int(selected_round["holes"])
mode          = event["handicap_mode"]
allowance_pct = float(event["allowance_pct"]) / 100.0

tee_a  = get_tee_deck_for_handicap(selected_round["tee_id_a"]) if selected_round["tee_id_a"] else None
tee_b  = get_tee_deck_for_handicap(selected_round["tee_id_b"]) if selected_round["tee_id_b"] else None
teams  = get_event_players_by_team(selected_eid)
ta_pl  = teams["A"]
tb_pl  = teams["B"]

def _play_hc(player, tee):
    if not tee:
        return None
    return playing_handicap_for_format(
        float(player["current_index"]),
        tee["slope"], tee["rating"], tee["par"],
        fmt, allowance_pct,
    )["playing_hc"]

all_phcs = (
    [_play_hc(p, tee_a or tee_b) or 0 for p in ta_pl] +
    [_play_hc(p, tee_b or tee_a) or 0 for p in tb_pl]
)

# ---------------------------------------------------------------
# Two-column layout
# ---------------------------------------------------------------
col_left, col_right = st.columns([1, 1], gap="large")

# ==============================================================
# LEFT — Analysis panel
# ==============================================================
with col_left:
    st.subheader(f"Round {selected_round['round_number']} — {selected_round['date']}")
    m1, m2, m3 = st.columns(3)
    m1.metric("Format", FORMAT_LABELS.get(fmt, fmt))
    m2.metric("Holes",  holes)
    m3.metric("HC Mode", mode.replace("_", " ").title())

    if not tee_a and not tee_b:
        st.warning("⚠️ No tee decks assigned to this round.")

    def _player_card(player, tee):
        pid     = player["player_id"]
        diffs   = get_differentials(pid)
        recs    = get_score_records(pid)
        profile = build_player_intelligence(
            diffs, float(player["current_index"]), [r["date"] for r in recs]
        )
        tags     = get_tags_grouped(pid)
        tag_vals = [t["value"] for tl in tags.values() for t in tl]
        sig_e    = SIGNAL_BADGE[profile["signal"]]
        tr_a     = TREND_ARROW[profile["trend_direction"]]

        if tee:
            hc_det    = playing_handicap_for_format(
                float(player["current_index"]),
                tee["slope"], tee["rating"], tee["par"],
                fmt, allowance_pct,
            )
            play_hc   = hc_det["playing_hc"]
            course_hc = hc_det["course_hc"]
        else:
            play_hc = course_hc = None

        with st.container(border=True):
            h1, h2, h3 = st.columns([3, 1.5, 1.5])
            h1.markdown(f"**{sig_e} {player['name']}** {tr_a}")
            h2.metric("Course HC",  course_hc if course_hc is not None else "—")
            h3.metric("Playing HC", play_hc   if play_hc   is not None else "—")

            for msg in profile["flag_messages"]:
                flag_e = {"RED": "🔴", "AMBER": "🟡", "GREEN": "🟢"}.get(
                    profile["signal"], "ℹ️")
                st.caption(f"{flag_e} {msg}")

            if tag_vals:
                st.caption("🏷️ " + " · ".join(tag_vals[:3])
                            + (f" +{len(tag_vals)-3}" if len(tag_vals) > 3 else ""))

            if tee and play_hc is not None:
                si = tee.get("stroke_index", [])
                if si:
                    adj    = apply_handicap_mode(
                        [play_hc] + [h for h in all_phcs if h != play_hc],
                        mode, allowance_pct,
                    )
                    adj_hc = adj[0]
                    with st.expander(f"Strokes (adj HC {adj_hc})", expanded=False):
                        det  = stroke_allocation_detail(adj_hc, si, holes)
                        rows = [det[:9], det[9:]] if holes == 18 else [det]
                        for row in rows:
                            cs = st.columns(len(row))
                            for c, h in zip(cs, row):
                                c.markdown(
                                    f"<div style='text-align:center;font-size:0.72em'>"
                                    f"H{h['hole']}<br><small>SI{h['si']}</small><br>"
                                    f"<b style='color:{'#e74c3c' if h['receives_stroke'] else '#bbb'}'>"
                                    f"{'●' if h['receives_stroke'] else '·'}</b></div>",
                                    unsafe_allow_html=True,
                                )

    st.markdown(f"**🔵 {ev_ta}**")
    if ta_pl:
        for p in ta_pl:
            _player_card(p, tee_a or tee_b)
    else:
        st.caption("No players assigned to Team A.")

    st.markdown(f"**🔴 {ev_tb}**")
    if tb_pl:
        for p in tb_pl:
            _player_card(p, tee_b or tee_a)
    else:
        st.caption("No players assigned to Team B.")

# ==============================================================
# RIGHT — AI Advisor chat panel
# ==============================================================
with col_right:
    st.subheader("🤖 AI Advisor")
    st.caption("Your data-informed golf analyst. Ask anything.")

    session_key = f"chat_{selected_eid}_{selected_rid}"
    if session_key not in st.session_state:
        st.session_state[session_key] = []
    if "advisor_model" not in st.session_state:
        st.session_state["advisor_model"] = DEFAULT_MODEL

    history = st.session_state[session_key]

    # Top controls
    mc, cc = st.columns([3, 1])
    model_keys   = list(AVAILABLE_MODELS.keys())
    model_labels = list(AVAILABLE_MODELS.values())
    cur_idx      = model_keys.index(st.session_state["advisor_model"]) \
                   if st.session_state["advisor_model"] in model_keys else 0
    chosen = mc.selectbox(
        "model", model_keys, index=cur_idx,
        format_func=lambda k: AVAILABLE_MODELS[k],
        label_visibility="collapsed",
    )
    st.session_state["advisor_model"] = chosen

    if cc.button("🗑️ Clear", use_container_width=True):
        st.session_state[session_key] = []
        st.rerun()

    # Starter buttons when chat is empty
    if not history:
        st.markdown("**Quick starts:**")
        c1, c2 = st.columns(2)
        for i, s in enumerate(STARTER_PROMPTS):
            if (c1 if i % 2 == 0 else c2).button(
                s["label"], use_container_width=True, key=f"qs_{i}"
            ):
                st.session_state[session_key] = append_user_message([], s["prompt"])
                st.rerun()

    # Input
    user_input = st.chat_input("Ask your advisor…")
    if user_input:
        history = append_user_message(trim_history(history), user_input)
        st.session_state[session_key] = history
        st.rerun()

    # Chat history
    chat_box = st.container(height=480)
    with chat_box:
        for msg in history:
            with st.chat_message(msg["role"],
                                  avatar="🧢" if msg["role"] == "user" else "🤖"):
                st.markdown(msg["content"])

        # Trigger assistant response if the last message is from the user
        if history and history[-1]["role"] == "user":
            with st.chat_message("assistant", avatar="🤖"):
                placeholder   = st.empty()
                full_response = ""
                try:
                    for chunk in stream_advisor_response(
                        history,
                        selected_eid,
                        selected_rid,
                        model=st.session_state["advisor_model"],
                    ):
                        full_response += chunk
                        placeholder.markdown(full_response + "▌")

                    placeholder.markdown(full_response)
                    st.session_state[session_key] = append_assistant_message(
                        history, full_response
                    )
                    st.rerun()

                except ValueError as ve:
                    if "ANTHROPIC_API_KEY" in str(ve):
                        placeholder.error(
                            "**API key not configured.**\n\n"
                            "Add `ANTHROPIC_API_KEY=sk-ant-...` to your `.env` file "
                            "and restart the app."
                        )
                    else:
                        placeholder.error(f"Configuration error: {ve}")
                except Exception as e:
                    placeholder.error(f"Advisor unavailable: {e}")

    # Context packet viewer
    with st.expander("🔍 Context packet sent to AI", expanded=False):
        try:
            st.code(build_context_packet(selected_eid, selected_rid), language=None)
        except Exception as e:
            st.caption(f"Could not build context: {e}")

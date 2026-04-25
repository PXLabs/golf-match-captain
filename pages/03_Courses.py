"""
03_Courses.py — Course Library
Golf Match Captain | Phase 1C

Covers:
  - Add / edit / delete courses
  - Add / edit / delete tee decks (rating, slope, par, stroke index)
  - Stroke index entry with validation feedback
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
from database.db import initialise_database
from modules.courses import (
    add_course, get_course, list_courses, update_course, delete_course,
    add_tee_deck, get_tee_deck, list_tee_decks, update_tee_deck, delete_tee_deck,
)

initialise_database()

st.title("⛳ Course Library")
st.caption("Manage courses and tee deck configurations.")
st.markdown("---")

# ---------------------------------------------------------------
# Helper — stroke index grid (outside form so it can be reused)
# ---------------------------------------------------------------
def _render_si_grid(existing_si: list[int], key_prefix: str) -> list[int]:
    """
    Render an 18-cell grid of number inputs for stroke index entry.
    Returns the current values as a list of ints.
    """
    si_values = []
    rows = [range(9), range(9, 18)]
    labels = ["Holes 1–9", "Holes 10–18"]

    for row_range, row_label in zip(rows, labels):
        st.caption(row_label)
        cols = st.columns(9)
        for i in row_range:
            default = existing_si[i] if i < len(existing_si) else (i + 1)
            val = cols[i % 9].number_input(
                f"H{i+1}",
                min_value=1, max_value=18,
                step=1, value=default,
                key=f"{key_prefix}_si_{i}",
                label_visibility="visible",
            )
            si_values.append(val)

    # Live validation hint
    if sorted(si_values) != list(range(1, 19)):
        duplicates = [v for v in si_values if si_values.count(v) > 1]
        if duplicates:
            st.warning(
                f"⚠️ Duplicate SI values detected: {sorted(set(duplicates))}. "
                "Each value 1–18 must appear exactly once."
            )

    return si_values

def _get_tee_color(name: str) -> str:
    """Return an appropriate emoji circle based on the tee name."""
    n = name.lower()
    if 'blue' in n: return '🔵'
    if 'white' in n: return '⚪️'
    if 'red' in n: return '🔴'
    if 'black' in n: return '⚫'
    if 'green' in n: return '🟢'
    if 'yellow' in n or 'gold' in n: return '🟡'
    if 'orange' in n: return '🟠'
    if 'purple' in n: return '🟣'
    if 'brown' in n: return '🟤'
    if 'silver' in n or 'grey' in n or 'gray' in n: return '⚪️'
    return '⚪️' # Default colour

# ---------------------------------------------------------------
# Sidebar — add new course
# ---------------------------------------------------------------
with st.sidebar:
    st.header("➕ Add New Course")
    with st.form("add_course_form", clear_on_submit=True):
        c_name     = st.text_input("Course Name *", placeholder="e.g. Heron Point GC")
        c_location = st.text_input("Location", placeholder="e.g. Picton, ON")
        submitted  = st.form_submit_button("Add Course", use_container_width=True,
                                            type="primary")
        if submitted:
            if not c_name.strip():
                st.error("Course name is required.")
            else:
                add_course(c_name, c_location)
                st.success(f"✅ {c_name.strip()} added.")
                st.rerun()

# ---------------------------------------------------------------
# Course list
# ---------------------------------------------------------------
courses = list_courses()

if not courses:
    st.info("No courses yet. Add your first course using the sidebar.")
    st.stop()

st.metric("Courses in Library", len(courses))
st.markdown("---")

for course in courses:
    cid    = course["course_id"]
    decks  = list_tee_decks(cid)
    label  = f"**{course['name']}**  |  {course['location'] or 'Location not set'}  |  {len(decks)} tee deck(s)"

    with st.expander(label, expanded=False):
        tab_details, tab_decks = st.tabs(["📋 Course Details", "🏌️ Tee Decks"])

        # -------------------------------------------------------
        # Course details / edit
        # -------------------------------------------------------
        with tab_details:
            with st.form(f"edit_course_{cid}"):
                ec_name = st.text_input("Course Name *", value=course["name"])
                ec_loc  = st.text_input("Location", value=course["location"] or "")
                col_s, col_d = st.columns([3, 1])
                save = col_s.form_submit_button("💾 Save", use_container_width=True,
                                                 type="primary")
                dele = col_d.form_submit_button("🗑️ Delete", use_container_width=True)
                if save:
                    if not ec_name.strip():
                        st.error("Course name required.")
                    else:
                        update_course(cid, ec_name, ec_loc)
                        st.success("Saved.")
                        st.rerun()
                if dele:
                    delete_course(cid)
                    st.warning("Course deleted.")
                    st.rerun()

        # -------------------------------------------------------
        # Tee decks
        # -------------------------------------------------------
        with tab_decks:
            # Display existing decks
            if decks:
                for deck in decks:
                    tid = deck["tee_id"]
                    si  = deck["stroke_index"]
                    si_display = ", ".join(str(v) for v in si) if si else "Not set"

                    tee_badge = _get_tee_color(deck['name'])
                    yards_str = f"  |  {deck['total_yards']} yds" if deck.get('total_yards') else ""
                    with st.expander(
                        f"{tee_badge} {deck['name']} tees  |  "
                        f"Rating {deck['rating']}  |  Slope {deck['slope']}  |  Par {deck['par']}{yards_str}",
                        expanded=False,
                    ):
                        with st.form(f"edit_deck_{tid}"):
                            d_col1, d_col2, d_col3, d_col4 = st.columns(4)
                            d_name   = d_col1.text_input("Tee Name *", value=deck["name"])
                            d_rating = d_col2.number_input("Course Rating *",
                                                            min_value=55.0, max_value=80.0,
                                                            step=0.1, value=float(deck["rating"]))
                            d_slope  = d_col3.number_input("Slope Rating *",
                                                             min_value=55, max_value=155,
                                                             step=1, value=int(deck["slope"]))
                            d_par    = d_col4.number_input("Par", min_value=60, max_value=75,
                                                        step=1, value=int(deck["par"]))

                            d_col5, d_col6 = st.columns([1, 2])
                            d_yards = d_col5.number_input("Total Yards", min_value=0, step=1, value=int(deck.get("total_yards") or 0))
                            d_notes = d_col6.text_input("Notes", value=deck.get("notes") or "")

                            d_yards_val = d_yards if d_yards > 0 else None
                            d_notes_val = d_notes.strip() if d_notes.strip() else None

                            st.markdown("**Stroke Index (SI 1–18, one per hole)**")
                            st.caption(
                                "Enter the Stroke Index for each hole from the scorecard. "
                                "Each number 1–18 must appear exactly once."
                            )

                            si_input = _render_si_grid(si, key_prefix=f"edit_{tid}")

                            col_s2, col_d2 = st.columns([3, 1])
                            save2 = col_s2.form_submit_button("💾 Save Tee Deck",
                                                               use_container_width=True,
                                                               type="primary")
                            dele2 = col_d2.form_submit_button("🗑️ Delete", use_container_width=True)

                            if save2:
                                try:
                                    update_tee_deck(tid, d_name, d_rating, d_slope,
                                                    d_par, si_input, d_yards_val, d_notes_val)
                                    st.success("Tee deck updated.")
                                    st.rerun()
                                except ValueError as e:
                                    st.error(str(e))
                            if dele2:
                                delete_tee_deck(tid)
                                st.warning("Tee deck deleted.")
                                st.rerun()
            else:
                st.caption("No tee decks yet. Add one below.")

            st.markdown("---")
            st.markdown("**Add a Tee Deck**")

            with st.form(f"add_deck_{cid}", clear_on_submit=True):
                a_col1, a_col2, a_col3, a_col4 = st.columns(4)
                a_name   = a_col1.text_input("Tee Name *", placeholder="e.g. White")
                a_rating = a_col2.number_input("Course Rating *",
                                                min_value=55.0, max_value=80.0,
                                                step=0.1, value=70.0)
                a_slope  = a_col3.number_input("Slope Rating *",
                                                min_value=55, max_value=155,
                                                step=1, value=113)
                a_par    = a_col4.number_input("Par", min_value=60, max_value=75,
                                            step=1, value=72)

                a_col5, a_col6 = st.columns([1, 2])
                a_yards = a_col5.number_input("Total Yards", min_value=0, step=1, value=0)
                a_notes = a_col6.text_input("Notes", placeholder="e.g. Championship tees")

                a_yards_val = a_yards if a_yards > 0 else None
                a_notes_val = a_notes.strip() if a_notes.strip() else None

                st.markdown("**Stroke Index**")
                st.caption("Enter hole-by-hole SI from the scorecard (each of 1–18 once).")
                si_new = _render_si_grid([], key_prefix=f"new_{cid}")

                deck_submitted = st.form_submit_button("Add Tee Deck", type="primary")
                if deck_submitted:
                    if not a_name.strip():
                        st.error("Tee name is required.")
                    else:
                        try:
                            add_tee_deck(cid, a_name, a_rating, a_slope, a_par, si_new, a_yards_val, a_notes_val)
                            st.success(f"{a_name.strip()} tee deck added.")
                            st.rerun()
                        except ValueError as e:
                            st.error(str(e))




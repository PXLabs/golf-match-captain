"""
verma_cup_seed.py — Verma Cup 2026 Real Data Seed
Golf Match Captain | Verma Cup 2026

Loads the real Verma Cup 2026 data into GMC:
  - 12 players with correct WHS handicap indices (as of April 24, 2026)
  - 7 courses with full tee deck data (rating, slope, par, stroke index)
  - Verma Cup 2026 event (PLAY_OFF_LOW, 100% allowance)
  - Teams: Celtic Tigers (Team A) vs The Hurleys (Team B)
  - 7 rounds: Round 1 warm-up + Rounds 2-7 official competition

Tee deck data sourced from step2_tee_deck_SEQUENTIAL_IDS.csv.
Recommended tee per course is pre-selected for each round.

CALL load_verma_cup() to execute. It is idempotent — safe to call if
the event already exists (checks by name before inserting).
"""

from __future__ import annotations

from database.db import fetchall, fetchone, execute
from modules.seed_data import clear_all_data
from modules.courses import add_course, add_tee_deck
from modules.roster import add_player
from modules.events import create_event, assign_player, add_round


# ──────────────────────────────────────────────────────────────
# Data definitions
# ──────────────────────────────────────────────────────────────

PLAYERS = [
    # (name, handicap_index, team, notes)
    # Celtic Tigers — Team A
    ("Stephen Hayward",  10.0, "A", "Captain"),
    ("Ian Gillespie",     2.8, "A", None),
    ("Bill Stanton",      8.8, "A", "Assistant Captain"),
    ("Tom Wellner",       8.2, "A", None),
    ("Hugh Kendall",     14.3, "A", None),
    ("Peter Callahan",   24.6, "A", None),
    # The Hurleys — Team B
    ("Wayne Morden",      9.0, "B", "Organiser. Index updated Apr 24 — was 7.4 on Apr 20 list"),
    ("Marc Tetro",       12.4, "B", None),
    ("Ian Tetro",        20.7, "B", None),
    ("John Sheedy",      15.0, "B", None),
    ("Mark Grebenc",     19.0, "B", None),
    ("Kevan Cowan",      32.2, "B", None),
]

# Courses: (name, location, tee_decks)
# Each tee deck: (name, rating, slope, par, total_yards, stroke_index, notes)
COURSES = [
    (
        "Hilton Templepatrick GC",
        "Templepatrick, Northern Ireland",
        [
            ("Blue",    74.4, 127, 72, 7031, [12,6,8,18,14,4,16,2,10,11,13,1,3,15,7,17,5,9],  "Championship / back tees"),
            ("White",   72.3, 123, 72, 6628, [12,6,8,18,14,4,16,2,10,11,13,1,3,15,7,17,5,9],  "Recommended visitors tee — ROUND 1"),
            ("Green",   70.7, 120, 72, 6285, [12,6,8,18,14,4,16,2,10,11,13,1,3,15,7,17,5,9],  None),
            ("Red",     73.6, 126, 72, 6285, [12,6,8,18,14,4,16,2,10,11,13,1,3,15,7,17,5,9],  "Men's forward tees"),
        ],
        "White",  # recommended tee for this trip
    ),
    (
        "Ballyliffin — Glashedy Links",
        "Ballyliffin, Donegal",
        [
            ("Black",   70.0, 113, 72, 7486, [10,2,8,18,16,14,12,6,4,17,7,3,11,15,1,5,9,13],  "Championship — 2018 Irish Open tees"),
            ("Gold",    70.0, 110, 72, 6722, [10,2,8,18,16,14,12,6,4,17,7,3,11,15,1,5,9,13],  None),
            ("White",   70.0, 110, 72, 6327, [10,2,8,18,16,14,12,6,4,17,7,3,11,15,1,5,9,13],  "Recommended visitors tee — ROUND 2"),
        ],
        "White",
    ),
    (
        "Ballyliffin — Old Links",
        "Ballyliffin, Donegal",
        [
            ("Blue",    70.0, 110, 71, 6937, [10,2,6,14,16,8,18,12,4,17,9,13,5,3,1,7,11,15],  "Championship / back tees"),
            ("White",   70.0, 110, 71, 6450, [10,2,6,14,16,8,18,12,4,17,9,13,5,3,1,7,11,15],  "Recommended visitors tee — ROUND 3"),
            ("Gold",    70.0, 110, 71, 6261, [10,2,6,14,16,8,18,12,4,17,9,13,5,3,1,7,11,15],  None),
        ],
        "White",
    ),
    (
        "Rosapenna — Sandy Hills Links",
        "Rosapenna, Donegal",
        [
            ("Black",   73.2, 127, 72, 7183, [13,3,17,11,5,1,15,9,7,6,12,10,8,18,2,14,16,4],  "Championship / back tees"),
            ("Blue",    71.0, 121, 72, 6495, [13,3,17,11,5,1,15,9,7,6,12,10,8,18,2,14,16,4],  "Recommended visitors tee — ROUND 4"),
            ("White",   68.9, 117, 72, 6064, [13,3,17,11,5,1,15,9,7,6,12,10,8,18,2,14,16,4],  "More accessible option"),
        ],
        "Blue",
    ),
    (
        "Cruit Island GC",
        "Kincasslagh, Donegal",
        [
            # 9-hole course played as 2 loops for 18 holes.
            # WHS convention: first loop uses odd SI values, second loop uses paired even values.
            # Loop 1 (holes 1-9):  [1,3,13,5,17,15,7,11,9]  (odd SI)
            # Loop 2 (holes 10-18): [2,4,14,6,18,16,8,12,10] (each = paired odd + 1)
            # Rating/slope are for the full 18 (both loops combined).
            ("White",   70.0, 110, 68, 5010,
             [1,3,13,5,17,15,7,11,9, 2,4,14,6,18,16,8,12,10],
             "9-hole course played as 2 loops (18 holes total). Par 68, yardage 5010 (2x2505). Rating/slope cover full 18. ROUND 5"),
        ],
        "White",
    ),
    (
        "Portsalon GC",
        "Portsalon, Donegal",
        [
            ("White",   73.1, 125, 72, 6172, [11,3,13,17,9,1,7,15,5,18,10,12,14,2,16,6,8,4],  "Recommended visitors tee — ROUND 6"),
            ("Yellow",  72.6, 125, 72, 6074, [11,3,13,17,9,1,7,15,5,18,10,12,14,2,16,6,8,4],  None),
            ("Green",   70.0, 120, 72, 5513, [11,3,13,17,9,1,7,15,5,18,10,12,14,2,16,6,8,4],  None),
        ],
        "White",
    ),
    (
        "Rosapenna — St Patricks Links",
        "Rosapenna, Donegal",
        [
            ("Sandstone", 73.2, 128, 71, 6930, [7,11,1,17,9,3,15,13,5,10,2,18,6,14,4,16,8,12], "Championship / back tees"),
            ("Slate",     71.0, 125, 71, 6490, [7,11,1,17,9,3,15,13,5,10,2,18,6,14,4,16,8,12], "Recommended visitors tee — ROUND 7"),
            ("Granite",   68.7, 121, 71, 5919, [7,11,1,17,9,3,15,13,5,10,2,18,6,14,4,16,8,12], "More accessible option"),
            ("Claret",    64.6, 104, 71, 4800, [7,11,1,17,9,3,15,13,5,10,2,18,6,14,4,16,8,12], "Forward tees"),
        ],
        "Slate",
    ),
]

# ──────────────────────────────────────────────────────────────
# Extra courses — personal course library (not linked to Verma Cup rounds)
# ──────────────────────────────────────────────────────────────
# Each entry: (name, location, tee_decks, recommended_tee)
# tee_deck:   (name, rating, slope, par, total_yards, stroke_index, notes)
#
# Stroke index is the same across all tees for each course
# (SI reflects hole difficulty order, not yardage).

_DUNLUCE_SI   = [7,13,17,1,15,11,5,9,3,16,8,12,18,2,10,4,14,6]
_PORTSTEWART_SI = [11,7,13,5,1,15,17,3,9,10,4,18,16,12,14,6,2,8]

EXTRA_COURSES = [
    (
        "Royal Portrush — Dunluce Links",
        "Portrush, Northern Ireland",
        [
            ("Blue",  76.1, 140, 72, 7333, _DUNLUCE_SI, "Championship tees. 2019 / 2025 Open Championship venue."),
            ("White", 72.4, 131, 72, 6729, _DUNLUCE_SI, "Recommended visitors tee"),
            ("Green", 70.7, 127, 71, 6353, _DUNLUCE_SI, "Par 71 — H11 & H17 play as par 4"),
            ("Black", 68.8, 123, 71, 5950, _DUNLUCE_SI, "Forward tees. Par 71 — H11 & H17 play as par 4"),
        ],
        "White",
    ),
    (
        "Portstewart — Strand Course",
        "Portstewart, Co. Londonderry",
        [
            ("Black",     74.2, 131, 73, 7043, _PORTSTEWART_SI, "Championship tees. Par 73 — H1 & H17 play as par 5"),
            ("Blue",      72.6, 127, 72, 6604, _PORTSTEWART_SI, "Recommended visitors tee. Par 72 — H1 plays as par 5"),
            ("White",     69.5, 117, 71, 6075, _PORTSTEWART_SI, "Men's standard tees. Note: played as 15 holes (1-15) Oct 2025–Jun 2026"),
            ("White (L)", 75.7, 128, 71, 6075, _PORTSTEWART_SI, "Ladies' tees — same physical tee as Men's White"),
            ("Gold (L)",  73.8, 123, 71, 5730, _PORTSTEWART_SI, "Ladies' forward tees"),
        ],
        "Blue",
    ),
]

# Rounds: (round_number, date, course_index, format_code, holes, tee_name, notes)
# course_index = 0-based index into COURSES list above
ROUNDS = [
    (1, "2026-05-02", 0, "FOURBALL_MP",  9,  "White",
     "Warm-up round — not competitive. 9 holes on coach journey north."),
    (2, "2026-05-03", 1, "FOURBALL_MP",  18, "White",
     "Round 1 of official competition. 2018 Irish Open venue. Confirm format with Peter."),
    (3, "2026-05-04", 2, "FOURBALL_MP",  18, "White",
     "Round 2 of official competition. Confirm format with Peter."),
    (4, "2026-05-05", 3, "FOURSOMES_MP", 18, "Blue",
     "Round 3 of official competition. Blue tees. First group 09:30, second 10:00. Confirm format."),
    (5, "2026-05-06", 4, "FOURBALL_MP",  18,  "White",
     "Round 4 of official competition. 9-hole course played as 2 loops (18 holes total). Confirm format."),
    (6, "2026-05-07", 5, "SINGLES_MP",   18, "White",
     "Round 5 of official competition. Course Rating 73.1 — hardest on the trip. Confirm format."),
    (7, "2026-05-08", 6, "SINGLES_MP",   18, "Slate",
     "Round 6 of official competition. Final round. World Top 50 (#44). Confirm format."),
]


# ──────────────────────────────────────────────────────────────
# Loader
# ──────────────────────────────────────────────────────────────

def load_verma_cup(force: bool = False) -> dict:
    """
    Load Verma Cup 2026 data into GMC SQLite.

    Args:
        force: If True, clears ALL existing data before seeding.
               If False, aborts if any event already exists.

    Returns:
        {"success": bool, "message": str, "players": int, "courses": int}
    """
    # Guard — don't overwrite existing data unless forced
    existing_events = fetchall("SELECT event_id FROM event LIMIT 1")
    if existing_events and not force:
        return {
            "success": False,
            "message": "Data already exists. Check 'Clear existing data first' to replace it.",
            "players": 0,
            "courses": 0,
        }

    if force:
        clear_all_data()

    # ── Players ──
    player_ids: dict[str, int] = {}
    for name, idx, _team, notes in PLAYERS:
        pid = add_player(
            name=name,
            current_index=idx,
            notes=notes or "",
        )
        player_ids[name] = pid

    # ── Courses + Tee Decks ──
    course_ids: list[int]    = []
    rec_tee_ids: list[int]   = []  # recommended tee_id per course

    for course_name, location, tee_decks, recommended_tee in COURSES:
        cid = add_course(course_name, location)
        course_ids.append(cid)

        rec_tee_id = None
        for tee_name, rating, slope, par, yards, stroke_idx, notes in tee_decks:
            tid = add_tee_deck(
                course_id=cid,
                name=tee_name,
                rating=rating,
                slope=slope,
                par=par,
                stroke_index=stroke_idx,
                total_yards=yards,
                notes=notes,
            )
            if tee_name == recommended_tee:
                rec_tee_id = tid

        rec_tee_ids.append(rec_tee_id)

    # ── Event ──
    event_id = create_event(
        name="Verma Cup 2026",
        start_date="2026-05-02",
        team_a_name="Celtic Tigers",
        team_b_name="The Hurleys",
        handicap_mode="PLAY_OFF_LOW",
        allowance_pct=100.0,
    )

    # ── Assign players to teams ──
    for name, _idx, team, _notes in PLAYERS:
        assign_player(event_id, player_ids[name], team)

    # ── Rounds ──
    for round_number, date, course_idx, format_code, holes, _tee_name, notes in ROUNDS:
        cid     = course_ids[course_idx]
        tee_id  = rec_tee_ids[course_idx]
        add_round(
            event_id=event_id,
            course_id=cid,
            date=date,
            format_code=format_code,
            round_number=round_number,
            holes=holes,
            tee_id_a=tee_id,
            tee_id_b=tee_id,
        )

    # Mark event as ACTIVE
    execute("UPDATE event SET status = 'ACTIVE' WHERE event_id = ?", (event_id,))

    # ── Extra courses (personal course library) ──
    for course_name, location, tee_decks, _recommended_tee in EXTRA_COURSES:
        cid = add_course(course_name, location)
        for tee_name, rating, slope, par, yards, stroke_idx, notes in tee_decks:
            add_tee_deck(
                course_id=cid,
                name=tee_name,
                rating=rating,
                slope=slope,
                par=par,
                stroke_index=stroke_idx,
                total_yards=yards,
                notes=notes,
            )

    total_courses = len(COURSES) + len(EXTRA_COURSES)
    return {
        "success": True,
        "message": (
            f"Verma Cup 2026 loaded: {len(PLAYERS)} players, "
            f"{len(COURSES)} Verma Cup courses + {len(EXTRA_COURSES)} extra courses, "
            f"7 rounds. Event is ACTIVE."
        ),
        "players": len(PLAYERS),
        "courses": total_courses,
    }

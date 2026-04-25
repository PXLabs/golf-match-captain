"""
test_events.py — Phase 1C Test Suite
Golf Match Captain

Tests: courses, tee decks, event CRUD, player assignment, round management.
Run from project root:
    python tests/test_events.py
"""

import sys, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Use an isolated in-memory test DB
import database.db as db_module
import tempfile, shutil

_tmpdir = tempfile.mkdtemp()
db_module.DB_PATH = Path(_tmpdir) / "test.db"

from database.db import initialise_database
from modules.roster import add_player
from modules.courses import (
    add_course, get_course, list_courses, update_course, delete_course,
    add_tee_deck, get_tee_deck, list_tee_decks, update_tee_deck, delete_tee_deck,
    get_tee_deck_for_handicap, _validate_stroke_index,
)
from modules.events import (
    create_event, get_event, list_events, update_event, delete_event,
    assign_player, remove_player_from_event,
    get_event_players, get_event_players_by_team, get_unassigned_players,
    add_round, list_rounds, update_round, delete_round,
    get_event_summary, HANDICAP_MODES,
)

initialise_database()

PASS = 0
FAIL = 0

VALID_SI = [7, 15, 3, 11, 5, 17, 1, 13, 9, 6, 14, 2, 10, 4, 16, 8, 12, 18]


def check(description: str, result, expected) -> None:
    global PASS, FAIL
    if result == expected:
        print(f"  ✅  {description}")
        PASS += 1
    else:
        print(f"  ❌  {description}")
        print(f"       Expected: {expected}")
        print(f"       Got:      {result}")
        FAIL += 1


def check_true(description: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        print(f"  ✅  {description}")
        PASS += 1
    else:
        print(f"  ❌  {description}")
        FAIL += 1


# ==================================================================
print("\n--- 1. Course CRUD ---")
# ==================================================================

cid1 = add_course("Heron Point GC", "Picton, ON")
cid2 = add_course("Cobble Beach GC", "Owen Sound, ON")
check("Two courses added", len(list_courses()), 2)

course = get_course(cid1)
check("get_course returns correct name", course["name"], "Heron Point GC")
check("get_course returns correct location", course["location"], "Picton, ON")

update_course(cid1, "Heron Point Golf Club", "Prince Edward County, ON")
updated = get_course(cid1)
check("update_course name", updated["name"], "Heron Point Golf Club")
check("update_course location", updated["location"], "Prince Edward County, ON")


# ==================================================================
print("\n--- 2. Tee Deck CRUD ---")
# ==================================================================

tid_white = add_tee_deck(cid1, "White", 71.5, 125, 72, VALID_SI)
tid_blue  = add_tee_deck(cid1, "Blue",  73.2, 132, 72, VALID_SI)

decks = list_tee_decks(cid1)
check("Two tee decks added to Heron Point", len(decks), 2)

deck = get_tee_deck(tid_white)
check("Tee deck name", deck["name"], "White")
check("Tee deck rating", deck["rating"], 71.5)
check("Tee deck slope", deck["slope"], 125)
check("Tee deck par", deck["par"], 72)
check("Stroke index length", len(deck["stroke_index"]), 18)
check("Stroke index first value", deck["stroke_index"][0], VALID_SI[0])

# Handicap-ready format
hc_deck = get_tee_deck_for_handicap(tid_white)
check_true("get_tee_deck_for_handicap has required keys",
           all(k in hc_deck for k in ["rating", "slope", "par", "stroke_index"]))

# Update tee deck
new_si = list(range(1, 19))  # simple sequential SI
update_tee_deck(tid_white, "White (Updated)", 71.8, 126, 72, new_si)
updated_deck = get_tee_deck(tid_white)
check("update_tee_deck name", updated_deck["name"], "White (Updated)")
check("update_tee_deck rating", updated_deck["rating"], 71.8)
check("update_tee_deck SI[0]", updated_deck["stroke_index"][0], 1)


# ==================================================================
print("\n--- 3. Stroke index validation ---")
# ==================================================================

try:
    _validate_stroke_index(list(range(1, 18)))  # only 17 values
    check("Short SI raises ValueError", False, True)
except ValueError:
    check("Short SI raises ValueError", True, True)

try:
    bad_si = [1, 1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18]  # dup 1
    _validate_stroke_index(bad_si)
    check("Duplicate SI raises ValueError", False, True)
except ValueError:
    check("Duplicate SI raises ValueError", True, True)

try:
    _validate_stroke_index(VALID_SI)
    check("Valid SI passes validation", True, True)
except ValueError:
    check("Valid SI passes validation", False, True)


# ==================================================================
print("\n--- 4. Event CRUD ---")
# ==================================================================

eid1 = create_event(
    name="Heron Point Cup 2025",
    start_date="2025-07-12",
    team_a_name="The Aces",
    team_b_name="The Bogeys",
    handicap_mode="PLAY_OFF_LOW",
    allowance_pct=100.0,
)
eid2 = create_event(
    name="Cobble Beach Invitational",
    start_date="2025-08-20",
    handicap_mode="PERCENTAGE",
    allowance_pct=80.0,
)

events = list_events()
check("Two events created", len(events), 2)

ev = get_event(eid1)
check("Event name", ev["name"], "Heron Point Cup 2025")
check("Team A name", ev["team_a_name"], "The Aces")
check("Team B name", ev["team_b_name"], "The Bogeys")
check("Handicap mode", ev["handicap_mode"], "PLAY_OFF_LOW")
check("Allowance pct", float(ev["allowance_pct"]), 100.0)
check("Default status", ev["status"], "ACTIVE")

update_event(eid1, "Heron Point Cup 2025 (Updated)", "2025-07-13",
             "The Aces", "The Bogeys", "FULL_INDEX", 100.0, "ACTIVE")
updated_ev = get_event(eid1)
check("update_event name", updated_ev["name"], "Heron Point Cup 2025 (Updated)")
check("update_event mode", updated_ev["handicap_mode"], "FULL_INDEX")

# Filter by status
active = list_events(status="ACTIVE")
check("list_events(ACTIVE) returns 2", len(active), 2)


# ==================================================================
print("\n--- 5. Player assignment ---")
# ==================================================================

pid1 = add_player("Tom MacKay",     12.3, tee_preference="White")
pid2 = add_player("Bill Henderson",  7.6, tee_preference="Blue")
pid3 = add_player("Steve Dalton",   18.0)
pid4 = add_player("Gary Prentice",  22.5)

assign_player(eid1, pid1, "A")
assign_player(eid1, pid2, "B")
assign_player(eid1, pid3, "A")

players = get_event_players(eid1)
check("3 players assigned to event", len(players), 3)

teams = get_event_players_by_team(eid1)
check("Team A has 2 players", len(teams["A"]), 2)
check("Team B has 1 player",  len(teams["B"]), 1)

# Upsert — move Bill to Team A
assign_player(eid1, pid2, "A")
teams2 = get_event_players_by_team(eid1)
check("After upsert: Team A has 3", len(teams2["A"]), 3)
check("After upsert: Team B has 0", len(teams2["B"]), 0)

# Move back
assign_player(eid1, pid2, "B")

# Unassigned players
unassigned = get_unassigned_players(eid1)
check("Gary not yet assigned — appears in unassigned", pid4 in [p["player_id"] for p in unassigned], True)
check("Tom already assigned — not in unassigned", pid1 not in [p["player_id"] for p in unassigned], True)

# Remove a player
remove_player_from_event(eid1, pid3)
players2 = get_event_players(eid1)
check("After remove: 2 players remain", len(players2), 2)

# Re-assign for summary test
assign_player(eid1, pid3, "A")
assign_player(eid1, pid4, "B")


# ==================================================================
print("\n--- 6. Round management ---")
# ==================================================================

rid1 = add_round(
    event_id=eid1, course_id=cid1, date="2025-07-12",
    format_code="FOURBALL_MP", round_number=1, holes=18,
    tee_id_a=tid_white, tee_id_b=tid_blue,
)
rid2 = add_round(
    event_id=eid1, course_id=cid1, date="2025-07-13",
    format_code="FOURSOMES_MP", round_number=2, holes=18,
    tee_id_a=tid_white, tee_id_b=tid_white,
)
rid3 = add_round(
    event_id=eid1, course_id=cid1, date="2025-07-14",
    format_code="SINGLES_MP", round_number=3, holes=18,
    tee_id_a=tid_blue, tee_id_b=tid_blue,
)

rounds = list_rounds(eid1)
check("3 rounds added", len(rounds), 3)
check("Round 1 format", rounds[0]["format_code"], "FOURBALL_MP")
check("Round 2 format", rounds[1]["format_code"], "FOURSOMES_MP")
check("Round 3 format", rounds[2]["format_code"], "SINGLES_MP")
check("Round 1 tee_id_a", rounds[0]["tee_id_a"], tid_white)
check("Round 1 tee_id_b", rounds[0]["tee_id_b"], tid_blue)
check("Rounds include course name", rounds[0]["course_name"] is not None, True)

update_round(rid1, cid1, "2025-07-12", "SCRAMBLE", 1, 9, tid_white, tid_white)
updated_rounds = list_rounds(eid1)
check("update_round format", updated_rounds[0]["format_code"], "SCRAMBLE")
check("update_round holes", int(updated_rounds[0]["holes"]), 9)

delete_round(rid3)
check("delete_round leaves 2 rounds", len(list_rounds(eid1)), 2)


# ==================================================================
print("\n--- 7. Event summary ---")
# ==================================================================

summary = get_event_summary(eid1)
check("Summary event_id", summary["event_id"], eid1)
check("Summary team_a_name", summary["team_a_name"], "The Aces")
check("Summary total_rounds", summary["total_rounds"], 2)
check("Summary team_a_count", summary["team_a_count"], 2)
check("Summary team_b_count", summary["team_b_count"], 2)
check("Summary completed_rounds is 0 (no results yet)", summary["completed_rounds"], 0)


# ==================================================================
print("\n--- 8. Course cascade delete ---")
# ==================================================================

cid3 = add_course("Test Course", "Testville")
add_tee_deck(cid3, "Red", 68.0, 110, 71, list(range(1, 19)))
check("Temp course has 1 deck", len(list_tee_decks(cid3)), 1)
delete_course(cid3)
check("After delete: course gone", get_course(cid3) is None, True)
check("After delete: decks gone", len(list_tee_decks(cid3)), 0)


# ==================================================================
# Cleanup
# ==================================================================
shutil.rmtree(_tmpdir)

total = PASS + FAIL
print(f"\n{'='*50}")
print(f"  Phase 1C Results: {PASS}/{total} tests passed")
if FAIL == 0:
    print("  🏌️  All event & course tests passed.")
else:
    print(f"  ⚠️   {FAIL} test(s) failed — review above.")
print(f"{'='*50}\n")

sys.exit(0 if FAIL == 0 else 1)

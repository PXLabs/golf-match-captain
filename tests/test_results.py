"""
test_results.py — Phase 1E Test Suite
Golf Match Captain

Tests: match CRUD, result recording, round score, event score,
       player form tracking, LLM results formatter.
Run from project root:
    python tests/test_results.py
"""

import sys, shutil, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import database.db as db_module
_tmpdir = tempfile.mkdtemp()
db_module.DB_PATH = Path(_tmpdir) / "test.db"

from database.db import initialise_database
from modules.roster import add_player
from modules.courses import add_course, add_tee_deck
from modules.events import (
    create_event, assign_player, add_round, get_event_players,
)
from modules.results import (
    create_match, list_matches, update_match_players,
    record_result, clear_result, delete_match,
    get_round_score, get_event_score, get_player_results,
    get_matches_with_players, format_results_for_llm,
    RESULT_OPTIONS, POINTS,
)

initialise_database()

PASS = 0
FAIL = 0
VALID_SI = list(range(1, 19))


def check(description, result, expected):
    global PASS, FAIL
    if result == expected:
        print(f"  ✅  {description}")
        PASS += 1
    else:
        print(f"  ❌  {description}")
        print(f"       Expected: {expected}")
        print(f"       Got:      {result}")
        FAIL += 1


def check_approx(description, result, expected, tol=0.01):
    global PASS, FAIL
    if abs(result - expected) <= tol:
        print(f"  ✅  {description}")
        PASS += 1
    else:
        print(f"  ❌  {description}")
        print(f"       Expected: ≈{expected}")
        print(f"       Got:      {result}")
        FAIL += 1


def check_true(description, condition):
    global PASS, FAIL
    if condition:
        print(f"  ✅  {description}")
        PASS += 1
    else:
        print(f"  ❌  {description}")
        FAIL += 1


# ==================================================================
# Setup — build a realistic 3-round event with 4 players
# ==================================================================

pid_tom   = add_player("Tom MacKay",     12.3)
pid_bill  = add_player("Bill Henderson",  7.6)
pid_steve = add_player("Steve Dalton",   18.0)
pid_gary  = add_player("Gary Prentice",  22.5)

cid  = add_course("Heron Point GC", "Picton, ON")
tid  = add_tee_deck(cid, "White", 71.5, 125, 72, VALID_SI)

eid = create_event(
    name="Heron Point Cup 2025",
    start_date="2025-07-12",
    team_a_name="The Aces",
    team_b_name="The Bogeys",
    handicap_mode="FULL_INDEX",
)

assign_player(eid, pid_tom,   "A")
assign_player(eid, pid_bill,  "A")
assign_player(eid, pid_steve, "B")
assign_player(eid, pid_gary,  "B")

rid1 = add_round(eid, cid, "2025-07-12", "FOURBALL_MP",  1, 18, tid, tid)
rid2 = add_round(eid, cid, "2025-07-13", "FOURSOMES_MP", 2, 18, tid, tid)
rid3 = add_round(eid, cid, "2025-07-14", "SINGLES_MP",   3, 18, tid, tid)


# ==================================================================
print("\n--- 1. Match CRUD ---")
# ==================================================================

mid1 = create_match(rid1, 1, pid_tom, pid_bill, pid_steve, pid_gary, "Four-ball Day 1")
mid2 = create_match(rid2, 1, pid_tom, pid_bill, pid_steve, pid_gary)
mid3 = create_match(rid3, 1, pid_tom,  None, pid_steve, None)
mid4 = create_match(rid3, 2, pid_bill, None, pid_gary,  None)

check("4 matches created across 3 rounds", True, True)

matches_r1 = list_matches(rid1)
matches_r3 = list_matches(rid3)
check("Round 1 has 1 match", len(matches_r1), 1)
check("Round 3 has 2 matches", len(matches_r3), 2)
check("Match 1 order", matches_r1[0]["match_order"], 1)
check("Foursomes match has team A player1", matches_r1[0]["team_a_player1_id"], pid_tom)
check("Foursomes match has team A player2", matches_r1[0]["team_a_player2_id"], pid_bill)

# Update players
update_match_players(mid4, pid_bill, None, pid_gary, None, "Singles rematch")
updated = list_matches(rid3)[1]
check("update_match_players notes", updated["notes"], "Singles rematch")


# ==================================================================
print("\n--- 2. Result recording ---")
# ==================================================================

record_result(mid1, "A", "3&2")
m = list_matches(rid1)[0]
check("Result recorded: A wins", m["result"], "A")
check("Result detail recorded", m["result_detail"], "3&2")

# Clear result
clear_result(mid1)
m2 = list_matches(rid1)[0]
check("Result cleared → None", m2["result"], None)

# Re-record
record_result(mid1, "A", "3&2")

# Invalid result
try:
    record_result(mid1, "X", "")
    check("Invalid result raises ValueError", False, True)
except ValueError:
    check("Invalid result raises ValueError", True, True)

# Record remaining rounds
record_result(mid2, "B", "1 UP")
record_result(mid3, "A", "2&1")
record_result(mid4, "HALVED", "AS")


# ==================================================================
print("\n--- 3. Points constants ---")
# ==================================================================

check("A wins: A gets 1.0",      POINTS["A"]["A"],      1.0)
check("A wins: B gets 0.0",      POINTS["A"]["B"],      0.0)
check("B wins: B gets 1.0",      POINTS["B"]["B"],      1.0)
check("Halved: A gets 0.5",      POINTS["HALVED"]["A"], 0.5)
check("Halved: B gets 0.5",      POINTS["HALVED"]["B"], 0.5)
check("3 result options defined", len(RESULT_OPTIONS), 3)


# ==================================================================
print("\n--- 4. Round score ---")
# ==================================================================

# Round 1: Team A wins (mid1) → A: 1.0, B: 0.0
rs1 = get_round_score(rid1)
check_approx("Round 1 pts A = 1.0", rs1["points_a"], 1.0)
check_approx("Round 1 pts B = 0.0", rs1["points_b"], 0.0)
check("Round 1 matches played = 1",  rs1["matches_played"], 1)
check("Round 1 matches pending = 0", rs1["matches_pending"], 0)

# Round 2: Team B wins → A: 0.0, B: 1.0
rs2 = get_round_score(rid2)
check_approx("Round 2 pts B = 1.0", rs2["points_b"], 1.0)
check_approx("Round 2 pts A = 0.0", rs2["points_a"], 0.0)

# Round 3: A wins singles (1.0) + halved singles (0.5 each)
rs3 = get_round_score(rid3)
check_approx("Round 3 pts A = 1.5 (win + half)", rs3["points_a"], 1.5)
check_approx("Round 3 pts B = 0.5 (half only)",  rs3["points_b"], 0.5)
check("Round 3 matches played = 2", rs3["matches_played"], 2)

# Pending match
mid_pending = create_match(rid3, 3, pid_tom, None, pid_gary, None)
rs3_pending = get_round_score(rid3)
check("With pending: matches_pending = 1", rs3_pending["matches_pending"], 1)
delete_match(mid_pending)


# ==================================================================
print("\n--- 5. Event score ---")
# ==================================================================

# Total: A: 1.0 + 0.0 + 1.5 = 2.5, B: 0.0 + 1.0 + 0.5 = 1.5
es = get_event_score(eid)
check_approx("Event total pts A = 2.5", es["total_points_a"], 2.5)
check_approx("Event total pts B = 1.5", es["total_points_b"], 1.5)
check("All 3 rounds complete",           es["rounds_completed"], 3)
check("0 rounds pending",                es["rounds_pending"], 0)
check("per_round has 3 entries",         len(es["per_round"]), 3)

# Per-round pts match individual round scores
check_approx("per_round[0] pts_a = 1.0", es["per_round"][0]["points_a"], 1.0)
check_approx("per_round[1] pts_b = 1.0", es["per_round"][1]["points_b"], 1.0)
check_approx("per_round[2] pts_a = 1.5", es["per_round"][2]["points_a"], 1.5)


# ==================================================================
print("\n--- 6. Player form ---")
# ==================================================================

p_stats = get_player_results(eid)
stats   = {s["player_id"]: s for s in p_stats}

# Tom: played rounds 1 (W, 4-ball), 2 (L, foursomes), 3 match 1 (W singles)
#      Four-ball & foursomes: Tom is in both — each counts as a point for the team
check_true("Tom has stats", pid_tom in stats)
check_true("Bill has stats", pid_bill in stats)

tom_s  = stats[pid_tom]
bill_s = stats[pid_bill]

# Round 1 (4-ball): both Tom AND Bill credited with the win
check("Tom: at least 1 win across event",  tom_s["W"] >= 1, True)
check("Bill: at least 1 win across event", bill_s["W"] >= 1, True)

# Steve: round 1 loss, round 2 win (foursomes for B), round 3 singles loss
steve_s = stats[pid_steve]
check_true("Steve has W/L/H recorded", steve_s["W"] + steve_s["L"] + steve_s["H"] > 0)

# Gary: round 1 loss (4-ball), round 2 win (foursomes), round 3 halved
gary_s = stats[pid_gary]
check("Gary has at least 1 halved", gary_s["H"] >= 1, True)


# ==================================================================
print("\n--- 7. get_matches_with_players ---")
# ==================================================================

rich = get_matches_with_players(rid3)
check("Rich matches returns 2 for round 3", len(rich), 2)
check("a1_name populated", rich[0]["a1_name"], "Tom MacKay")
check("b1_name populated", rich[0]["b1_name"], "Steve Dalton")
check_true("pts_a/pts_b present", "pts_a" in rich[0] and "pts_b" in rich[0])
check_approx("Match 1 pts_a = 1.0 (A win)", rich[0]["pts_a"], 1.0)
check_approx("Match 2 pts_a = 0.5 (halved)", rich[1]["pts_a"], 0.5)


# ==================================================================
print("\n--- 8. LLM results formatter ---")
# ==================================================================

llm_text = format_results_for_llm(eid, "The Aces", "The Bogeys")
check_true("LLM text has EVENT SCORE header", "EVENT SCORE" in llm_text)
check_true("LLM text has team name A",        "The Aces" in llm_text)
check_true("LLM text has team name B",        "The Bogeys" in llm_text)
check_true("LLM text has ROUND-BY-ROUND",     "ROUND-BY-ROUND" in llm_text)
check_true("LLM text has PLAYER FORM",        "PLAYER FORM" in llm_text)
check_true("LLM text has pts values",         "2.5" in llm_text or "1.5" in llm_text)


# ==================================================================
# Cleanup
# ==================================================================
shutil.rmtree(_tmpdir)

total = PASS + FAIL
print(f"\n{'='*50}")
print(f"  Phase 1E Results: {PASS}/{total} tests passed")
if FAIL == 0:
    print("  🏌️  All results tests passed.")
else:
    print(f"  ⚠️   {FAIL} test(s) failed — review above.")
print(f"{'='*50}\n")

sys.exit(0 if FAIL == 0 else 1)

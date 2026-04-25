"""
test_data_management.py — Data Management Test Suite
Golf Match Captain

Tests: seed_all, clear_all_data, is_seeded, re-seed idempotency,
       career stats SQL, CSV export queries.
Run from project root:
    python tests/test_data_management.py
"""

import sys, shutil, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import database.db as db_module
_tmpdir = tempfile.mkdtemp()
db_module.DB_PATH = Path(_tmpdir) / "test.db"

from database.db import initialise_database, fetchall, fetchone
from modules.seed_data import seed_all, clear_all_data, is_seeded
from modules.events import list_events, get_event_players_by_team
from modules.results import get_event_score, get_player_results

initialise_database()

PASS = 0
FAIL = 0


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


def check_true(description, condition):
    global PASS, FAIL
    if condition:
        print(f"  ✅  {description}")
        PASS += 1
    else:
        print(f"  ❌  {description}")
        FAIL += 1


# ==================================================================
print("\n--- 1. Empty database state ---")
# ==================================================================

check("Empty DB: is_seeded() is False", is_seeded(), False)
check("Empty DB: no players",    fetchone("SELECT COUNT(*) as c FROM player")["c"],  0)
check("Empty DB: no events",     fetchone("SELECT COUNT(*) as c FROM event")["c"],   0)
check("Empty DB: no courses",    fetchone("SELECT COUNT(*) as c FROM course")["c"],  0)


# ==================================================================
print("\n--- 2. seed_all() ---")
# ==================================================================

result = seed_all(force=False)
check("seed_all returns summary dict",         isinstance(result, dict), True)
check("8 players seeded",                      result["players"],        8)
check("2 courses seeded",                      result["courses"],        2)
check("1 event seeded",                        result["events"],         1)
check("is_seeded() is True after seed",        is_seeded(),              True)

player_count = fetchone("SELECT COUNT(*) as c FROM player")["c"]
course_count = fetchone("SELECT COUNT(*) as c FROM course")["c"]
event_count  = fetchone("SELECT COUNT(*) as c FROM event")["c"]
round_count  = fetchone("SELECT COUNT(*) as c FROM round")["c"]
match_count  = fetchone("SELECT COUNT(*) as c FROM match")["c"]
score_count  = fetchone("SELECT COUNT(*) as c FROM score_record")["c"]
tag_count    = fetchone("SELECT COUNT(*) as c FROM player_tag")["c"]

check("8 players in DB",        player_count, 8)
check("2 courses in DB",        course_count, 2)
check("1 event in DB",          event_count,  1)
check("3 rounds in DB",         round_count,  3)
check("12 matches in DB",       match_count,  12)
check_true("Score records loaded",   score_count >= 60)   # ~10 per player
check_true("Tags loaded",            tag_count   >= 10)


# ==================================================================
print("\n--- 3. Seeded data quality ---")
# ==================================================================

events = list_events()
eid    = events[0]["event_id"]
teams  = get_event_players_by_team(eid)

check("Team A has 4 players", len(teams["A"]), 4)
check("Team B has 4 players", len(teams["B"]), 4)

# Verify player names
all_names = {p["name"] for p in teams["A"] + teams["B"]}
for expected_name in ["Tom MacKay", "Bill Henderson", "Steve Dalton", "Gary Prentice",
                       "Mike Kowalski", "Emeka Okafor", "Marc Leblanc", "Dave Brennan"]:
    check_true(f"Player '{expected_name}' present", expected_name in all_names)

# Verify courses
courses = fetchall("SELECT name FROM course ORDER BY name")
course_names = {r["name"] for r in courses}
check_true("Heron Point GC seeded",  "Heron Point GC" in course_names)
check_true("Cobble Beach GC seeded", "Cobble Beach GC" in course_names)

# Verify tee decks
deck_count = fetchone("SELECT COUNT(*) as c FROM tee_deck")["c"]
check_true("At least 5 tee decks (3 Heron + 2 Cobble)", deck_count >= 5)

# Verify stroke index stored correctly
deck = fetchone("SELECT stroke_index FROM tee_deck LIMIT 1")
check_true("Stroke index is non-empty JSON",
           deck and len(deck["stroke_index"]) > 2)


# ==================================================================
print("\n--- 4. Event score and results ---")
# ==================================================================

score = get_event_score(eid)
check_true("Event has points recorded", score["total_points_a"] + score["total_points_b"] > 0)
check("3 rounds in event", len(score["per_round"]), 3)
check_true("All rounds have results", all(r["matches_played"] > 0
                                         for r in score["per_round"]))
check_true("Points total is 12 (12 matches × 1pt)",
           abs(score["total_points_a"] + score["total_points_b"] - 12.0) < 0.01)

# Player form
p_stats = get_player_results(eid)
check_true("All 8 players have form stats", len(p_stats) == 8)
check_true("All players appeared in matches",
           all(s["W"] + s["L"] + s["H"] > 0 for s in p_stats))


# ==================================================================
print("\n--- 5. Intelligence signals from seeded data ---")
# ==================================================================

from modules.roster import get_differentials, get_score_records
from modules.intelligence import build_player_intelligence

# Tom MacKay should trigger RED (best-3 gap > 4)
tom = fetchone("SELECT * FROM player WHERE name = 'Tom MacKay'")
tom_diffs = get_differentials(tom["player_id"])
tom_recs  = get_score_records(tom["player_id"])
tom_prof  = build_player_intelligence(
    tom_diffs, float(tom["current_index"]),
    [r["date"] for r in tom_recs]
)
check("Tom MacKay signal is RED (sandbagger)",
      tom_prof["signal"], "RED")
check_true("Tom's best-3 gap > 4",  tom_prof["best3_gap"] > 4.0)

# Bill Henderson should be GREEN (consistent)
bill = fetchone("SELECT * FROM player WHERE name = 'Bill Henderson'")
bill_diffs = get_differentials(bill["player_id"])
bill_recs  = get_score_records(bill["player_id"])
bill_prof  = build_player_intelligence(
    bill_diffs, float(bill["current_index"]),
    [r["date"] for r in bill_recs]
)
check("Bill Henderson signal is GREEN", bill_prof["signal"], "GREEN")

# Steve Dalton should be AMBER (high variance)
steve = fetchone("SELECT * FROM player WHERE name = 'Steve Dalton'")
steve_diffs = get_differentials(steve["player_id"])
steve_recs  = get_score_records(steve["player_id"])
steve_prof  = build_player_intelligence(
    steve_diffs, float(steve["current_index"]),
    [r["date"] for r in steve_recs]
)
check("Steve Dalton signal is AMBER (high variance)",
      steve_prof["signal"], "AMBER")
check_true("Steve's volatility > 4.0", steve_prof["volatility"] > 4.0)

# Mike Kowalski should be AMBER (infrequent posting)
mike = fetchone("SELECT * FROM player WHERE name = 'Mike Kowalski'")
mike_diffs = get_differentials(mike["player_id"])
mike_recs  = get_score_records(mike["player_id"])
mike_prof  = build_player_intelligence(
    mike_diffs, float(mike["current_index"]),
    [r["date"] for r in mike_recs]
)
check("Mike Kowalski signal is AMBER (infrequent posting)",
      mike_prof["signal"], "AMBER")


# ==================================================================
print("\n--- 6. seed_all skip when already seeded ---")
# ==================================================================

result2 = seed_all(force=False)
check("Second seed without force → skipped",
      result2.get("skipped"), True)
check("Player count unchanged after skip",
      fetchone("SELECT COUNT(*) as c FROM player")["c"], 8)


# ==================================================================
print("\n--- 7. seed_all force=True re-seeds cleanly ---")
# ==================================================================

result3 = seed_all(force=True)
check("Force re-seed: players = 8",  result3["players"], 8)
check("Force re-seed: courses = 2",  result3["courses"], 2)

# Confirm no duplicate data
check("No duplicate players after force re-seed",
      fetchone("SELECT COUNT(*) as c FROM player")["c"], 8)
check("No duplicate events after force re-seed",
      fetchone("SELECT COUNT(*) as c FROM event")["c"],  1)


# ==================================================================
print("\n--- 8. clear_all_data ---")
# ==================================================================

clear_all_data()

check("After clear: players = 0",
      fetchone("SELECT COUNT(*) as c FROM player")["c"],       0)
check("After clear: courses = 0",
      fetchone("SELECT COUNT(*) as c FROM course")["c"],       0)
check("After clear: events = 0",
      fetchone("SELECT COUNT(*) as c FROM event")["c"],        0)
check("After clear: matches = 0",
      fetchone("SELECT COUNT(*) as c FROM match")["c"],        0)
check("After clear: score_records = 0",
      fetchone("SELECT COUNT(*) as c FROM score_record")["c"], 0)
check("After clear: is_seeded() False",
      is_seeded(),                                             False)

# Schema still intact — can seed again after clear
result4 = seed_all(force=False)
check("Can re-seed after clear",
      result4["players"], 8)


# ==================================================================
print("\n--- 9. Career stats SQL ---")
# ==================================================================

career_rows = fetchall("""
    SELECT p.name, COUNT(DISTINCT ep.event_id) AS events,
           SUM(CASE WHEN ep.team='A' AND m.result='A' THEN 1
                    WHEN ep.team='B' AND m.result='B' THEN 1
                    ELSE 0 END) AS wins
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
    HAVING wins > 0
""")

check_true("Career stats returns players with wins", len(career_rows) > 0)
check_true("Each career row has name",  all("name" in dict(r) for r in career_rows))
check_true("Each career row has wins",  all(dict(r)["wins"] >= 0 for r in career_rows))


# ==================================================================
# Cleanup
# ==================================================================
shutil.rmtree(_tmpdir)

total = PASS + FAIL
print(f"\n{'='*50}")
print(f"  Data Management Results: {PASS}/{total} tests passed")
if FAIL == 0:
    print("  🏌️  All data management tests passed.")
else:
    print(f"  ⚠️   {FAIL} test(s) failed — review above.")
print(f"{'='*50}\n")

import sys
sys.exit(0 if FAIL == 0 else 1)

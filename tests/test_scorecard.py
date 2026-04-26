"""
test_scorecard.py — Scorecard Feature Test Suite
Golf Match Captain

Tests: Vision response parsing, hole-by-hole calculation, match result
       derivation, persistence, and schema migration.
No live API calls made.
Run from project root:
    python tests/test_scorecard.py
"""

import sys, shutil, tempfile, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import database.db as db_module
_tmpdir = tempfile.mkdtemp()
db_module.DB_PATH = Path(_tmpdir) / "test.db"

from database.db import initialise_database, fetchone
from modules.seed_data import seed_all
from modules.events import list_events, list_rounds, get_event
from modules.results import list_matches, create_match
from modules.scorecard import (
    ExtractionResult, ExtractedPlayer,
    _parse_vision_response,
    _derive_match_result,
    calculate_match,
    save_scorecard_result,
    get_hole_scores,
    HoleResult, MatchCalculation,
    image_bytes_to_media_type,
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


def check_true(description, condition):
    global PASS, FAIL
    if condition:
        print(f"  ✅  {description}")
        PASS += 1
    else:
        print(f"  ❌  {description}")
        FAIL += 1


# ==================================================================
print("\n--- 1. Schema migration — hole_scores column ---")
# ==================================================================

cols = [r[1] for r in fetchone("SELECT GROUP_CONCAT(name) as n FROM pragma_table_info('match')")
        ["n"].split(",")]
# Re-check properly
import sqlite3
conn = sqlite3.connect(str(db_module.DB_PATH))
col_names = [r[1] for r in conn.execute("PRAGMA table_info(match)").fetchall()]
conn.close()

check_true("hole_scores column exists in match table",
           "hole_scores" in col_names)


# ==================================================================
print("\n--- 2. _parse_vision_response ---")
# ==================================================================

# Valid JSON response
valid_json = json.dumps({
    "course_name": "Heron Point GC",
    "holes": 18,
    "confidence": "high",
    "notes": "",
    "par": [4,3,5,4,4,3,5,4,3,4,3,5,4,4,3,5,4,3],
    "players": [
        {"name": "MacKay",    "scores": [5,3,6,4,4,3,5,4,4,4,3,5,4,4,4,5,4,4]},
        {"name": "Henderson", "scores": [4,3,5,4,3,3,5,3,4,4,3,5,4,4,3,5,3,4]},
        {"name": "Dalton",    "scores": [6,4,6,5,5,4,6,5,5,5,4,6,5,5,4,6,5,5]},
        {"name": "Kowalski",  "scores": [5,4,6,4,5,4,5,4,4,4,4,5,4,4,4,5,4,4]},
    ]
})

result = _parse_vision_response(valid_json, 18)
check("Valid JSON: success=True",            result.success,      True)
check("Valid JSON: course_name",             result.course_name,  "Heron Point GC")
check("Valid JSON: confidence",              result.confidence,   "high")
check("Valid JSON: 4 players",               len(result.players), 4)
check("Valid JSON: holes=18",                result.holes,        18)
check("Valid JSON: par length",              len(result.par),     18)
check("Valid JSON: first player name",       result.players[0].raw_name, "MacKay")
check("Valid JSON: first player 18 scores",  len(result.players[0].scores), 18)
check("Valid JSON: first score of MacKay",   result.players[0].scores[0], 5)
check("Valid JSON: par[0]",                  result.par[0],       4)

# JSON in markdown code fence
fenced = "```json\n" + valid_json + "\n```"
result2 = _parse_vision_response(fenced, 18)
check("Fenced JSON: still parsed successfully", result2.success, True)
check("Fenced JSON: correct player count",      len(result2.players), 4)

# Invalid JSON
bad_result = _parse_vision_response("not json at all", 18)
check("Invalid JSON: success=False",    bad_result.success, False)
check_true("Invalid JSON: has error",   len(bad_result.error) > 0)

# Short scores array — padded to 18
short_json = json.dumps({
    "holes": 18, "confidence": "low", "par": [],
    "players": [{"name": "Test", "scores": [4, 3, 5]}]
})
short_result = _parse_vision_response(short_json, 18)
check("Short scores padded to 18",      len(short_result.players[0].scores), 18)
check("Padded values are 0",            short_result.players[0].scores[3],   0)

# 9-hole round
nine_json = json.dumps({
    "holes": 9, "confidence": "medium", "par": [4,3,5,4,4,3,5,4,3],
    "players": [
        {"name": "Alpha", "scores": [5,3,6,4,4,3,5,4,4]},
        {"name": "Beta",  "scores": [4,3,5,4,3,3,5,3,4]},
    ]
})
nine_result = _parse_vision_response(nine_json, 9)
check("9-hole: success",             nine_result.success,         True)
check("9-hole: holes=9",             nine_result.holes,           9)
check("9-hole: par length=9",        len(nine_result.par),        9)
check("9-hole: scores length=9",     len(nine_result.players[0].scores), 9)


# ==================================================================
print("\n--- 3. _derive_match_result ---")
# ==================================================================

def _make_holes(won_a, won_b, halved, total=18):
    """Build a minimal hole_results list for testing."""
    results = []
    # Fill with wins/losses/halves
    idx = 0
    for _ in range(won_a):
        results.append(HoleResult(
            hole=idx+1, par=4, gross_a1=4, gross_a2=None,
            gross_b1=5, gross_b2=None, net_a1=4, net_a2=None,
            net_b1=5, net_b2=None, best_net_a=4, best_net_b=5,
            winner="A",
        ))
        idx += 1
    for _ in range(won_b):
        results.append(HoleResult(
            hole=idx+1, par=4, gross_a1=5, gross_a2=None,
            gross_b1=4, gross_b2=None, net_a1=5, net_a2=None,
            net_b1=4, net_b2=None, best_net_a=5, best_net_b=4,
            winner="B",
        ))
        idx += 1
    for _ in range(halved):
        results.append(HoleResult(
            hole=idx+1, par=4, gross_a1=4, gross_a2=None,
            gross_b1=4, gross_b2=None, net_a1=4, net_a2=None,
            net_b1=4, net_b2=None, best_net_a=4, best_net_b=4,
            winner="H",
        ))
        idx += 1
    return results

# A wins 10–8
r1, d1 = _derive_match_result(_make_holes(10, 8, 0), 10, 8)
check("10–8: A wins",         r1, "A")
check_true("10–8: detail set", len(d1) > 0)

# B wins 11–7
r2, d2 = _derive_match_result(_make_holes(7, 11, 0), 7, 11)
check("7–11: B wins",         r2, "B")

# Tied 9–9
r3, d3 = _derive_match_result(_make_holes(9, 9, 0), 9, 9)
check("9–9: HALVED",          r3, "HALVED")
check("9–9: detail is AS",    d3, "AS")

# Halved holes count
r4, d4 = _derive_match_result(_make_holes(8, 6, 4), 8, 6)
check("8–6 with 4 halved: A wins", r4, "A")


# ==================================================================
print("\n--- 4. Full calculate_match — with seeded data ---")
# ==================================================================

# Seed the database
seed_all(force=True)
events = list_events()
eid    = events[0]["event_id"]
event  = get_event(eid)
rounds = list_rounds(eid)
# Use round 3 (singles)
singles_rnd = next(r for r in rounds if r["format_code"] == "SINGLES_MP")
rid = singles_rnd["round_id"]

# Get match players from seeded data
matches = list_matches(rid)
m = matches[0]  # Tom vs Steve (singles)

# Build a synthetic extraction that matches these players
# Tom: index 16.0, Steve: index 18.0
# Tom shoots ~84 gross, Steve shoots ~90 gross
tom_scores  = [5,3,6,4,5,4,6,5,5,5,4,6,5,5,4,6,5,5]  # 92 gross
steve_scores = [6,4,7,5,6,4,7,5,6,6,4,7,6,6,4,7,6,6]  # 102 gross

extraction = ExtractionResult(
    success=True,
    holes=18,
    confidence="high",
    course_name="Heron Point GC",
    par=[4,3,5,4,4,3,5,4,3,4,3,5,4,4,3,5,4,3],
    players=[
        ExtractedPlayer(
            raw_name="MacKay",
            scores=tom_scores,
            player_id=m["team_a_player1_id"],
            side="A1",
        ),
        ExtractedPlayer(
            raw_name="Dalton",
            scores=steve_scores,
            player_id=m["team_b_player1_id"],
            side="B1",
        ),
    ],
)

calc = calculate_match(
    extraction=extraction,
    player_a1_id=m["team_a_player1_id"],
    player_b1_id=m["team_b_player1_id"],
    player_a2_id=None,
    player_b2_id=None,
    round_id=rid,
    format_code="SINGLES_MP",
    handicap_mode=event["handicap_mode"],
    allowance_pct=float(event["allowance_pct"]) / 100.0,
)

check_true("calculate_match returns MatchCalculation", calc is not None)
if calc:
    check("18 hole results",                len(calc.hole_results), 18)
    check_true("final_result is A, B, or HALVED",
               calc.final_result in ("A", "B", "HALVED"))
    check_true("result_detail is non-empty",    len(calc.result_detail) > 0)
    check("running_score has 18 entries",   len(calc.running_score), 18)
    check_true("holes_won sum = non-halved holes",
               calc.holes_won_a + calc.holes_won_b + calc.holes_halved == 18)
    check_true("Each hole has winner A/B/H",
               all(h.winner in ("A","B","H") for h in calc.hole_results))
    check_true("Net scores populated",
               all(h.net_a1 is not None and h.net_b1 is not None
                   for h in calc.hole_results))
    # With Tom shooting much better, A should win
    check("Tom shoots better → A wins (most likely)", calc.final_result, "A")


# ==================================================================
print("\n--- 5. save_scorecard_result + get_hole_scores ---")
# ==================================================================

if calc:
    save_scorecard_result(
        match_id=m["match_id"],
        calculation=calc,
        extraction=extraction,
    )

    blob = get_hole_scores(m["match_id"])
    check_true("Blob saved and retrievable",        blob is not None)
    check_true("Blob has hole_detail",              "hole_detail" in blob)
    check("Blob has 18 hole entries",               len(blob["hole_detail"]), 18)
    check("Blob holes_won_a matches calc",          blob["holes_won_a"], calc.holes_won_a)
    check("Blob holes_won_b matches calc",          blob["holes_won_b"], calc.holes_won_b)
    check("Blob confidence = high",                 blob["confidence"],  "high")
    check_true("Blob running_score is list",        isinstance(blob["running_score"], list))

    # Match record updated with result
    m_updated = fetchone("SELECT result, result_detail, hole_scores FROM match WHERE match_id = %s",
                          (m["match_id"],))
    check("Match result updated in DB",        m_updated["result"], calc.final_result)
    check_true("Match result_detail updated",  len(m_updated["result_detail"]) > 0)
    check_true("hole_scores column populated", m_updated["hole_scores"] is not None)

    # Overwrite — save again should replace, not append
    save_scorecard_result(m["match_id"], calc, extraction)
    blob2 = get_hole_scores(m["match_id"])
    check("Re-save does not duplicate hole_detail",
          len(blob2["hole_detail"]), 18)


# ==================================================================
print("\n--- 6. get_hole_scores on match with no scores ---")
# ==================================================================

matches2 = list_matches(rid)
other_mid = next(mm["match_id"] for mm in matches2
                  if mm["match_id"] != m["match_id"])
check("No scores → returns None", get_hole_scores(other_mid), None)


# ==================================================================
print("\n--- 7. image_bytes_to_media_type ---")
# ==================================================================

check("JPEG extension",    image_bytes_to_media_type("photo.jpg"),  "image/jpeg")
check("JPEG long ext",     image_bytes_to_media_type("photo.jpeg"), "image/jpeg")
check("PNG extension",     image_bytes_to_media_type("photo.png"),  "image/png")
check("WEBP extension",    image_bytes_to_media_type("photo.webp"), "image/webp")
check("Unknown → jpeg",    image_bytes_to_media_type("photo.bmp"),  "image/jpeg")
check("Uppercase ext",     image_bytes_to_media_type("PHOTO.JPG"),  "image/jpeg")


# ==================================================================
# Cleanup
# ==================================================================
shutil.rmtree(_tmpdir)

total = PASS + FAIL
print(f"\n{'='*50}")
print(f"  Scorecard Results: {PASS}/{total} tests passed")
if FAIL == 0:
    print("  🏌️  All scorecard tests passed.")
else:
    print(f"  ⚠️   {FAIL} test(s) failed — review above.")
print(f"{'='*50}\n")

sys.exit(0 if FAIL == 0 else 1)

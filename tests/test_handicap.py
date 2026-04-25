"""
test_handicap.py — WHS 2024 Handicap Engine Test Suite
Golf Match Captain | Phase 1B

All test cases are validated against known WHS 2024 formula outputs.
Run from the project root:
    python tests/test_handicap.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.handicap import (
    course_handicap,
    course_handicap_rounded,
    playing_handicap,
    playing_handicap_for_format,
    apply_handicap_mode,
    strokes_received,
    stroke_allocation,
    stroke_allocation_detail,
    matchup_handicap_detail,
    foursomes_team_handicap,
    _round_half_up,
    FORMAT_ALLOWANCES,
    FORMAT_LABELS,
)

PASS = 0
FAIL = 0


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


def approx(a: float, b: float, tol: float = 0.01) -> bool:
    return abs(a - b) <= tol


def check_approx(description: str, result: float, expected: float, tol: float = 0.01) -> None:
    global PASS, FAIL
    if approx(result, expected, tol):
        print(f"  ✅  {description}")
        PASS += 1
    else:
        print(f"  ❌  {description}")
        print(f"       Expected: ≈{expected} (±{tol})")
        print(f"       Got:      {result}")
        FAIL += 1


# =================================================================
print("\n--- 1. Rounding utility ---")
# =================================================================
check("0.5 rounds up to 1",  _round_half_up(0.5),  1)
check("1.5 rounds up to 2",  _round_half_up(1.5),  2)
check("2.4 rounds down to 2", _round_half_up(2.4), 2)
check("-0.5 rounds to 0",    _round_half_up(-0.5), 0)
check("14.7 rounds to 15",   _round_half_up(14.7), 15)
check("14.5 rounds to 15",   _round_half_up(14.5), 15)


# =================================================================
print("\n--- 2. Course Handicap formula ---")
# WHS: (Index × Slope / 113) + (Course Rating − Par)
# =================================================================

# Example A: Index 12.0, Slope 125, Rating 71.5, Par 72
# = (12.0 × 125 / 113) + (71.5 − 72) = 13.274 + (−0.5) = 12.774 → 13
ch_a_raw = course_handicap(12.0, 125, 71.5, 72)
check_approx("Index 12.0, Slope 125, Rating 71.5, Par 72 → raw ≈ 12.77", ch_a_raw, 12.774)
check("Rounded → 13", course_handicap_rounded(12.0, 125, 71.5, 72), 13)

# Example B: Index 7.6, Slope 130, Rating 73.2, Par 72
# = (7.6 × 130 / 113) + (73.2 − 72) = 8.743 + 1.2 = 9.943 → 10
ch_b_raw = course_handicap(7.6, 130, 73.2, 72)
check_approx("Index 7.6, Slope 130, Rating 73.2, Par 72 → raw ≈ 9.94", ch_b_raw, 9.943)
check("Rounded → 10", course_handicap_rounded(7.6, 130, 73.2, 72), 10)

# Example C: Index 18.0, Slope 113 (standard), Rating 72.0, Par 72
# = (18.0 × 113 / 113) + 0 = 18.0 → 18
check_approx("Standard slope, rating = par → Course HC equals index", 
             course_handicap(18.0, 113, 72.0, 72), 18.0)

# Example D: Index 0.0 — scratch player on tough course
# = 0 + (74.0 − 72) = 2.0 → 2
check("Scratch player on tough course → Course HC 2",
      course_handicap_rounded(0.0, 120, 74.0, 72), 2)

# Example E: High handicapper
# Index 28.0, Slope 120, Rating 70.5, Par 71
# = (28.0 × 120 / 113) + (70.5 − 71) = 29.734 − 0.5 = 29.234 → 29
check_approx("High index player raw", course_handicap(28.0, 120, 70.5, 71), 29.234, 0.05)
check("High index player rounded → 29", course_handicap_rounded(28.0, 120, 70.5, 71), 29)


# =================================================================
print("\n--- 3. Playing Handicap (allowances) ---")
# =================================================================

# Singles Match Play: 100%
check("100% allowance: CH 13 → Playing HC 13", playing_handicap(13, 1.00), 13)

# Four-Ball: 90%
check("90% allowance: CH 13 → Playing HC 12 (13×0.9=11.7→12)",
      playing_handicap(13, 0.90), 12)

# Foursomes: 50%
check("50% allowance: CH 13 → Playing HC 7 (13×0.5=6.5→7)",
      playing_handicap(13, 0.50), 7)

# Stroke play: 95%
check("95% allowance: CH 10 → Playing HC 10 (10×0.95=9.5→10)",
      playing_handicap(10, 0.95), 10)

# Event-level 80% override
check("80% allowance: CH 20 → Playing HC 16", playing_handicap(20, 0.80), 16)


# =================================================================
print("\n--- 4. Full chain — playing_handicap_for_format ---")
# =================================================================

# Player: Index 12.0 at Heron Point (Slope 125, Rating 71.5, Par 72)
# Singles Match Play (100%)
result = playing_handicap_for_format(12.0, 125, 71.5, 72, "SINGLES_MP")
check_approx("Full chain: Index 12.0, SINGLES_MP → course_hc_raw ≈ 12.77",
             result["course_hc_raw"], 12.77)
check("Full chain: course_hc = 13", result["course_hc"], 13)
check("Full chain: playing_hc = 13 (100% of 13)", result["playing_hc"], 13)

# Same player, Four-Ball (90%)
result_fb = playing_handicap_for_format(12.0, 125, 71.5, 72, "FOURBALL_MP")
check("Four-Ball: playing_hc = 12 (90% of 13)", result_fb["playing_hc"], 12)

# Same player, Stroke Play (95%)
result_sp = playing_handicap_for_format(12.0, 125, 71.5, 72, "SINGLES_STROKE")
check("Stroke Play: playing_hc = 12 (95% of 13)", result_sp["playing_hc"], 12)

# With event-level 80% allowance
result_ev = playing_handicap_for_format(12.0, 125, 71.5, 72, "SINGLES_MP",
                                         event_allowance_pct=0.80)
check("80% event override, SINGLES: playing_hc = 10 (80% of 13 = 10.4→10)",
      result_ev["playing_hc"], 10)


# =================================================================
print("\n--- 5. Handicap Mode — PLAY_OFF_LOW ---")
# =================================================================

# Group: playing HCs [13, 7, 18]
# Low = 7; adjusted = [6, 0, 11]
adjusted = apply_handicap_mode([13, 7, 18], "PLAY_OFF_LOW")
check("PLAY_OFF_LOW: [13,7,18] → [6,0,11]", adjusted, [6, 0, 11])

# Already equal
check("PLAY_OFF_LOW: [10,10] → [0,0]", apply_handicap_mode([10, 10], "PLAY_OFF_LOW"), [0, 0])

# FULL_INDEX — no change
check("FULL_INDEX: passthrough", apply_handicap_mode([13, 7, 18], "FULL_INDEX"), [13, 7, 18])


# =================================================================
print("\n--- 6. Strokes received ---")
# =================================================================

check("Player A HC 13, Player B HC 7 → 6 strokes", strokes_received(13, 7), 6)
check("Equal HCs → 0 strokes", strokes_received(10, 10), 0)
check("B higher than A → 5 strokes", strokes_received(5, 10), 5)


# =================================================================
print("\n--- 7. Stroke allocation (hole-by-hole) ---")
# =================================================================

# Standard 18-hole SI: [1..18] in order (SI 1 is hardest)
si_simple = list(range(1, 19))  # [1, 2, 3, ..., 18]

# Playing HC 3 → receives stroke on holes with SI 1, 2, 3
alloc = stroke_allocation(3, si_simple)
check("HC 3: hole 1 (SI 1) gets stroke",   alloc[0], True)
check("HC 3: hole 2 (SI 2) gets stroke",   alloc[1], True)
check("HC 3: hole 3 (SI 3) gets stroke",   alloc[2], True)
check("HC 3: hole 4 (SI 4) no stroke",     alloc[3], False)
check("HC 3: hole 18 (SI 18) no stroke",   alloc[17], False)
check("HC 3: exactly 3 strokes total",      sum(alloc), 3)

# Playing HC 18 → stroke on every hole
alloc18 = stroke_allocation(18, si_simple)
check("HC 18: all 18 holes get a stroke", sum(alloc18), 18)

# Playing HC 0 → no strokes
alloc0 = stroke_allocation(0, si_simple)
check("HC 0: no strokes on any hole", sum(alloc0), 0)

# Playing HC 19 → all 18 + one extra on SI 1 (still just True for receives_stroke)
alloc19 = stroke_allocation(19, si_simple)
check("HC 19: all 18 holes show receives_stroke=True", all(alloc19), True)

# Realistic SI (not sequential — test that SI ordering matters)
si_realistic = [7, 15, 3, 11, 5, 17, 1, 13, 9,  # holes 1-9
                6, 14, 2, 10, 4, 16, 8, 12, 18]  # holes 10-18
# HC 1 → only hole with SI=1, which is hole index 6 (hole 7)
alloc_r1 = stroke_allocation(1, si_realistic)
check("Realistic SI, HC 1: exactly 1 stroke", sum(alloc_r1), 1)
check("Realistic SI, HC 1: stroke on hole 7 (SI=1)", alloc_r1[6], True)
check("Realistic SI, HC 1: no stroke on hole 1 (SI=7)", alloc_r1[0], False)

# HC 2 → holes with SI 1 and SI 2
alloc_r2 = stroke_allocation(2, si_realistic)
check("Realistic SI, HC 2: exactly 2 strokes", sum(alloc_r2), 2)


# =================================================================
print("\n--- 8. Stroke allocation detail ---")
# =================================================================

detail = stroke_allocation_detail(3, si_simple)
check("Detail: 18 hole entries returned", len(detail), 18)
check("Detail: hole 1 has SI=1, strokes=1", 
      (detail[0]["si"], detail[0]["strokes"]), (1, 1))
check("Detail: hole 4 has SI=4, strokes=0",
      (detail[3]["si"], detail[3]["strokes"]), (4, 0))
check("Detail: hole 3 receives_stroke=True",
      detail[2]["receives_stroke"], True)
check("Detail: hole 5 receives_stroke=False",
      detail[4]["receives_stroke"], False)


# =================================================================
print("\n--- 9. Matchup detail ---")
# =================================================================

player_a = {"name": "Tom",  "current_index": 12.0}
player_b = {"name": "Bill", "current_index": 7.6}
tee_deck  = {
    "rating": 71.5, "slope": 125, "par": 72,
    "stroke_index": si_realistic,
}

matchup = matchup_handicap_detail(
    player_a, player_b, tee_deck, tee_deck,
    "SINGLES_MP", "FULL_INDEX", 1.0, 18,
)

check("Matchup: Tom's course HC is 13",  matchup["player_a"]["course_hc"], 13)
# Bill: (7.6 × 125 / 113) + (71.5 − 72) = 8.407 − 0.5 = 7.907 → 8
check("Matchup: Bill's course HC is 8",  matchup["player_b"]["course_hc"], 8)
check("Matchup: 5 strokes given (13−8)", matchup["strokes_given"], 5)
check("Matchup: Tom is higher HC",       matchup["higher_hc_player"], "Tom")

# PLAY_OFF_LOW mode — Bill (lower HC=8) plays scratch; Tom gets (13−8)=5
matchup_pol = matchup_handicap_detail(
    player_a, player_b, tee_deck, tee_deck,
    "SINGLES_MP", "PLAY_OFF_LOW", 1.0, 18,
)
check("PLAY_OFF_LOW: Bill's adjusted HC = 0", matchup_pol["player_b"]["adjusted_hc"], 0)
check("PLAY_OFF_LOW: Tom's adjusted HC = 5",  matchup_pol["player_a"]["adjusted_hc"], 5)
check("PLAY_OFF_LOW: strokes given = 5",      matchup_pol["strokes_given"], 5)


# =================================================================
print("\n--- 10. Foursomes team handicap ---")
# =================================================================

# Team: Index 12.0 + 7.6 at (Slope 125, Rating 71.5, Par 72)
# Course HCs: Tom=13, Bill=8 → combined=21
# 50% of 21 = 10.5 → 11
team_hc = foursomes_team_handicap(12.0, 7.6, 125, 71.5, 72)
check("Foursomes team HC: (13+8)×50% = 10.5→11", team_hc, 11)

# Equal players: Index 10 each at standard course (Slope 113, Rating 72, Par 72)
# Course HCs: 10 + 10 = 20 combined; 50% = 10.0 → 10
team_hc2 = foursomes_team_handicap(10.0, 10.0, 113, 72.0, 72)
check("Foursomes equal team: (10+10)×50% = 10", team_hc2, 10)


# =================================================================
print("\n--- 11. Format constants completeness ---")
# =================================================================

expected_formats = {"SINGLES_MP", "FOURBALL_MP", "FOURSOMES_MP", "SINGLES_STROKE", "SCRAMBLE"}
check("All 5 formats have allowances", set(FORMAT_ALLOWANCES.keys()), expected_formats)
check("All 5 formats have labels",     set(FORMAT_LABELS.keys()),     expected_formats)


# =================================================================
# Summary
# =================================================================
total = PASS + FAIL
print(f"\n{'='*50}")
print(f"  Phase 1B Results: {PASS}/{total} tests passed")
if FAIL == 0:
    print("  🏌️  All handicap engine tests passed.")
else:
    print(f"  ⚠️   {FAIL} test(s) failed — review output above.")
print(f"{'='*50}\n")

sys.exit(0 if FAIL == 0 else 1)

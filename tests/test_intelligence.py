"""
test_intelligence.py — Phase 1D Test Suite
Golf Match Captain

Tests: trend analysis, volatility, best-3 gap, sandbagging flags,
       derived index, posting frequency, LLM formatting.
Run from project root:
    python tests/test_intelligence.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.intelligence import (
    build_player_intelligence,
    format_intelligence_for_llm,
    _trend_direction,
    _volatility,
    _best3_average,
    _derived_index,
    _avg_days_between_posts,
    _sandbagging_flags,
)

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


def check_approx(description, result, expected, tol=0.1):
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
print("\n--- 1. Trend direction ---")
# ==================================================================

# Clearly improving: recent avg lower than baseline
improving_diffs = [8.0, 8.5, 9.0, 9.2, 8.8,   # recent 5 (low = better)
                   12.0, 12.5, 11.8, 13.0, 12.2] # baseline 5-14
trend = _trend_direction(improving_diffs)
check("Improving trend detected",      trend["direction"], "IMPROVING")
check_true("Improving label contains ↓", "↓" in trend["label"])
check_true("Delta is negative (lower = better)", trend["delta"] < 0)

# Clearly declining
declining_diffs = [15.0, 14.5, 15.2, 14.8, 15.5,
                    11.0, 10.5, 11.2, 10.8, 11.0]
trend2 = _trend_direction(declining_diffs)
check("Declining trend detected", trend2["direction"], "DECLINING")

# Stable (within ±1.0)
stable_diffs = [12.0, 12.2, 11.9, 12.1, 12.0,
                12.3, 11.8, 12.2, 12.0, 12.1]
trend3 = _trend_direction(stable_diffs)
check("Stable trend detected",    trend3["direction"], "STABLE")

# Insufficient data — only 3 rounds
short_diffs = [12.0, 11.5, 13.0]
trend4 = _trend_direction(short_diffs)
check("Short data → STABLE fallback", trend4["direction"], "STABLE")


# ==================================================================
print("\n--- 2. Volatility ---")
# ==================================================================

consistent = [12.0, 12.1, 11.9, 12.2, 11.8, 12.0, 12.1, 11.9]
check_approx("Very consistent player — low SD", _volatility(consistent), 0.12, tol=0.15)

volatile = [8.0, 18.0, 10.0, 20.0, 9.0, 17.0, 11.0, 19.0]
check_true("Volatile player — SD > 4", _volatility(volatile) > 4.0)

check("Single round — SD is 0.0", _volatility([12.0]), 0.0)


# ==================================================================
print("\n--- 3. Best-3 gap ---")
# ==================================================================

diffs_gap = [10.0, 11.0, 12.0, 15.0, 16.0, 17.0, 18.0]
best3_avg = _best3_average(diffs_gap)
check_approx("Best-3 average of [10,11,12,...18]", best3_avg, 11.0, tol=0.1)

# Gap = current_index - best3_avg
# If index is 15.0 and best3 is 11.0 → gap = 4.0
check_approx("Gap: index 15 minus best3 11 = 4.0", 15.0 - best3_avg, 4.0, tol=0.1)

check("Empty diffs → best3 = 0.0", _best3_average([]), 0.0)
check("Single diff → best3 = that value", _best3_average([7.5]), 7.5)


# ==================================================================
print("\n--- 4. Derived index ---")
# ==================================================================

diffs_20 = [10.0 + i * 0.3 for i in range(20)]  # 20 rounds, some better some worse
derived = _derived_index(diffs_20)
check_true("Derived index: best-8 average is lower than overall avg",
           derived < sum(diffs_20) / len(diffs_20))

check("Fewer than 3 rounds → None", _derived_index([12.0, 11.5]), None)

diffs_5 = [10.0, 11.0, 12.0, 13.0, 14.0]
derived5 = _derived_index(diffs_5)
check_true("5 rounds → derived index uses best 5 (capped at 8)", derived5 is not None)


# ==================================================================
print("\n--- 5. Posting frequency ---")
# ==================================================================

# Dates every 2 weeks — well within threshold
frequent_dates = [
    "2025-09-01", "2025-08-18", "2025-08-04",
    "2025-07-21", "2025-07-07", "2025-06-23",
]
avg_days = _avg_days_between_posts(frequent_dates)
check_approx("Bi-weekly posting → avg ~14 days", avg_days, 14.0, tol=2.0)

# Dates every 6 weeks — above threshold (21 days)
infrequent_dates = [
    "2025-09-01", "2025-07-21", "2025-06-09",
    "2025-04-28", "2025-03-17",
]
avg_days2 = _avg_days_between_posts(infrequent_dates)
check_true("6-weekly posting → avg > 21 days", avg_days2 > 21)

check("Fewer than 2 dates → None", _avg_days_between_posts(["2025-09-01"]), None)


# ==================================================================
print("\n--- 6. Sandbagging flags ---")
# ==================================================================

# Red flag: best3_gap > 4
flags_red = _sandbagging_flags(best3_gap=5.2, posting_days_avg=14, volatility=2.0, n_rounds=10)
check("Best-3 gap >4 triggers RED", flags_red["red"], True)
check("RED flag has a message",      len(flags_red["messages"]) > 0, True)

# Amber: infrequent posting
flags_amber_posting = _sandbagging_flags(best3_gap=1.0, posting_days_avg=28, volatility=2.0, n_rounds=10)
check("Infrequent posting triggers AMBER", flags_amber_posting["amber"], True)

# Amber: high volatility
flags_amber_vol = _sandbagging_flags(best3_gap=1.0, posting_days_avg=14, volatility=5.0, n_rounds=10)
check("High volatility triggers AMBER", flags_amber_vol["amber"], True)

# Green: everything clean
flags_green = _sandbagging_flags(best3_gap=1.0, posting_days_avg=14, volatility=2.0, n_rounds=10)
check("Clean profile → GREEN",   flags_green["green"], True)
check("Clean profile → not RED", flags_green["red"],   False)

# Not enough rounds → no green
flags_none = _sandbagging_flags(best3_gap=1.0, posting_days_avg=14, volatility=2.0, n_rounds=2)
check("< 5 rounds → no GREEN flag", flags_none["green"], False)


# ==================================================================
print("\n--- 7. Full profile — build_player_intelligence ---")
# ==================================================================

# Construct a 15-round profile with a clear sandbagging red flag
# Index: 16.0, best-3 rounds: 9.0, 9.5, 10.0 → gap = 16 - 9.5 = 6.5 → RED
diffs_sandbagger = [9.0, 9.5, 10.0, 16.5, 17.0, 17.5, 16.0, 17.2,
                    16.8, 17.1, 16.5, 17.3, 16.9, 17.0, 16.7]
dates_sandbagger = [f"2025-{(m):02d}-01" for m in [9,8,7,6,5,4,3,2,1,1,1,1,1,1,1]]

profile_sb = build_player_intelligence(diffs_sandbagger, 16.0, dates_sandbagger)
check("Sandbagger: signal is RED", profile_sb["signal"], "RED")
check_true("Sandbagger: best3_gap > 4", profile_sb["best3_gap"] > 4.0)
check_true("Sandbagger: has flag messages", len(profile_sb["flag_messages"]) > 0)

# Construct a clean 12-round profile
diffs_clean = [12.0, 12.2, 11.8, 12.1, 11.9, 12.3, 12.0, 11.7, 12.2, 12.1, 11.9, 12.0]
dates_clean = [f"2025-{9-(i//2):02d}-{(15 if i%2==0 else 1):02d}" for i in range(12)]

profile_clean = build_player_intelligence(diffs_clean, 12.0, dates_clean)
check("Clean player: signal is GREEN", profile_clean["signal"], "GREEN")
check_true("Clean player: n_rounds == 12", profile_clean["n_rounds"] == 12)
check_true("Clean player: derived_index is set", profile_clean["derived_index"] is not None)
check_true("Clean player: summary_lines is non-empty", len(profile_clean["summary_lines"]) > 0)

# Empty profile (no rounds)
profile_empty = build_player_intelligence([], 15.0)
check("Empty profile: signal is NONE", profile_empty["signal"], "NONE")
check("Empty profile: n_rounds == 0", profile_empty["n_rounds"], 0)
check("Empty profile: derived_index None", profile_empty["derived_index"], None)


# ==================================================================
print("\n--- 8. LLM context formatter ---")
# ==================================================================

llm_text = format_intelligence_for_llm("Tom MacKay", profile_sb)
check_true("LLM text contains player name", "Tom MacKay" in llm_text)
check_true("LLM text contains index",       "16.0" in llm_text)
check_true("LLM text contains signal",      "RED" in llm_text)
check_true("LLM text contains trend",       "Trend:" in llm_text)
check_true("LLM text has arrow indicator",  "→" in llm_text)

llm_text_clean = format_intelligence_for_llm("Bill Henderson", profile_clean)
check_true("Clean player LLM text contains GREEN", "GREEN" in llm_text_clean)


# ==================================================================
print("\n--- 9. All profile dict keys present ---")
# ==================================================================

required_keys = [
    "n_rounds", "current_index", "derived_index",
    "trend_direction", "trend_label", "trend_delta",
    "recent_avg", "baseline_avg",
    "volatility", "volatility_label",
    "best3_avg", "best3_gap",
    "posting_days_avg",
    "flag_red", "flag_amber", "flag_green", "flag_messages",
    "signal", "summary_lines",
]
for key in required_keys:
    check_true(f"Profile has key: {key}", key in profile_clean)


# ==================================================================
total = PASS + FAIL
print(f"\n{'='*50}")
print(f"  Phase 1D Results: {PASS}/{total} tests passed")
if FAIL == 0:
    print("  🏌️  All intelligence tests passed.")
else:
    print(f"  ⚠️   {FAIL} test(s) failed — review above.")
print(f"{'='*50}\n")

sys.exit(0 if FAIL == 0 else 1)

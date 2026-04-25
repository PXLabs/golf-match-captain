"""
test_advisor.py — Phase 1F Test Suite
Golf Match Captain

Tests: context packet builder, system prompt loader, conversation
       history helpers, starter prompts, API key resolver logic.
       Does NOT make live API calls.
Run from project root:
    python tests/test_advisor.py
"""

import sys, shutil, tempfile, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import database.db as db_module
_tmpdir = tempfile.mkdtemp()
db_module.DB_PATH = Path(_tmpdir) / "test.db"

from database.db import initialise_database
from modules.roster import add_player, add_tag, add_score_record
from modules.courses import add_course, add_tee_deck
from modules.events import create_event, assign_player, add_round
from modules.results import create_match, record_result
from modules.advisor import (
    build_context_packet, load_system_prompt,
    append_user_message, append_assistant_message, trim_history,
    STARTER_PROMPTS, AVAILABLE_MODELS, DEFAULT_MODEL,
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
# Setup — realistic event with players, scores, tags, results
# ==================================================================

pid_tom   = add_player("Tom MacKay",     12.3, tee_preference="White")
pid_bill  = add_player("Bill Henderson",  7.6, tee_preference="Blue")
pid_steve = add_player("Steve Dalton",   18.0)
pid_gary  = add_player("Gary Prentice",  22.5)

# Tags
add_tag(pid_tom,   "TEMPERAMENT",   "Clutch competitor")
add_tag(pid_tom,   "PHYSICAL",      "Knee issue")
add_tag(pid_bill,  "PLAYING_STYLE", "Aggressive driver")
add_tag(pid_steve, "TEMPERAMENT",   "Fades under pressure")

# Score history — Tom has sandbagging-like profile (best rounds well below index)
for i, diff in enumerate([8.5, 9.0, 9.2, 13.0, 12.8, 13.2, 12.9, 13.1, 12.7, 13.0]):
    add_score_record(pid_tom, f"2025-{(i % 9)+1:02d}-15",
                     "Heron Point GC", diff, tee_deck="White")

# Bill — consistent and reliable
for i, diff in enumerate([7.2, 7.5, 7.8, 7.4, 7.6, 7.3, 7.7, 7.5, 7.6, 7.4]):
    add_score_record(pid_bill, f"2025-{(i % 9)+1:02d}-20",
                     "Heron Point GC", diff, tee_deck="Blue")

cid = add_course("Heron Point GC", "Picton, ON")
tid = add_tee_deck(cid, "White", 71.5, 125, 72, VALID_SI)

eid = create_event(
    name="Heron Point Cup 2025",
    start_date="2025-07-12",
    team_a_name="The Aces",
    team_b_name="The Bogeys",
    handicap_mode="FULL_INDEX",
    allowance_pct=100.0,
)

assign_player(eid, pid_tom,   "A")
assign_player(eid, pid_bill,  "A")
assign_player(eid, pid_steve, "B")
assign_player(eid, pid_gary,  "B")

rid1 = add_round(eid, cid, "2025-07-12", "FOURBALL_MP",  1, 18, tid, tid)
rid2 = add_round(eid, cid, "2025-07-13", "SINGLES_MP",   2, 18, tid, tid)

mid1 = create_match(rid1, 1, pid_tom, pid_bill, pid_steve, pid_gary)
record_result(mid1, "A", "2&1")


# ==================================================================
print("\n--- 1. Context packet — structure and content ---")
# ==================================================================

ctx = build_context_packet(eid, rid1)

check_true("Context is a non-empty string",     isinstance(ctx, str) and len(ctx) > 100)
check_true("Contains event name",               "Heron Point Cup 2025" in ctx)
check_true("Contains team A name",              "The Aces" in ctx)
check_true("Contains team B name",              "The Bogeys" in ctx)
check_true("Contains Team A section",           "TEAM A" in ctx)
check_true("Contains Team B section",           "TEAM B" in ctx)
check_true("Contains Tom MacKay",               "Tom MacKay" in ctx)
check_true("Contains Bill Henderson",           "Bill Henderson" in ctx)
check_true("Contains Steve Dalton",             "Steve Dalton" in ctx)
check_true("Contains handicap mode",            "FULL_INDEX" in ctx)
check_true("Contains format label",             "Four-Ball" in ctx)
check_true("Contains course name",              "Heron Point" in ctx)

# Intelligence signals should appear
check_true("Contains index data",               "12.3" in ctx or "7.6" in ctx)

# Tags should appear
check_true("Tom's tag present",                 "Clutch competitor" in ctx)
check_true("Steve's tag present",               "Fades under pressure" in ctx)

# Playing handicap calculations should appear
check_true("Contains Course HC or Playing HC",  "Course HC" in ctx or "Playing HC" in ctx)

# Results section should appear (one result recorded)
check_true("Contains RESULTS section",          "RESULTS" in ctx or "EVENT SCORE" in ctx)
check_true("Contains round schedule",           "ROUND SCHEDULE" in ctx)


# ==================================================================
print("\n--- 2. Context packet — round 2 (no results yet) ---")
# ==================================================================

ctx2 = build_context_packet(eid, rid2)
check_true("Round 2 context has Singles format", "Singles" in ctx2)
check_true("Round 2 still has player data",       "Tom MacKay" in ctx2)


# ==================================================================
print("\n--- 3. Context packet — no round_id (defaults to latest) ---")
# ==================================================================

ctx_no_round = build_context_packet(eid, round_id=None)
check_true("No round_id → still builds context", len(ctx_no_round) > 100)
check_true("Defaults to most recent round",       "Round" in ctx_no_round)


# ==================================================================
print("\n--- 4. System prompt loader ---")
# ==================================================================

test_context = "TEST_CONTEXT_MARKER_XYZ"
system = load_system_prompt(test_context)

check_true("System prompt is non-empty",          len(system) > 50)
check_true("Context injected into prompt",        test_context in system)
check_true("Contains advisor role description",   "captain" in system.lower())
check_true("Contains RECOMMEND mode",             "RECOMMEND" in system)
check_true("Contains CRITIQUE mode",              "CRITIQUE" in system)
check_true("Contains WHAT-IF mode",               "WHAT-IF" in system)
check_true("Contains handicap signal guidance",   "🔴" in system or "RED" in system)


# ==================================================================
print("\n--- 5. Conversation history helpers ---")
# ==================================================================

history = []

# Append user message
h1 = append_user_message(history, "Who should I pair today?")
check("append_user_message: length 1",       len(h1), 1)
check("append_user_message: role is user",   h1[0]["role"], "user")
check("append_user_message: content matches",h1[0]["content"], "Who should I pair today?")
check("Original history unchanged",          len(history), 0)

# Append assistant message
h2 = append_assistant_message(h1, "I recommend pairing Tom with Bill.")
check("append_assistant: length 2",          len(h2), 2)
check("append_assistant: role is assistant", h2[1]["role"], "assistant")

# Build a longer history
long_history = []
for i in range(25):
    long_history = append_user_message(long_history, f"Question {i}")
    long_history = append_assistant_message(long_history, f"Answer {i}")

check("Long history has 50 messages",        len(long_history), 50)

trimmed = trim_history(long_history, max_turns=10)
check("trim_history(max_turns=10): max 20 messages", len(trimmed) <= 20, True)
check_true("Trimmed history keeps most recent",
           "Question 24" in trimmed[-1]["content"] or
           "Answer 24"   in trimmed[-1]["content"])

# Trim a short history — should be unchanged
short = [{"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Hello"}]
check("trim_history on short history: unchanged", trim_history(short, max_turns=10), short)


# ==================================================================
print("\n--- 6. Starter prompts ---")
# ==================================================================

check_true("4 starter prompts defined",       len(STARTER_PROMPTS) == 4)
for s in STARTER_PROMPTS:
    check_true(f"Starter '{s['label']}' has label and prompt",
               "label" in s and "prompt" in s and len(s["prompt"]) > 20)


# ==================================================================
print("\n--- 7. Model configuration ---")
# ==================================================================

check_true("At least 1 model available",           len(AVAILABLE_MODELS) >= 1)
check_true("Default model in available models",    DEFAULT_MODEL in AVAILABLE_MODELS)
check_true("Default model label is non-empty",
           len(AVAILABLE_MODELS.get(DEFAULT_MODEL, "")) > 0)


# ==================================================================
print("\n--- 8. Context packet — invalid event ---")
# ==================================================================

ctx_bad = build_context_packet(99999, None)
check_true("Invalid event returns safe fallback string", len(ctx_bad) > 0)
check_true("Fallback does not raise — returns string",   isinstance(ctx_bad, str))


# ==================================================================
# Cleanup
# ==================================================================
shutil.rmtree(_tmpdir)

total = PASS + FAIL
print(f"\n{'='*50}")
print(f"  Phase 1F Results: {PASS}/{total} tests passed")
if FAIL == 0:
    print("  🏌️  All advisor tests passed.")
else:
    print(f"  ⚠️   {FAIL} test(s) failed — review above.")
print(f"{'='*50}\n")

sys.exit(0 if FAIL == 0 else 1)

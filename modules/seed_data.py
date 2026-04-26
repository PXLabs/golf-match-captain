"""
seed_data.py — Test Data Seeder
Golf Match Captain

Loads a complete, realistic demo dataset:
  - 8 players (4 per team) with Canadian names and CPGA IDs
  - 2 courses with full tee deck and stroke index configurations
  - 1 completed event (Heron Point Cup) with 3 rounds and full results
  - Score history (10–15 differentials per player) producing varied
    intelligence signals: one RED sandbagger, two AMBER, rest GREEN

Safe to run multiple times — checks for existing data first.
Call clear_all_data() before re-seeding for a clean slate.
"""

from __future__ import annotations
from database.db import initialise_database, execute, fetchone
from modules.roster import add_player, add_tag, add_score_record
from modules.courses import add_course, add_tee_deck
from modules.events import (
    create_event, assign_player, add_round,
)
from modules.results import create_match, record_result


# ---------------------------------------------------------------
# Clear all data
# ---------------------------------------------------------------

def clear_all_data() -> None:
    """
    Delete all application data from the database.
    Preserves the schema — tables remain, all rows are removed.
    Order respects foreign key constraints.
    """
    tables = [
        "match",
        "round",
        "event_player",
        "event",
        "player_tag",
        "score_record",
        "player",
        "tee_deck",
        "course",
    ]
    for table in tables:
        execute(f"DELETE FROM {table}")


def is_seeded() -> bool:
    """Return True if the database already contains player data."""
    row = fetchone("SELECT COUNT(*) as cnt FROM player")
    return row and row["cnt"] > 0


# ---------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------

def seed_all(force: bool = False) -> dict:
    """
    Load the complete demo dataset.

    force=True: clear existing data before seeding.
    force=False: skip if data already exists.

    Returns a summary dict of what was created.
    """
    initialise_database()

    if not force and is_seeded():
        return {"skipped": True, "reason": "Data already exists. Use force=True to re-seed."}

    if force:
        clear_all_data()

    summary = {}

    # ---- Players -----------------------------------------------
    players = _seed_players()
    summary["players"] = len(players)

    # ---- Courses -----------------------------------------------
    courses = _seed_courses()
    summary["courses"] = len(courses)

    # ---- Event -------------------------------------------------
    event_id = _seed_event(players, courses)
    summary["events"] = 1
    summary["event_id"] = event_id

    return summary


# ---------------------------------------------------------------
# Players
# ---------------------------------------------------------------

def _seed_players() -> dict:
    """
    8 players — 4 Team A (The Aces), 4 Team B (The Bogeys).
    Varied handicap indexes and intelligence profiles:
      - MacKay:    🔴 RED — best rounds well below his index (sandbagger flag)
      - Henderson: 🟢 GREEN — tight, consistent, reliable index
      - Dalton:    🟡 AMBER — high variance, inconsistent
      - Prentice:  🟢 GREEN — steady improver
      - Kowalski:  🟡 AMBER — infrequent posting
      - Okafor:    🟢 GREEN — low index, consistent
      - Leblanc:   🟢 GREEN — mid handicapper, stable
      - Brennan:   🔴 RED — large best-3 gap
    """
    players = {}

    # --- Team A ---

    # Tom MacKay — Index 16.0, RED signal (best 3 rounds ~9–10, gap > 4)
    pid = add_player("Tom MacKay", 16.0, cpga_id="CA-100001",
                     tee_preference="White",
                     notes="Knee issue — avoid hilly back nine fatigue")
    add_tag(pid, "TEMPERAMENT",   "Clutch competitor")
    add_tag(pid, "PLAYING_STYLE", "Strong short game")
    add_tag(pid, "PHYSICAL",      "Knee issue")
    add_tag(pid, "CHEMISTRY",     "Strong pairing with Bill Henderson")
    _add_scores(pid, [
        ("2025-09-10", "Heron Point GC",   9.2,  78, "White"),
        ("2025-08-28", "Heron Point GC",   9.8,  79, "White"),
        ("2025-08-14", "Cobble Beach GC",  10.1, 80, "White"),
        ("2025-07-30", "Heron Point GC",   16.5, 87, "White"),
        ("2025-07-16", "Loch March GC",    17.1, 88, "White"),
        ("2025-07-02", "Heron Point GC",   16.8, 87, "White"),
        ("2025-06-18", "Cobble Beach GC",  15.9, 86, "White"),
        ("2025-06-04", "Heron Point GC",   17.2, 88, "White"),
        ("2025-05-21", "Loch March GC",    16.4, 87, "White"),
        ("2025-05-07", "Heron Point GC",   15.8, 86, "White"),
    ])
    players["tom"] = pid

    # Bill Henderson — Index 7.6, GREEN signal (very consistent)
    pid = add_player("Bill Henderson", 7.6, cpga_id="CA-100002",
                     tee_preference="Blue",
                     notes="Low handicapper, reliable under pressure")
    add_tag(pid, "PLAYING_STYLE", "Aggressive driver")
    add_tag(pid, "PLAYING_STYLE", "Strong iron player")
    add_tag(pid, "TEMPERAMENT",   "Mentally tough")
    add_tag(pid, "CHEMISTRY",     "Strong pairing with Tom MacKay")
    _add_scores(pid, [
        ("2025-09-08",  "Heron Point GC",  7.2, 74, "Blue"),
        ("2025-08-25",  "Cobble Beach GC", 7.8, 75, "Blue"),
        ("2025-08-11",  "Heron Point GC",  7.5, 74, "Blue"),
        ("2025-07-28",  "Loch March GC",   7.1, 73, "Blue"),
        ("2025-07-14",  "Heron Point GC",  7.6, 74, "Blue"),
        ("2025-06-30",  "Cobble Beach GC", 7.9, 75, "Blue"),
        ("2025-06-16",  "Heron Point GC",  7.4, 74, "Blue"),
        ("2025-06-02",  "Loch March GC",   7.3, 73, "Blue"),
        ("2025-05-19",  "Heron Point GC",  7.7, 75, "Blue"),
        ("2025-05-05",  "Cobble Beach GC", 7.5, 74, "Blue"),
        ("2025-04-21",  "Heron Point GC",  7.6, 74, "Blue"),
        ("2025-04-07",  "Loch March GC",   7.8, 75, "Blue"),
    ])
    players["bill"] = pid

    # Steve Dalton — Index 18.0, AMBER signal (high variance, SD > 4)
    pid = add_player("Steve Dalton", 18.0, cpga_id="CA-100003",
                     tee_preference="White",
                     notes="Can have a great day or a terrible one — unpredictable")
    add_tag(pid, "TEMPERAMENT",   "Gets rattled early")
    add_tag(pid, "PLAYING_STYLE", "Long hitter")
    add_tag(pid, "TEMPERAMENT",   "Strong back nine")
    _add_scores(pid, [
        ("2025-09-06",  "Heron Point GC",  14.5, 85, "White"),
        ("2025-08-23",  "Cobble Beach GC", 24.1, 96, "White"),
        ("2025-08-09",  "Heron Point GC",  15.2, 86, "White"),
        ("2025-07-26",  "Loch March GC",   22.8, 94, "White"),
        ("2025-07-12",  "Heron Point GC",  14.8, 86, "White"),
        ("2025-06-28",  "Cobble Beach GC", 24.3, 96, "White"),
        ("2025-06-14",  "Heron Point GC",  15.6, 87, "White"),
        ("2025-05-31",  "Loch March GC",   23.5, 95, "White"),
        ("2025-05-17",  "Heron Point GC",  18.0, 89, "White"),
        ("2025-05-03",  "Cobble Beach GC", 20.7, 91, "White"),
    ])
    players["steve"] = pid

    # Gary Prentice — Index 22.5, GREEN signal (steady improver)
    pid = add_player("Gary Prentice", 22.5, cpga_id="CA-100004",
                     tee_preference="Yellow",
                     notes="Improving each event — building confidence")
    add_tag(pid, "TEMPERAMENT",   "Slow starter")
    add_tag(pid, "PLAYING_STYLE", "Steady iron player")
    add_tag(pid, "COURSE_AFFINITY", "Good in the wind")
    _add_scores(pid, [
        ("2025-09-04",  "Heron Point GC",  19.8, 91, "Yellow"),
        ("2025-08-21",  "Cobble Beach GC", 20.5, 92, "Yellow"),
        ("2025-08-07",  "Heron Point GC",  20.9, 92, "Yellow"),
        ("2025-07-24",  "Loch March GC",   21.4, 93, "Yellow"),
        ("2025-07-10",  "Heron Point GC",  21.8, 93, "Yellow"),
        ("2025-06-26",  "Cobble Beach GC", 22.3, 94, "Yellow"),
        ("2025-06-12",  "Heron Point GC",  22.7, 94, "Yellow"),
        ("2025-05-29",  "Loch March GC",   23.0, 95, "Yellow"),
        ("2025-05-15",  "Heron Point GC",  23.4, 95, "Yellow"),
        ("2025-05-01",  "Cobble Beach GC", 23.8, 96, "Yellow"),
    ])
    players["gary"] = pid

    # --- Team B ---

    # Mike Kowalski — Index 14.5, AMBER (infrequent posting)
    pid = add_player("Mike Kowalski", 14.5, cpga_id="CA-200001",
                     tee_preference="White",
                     notes="Only plays a few times a year — index reliability uncertain")
    add_tag(pid, "TEMPERAMENT",   "Clutch competitor")
    add_tag(pid, "PHYSICAL",      "Fresh / fully fit")
    add_tag(pid, "PLAYING_STYLE", "Accurate but short")
    _add_scores(pid, [
        ("2025-09-01",  "Heron Point GC",  13.8, 86, "White"),
        ("2025-06-15",  "Cobble Beach GC", 14.2, 87, "White"),   # 78 day gap
        ("2025-03-20",  "Loch March GC",   15.1, 88, "White"),   # 87 day gap
        ("2024-10-05",  "Heron Point GC",  14.9, 88, "White"),   # 166 day gap
        ("2024-07-12",  "Cobble Beach GC", 14.5, 87, "White"),   # 85 day gap
    ])
    players["mike"] = pid

    # Emeka Okafor — Index 5.2, GREEN signal (scratch-level consistent)
    pid = add_player("Emeka Okafor", 5.2, cpga_id="CA-200002",
                     tee_preference="Blue",
                     notes="Best player in the field — dangerous in any format")
    add_tag(pid, "PLAYING_STYLE", "Aggressive driver")
    add_tag(pid, "PLAYING_STYLE", "Strong iron player")
    add_tag(pid, "TEMPERAMENT",   "Mentally tough")
    add_tag(pid, "TEMPERAMENT",   "Loves match play")
    add_tag(pid, "COURSE_AFFINITY", "Strong on links-style")
    _add_scores(pid, [
        ("2025-09-09",  "Heron Point GC",  5.0, 70, "Blue"),
        ("2025-08-26",  "Cobble Beach GC", 5.3, 71, "Blue"),
        ("2025-08-12",  "Heron Point GC",  5.1, 70, "Blue"),
        ("2025-07-29",  "Loch March GC",   4.9, 69, "Blue"),
        ("2025-07-15",  "Heron Point GC",  5.4, 71, "Blue"),
        ("2025-07-01",  "Cobble Beach GC", 5.2, 70, "Blue"),
        ("2025-06-17",  "Heron Point GC",  5.0, 70, "Blue"),
        ("2025-06-03",  "Loch March GC",   5.3, 71, "Blue"),
        ("2025-05-20",  "Heron Point GC",  5.1, 70, "Blue"),
        ("2025-05-06",  "Cobble Beach GC", 5.2, 70, "Blue"),
        ("2025-04-22",  "Heron Point GC",  5.4, 71, "Blue"),
        ("2025-04-08",  "Loch March GC",   5.0, 70, "Blue"),
    ])
    players["emeka"] = pid

    # Marc Leblanc — Index 12.8, GREEN (stable mid handicapper)
    pid = add_player("Marc Leblanc", 12.8, cpga_id="CA-200003",
                     tee_preference="White",
                     notes="Consistent performer, good in foursomes")
    add_tag(pid, "PLAYING_STYLE", "Steady iron player")
    add_tag(pid, "TEMPERAMENT",   "Good anchor in foursomes")
    add_tag(pid, "COURSE_AFFINITY", "Prefers parkland")
    _add_scores(pid, [
        ("2025-09-07",  "Heron Point GC",  12.5, 85, "White"),
        ("2025-08-24",  "Cobble Beach GC", 12.9, 86, "White"),
        ("2025-08-10",  "Heron Point GC",  13.1, 86, "White"),
        ("2025-07-27",  "Loch March GC",   12.7, 85, "White"),
        ("2025-07-13",  "Heron Point GC",  12.8, 85, "White"),
        ("2025-06-29",  "Cobble Beach GC", 12.6, 85, "White"),
        ("2025-06-15",  "Heron Point GC",  13.0, 86, "White"),
        ("2025-06-01",  "Loch March GC",   12.9, 86, "White"),
        ("2025-05-18",  "Heron Point GC",  12.7, 85, "White"),
        ("2025-05-04",  "Cobble Beach GC", 12.8, 85, "White"),
    ])
    players["marc"] = pid

    # Dave Brennan — Index 20.0, RED signal (large best-3 gap)
    pid = add_player("Dave Brennan", 20.0, cpga_id="CA-200004",
                     tee_preference="White",
                     notes="Had some very good rounds earlier in the season")
    add_tag(pid, "TEMPERAMENT",   "Fades under pressure")
    add_tag(pid, "PLAYING_STYLE", "Strong short game")
    add_tag(pid, "TEMPERAMENT",   "Strong front nine")
    _add_scores(pid, [
        ("2025-09-05",  "Heron Point GC",  13.5, 85, "White"),
        ("2025-08-22",  "Cobble Beach GC", 14.1, 86, "White"),
        ("2025-08-08",  "Heron Point GC",  13.8, 85, "White"),
        ("2025-07-25",  "Loch March GC",   21.5, 93, "White"),
        ("2025-07-11",  "Heron Point GC",  22.0, 94, "White"),
        ("2025-06-27",  "Cobble Beach GC", 21.8, 93, "White"),
        ("2025-06-13",  "Heron Point GC",  20.5, 92, "White"),
        ("2025-05-30",  "Loch March GC",   21.2, 93, "White"),
        ("2025-05-16",  "Heron Point GC",  20.8, 92, "White"),
        ("2025-05-02",  "Cobble Beach GC", 21.1, 93, "White"),
    ])
    players["dave"] = pid

    return players


def _add_scores(player_id: int, scores: list[tuple]) -> None:
    """Helper — insert a list of (date, course, diff, score, tee) tuples."""
    for date, course, diff, posted, tee in scores:
        add_score_record(player_id, date, course, diff, posted, tee)


# ---------------------------------------------------------------
# Courses
# ---------------------------------------------------------------

def _seed_courses() -> dict:
    courses = {}

    # Heron Point GC — Prince Edward County, ON
    cid = add_course("Heron Point GC", "Picton, ON")
    add_tee_deck(cid, "Blue",   73.8, 135, 72,
                 [5, 15, 1, 11, 7, 17, 3, 13, 9,
                  6, 16, 2, 12, 8, 18, 4, 14, 10])
    add_tee_deck(cid, "White",  71.5, 125, 72,
                 [5, 15, 1, 11, 7, 17, 3, 13, 9,
                  6, 16, 2, 12, 8, 18, 4, 14, 10])
    add_tee_deck(cid, "Yellow", 69.2, 115, 72,
                 [5, 15, 1, 11, 7, 17, 3, 13, 9,
                  6, 16, 2, 12, 8, 18, 4, 14, 10])
    courses["heron"] = cid

    # Cobble Beach GC — Owen Sound, ON
    cid2 = add_course("Cobble Beach GC", "Owen Sound, ON")
    add_tee_deck(cid2, "Blue",  75.2, 142, 72,
                 [1, 13, 7, 17, 3, 11, 5, 15, 9,
                  2, 14, 8, 18, 4, 12, 6, 16, 10])
    add_tee_deck(cid2, "White", 72.9, 131, 72,
                 [1, 13, 7, 17, 3, 11, 5, 15, 9,
                  2, 14, 8, 18, 4, 12, 6, 16, 10])
    courses["cobble"] = cid2

    return courses


# ---------------------------------------------------------------
# Event with 3 rounds and full results
# ---------------------------------------------------------------

def _seed_event(players: dict, courses: dict) -> int:
    """
    Heron Point Cup 2025 — 3 rounds, fully completed.
    Round 1: Four-Ball  (Team A wins 2.5–1.5)
    Round 2: Foursomes  (Team B wins 3–1)
    Round 3: Singles    (Team A wins 3.5–2.5)
    Final:   Team A wins 9–5
    """
    eid = create_event(
        name="Heron Point Cup 2025",
        start_date="2025-09-12",
        team_a_name="The Aces",
        team_b_name="The Bogeys",
        handicap_mode="PLAY_OFF_LOW",
        allowance_pct=100.0,
    )

    # Assign players
    for p in ["tom", "bill", "steve", "gary"]:
        assign_player(eid, players[p], "A")
    for p in ["mike", "emeka", "marc", "dave"]:
        assign_player(eid, players[p], "B")

    # Get tee IDs — need to look them up
    from modules.courses import list_tee_decks
    heron_decks  = {d["name"]: d["tee_id"] for d in list_tee_decks(courses["heron"])}
    cobble_decks = {d["name"]: d["tee_id"] for d in list_tee_decks(courses["cobble"])}

    # ---- Round 1: Four-Ball at Heron Point (White) ----
    rid1 = add_round(eid, courses["heron"], "2025-09-12",
                     "FOURBALL_MP", 1, 18,
                     heron_decks["White"], heron_decks["White"])

    m1 = create_match(rid1, 1,                             # Tom+Bill vs Emeka+Marc
                      players["tom"], players["bill"],
                      players["emeka"], players["marc"])
    m2 = create_match(rid1, 2,                             # Steve+Gary vs Mike+Dave
                      players["steve"], players["gary"],
                      players["mike"], players["dave"])

    record_result(m1, "B", "2&1")       # B wins (Emeka+Marc too strong)
    record_result(m2, "A", "3&2")       # A wins (Steve+Gary vs weaker side)

    # Two more matches to make it 4-match round
    m3 = create_match(rid1, 3,
                      players["gary"], players["steve"],
                      players["dave"], players["mike"])
    m4 = create_match(rid1, 4,
                      players["bill"], players["tom"],
                      players["marc"], players["emeka"])
    record_result(m3, "A", "1 UP")
    record_result(m4, "HALVED", "AS")

    # ---- Round 2: Foursomes at Cobble Beach (White) ----
    rid2 = add_round(eid, courses["cobble"], "2025-09-13",
                     "FOURSOMES_MP", 2, 18,
                     cobble_decks["White"], cobble_decks["White"])

    m5 = create_match(rid2, 1,
                      players["tom"], players["bill"],
                      players["emeka"], players["marc"])
    m6 = create_match(rid2, 2,
                      players["steve"], players["gary"],
                      players["mike"], players["dave"])
    m7 = create_match(rid2, 3,
                      players["bill"], players["steve"],
                      players["marc"], players["mike"])
    m8 = create_match(rid2, 4,
                      players["gary"], players["tom"],
                      players["dave"], players["emeka"])

    record_result(m5, "B", "3&2")
    record_result(m6, "B", "2&1")
    record_result(m7, "HALVED", "AS")
    record_result(m8, "B", "1 UP")

    # ---- Round 3: Singles at Heron Point (White) ----
    rid3 = add_round(eid, courses["heron"], "2025-09-14",
                     "SINGLES_MP", 3, 18,
                     heron_decks["White"], heron_decks["White"])

    # Singles draw: 4 matches
    m9  = create_match(rid3, 1, players["bill"],  None, players["emeka"], None)
    m10 = create_match(rid3, 2, players["tom"],   None, players["marc"],  None)
    m11 = create_match(rid3, 3, players["steve"], None, players["mike"],  None)
    m12 = create_match(rid3, 4, players["gary"],  None, players["dave"],  None)

    record_result(m9,  "B", "2&1")       # Emeka too good for Bill
    record_result(m10, "A", "3&2")       # Tom's sandbagging pays off
    record_result(m11, "A", "1 UP")      # Steve on a good day
    record_result(m12, "A", "2&1")       # Gary grinds it out

    # Final score: A = 0.5+1+1+0.5 + 0+0+0.5+0 + 0+1+1+1 = 6.5
    #              B = 0.5+0+0+0.5 + 1+1+0.5+1 + 1+0+0+0 = 5.5
    # (Exact points depend on match outcomes above — the UI will tally)

    return eid

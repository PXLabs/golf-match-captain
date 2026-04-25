"""
roster.py — Player CRUD, tag management, and score differential entry.
Golf Match Captain | Phase 1A
"""

from __future__ import annotations
import sqlite3
from database.db import fetchall, fetchone, execute, executemany

# ---------------------------------------------------------------
# Tag categories (Section 5.3 of Context Document)
# ---------------------------------------------------------------

TAG_CATEGORIES: dict[str, list[str]] = {
    "PLAYING_STYLE": [
        "Aggressive driver",
        "Steady iron player",
        "Strong short game",
        "Weak putter",
        "Long hitter",
        "Accurate but short",
        "Strong chipper",
        "Unreliable off the tee",
    ],
    "TEMPERAMENT": [
        "Loves match play",
        "Fades under pressure",
        "Clutch competitor",
        "Gets rattled early",
        "Strong front nine",
        "Strong back nine",
        "Slow starter",
        "Mentally tough",
    ],
    "COURSE_AFFINITY": [
        "Strong on links-style",
        "Dislikes tight tree-lined courses",
        "Good in the wind",
        "Prefers parkland",
        "Struggles on firm fast greens",
        "Good in wet conditions",
    ],
    "PHYSICAL": [
        "Fresh / fully fit",
        "Knee issue",
        "Bad back — avoid hilly courses",
        "Shoulder issue",
        "Managing fatigue over multi-day event",
    ],
    "CHEMISTRY": [
        "Strong pairing with [name]",
        "Rivalry with [opponent]",
        "Do not pair with [name]",
        "Good anchor in foursomes",
        "Works best at top of order",
        "Works best at bottom of order",
    ],
}

TAG_CATEGORY_LABELS: dict[str, str] = {
    "PLAYING_STYLE": "Playing Style",
    "TEMPERAMENT": "Match Play Temperament",
    "COURSE_AFFINITY": "Course Affinity",
    "PHYSICAL": "Physical Condition",
    "CHEMISTRY": "Chemistry Notes",
}

# ---------------------------------------------------------------
# Player CRUD
# ---------------------------------------------------------------

def add_player(
    name: str,
    current_index: float,
    cpga_id: str = "",
    tee_preference: str = "",
    notes: str = "",
) -> int:
    """Insert a new player. Returns the new player_id."""
    sql = """
        INSERT INTO player (name, cpga_id, current_index, tee_preference, notes)
        VALUES (?, ?, ?, ?, ?)
    """
    return execute(sql, (name.strip(), cpga_id.strip(), current_index,
                         tee_preference.strip(), notes.strip()))


def get_player(player_id: int) -> sqlite3.Row | None:
    """Return a single player row by ID."""
    return fetchone("SELECT * FROM player WHERE player_id = ?", (player_id,))


def list_players() -> list[sqlite3.Row]:
    """Return all players ordered by name."""
    return fetchall("SELECT * FROM player ORDER BY name ASC")


def update_player(
    player_id: int,
    name: str,
    current_index: float,
    cpga_id: str = "",
    tee_preference: str = "",
    notes: str = "",
) -> None:
    """Update an existing player record."""
    sql = """
        UPDATE player
        SET name = ?, cpga_id = ?, current_index = ?,
            tee_preference = ?, notes = ?,
            updated_at = datetime('now')
        WHERE player_id = ?
    """
    execute(sql, (name.strip(), cpga_id.strip(), current_index,
                  tee_preference.strip(), notes.strip(), player_id))


def delete_player(player_id: int) -> None:
    """
    Delete a player and all associated records (cascade).
    Use with caution — also removes score records and tags.
    """
    execute("DELETE FROM player WHERE player_id = ?", (player_id,))


# ---------------------------------------------------------------
# Player Tags
# ---------------------------------------------------------------

def get_tags_for_player(player_id: int) -> list[sqlite3.Row]:
    """Return all tags for a player, ordered by type."""
    return fetchall(
        "SELECT * FROM player_tag WHERE player_id = ? ORDER BY tag_type, tag_value",
        (player_id,),
    )


def add_tag(player_id: int, tag_type: str, tag_value: str) -> int:
    """Add a tag to a player. Returns new tag_id."""
    sql = """
        INSERT INTO player_tag (player_id, tag_type, tag_value)
        VALUES (?, ?, ?)
    """
    return execute(sql, (player_id, tag_type.strip(), tag_value.strip()))


def remove_tag(tag_id: int) -> None:
    """Remove a specific tag by its ID."""
    execute("DELETE FROM player_tag WHERE tag_id = ?", (tag_id,))


def get_tags_grouped(player_id: int) -> dict[str, list[dict]]:
    """
    Return a player's tags grouped by category.
    Useful for display and LLM context building.
    """
    rows = get_tags_for_player(player_id)
    grouped: dict[str, list[dict]] = {k: [] for k in TAG_CATEGORIES}
    for row in rows:
        cat = row["tag_type"]
        if cat in grouped:
            grouped[cat].append({"tag_id": row["tag_id"], "value": row["tag_value"]})
    return grouped


# ---------------------------------------------------------------
# Score Differentials
# ---------------------------------------------------------------

MAX_SCORE_RECORDS = 20


def add_score_record(
    player_id: int,
    date: str,
    course: str,
    differential: float,
    posted_score: int | None = None,
    tee_deck: str = "",
) -> int:
    """
    Add a score differential record for a player.
    Enforces the 20-record cap by removing the oldest if needed.
    Returns the new record_id.
    """
    _enforce_score_cap(player_id)
    sql = """
        INSERT INTO score_record
            (player_id, date, course, tee_deck, posted_score, differential)
        VALUES (?, ?, ?, ?, ?, ?)
    """
    return execute(sql, (player_id, date, course.strip(), tee_deck.strip(),
                         posted_score, differential))


def _enforce_score_cap(player_id: int) -> None:
    """Remove oldest records if player already has MAX_SCORE_RECORDS."""
    count_row = fetchone(
        "SELECT COUNT(*) as cnt FROM score_record WHERE player_id = ?", (player_id,)
    )
    if count_row and count_row["cnt"] >= MAX_SCORE_RECORDS:
        # Delete oldest record(s) to stay within cap
        excess = count_row["cnt"] - MAX_SCORE_RECORDS + 1
        execute(
            """
            DELETE FROM score_record
            WHERE record_id IN (
                SELECT record_id FROM score_record
                WHERE player_id = ?
                ORDER BY date ASC, record_id ASC
                LIMIT ?
            )
            """,
            (player_id, excess),
        )


def get_score_records(player_id: int) -> list[sqlite3.Row]:
    """Return all score records for a player, newest first."""
    return fetchall(
        """
        SELECT * FROM score_record
        WHERE player_id = ?
        ORDER BY date DESC, record_id DESC
        """,
        (player_id,),
    )


def delete_score_record(record_id: int) -> None:
    """Remove a single score record."""
    execute("DELETE FROM score_record WHERE record_id = ?", (record_id,))


def get_differentials(player_id: int) -> list[float]:
    """
    Return a list of differentials (newest first) for use in
    handicap trend and intelligence calculations.
    """
    rows = get_score_records(player_id)
    return [row["differential"] for row in rows]

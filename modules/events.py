"""
events.py — Event and Round management.
Golf Match Captain | Phase 1C

Handles:
  - Event CRUD (name, dates, team names, handicap mode, allowance %)
  - Player assignment to teams within an event
  - Round CRUD (course, tee decks, format, holes, date)
  - Summary helpers used by the dashboard and match analysis
"""

from __future__ import annotations
import sqlite3
from database.db import fetchall, fetchone, execute

# ---------------------------------------------------------------
# Handicap mode options (Section 3.2)
# ---------------------------------------------------------------

HANDICAP_MODES: dict[str, str] = {
    "FULL_INDEX":    "Full Index — Course Handicap used as-is",
    "PERCENTAGE":    "Percentage Allowance — Event % applied to Course HC",
    "PLAY_OFF_LOW":  "Play Off the Low — Lowest HC plays scratch",
}

EVENT_STATUSES = ["ACTIVE", "COMPLETED", "ARCHIVED"]

# ---------------------------------------------------------------
# Event CRUD
# ---------------------------------------------------------------

def create_event(
    name: str,
    start_date: str,
    team_a_name: str = "Team A",
    team_b_name: str = "Team B",
    handicap_mode: str = "FULL_INDEX",
    allowance_pct: float = 100.0,
) -> int:
    """Create a new event. Returns the new event_id."""
    return execute(
        """
        INSERT INTO event
            (name, start_date, team_a_name, team_b_name,
             handicap_mode, allowance_pct, status)
        VALUES (?, ?, ?, ?, ?, ?, 'ACTIVE')
        """,
        (name.strip(), start_date, team_a_name.strip(),
         team_b_name.strip(), handicap_mode, allowance_pct),
    )


def get_event(event_id: int) -> sqlite3.Row | None:
    return fetchone("SELECT * FROM event WHERE event_id = ?", (event_id,))


def list_events(status: str | None = None) -> list[sqlite3.Row]:
    """Return events. Optionally filter by status (ACTIVE / COMPLETED / ARCHIVED)."""
    if status:
        return fetchall(
            "SELECT * FROM event WHERE status = ? ORDER BY start_date DESC",
            (status,),
        )
    return fetchall("SELECT * FROM event ORDER BY start_date DESC")


def update_event(
    event_id: int,
    name: str,
    start_date: str,
    team_a_name: str,
    team_b_name: str,
    handicap_mode: str,
    allowance_pct: float,
    status: str,
) -> None:
    execute(
        """
        UPDATE event
        SET name = ?, start_date = ?, team_a_name = ?, team_b_name = ?,
            handicap_mode = ?, allowance_pct = ?, status = ?
        WHERE event_id = ?
        """,
        (name.strip(), start_date, team_a_name.strip(), team_b_name.strip(),
         handicap_mode, allowance_pct, status, event_id),
    )


def delete_event(event_id: int) -> None:
    """Delete event and all rounds / matches within it (cascade)."""
    execute("DELETE FROM event WHERE event_id = ?", (event_id,))


# ---------------------------------------------------------------
# Player ↔ Event assignment
# ---------------------------------------------------------------

def assign_player(event_id: int, player_id: int, team: str) -> None:
    """
    Assign a player to a team ('A' or 'B') in an event.
    Upserts — if the player is already in the event, updates their team.
    """
    team = team.upper()
    if team not in ("A", "B"):
        raise ValueError("Team must be 'A' or 'B'.")
    execute(
        """
        INSERT INTO event_player (event_id, player_id, team)
        VALUES (?, ?, ?)
        ON CONFLICT(event_id, player_id) DO UPDATE SET team = excluded.team
        """,
        (event_id, player_id, team),
    )


def remove_player_from_event(event_id: int, player_id: int) -> None:
    execute(
        "DELETE FROM event_player WHERE event_id = ? AND player_id = ?",
        (event_id, player_id),
    )


def set_player_role(event_id: int, player_id: int, role: str) -> None:
    """Update a player's role (e.g. 'Captain', 'Alternate Captain', 'Player')."""
    execute(
        "UPDATE event_player SET role = ? WHERE event_id = ? AND player_id = ?",
        (role, event_id, player_id)
    )


def get_event_players(event_id: int) -> list[sqlite3.Row]:
    """
    Return all players assigned to an event, joined with player details.
    Each row includes: player_id, name, current_index, tee_preference,
                       cpga_id, team.
    """
    return fetchall(
        """
        SELECT p.player_id, p.name, p.current_index, p.tee_preference,
               p.cpga_id, ep.team, ep.role
        FROM event_player ep
        JOIN player p ON p.player_id = ep.player_id
        WHERE ep.event_id = ?
        ORDER BY ep.team, p.name
        """,
        (event_id,),
    )


def get_event_players_by_team(event_id: int) -> dict[str, list[sqlite3.Row]]:
    """
    Return a dict with keys 'A' and 'B', each containing their player rows.
    """
    rows = get_event_players(event_id)
    return {
        "A": [r for r in rows if r["team"] == "A"],
        "B": [r for r in rows if r["team"] == "B"],
    }


def get_unassigned_players(event_id: int) -> list[sqlite3.Row]:
    """Return players in the global roster not yet assigned to this event."""
    return fetchall(
        """
        SELECT * FROM player
        WHERE player_id NOT IN (
            SELECT player_id FROM event_player WHERE event_id = ?
        )
        ORDER BY name ASC
        """,
        (event_id,),
    )


# ---------------------------------------------------------------
# Round CRUD
# ---------------------------------------------------------------

def add_round(
    event_id: int,
    course_id: int,
    date: str,
    format_code: str,
    round_number: int,
    holes: int = 18,
    tee_id_a: int | None = None,
    tee_id_b: int | None = None,
) -> int:
    """Add a round to an event. Returns the new round_id."""
    return execute(
        """
        INSERT INTO round
            (event_id, course_id, date, format_code, round_number,
             holes, tee_id_a, tee_id_b)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (event_id, course_id, date, format_code, round_number,
         holes, tee_id_a, tee_id_b),
    )


def get_round(round_id: int) -> sqlite3.Row | None:
    return fetchone("SELECT * FROM round WHERE round_id = ?", (round_id,))


def list_rounds(event_id: int) -> list[sqlite3.Row]:
    """Return all rounds for an event in day order."""
    return fetchall(
        """
        SELECT r.*, c.name as course_name
        FROM round r
        JOIN course c ON c.course_id = r.course_id
        WHERE r.event_id = ?
        ORDER BY r.round_number ASC, r.date ASC
        """,
        (event_id,),
    )


def update_round(
    round_id: int,
    course_id: int,
    date: str,
    format_code: str,
    round_number: int,
    holes: int,
    tee_id_a: int | None,
    tee_id_b: int | None,
) -> None:
    execute(
        """
        UPDATE round
        SET course_id = ?, date = ?, format_code = ?, round_number = ?,
            holes = ?, tee_id_a = ?, tee_id_b = ?
        WHERE round_id = ?
        """,
        (course_id, date, format_code, round_number,
         holes, tee_id_a, tee_id_b, round_id),
    )


def delete_round(round_id: int) -> None:
    execute("DELETE FROM round WHERE round_id = ?", (round_id,))


# ---------------------------------------------------------------
# Summary helpers
# ---------------------------------------------------------------

def get_event_summary(event_id: int) -> dict:
    """
    Return a lightweight summary dict used by the Dashboard
    and the LLM advisor context builder.
    """
    event = get_event(event_id)
    if not event:
        return {}

    rounds      = list_rounds(event_id)
    players     = get_event_players(event_id)
    team_a      = [p for p in players if p["team"] == "A"]
    team_b      = [p for p in players if p["team"] == "B"]

    completed_rounds = fetchall(
        """
        SELECT r.round_id FROM round r
        WHERE r.event_id = ?
          AND EXISTS (
              SELECT 1 FROM match m
              WHERE m.round_id = r.round_id AND m.result IS NOT NULL
          )
        """,
        (event_id,),
    )

    return {
        "event_id":        event["event_id"],
        "name":            event["name"],
        "start_date":      event["start_date"],
        "status":          event["status"],
        "team_a_name":     event["team_a_name"],
        "team_b_name":     event["team_b_name"],
        "handicap_mode":   event["handicap_mode"],
        "allowance_pct":   event["allowance_pct"],
        "total_rounds":    len(rounds),
        "completed_rounds": len(completed_rounds),
        "team_a_count":    len(team_a),
        "team_b_count":    len(team_b),
        "rounds":          [dict(r) for r in rounds],
    }

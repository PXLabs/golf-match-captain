"""
courses.py — Course and Tee Deck management.
Golf Match Captain | Phase 1C

Handles:
  - Course CRUD
  - Tee deck CRUD (rating, slope, par, 18-hole stroke index)
  - Helpers for retrieving tee deck data in handicap-ready format
"""

from __future__ import annotations
import json
import sqlite3
from database.db import fetchall, fetchone, execute

# ---------------------------------------------------------------
# Course CRUD
# ---------------------------------------------------------------

def add_course(name: str, location: str = "") -> int:
    """Insert a new course. Returns the new course_id."""
    return execute(
        "INSERT INTO course (name, location) VALUES (?, ?)",
        (name.strip(), location.strip()),
    )


def get_course(course_id: int) -> sqlite3.Row | None:
    return fetchone("SELECT * FROM course WHERE course_id = ?", (course_id,))


def list_courses() -> list[sqlite3.Row]:
    return fetchall("SELECT * FROM course ORDER BY name ASC")


def update_course(course_id: int, name: str, location: str = "") -> None:
    execute(
        "UPDATE course SET name = ?, location = ? WHERE course_id = ?",
        (name.strip(), location.strip(), course_id),
    )


def delete_course(course_id: int) -> None:
    """Delete a course and all its tee decks (cascade)."""
    execute("DELETE FROM course WHERE course_id = ?", (course_id,))


# ---------------------------------------------------------------
# Tee Deck CRUD
# ---------------------------------------------------------------

def add_tee_deck(
    course_id: int,
    name: str,
    rating: float,
    slope: int,
    par: int,
    stroke_index: list[int],
    total_yards: int | None = None,
    notes: str | None = None,
) -> int:
    """
    Insert a tee deck for a course.
    stroke_index: list of 18 integers representing SI per hole (SI 1 = hardest).
    Returns the new tee_id.
    """
    _validate_stroke_index(stroke_index)
    return execute(
        """
        INSERT INTO tee_deck (course_id, name, rating, slope, par, stroke_index, total_yards, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (course_id, name.strip(), rating, slope, par, json.dumps(stroke_index), total_yards, notes),
    )


def get_tee_deck(tee_id: int) -> dict | None:
    """Return a tee deck with stroke_index parsed from JSON."""
    row = fetchone("SELECT * FROM tee_deck WHERE tee_id = ?", (tee_id,))
    return _parse_tee_deck(row) if row else None


def list_tee_decks(course_id: int) -> list[dict]:
    """Return all tee decks for a course, with stroke_index parsed."""
    rows = fetchall(
        "SELECT * FROM tee_deck WHERE course_id = ? ORDER BY rating DESC",
        (course_id,),
    )
    return [_parse_tee_deck(r) for r in rows]


def update_tee_deck(
    tee_id: int,
    name: str,
    rating: float,
    slope: int,
    par: int,
    stroke_index: list[int],
    total_yards: int | None = None,
    notes: str | None = None,
) -> None:
    _validate_stroke_index(stroke_index)
    execute(
        """
        UPDATE tee_deck
        SET name = ?, rating = ?, slope = ?, par = ?, stroke_index = ?, total_yards = ?, notes = ?
        WHERE tee_id = ?
        """,
        (name.strip(), rating, slope, par, json.dumps(stroke_index), total_yards, notes, tee_id),
    )


def delete_tee_deck(tee_id: int) -> None:
    execute("DELETE FROM tee_deck WHERE tee_id = ?", (tee_id,))


# ---------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------

def get_tee_deck_for_handicap(tee_id: int) -> dict | None:
    """
    Return a tee deck in the format expected by handicap.py:
        {"rating": float, "slope": int, "par": int, "stroke_index": list[int]}
    Returns None if tee_id not found.
    """
    deck = get_tee_deck(tee_id)
    if not deck:
        return None
    return {
        "name":         deck["name"],
        "rating":       deck["rating"],
        "slope":        deck["slope"],
        "par":          deck["par"],
        "stroke_index": deck["stroke_index"],
        "total_yards":  deck.get("total_yards"),
        "notes":        deck.get("notes"),
    }


def _parse_tee_deck(row: sqlite3.Row) -> dict:
    """Convert a tee_deck Row to a plain dict with stroke_index parsed."""
    d = dict(row)
    try:
        d["stroke_index"] = json.loads(d.get("stroke_index") or "[]")
    except (json.JSONDecodeError, TypeError):
        d["stroke_index"] = []
    return d


def _validate_stroke_index(si: list[int]) -> None:
    """
    Stroke index must be a list of 18 unique integers covering 1–18.
    Raises ValueError with a clear message on any violation.
    """
    if len(si) != 18:
        raise ValueError(f"Stroke index must contain exactly 18 values, got {len(si)}.")
    if sorted(si) != list(range(1, 19)):
        raise ValueError(
            "Stroke index must contain each integer from 1 to 18 exactly once."
        )

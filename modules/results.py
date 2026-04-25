"""
results.py — Match Result Entry and Score Tracking
Golf Match Captain | Phase 1E

Handles:
  - Creating and managing match pairings for a round
  - Recording match results (win / loss / halved)
  - Computing running team scores across all completed rounds
  - Producing a results summary for the LLM advisor context
"""

from __future__ import annotations
import sqlite3
from database.db import fetchall, fetchone, execute

# ---------------------------------------------------------------
# Result constants
# ---------------------------------------------------------------

RESULT_OPTIONS: dict[str, str] = {
    "A":      "Team A wins",
    "B":      "Team B wins",
    "HALVED": "Halved",
}

# Points awarded per result (Ryder Cup-style)
POINTS: dict[str, dict[str, float]] = {
    "A":      {"A": 1.0, "B": 0.0},
    "B":      {"A": 0.0, "B": 1.0},
    "HALVED": {"A": 0.5, "B": 0.5},
}


# ---------------------------------------------------------------
# Match (pairing) management
# ---------------------------------------------------------------

def create_match(
    round_id: int,
    match_order: int,
    team_a_player1_id: int | None = None,
    team_a_player2_id: int | None = None,
    team_b_player1_id: int | None = None,
    team_b_player2_id: int | None = None,
    notes: str = "",
) -> int:
    """
    Create a match pairing within a round.
    Singles: provide only player1 for each team (player2 = None).
    Pairs:   provide both player1 and player2 for each team.
    Returns the new match_id.
    """
    return execute(
        """
        INSERT INTO match
            (round_id, match_order,
             team_a_player1_id, team_a_player2_id,
             team_b_player1_id, team_b_player2_id,
             notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (round_id, match_order,
         team_a_player1_id, team_a_player2_id,
         team_b_player1_id, team_b_player2_id,
         notes.strip()),
    )


def get_match(match_id: int) -> sqlite3.Row | None:
    return fetchone("SELECT * FROM match WHERE match_id = ?", (match_id,))


def list_matches(round_id: int) -> list[sqlite3.Row]:
    """Return all matches for a round in draw order."""
    return fetchall(
        "SELECT * FROM match WHERE round_id = ? ORDER BY match_order ASC",
        (round_id,),
    )


def update_match_players(
    match_id: int,
    team_a_player1_id: int | None,
    team_a_player2_id: int | None,
    team_b_player1_id: int | None,
    team_b_player2_id: int | None,
    notes: str = "",
) -> None:
    execute(
        """
        UPDATE match
        SET team_a_player1_id = ?,
            team_a_player2_id = ?,
            team_b_player1_id = ?,
            team_b_player2_id = ?,
            notes = ?
        WHERE match_id = ?
        """,
        (team_a_player1_id, team_a_player2_id,
         team_b_player1_id, team_b_player2_id,
         notes.strip(), match_id),
    )


def record_result(
    match_id: int,
    result: str,
    result_detail: str = "",
) -> None:
    """
    Record the outcome of a match.
    result:        'A' | 'B' | 'HALVED'
    result_detail: e.g. '3&2', '1 UP', 'AS' (all square)
    """
    if result not in RESULT_OPTIONS:
        raise ValueError(f"Invalid result '{result}'. Must be one of: {list(RESULT_OPTIONS)}")
    execute(
        """
        UPDATE match
        SET result = ?, result_detail = ?
        WHERE match_id = ?
        """,
        (result, result_detail.strip(), match_id),
    )


def clear_result(match_id: int) -> None:
    """Remove a previously entered result (mark as pending)."""
    execute(
        "UPDATE match SET result = NULL, result_detail = '' WHERE match_id = ?",
        (match_id,),
    )


def delete_match(match_id: int) -> None:
    execute("DELETE FROM match WHERE match_id = ?", (match_id,))


# ---------------------------------------------------------------
# Score computation
# ---------------------------------------------------------------

def get_round_score(round_id: int) -> dict:
    """
    Compute the points tally for a single completed round.

    Returns:
        {
            round_id, points_a, points_b,
            matches_played, matches_pending,
            match_results: [ {match_id, result, detail, pts_a, pts_b} ]
        }
    """
    matches = list_matches(round_id)
    points_a = 0.0
    points_b = 0.0
    played   = 0
    pending  = 0
    details  = []

    for m in matches:
        result = m["result"]
        if result and result in POINTS:
            pts = POINTS[result]
            points_a += pts["A"]
            points_b += pts["B"]
            played   += 1
        else:
            pending  += 1
            pts = {"A": 0.0, "B": 0.0}

        details.append({
            "match_id":   m["match_id"],
            "match_order": m["match_order"],
            "result":     result,
            "detail":     m["result_detail"] or "",
            "pts_a":      pts["A"],
            "pts_b":      pts["B"],
        })

    return {
        "round_id":        round_id,
        "points_a":        points_a,
        "points_b":        points_b,
        "matches_played":  played,
        "matches_pending": pending,
        "match_results":   details,
    }


def get_event_score(event_id: int) -> dict:
    """
    Compute the cumulative team scores across all rounds in an event.

    Returns:
        {
            event_id,
            total_points_a, total_points_b,
            rounds_completed, rounds_pending,
            per_round: [ {round_id, round_number, date, format_code,
                           points_a, points_b, matches_played, matches_pending} ]
        }
    """
    from modules.events import list_rounds
    rounds = list_rounds(event_id)

    total_a   = 0.0
    total_b   = 0.0
    completed = 0
    per_round = []

    for rnd in rounds:
        rs = get_round_score(rnd["round_id"])
        total_a += rs["points_a"]
        total_b += rs["points_b"]
        if rs["matches_played"] > 0 and rs["matches_pending"] == 0:
            completed += 1

        per_round.append({
            "round_id":        rnd["round_id"],
            "round_number":    rnd["round_number"],
            "date":            rnd["date"],
            "format_code":     rnd["format_code"],
            "course_name":     dict(rnd).get("course_name", ""),
            "points_a":        rs["points_a"],
            "points_b":        rs["points_b"],
            "matches_played":  rs["matches_played"],
            "matches_pending": rs["matches_pending"],
        })

    return {
        "event_id":         event_id,
        "total_points_a":   total_a,
        "total_points_b":   total_b,
        "rounds_completed": completed,
        "rounds_pending":   len(rounds) - completed,
        "per_round":        per_round,
    }


# ---------------------------------------------------------------
# Player performance tracking
# ---------------------------------------------------------------

def get_player_results(event_id: int) -> list[dict]:
    """
    Return per-player win/loss/halved counts for an event.
    Used to identify form players and LLM context ("Steve is 3-0").
    """
    from modules.events import list_rounds

    rounds = list_rounds(event_id)
    player_stats: dict[int, dict] = {}

    def _ensure(pid):
        if pid not in player_stats:
            player_stats[pid] = {"player_id": pid, "W": 0, "L": 0, "H": 0, "pts": 0.0}

    for rnd in rounds:
        matches = list_matches(rnd["round_id"])
        for m in matches:
            if not m["result"]:
                continue
            result = m["result"]
            # Team A players
            for pid_field in ("team_a_player1_id", "team_a_player2_id"):
                pid = m[pid_field]
                if pid:
                    _ensure(pid)
                    if result == "A":
                        player_stats[pid]["W"]   += 1
                        player_stats[pid]["pts"] += 1.0
                    elif result == "B":
                        player_stats[pid]["L"]   += 1
                    elif result == "HALVED":
                        player_stats[pid]["H"]   += 1
                        player_stats[pid]["pts"] += 0.5
            # Team B players
            for pid_field in ("team_b_player1_id", "team_b_player2_id"):
                pid = m[pid_field]
                if pid:
                    _ensure(pid)
                    if result == "B":
                        player_stats[pid]["W"]   += 1
                        player_stats[pid]["pts"] += 1.0
                    elif result == "A":
                        player_stats[pid]["L"]   += 1
                    elif result == "HALVED":
                        player_stats[pid]["H"]   += 1
                        player_stats[pid]["pts"] += 0.5

    return list(player_stats.values())


# ---------------------------------------------------------------
# Rich match detail — with player names resolved
# ---------------------------------------------------------------

def get_matches_with_players(round_id: int) -> list[dict]:
    """
    Return matches enriched with player names — avoids N+1 queries.
    Each dict:
        match_id, match_order, result, result_detail, notes,
        a1_id, a1_name, a2_id, a2_name,
        b1_id, b1_name, b2_id, b2_name,
        pts_a, pts_b
    """
    rows = fetchall(
        """
        SELECT
            m.match_id, m.match_order, m.result, m.result_detail, m.notes,
            m.team_a_player1_id AS a1_id,  pa1.name AS a1_name,
            m.team_a_player2_id AS a2_id,  pa2.name AS a2_name,
            m.team_b_player1_id AS b1_id,  pb1.name AS b1_name,
            m.team_b_player2_id AS b2_id,  pb2.name AS b2_name
        FROM match m
        LEFT JOIN player pa1 ON pa1.player_id = m.team_a_player1_id
        LEFT JOIN player pa2 ON pa2.player_id = m.team_a_player2_id
        LEFT JOIN player pb1 ON pb1.player_id = m.team_b_player1_id
        LEFT JOIN player pb2 ON pb2.player_id = m.team_b_player2_id
        WHERE m.round_id = ?
        ORDER BY m.match_order ASC
        """,
        (round_id,),
    )

    result_list = []
    for row in rows:
        r      = dict(row)
        result = r.get("result")
        pts    = POINTS.get(result, {"A": 0.0, "B": 0.0}) if result else {"A": 0.0, "B": 0.0}
        r["pts_a"] = pts["A"]
        r["pts_b"] = pts["B"]
        result_list.append(r)

    return result_list


# ---------------------------------------------------------------
# LLM context formatter
# ---------------------------------------------------------------

def format_results_for_llm(event_id: int, team_a_name: str, team_b_name: str) -> str:
    """
    Produce a compact results summary for the LLM advisor context packet.
    Includes overall score, per-round breakdown, and player form.
    """
    from modules.events import list_rounds, get_event_players
    from modules.roster import get_player

    score    = get_event_score(event_id)
    players  = {p["player_id"]: p["name"] for p in get_event_players(event_id)}
    p_stats  = get_player_results(event_id)

    lines = [
        "--- EVENT SCORE ---",
        f"{team_a_name}: {score['total_points_a']:.1f} pts",
        f"{team_b_name}: {score['total_points_b']:.1f} pts",
        "",
        "--- ROUND-BY-ROUND ---",
    ]

    for rnd in score["per_round"]:
        status = (
            f"{rnd['points_a']:.1f}–{rnd['points_b']:.1f}"
            if rnd["matches_played"] > 0
            else "Not yet played"
        )
        lines.append(
            f"  Round {rnd['round_number']} ({rnd['date']} | {rnd['format_code']}): {status}"
            + (f" [{rnd['matches_pending']} pending]" if rnd["matches_pending"] else "")
        )

    if p_stats:
        lines += ["", "--- PLAYER FORM ---"]
        sorted_stats = sorted(p_stats, key=lambda x: -x["pts"])
        for s in sorted_stats:
            name  = players.get(s["player_id"], f"Player {s['player_id']}")
            played = s["W"] + s["L"] + s["H"]
            if played > 0:
                lines.append(
                    f"  {name}: {s['W']}W / {s['L']}L / {s['H']}H  ({s['pts']:.1f} pts)"
                )

    return "\n".join(lines)

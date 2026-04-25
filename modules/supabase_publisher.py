"""
supabase_publisher.py — Supabase Integration for Golf Match Captain
Golf Match Captain | Verma Cup 2026

Handles the two-way data flow between GMC SQLite and Supabase:

  PUBLISH (GMC → Supabase):
    - Writes match pairings (player UUIDs, handicap strokes) to Supabase
    - Transitions round status: DRAFT → LOCKED
    - Triggers scoreboard visibility in the weather app

  SYNC (Supabase → GMC):
    - Pulls COMPLETED match results from Supabase into GMC SQLite
    - Closes the loop: scoring app → Supabase → GMC → AI Advisor

Architecture decisions (locked — see CONTEXT.md Section 3):
  - GMC SQLite is source of record for captain-private data
  - Supabase is source of record for published match data
  - Captain controls publish/sync explicitly via buttons
  - Service role key used server-side only — never exposed to browser
  - Credentials stored in Streamlit secrets only — never in code or repo

Dependencies:
  - supabase>=2.0.0  (add to requirements.txt)
  - streamlit (for st.secrets access)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import streamlit as st

from database.db import fetchall, fetchone
from modules.handicap import (
    playing_handicap_for_format,
    apply_handicap_mode,
    strokes_received,
)


# ──────────────────────────────────────────────────────────────
# Supabase client
# ──────────────────────────────────────────────────────────────

def _get_client():
    """
    Return an authenticated Supabase client using the service role key.
    Uses st.secrets — safe for Streamlit Cloud server-side execution.
    Returns None if credentials are not configured.
    """
    try:
        from supabase import create_client
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_SERVICE_KEY"]
        return create_client(url, key)
    except Exception:
        return None


def is_configured() -> bool:
    """True if SUPABASE_URL and SUPABASE_SERVICE_KEY are in Streamlit secrets."""
    try:
        _ = st.secrets["SUPABASE_URL"]
        _ = st.secrets["SUPABASE_SERVICE_KEY"]
        return True
    except Exception:
        return False


# ──────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────

def _player_uuid_map(client) -> dict[str, str]:
    """Return {player_name: supabase_uuid} for all players in Supabase."""
    res = client.table("players").select("id, name").execute()
    return {row["name"]: row["id"] for row in (res.data or [])}


def _round_uuid(client, round_number: int) -> str | None:
    """Return the Supabase UUID for a round by its round_number, or None."""
    res = (
        client.table("rounds")
        .select("id, status")
        .eq("round_number", round_number)
        .execute()
    )
    if res.data:
        return res.data[0]["id"]
    return None


def _compute_adjusted_handicaps(
    player_indices: list[float],
    tee_rating: float,
    tee_slope: int,
    tee_par: int,
    format_code: str,
    allowance_pct_decimal: float,
    handicap_mode: str,
) -> list[int]:
    """
    Full WHS chain: index → course HC → playing HC → PLAY_OFF_LOW adjustment.
    Returns adjusted playing handicaps in the same order as player_indices.
    """
    playing_hcs = [
        playing_handicap_for_format(
            idx, tee_slope, tee_rating, tee_par,
            format_code, allowance_pct_decimal,
        )["playing_hc"]
        for idx in player_indices
    ]
    return apply_handicap_mode(playing_hcs, handicap_mode, allowance_pct_decimal)


_HC_NONE = {"strokes_a": None, "strokes_b": None, "low_handicap_idx": None,
            "ph_a1": None, "ph_a2": None, "ph_b1": None, "ph_b2": None}

def _strokes_for_match(
    match: dict,
    round_row: dict,
    format_code: str,
    allowance_pct_decimal: float,
    handicap_mode: str,
) -> dict:
    """
    Compute team strokes and per-player adjusted playing handicaps.

    Returns a dict with keys:
        strokes_a, strokes_b, low_handicap_idx   — team-level (as before)
        ph_a1, ph_a2, ph_b1, ph_b2               — individual adjusted HCs
                                                   (after PLAY_OFF_LOW)

    ph values are used by the scoring app to determine per-hole stroke
    allocation without needing to re-run the full WHS calculation.
    """
    if round_row.get("rating_a") is None:
        return _HC_NONE

    try:
        a1_idx = match.get("a1_idx")
        a2_idx = match.get("a2_idx")
        b1_idx = match.get("b1_idx")
        b2_idx = match.get("b2_idx")

        all_indices = [i for i in [a1_idx, a2_idx, b1_idx, b2_idx] if i is not None]
        low_idx     = float(min(all_indices)) if all_indices else None

        if format_code in ("FOURSOMES_MP", "SINGLES_MP", "SINGLES_STROKE"):
            indices = [i for i in [a1_idx, b1_idx] if i is not None]
            if len(indices) < 2:
                return _HC_NONE
            adj = _compute_adjusted_handicaps(
                indices, round_row["rating_a"], round_row["slope_a"],
                round_row["par_a"], format_code, allowance_pct_decimal, handicap_mode,
            )
            return {
                "strokes_a":       adj[0],
                "strokes_b":       adj[1],
                "low_handicap_idx": low_idx,
                "ph_a1":           adj[0],
                "ph_a2":           None,
                "ph_b1":           adj[1],
                "ph_b2":           None,
            }

        else:
            # FOURBALL_MP / SCRAMBLE — PLAY_OFF_LOW across all 4 players
            slot_indices = [a1_idx, a2_idx, b1_idx, b2_idx]
            valid = [(pos, idx) for pos, idx in enumerate(slot_indices) if idx is not None]
            if len(valid) < 2:
                return _HC_NONE

            adj = _compute_adjusted_handicaps(
                [idx for _, idx in valid],
                round_row["rating_a"], round_row["slope_a"], round_row["par_a"],
                format_code, allowance_pct_decimal, handicap_mode,
            )
            adj_by_pos = {pos: adj[i] for i, (pos, _) in enumerate(valid)}
            a_hcs = [adj_by_pos[p] for p in [0, 1] if p in adj_by_pos]
            b_hcs = [adj_by_pos[p] for p in [2, 3] if p in adj_by_pos]

            return {
                "strokes_a":        min(a_hcs) if a_hcs else 0,
                "strokes_b":        min(b_hcs) if b_hcs else 0,
                "low_handicap_idx": low_idx,
                "ph_a1":            adj_by_pos.get(0),
                "ph_a2":            adj_by_pos.get(1),
                "ph_b1":            adj_by_pos.get(2),
                "ph_b2":            adj_by_pos.get(3),
            }

    except Exception:
        return _HC_NONE


# ──────────────────────────────────────────────────────────────
# PUBLISH PAIRINGS
# ──────────────────────────────────────────────────────────────

def publish_pairings(gmc_round_id: int, event_id: int) -> dict:
    """
    Publish match pairings from GMC SQLite to Supabase and lock the round.

    Steps:
      1. Get GMC round (round_number, format, tee deck info)
      2. Get GMC matches with player names and handicap indices
      3. Resolve player names → Supabase UUIDs
      4. Resolve round_number → Supabase round UUID
      5. UPDATE placeholder match records in Supabase with player IDs + strokes
      6. Set round status → LOCKED in Supabase

    Returns:
      {"success": bool, "message": str, "matches_published": int}
    """
    client = _get_client()
    if not client:
        return {
            "success": False,
            "message": "Supabase not configured. Add SUPABASE_URL and SUPABASE_SERVICE_KEY to Streamlit secrets.",
            "matches_published": 0,
        }

    # ── GMC round ──
    round_row = fetchone(
        """
        SELECT r.*,
               c.name              AS course_name,
               ta.rating           AS rating_a,
               ta.slope            AS slope_a,
               ta.par              AS par_a,
               ta.stroke_index     AS stroke_index_a,
               tb.rating           AS rating_b,
               tb.slope            AS slope_b,
               tb.par              AS par_b
        FROM   round r
        LEFT JOIN course   c  ON c.course_id = r.course_id
        LEFT JOIN tee_deck ta ON ta.tee_id   = r.tee_id_a
        LEFT JOIN tee_deck tb ON tb.tee_id   = r.tee_id_b
        WHERE  r.round_id = ?
        """,
        (gmc_round_id,),
    )
    if not round_row:
        return {"success": False, "message": f"Round id {gmc_round_id} not found in GMC.", "matches_published": 0}

    round_row     = dict(round_row)
    round_number  = round_row["round_number"]
    format_code   = round_row["format_code"]

    # ── GMC matches with player names and indices ──
    matches = fetchall(
        """
        SELECT m.match_id,
               m.match_order,
               m.team_a_player1_id AS a1_id,  pa1.name AS a1_name,  pa1.current_index AS a1_idx,
               m.team_a_player2_id AS a2_id,  pa2.name AS a2_name,  pa2.current_index AS a2_idx,
               m.team_b_player1_id AS b1_id,  pb1.name AS b1_name,  pb1.current_index AS b1_idx,
               m.team_b_player2_id AS b2_id,  pb2.name AS b2_name,  pb2.current_index AS b2_idx
        FROM   match m
        LEFT JOIN player pa1 ON pa1.player_id = m.team_a_player1_id
        LEFT JOIN player pa2 ON pa2.player_id = m.team_a_player2_id
        LEFT JOIN player pb1 ON pb1.player_id = m.team_b_player1_id
        LEFT JOIN player pb2 ON pb2.player_id = m.team_b_player2_id
        WHERE  m.round_id = ?
        ORDER  BY m.match_order ASC
        """,
        (gmc_round_id,),
    )
    if not matches:
        return {
            "success": False,
            "message": "No matches in the draw for this round. Add pairings in Results first.",
            "matches_published": 0,
        }

    # ── Resolve names → Supabase UUIDs ──
    player_map    = _player_uuid_map(client)
    supa_round_id = _round_uuid(client, round_number)
    if not supa_round_id:
        return {
            "success": False,
            "message": f"Round {round_number} not found in Supabase. Has the seed data been run?",
            "matches_published": 0,
        }

    # ── Event handicap settings ──
    event_row = fetchone(
        "SELECT handicap_mode, allowance_pct FROM event WHERE event_id = ?",
        (event_id,),
    )
    handicap_mode        = (event_row["handicap_mode"] if event_row else "PLAY_OFF_LOW")
    allowance_pct_decimal = (event_row["allowance_pct"] if event_row else 100.0) / 100.0

    # ── Publish each match ──
    published = 0
    errors    = []

    for m in matches:
        m            = dict(m)
        match_number = m["match_order"]

        a1_uuid = player_map.get(m.get("a1_name"))
        b1_uuid = player_map.get(m.get("b1_name"))
        a2_uuid = player_map.get(m.get("a2_name")) if m.get("a2_name") else None
        b2_uuid = player_map.get(m.get("b2_name")) if m.get("b2_name") else None

        if not a1_uuid or not b1_uuid:
            missing = [n for n in [m.get("a1_name"), m.get("b1_name")] if not player_map.get(n)]
            errors.append(f"Match {match_number}: player(s) not found in Supabase — {missing}")
            continue

        hc = _strokes_for_match(
            m, round_row, format_code, allowance_pct_decimal, handicap_mode,
        )

        update_data: dict = {
            "team_a_p1_id":      a1_uuid,
            "team_a_p2_id":      a2_uuid,
            "team_b_p1_id":      b1_uuid,
            "team_b_p2_id":      b2_uuid,
            "status":            "LOCKED",
            "result_entered_by": "GMC",
        }
        if hc["strokes_a"] is not None:
            update_data["strokes_a"]        = hc["strokes_a"]
            update_data["strokes_b"]        = hc["strokes_b"]
            update_data["low_handicap_idx"] = hc["low_handicap_idx"]
        # Per-player adjusted playing handicaps for hole-by-hole stroke allocation
        for key in ("ph_a1", "ph_a2", "ph_b1", "ph_b2"):
            if hc[key] is not None:
                update_data[key] = hc[key]

        res = (
            client.table("matches")
            .update(update_data)
            .eq("round_id", supa_round_id)
            .eq("match_number", match_number)
            .execute()
        )
        if res.data:
            published += 1
        else:
            errors.append(f"Match {match_number}: Supabase update returned no data — check match_number alignment")

    # ── Lock the round + store tee deck data for scoring app ──
    if published > 0:
        round_update: dict = {
            "status":    "LOCKED",
            "locked_at": datetime.now(timezone.utc).isoformat(),
        }
        # Stroke index — stored as JSON text in SQLite, needs parsing
        si_raw = round_row.get("stroke_index_a")
        if si_raw is not None:
            try:
                si_list = json.loads(si_raw) if isinstance(si_raw, str) else list(si_raw)
                round_update["stroke_index"]  = si_list
                round_update["course_rating"] = round_row.get("rating_a")
                round_update["course_slope"]  = round_row.get("slope_a")
                round_update["course_par"]    = round_row.get("par_a")
            except Exception:
                pass  # tee deck data is best-effort; won't block the lock
        client.table("rounds").update(round_update).eq("id", supa_round_id).execute()

    if errors:
        msg = f"{published}/{len(matches)} match(es) published. Issues: {'; '.join(errors)}"
    else:
        msg = (
            f"{published} match(es) published. "
            f"Round {round_number} is LOCKED — pairings are now visible in the weather app."
        )

    return {"success": published > 0, "message": msg, "matches_published": published}


# ──────────────────────────────────────────────────────────────
# SYNC RESULTS
# ──────────────────────────────────────────────────────────────

def sync_results(event_id: int) -> dict:
    """
    Pull COMPLETED match results from Supabase into GMC SQLite.

    Steps:
      1. Get round_numbers for this event from GMC
      2. Query Supabase match_detail view for COMPLETED matches in those rounds
      3. Map Supabase round_number + match_number → GMC match_id
      4. Write result + result_detail into GMC (only where GMC has no result yet)

    Results already entered manually in GMC are not overwritten.

    Returns:
      {"success": bool, "message": str, "results_synced": int}
    """
    client = _get_client()
    if not client:
        return {"success": False, "message": "Supabase not configured.", "results_synced": 0}

    # ── GMC rounds for this event ──
    gmc_rounds = fetchall(
        "SELECT round_id, round_number FROM round WHERE event_id = ? ORDER BY round_number",
        (event_id,),
    )
    if not gmc_rounds:
        return {"success": False, "message": "No rounds found for this event in GMC.", "results_synced": 0}

    rnum_to_rid  = {r["round_number"]: r["round_id"] for r in gmc_rounds}
    round_numbers = list(rnum_to_rid.keys())

    # ── Fetch completed matches from Supabase match_detail view ──
    res = (
        client.table("match_detail")
        .select("round_number, match_number, result, result_detail, points_a, points_b")
        .eq("match_status", "COMPLETED")
        .in_("round_number", round_numbers)
        .execute()
    )

    if not res.data:
        return {"success": True, "message": "No completed matches in Supabase yet.", "results_synced": 0}

    synced = 0
    skipped = 0
    errors  = []

    for row in res.data:
        rnum          = row["round_number"]
        mnum          = row["match_number"]
        supa_result   = row.get("result")
        supa_detail   = row.get("result_detail") or ""

        if not supa_result:
            continue

        gmc_round_id = rnum_to_rid.get(rnum)
        if not gmc_round_id:
            continue

        gmc_match = fetchone(
            "SELECT match_id, result FROM match WHERE round_id = ? AND match_order = ?",
            (gmc_round_id, mnum),
        )
        if not gmc_match:
            errors.append(f"Round {rnum} Match {mnum}: not found in GMC draw")
            continue

        if gmc_match["result"] is not None:
            # Already entered in GMC — do not overwrite
            skipped += 1
            continue

        from modules.results import record_result
        record_result(gmc_match["match_id"], supa_result, supa_detail)
        synced += 1

    parts = [f"{synced} result(s) synced from Supabase."]
    if skipped:
        parts.append(f"{skipped} already entered in GMC (not overwritten).")
    if errors:
        parts.append(f"Issues: {'; '.join(errors)}")

    return {"success": True, "message": " ".join(parts), "results_synced": synced}


# ──────────────────────────────────────────────────────────────
# ROUND STATUS CHECK
# ──────────────────────────────────────────────────────────────

def get_round_supabase_status(round_number: int) -> str:
    """
    Return the Supabase status for a given round_number.
    Returns 'DRAFT', 'LOCKED', 'COMPLETED', or 'NOT_FOUND'.
    Returns 'UNCONFIGURED' if Supabase credentials are not set.
    """
    client = _get_client()
    if not client:
        return "UNCONFIGURED"
    try:
        res = (
            client.table("rounds")
            .select("status")
            .eq("round_number", round_number)
            .execute()
        )
        if res.data:
            return res.data[0]["status"]
        return "NOT_FOUND"
    except Exception:
        return "ERROR"

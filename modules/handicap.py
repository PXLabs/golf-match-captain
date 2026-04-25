"""
handicap.py — WHS 2024 Handicap Calculation Engine
Golf Match Captain | Phase 1B

Implements the full calculation chain:
    Handicap Index → Course Handicap → Playing Handicap → Strokes on holes

All formulas per WHS 2024 specification and Section 3.3 / Section 6
of the Golf Match Captain Context Document.

Format allowances (WHS recommended):
    SINGLES_MP      100% of Course Handicap; play off the low
    FOURBALL_MP      90% of Course Handicap; play off the low
    FOURSOMES_MP     50% of combined team handicap
    SINGLES_STROKE   95% of Course Handicap
    SCRAMBLE         Captain's choice — default 20% of combined team handicap
"""

from __future__ import annotations
import math


# ---------------------------------------------------------------
# Constants
# ---------------------------------------------------------------

STANDARD_SLOPE = 113  # WHS reference slope

# WHS-recommended allowance percentages per format (as decimals)
FORMAT_ALLOWANCES: dict[str, float] = {
    "SINGLES_MP":     1.00,
    "FOURBALL_MP":    0.90,
    "FOURSOMES_MP":   0.50,   # applied to combined team handicap
    "SINGLES_STROKE": 0.95,
    "SCRAMBLE":       0.20,   # captain's choice default
}

FORMAT_LABELS: dict[str, str] = {
    "SINGLES_MP":     "Singles Match Play",
    "FOURBALL_MP":    "Four-Ball (Best Ball) Match Play",
    "FOURSOMES_MP":   "Foursomes (Alternate Shot)",
    "SINGLES_STROKE": "Individual Stroke Play",
    "SCRAMBLE":       "Team Scramble",
}


# ---------------------------------------------------------------
# Step 1 — Course Handicap
# ---------------------------------------------------------------

def course_handicap(
    handicap_index: float,
    slope_rating: int,
    course_rating: float,
    par: int,
) -> float:
    """
    WHS 2024 formula:
        Course HC = (Index × Slope / 113) + (Course Rating − Par)

    Returns the unrounded course handicap (float).
    """
    return (handicap_index * slope_rating / STANDARD_SLOPE) + (course_rating - par)


def course_handicap_rounded(
    handicap_index: float,
    slope_rating: int,
    course_rating: float,
    par: int,
) -> int:
    """
    Returns Course Handicap rounded to the nearest integer
    (standard WHS rounding — .5 rounds up).
    """
    raw = course_handicap(handicap_index, slope_rating, course_rating, par)
    return _round_half_up(raw)


# ---------------------------------------------------------------
# Step 2 — Playing Handicap
# ---------------------------------------------------------------

def playing_handicap(
    course_hc: int,
    allowance_pct: float,
) -> int:
    """
    WHS 2024 formula:
        Playing HC = Course HC × Allowance %   [rounded to nearest integer]

    allowance_pct should be provided as a decimal (e.g. 0.90 for 90%).
    """
    return _round_half_up(course_hc * allowance_pct)


def playing_handicap_for_format(
    handicap_index: float,
    slope_rating: int,
    course_rating: float,
    par: int,
    format_code: str,
    event_allowance_pct: float = 1.0,
) -> dict:
    """
    Full chain for a single player in a given format.

    event_allowance_pct: the event-level override (e.g. 0.80 for 80%).
    If the format has its own WHS allowance, both are applied multiplicatively.

    Returns a dict with all intermediate values for transparency:
        {
            handicap_index, course_hc_raw, course_hc,
            format_allowance, event_allowance, effective_allowance,
            playing_hc, format_code, format_label
        }
    """
    format_allowance = FORMAT_ALLOWANCES.get(format_code, 1.0)
    effective_allowance = format_allowance * event_allowance_pct

    ch_raw  = course_handicap(handicap_index, slope_rating, course_rating, par)
    ch      = _round_half_up(ch_raw)
    play_hc = playing_handicap(ch, effective_allowance)

    return {
        "handicap_index":     handicap_index,
        "course_hc_raw":      round(ch_raw, 2),
        "course_hc":          ch,
        "format_allowance":   format_allowance,
        "event_allowance":    event_allowance_pct,
        "effective_allowance": round(effective_allowance, 4),
        "playing_hc":         play_hc,
        "format_code":        format_code,
        "format_label":       FORMAT_LABELS.get(format_code, format_code),
    }


# ---------------------------------------------------------------
# Step 3 — Handicap Mode Adjustments (Section 3.2)
# ---------------------------------------------------------------

def apply_handicap_mode(
    playing_hcs: list[int],
    mode: str,
    event_allowance_pct: float = 1.0,
) -> list[int]:
    """
    Apply the event-level handicap mode to a group of playing handicaps.

    Modes:
        FULL_INDEX      — no adjustment (playing HCs used as-is)
        PERCENTAGE      — already applied in playing_handicap_for_format()
        PLAY_OFF_LOW    — lowest HC in the group plays scratch;
                          all others receive (their HC − lowest HC)

    Returns adjusted playing handicaps in the same order as input.
    """
    if not playing_hcs:
        return []

    if mode == "PLAY_OFF_LOW":
        low = min(playing_hcs)
        return [hc - low for hc in playing_hcs]

    # FULL_INDEX and PERCENTAGE are already handled upstream
    return list(playing_hcs)


# ---------------------------------------------------------------
# Step 4 — Strokes on Holes (Section 3.3)
# ---------------------------------------------------------------

def strokes_received(playing_hc_a: int, playing_hc_b: int) -> int:
    """
    Match play strokes received by the higher-handicap player.
        Strokes = Playing HC A − Playing HC B  [lower plays scratch]

    Returns a positive integer (or 0 if equal).
    Raises ValueError if result is negative (caller passed wrong order).
    """
    diff = abs(playing_hc_a - playing_hc_b)
    return diff


def stroke_allocation(
    playing_hc: int,
    stroke_index: list[int],
    holes: int = 18,
) -> list[bool]:
    """
    Determine which holes a player receives strokes on.

    Args:
        playing_hc:   The player's playing handicap (after all adjustments)
        stroke_index: List of SI values for the tee deck.
                      Length must equal `holes`.
                      SI 1 = hardest hole (receives stroke first).
        holes:        18 (full round) or 9 (half round)

    Returns:
        A list of booleans, length == holes.
        True  → player receives a stroke on this hole.
        False → no stroke.

    Handles handicaps > holes (extra strokes cycle through SI again).
    """
    if len(stroke_index) < holes:
        raise ValueError(
            f"stroke_index length ({len(stroke_index)}) < holes ({holes}). "
            "Ensure the tee deck has SI values for all holes being played."
        )

    si = stroke_index[:holes]
    receives_stroke = [False] * holes

    if playing_hc <= 0:
        return receives_stroke

    # First pass: one stroke on each hole from SI 1 up to playing_hc
    full_passes  = playing_hc // holes
    remainder    = playing_hc % holes

    # Full passes — player gets a stroke on every hole
    if full_passes > 0:
        receives_stroke = [True] * holes

    # If full_passes > 1, we need a second True on some holes
    # We represent extra strokes as a count, but for display we only
    # show "receives stroke" (bool). Return extended dict for full detail.
    receives_stroke = []
    for hole_num in range(holes):
        hole_si = si[hole_num]
        strokes_on_hole = full_passes + (1 if hole_si <= remainder else 0)
        receives_stroke.append(strokes_on_hole > 0)

    return receives_stroke


def stroke_allocation_detail(
    playing_hc: int,
    stroke_index: list[int],
    holes: int = 18,
) -> list[dict]:
    """
    Extended version of stroke_allocation — returns per-hole detail dicts.

    Each dict:
        {
            hole:            int  (1-indexed hole number)
            si:              int  (stroke index for this hole)
            strokes:         int  (0, 1, or 2 for very high handicaps)
            receives_stroke: bool
        }
    """
    if len(stroke_index) < holes:
        raise ValueError(
            f"stroke_index length ({len(stroke_index)}) < holes ({holes})."
        )

    si = stroke_index[:holes]
    full_passes = playing_hc // holes
    remainder   = playing_hc % holes

    result = []
    for hole_num in range(holes):
        hole_si    = si[hole_num]
        extra      = 1 if hole_si <= remainder else 0
        strokes    = full_passes + extra
        result.append({
            "hole":            hole_num + 1,
            "si":              hole_si,
            "strokes":         strokes,
            "receives_stroke": strokes > 0,
        })

    return result


# ---------------------------------------------------------------
# Matchup helper — full comparison between two players
# ---------------------------------------------------------------

def matchup_handicap_detail(
    player_a: dict,
    player_b: dict,
    tee_deck_a: dict,
    tee_deck_b: dict,
    format_code: str,
    handicap_mode: str = "FULL_INDEX",
    event_allowance_pct: float = 1.0,
    holes: int = 18,
) -> dict:
    """
    Compute the full handicap picture for a head-to-head matchup.

    player_a / player_b: dicts with at least {"name": str, "current_index": float}
    tee_deck_a / tee_deck_b: dicts with:
        {"rating": float, "slope": int, "par": int, "stroke_index": list[int]}

    Returns a rich dict suitable for display and LLM context building.
    """
    # Calculate playing handicaps for each player
    detail_a = playing_handicap_for_format(
        player_a["current_index"],
        tee_deck_a["slope"],
        tee_deck_a["rating"],
        tee_deck_a["par"],
        format_code,
        event_allowance_pct,
    )
    detail_b = playing_handicap_for_format(
        player_b["current_index"],
        tee_deck_b["slope"],
        tee_deck_b["rating"],
        tee_deck_b["par"],
        format_code,
        event_allowance_pct,
    )

    # Apply handicap mode
    adjusted = apply_handicap_mode(
        [detail_a["playing_hc"], detail_b["playing_hc"]],
        handicap_mode,
        event_allowance_pct,
    )
    adj_hc_a, adj_hc_b = adjusted[0], adjusted[1]

    # Stroke allocation
    si_a = tee_deck_a.get("stroke_index", [])
    si_b = tee_deck_b.get("stroke_index", [])

    holes_a = stroke_allocation_detail(adj_hc_a, si_a, holes) if si_a else []
    holes_b = stroke_allocation_detail(adj_hc_b, si_b, holes) if si_b else []

    strokes = strokes_received(adj_hc_a, adj_hc_b)
    higher_hc_player = (
        player_a["name"] if adj_hc_a > adj_hc_b
        else player_b["name"] if adj_hc_b > adj_hc_a
        else "Equal"
    )

    return {
        "player_a": {
            "name":           player_a["name"],
            "index":          player_a["current_index"],
            "course_hc":      detail_a["course_hc"],
            "playing_hc":     detail_a["playing_hc"],
            "adjusted_hc":    adj_hc_a,
            "hole_detail":    holes_a,
        },
        "player_b": {
            "name":           player_b["name"],
            "index":          player_b["current_index"],
            "course_hc":      detail_b["course_hc"],
            "playing_hc":     detail_b["playing_hc"],
            "adjusted_hc":    adj_hc_b,
            "hole_detail":    holes_b,
        },
        "strokes_given":      strokes,
        "higher_hc_player":   higher_hc_player,
        "format_code":        format_code,
        "format_label":       FORMAT_LABELS.get(format_code, format_code),
        "handicap_mode":      handicap_mode,
        "holes":              holes,
    }


# ---------------------------------------------------------------
# Foursomes helper — combined team handicap (Section 6)
# ---------------------------------------------------------------

def foursomes_team_handicap(
    player1_index: float,
    player2_index: float,
    slope_rating: int,
    course_rating: float,
    par: int,
    event_allowance_pct: float = 1.0,
) -> int:
    """
    Foursomes (alternate shot): combined team Playing Handicap.
    WHS: 50% of combined course handicaps.

    Returns the team's playing handicap as an integer.
    """
    ch1 = course_handicap_rounded(player1_index, slope_rating, course_rating, par)
    ch2 = course_handicap_rounded(player2_index, slope_rating, course_rating, par)
    combined = ch1 + ch2
    team_hc = playing_handicap(combined, 0.50 * event_allowance_pct)
    return team_hc


# ---------------------------------------------------------------
# Internal utilities
# ---------------------------------------------------------------

def _round_half_up(value: float) -> int:
    """
    Standard rounding where .5 always rounds up (away from zero).
    Python's built-in round() uses banker's rounding — this ensures
    WHS-compliant behaviour.
    """
    return math.floor(value + 0.5)

"""
intelligence.py — Player Intelligence Layer
Golf Match Captain | Phase 1D

Implements Section 5 of the Context Document:
  - Handicap trend analysis (direction, volatility, Best-3 gap)
  - Sandbagging signals (Red / Amber / Green indicators)
  - Player intelligence summary for display and LLM context

All calculations operate on a list of score differentials,
newest-first, as returned by roster.get_differentials().
"""

from __future__ import annotations
import math
import statistics


# ---------------------------------------------------------------
# Constants (Section 5.1 / 5.2)
# ---------------------------------------------------------------

# Sandbagging thresholds
BEST3_GAP_RED_THRESHOLD     = 4.0   # Red flag: best-3 avg beats index by >4
POSTING_FREQ_AMBER_WEEKS    = 3     # Amber: fewer than 1 score per 3 weeks
VOLATILITY_AMBER_THRESHOLD  = 4.0   # Amber: standard deviation > 4.0

# Trend windows
RECENT_WINDOW   = 5    # Most recent N differentials
BASELINE_WINDOW = 10   # Next M differentials (positions 5–14)
OFFICIAL_WINDOW = 8    # Best 8 of 20 for official index


# ---------------------------------------------------------------
# Core intelligence function
# ---------------------------------------------------------------

def build_player_intelligence(
    differentials: list[float],
    current_index: float,
    score_dates: list[str] | None = None,
) -> dict:
    """
    Compute the full intelligence profile for a player.

    Args:
        differentials:  List of score differentials, newest first.
                        Up to 20 values.
        current_index:  The player's official handicap index (from roster).
        score_dates:    Optional list of ISO date strings (same order as
                        differentials). Used for posting frequency analysis.

    Returns a dict with all metrics, flags, and a plain-English summary.
    """
    n = len(differentials)

    if n == 0:
        return _empty_profile(current_index)

    # ---- Trend direction ----------------------------------------
    trend      = _trend_direction(differentials)

    # ---- Volatility ---------------------------------------------
    volatility = _volatility(differentials)

    # ---- Best-3 gap ---------------------------------------------
    best3_avg  = _best3_average(differentials)
    best3_gap  = current_index - best3_avg  # positive = plays better than index

    # ---- Posting frequency --------------------------------------
    posting_days_avg = _avg_days_between_posts(score_dates) if score_dates else None

    # ---- Derived index from stored rounds -----------------------
    derived_index = _derived_index(differentials)

    # ---- Sandbagging signals ------------------------------------
    flags = _sandbagging_flags(
        best3_gap, posting_days_avg, volatility, n
    )

    # ---- Overall signal colour ----------------------------------
    signal = _overall_signal(flags)

    # ---- Plain-English summary lines ----------------------------
    summary_lines = _build_summary(
        n, current_index, derived_index, trend,
        volatility, best3_gap, posting_days_avg, flags
    )

    return {
        # Raw data
        "n_rounds":          n,
        "current_index":     current_index,
        "derived_index":     derived_index,

        # Trend
        "trend_direction":   trend["direction"],    # "IMPROVING" | "DECLINING" | "STABLE"
        "trend_label":       trend["label"],        # human-readable
        "trend_delta":       trend["delta"],        # recent avg minus baseline avg
        "recent_avg":        trend["recent_avg"],
        "baseline_avg":      trend["baseline_avg"],

        # Volatility
        "volatility":        volatility,            # standard deviation
        "volatility_label":  _volatility_label(volatility),

        # Best-3 gap
        "best3_avg":         best3_avg,
        "best3_gap":         best3_gap,             # positive = plays better than index

        # Posting frequency
        "posting_days_avg":  posting_days_avg,

        # Flags
        "flag_red":          flags["red"],
        "flag_amber":        flags["amber"],
        "flag_green":        flags["green"],
        "flag_messages":     flags["messages"],

        # Signal
        "signal":            signal,                # "RED" | "AMBER" | "GREEN" | "NONE"

        # Summary
        "summary_lines":     summary_lines,
    }


# ---------------------------------------------------------------
# Trend direction (Section 5.1)
# ---------------------------------------------------------------

def _trend_direction(differentials: list[float]) -> dict:
    """
    Compare the average of the 5 most recent differentials against
    the average of differentials 6–15 (baseline window).

    Lower differential = better golf, so:
        recent_avg < baseline_avg → IMPROVING
        recent_avg > baseline_avg → DECLINING
    """
    recent   = differentials[:RECENT_WINDOW]
    baseline = differentials[RECENT_WINDOW : RECENT_WINDOW + BASELINE_WINDOW]

    recent_avg   = round(statistics.mean(recent), 2) if recent else None
    baseline_avg = round(statistics.mean(baseline), 2) if baseline else None

    if recent_avg is None or baseline_avg is None:
        return {"direction": "STABLE", "label": "Stable (insufficient data)",
                "delta": 0.0, "recent_avg": recent_avg, "baseline_avg": baseline_avg}

    delta = round(recent_avg - baseline_avg, 2)  # negative = improving

    if delta <= -1.0:
        direction = "IMPROVING"
        label = f"Improving (↓ {abs(delta):.1f} vs baseline)"
    elif delta >= 1.0:
        direction = "DECLINING"
        label = f"Declining (↑ {delta:.1f} vs baseline)"
    else:
        direction = "STABLE"
        label = f"Stable (±{abs(delta):.1f} vs baseline)"

    return {
        "direction":    direction,
        "label":        label,
        "delta":        delta,
        "recent_avg":   recent_avg,
        "baseline_avg": baseline_avg,
    }


# ---------------------------------------------------------------
# Volatility (Section 5.1)
# ---------------------------------------------------------------

def _volatility(differentials: list[float]) -> float:
    """Standard deviation of all stored differentials."""
    if len(differentials) < 2:
        return 0.0
    return round(statistics.stdev(differentials), 2)


def _volatility_label(sd: float) -> str:
    if sd == 0.0:
        return "N/A (< 2 rounds)"
    if sd < 2.0:
        return f"Very consistent (SD {sd:.1f})"
    if sd < 4.0:
        return f"Consistent (SD {sd:.1f})"
    if sd < 6.0:
        return f"Moderate variance (SD {sd:.1f})"
    return f"High variance (SD {sd:.1f})"


# ---------------------------------------------------------------
# Best-3 gap (Section 5.1)
# ---------------------------------------------------------------

def _best3_average(differentials: list[float]) -> float:
    """Average of the 3 lowest differentials stored."""
    if not differentials:
        return 0.0
    best3 = sorted(differentials)[:3]
    return round(sum(best3) / len(best3), 2)


# ---------------------------------------------------------------
# Derived index (best 8 of stored rounds)
# ---------------------------------------------------------------

def _derived_index(differentials: list[float]) -> float | None:
    """
    Approximate handicap index from stored rounds:
    average of best 8 differentials (capped at 20).
    Returns None if fewer than 3 rounds available.
    """
    if len(differentials) < 3:
        return None
    n_best = min(OFFICIAL_WINDOW, len(differentials))
    best   = sorted(differentials)[:n_best]
    return round(sum(best) / len(best), 1)


# ---------------------------------------------------------------
# Posting frequency
# ---------------------------------------------------------------

def _avg_days_between_posts(dates: list[str]) -> float | None:
    """
    Average number of days between posted scores.
    dates: ISO strings, same order as differentials (newest first).
    Returns None if fewer than 2 dates.
    """
    if len(dates) < 2:
        return None

    from datetime import date as date_type
    parsed = []
    for d in dates:
        try:
            parsed.append(date_type.fromisoformat(str(d)))
        except (ValueError, TypeError):
            pass

    if len(parsed) < 2:
        return None

    parsed_sorted = sorted(parsed, reverse=True)
    gaps = [(parsed_sorted[i] - parsed_sorted[i + 1]).days
            for i in range(len(parsed_sorted) - 1)]
    return round(sum(gaps) / len(gaps), 1)


# ---------------------------------------------------------------
# Sandbagging flags (Section 5.2)
# ---------------------------------------------------------------

def _sandbagging_flags(
    best3_gap: float,
    posting_days_avg: float | None,
    volatility: float,
    n_rounds: int,
) -> dict:
    """
    Return a dict of flag states and messages.

    Red:   Best-3 gap > 4 strokes
    Amber: Posting fewer than 1 score per 3 weeks (21 days)
    Amber: Volatility SD > 4.0
    Green: Consistent posting, stable trend, low gap
    """
    red_flags   = []
    amber_flags = []
    green_flags = []

    # --- Red ---
    if best3_gap > BEST3_GAP_RED_THRESHOLD:
        red_flags.append(
            f"Best-3 gap of {best3_gap:.1f} strokes suggests ceiling well "
            f"above current index."
        )

    # --- Amber: posting frequency ---
    if posting_days_avg is not None:
        posting_freq_weeks = posting_days_avg / 7
        if posting_freq_weeks > POSTING_FREQ_AMBER_WEEKS:
            amber_flags.append(
                f"Infrequent posting — avg {posting_days_avg:.0f} days between scores "
                f"({posting_freq_weeks:.1f} weeks)."
            )

    # --- Amber: volatility ---
    if volatility > VOLATILITY_AMBER_THRESHOLD and n_rounds >= 5:
        amber_flags.append(
            f"High variance player — SD {volatility:.1f} across {n_rounds} rounds. "
            "Performance is inconsistent."
        )

    # --- Green ---
    if not red_flags and not amber_flags and n_rounds >= 5:
        green_flags.append(
            "Consistent posting, reliable index, no sandbagging signals."
        )

    return {
        "red":      bool(red_flags),
        "amber":    bool(amber_flags),
        "green":    bool(green_flags),
        "messages": red_flags + amber_flags + green_flags,
    }


def _overall_signal(flags: dict) -> str:
    if flags["red"]:
        return "RED"
    if flags["amber"]:
        return "AMBER"
    if flags["green"]:
        return "GREEN"
    return "NONE"


# ---------------------------------------------------------------
# Plain-English summary builder
# ---------------------------------------------------------------

def _build_summary(
    n, current_index, derived_index, trend,
    volatility, best3_gap, posting_days_avg, flags
) -> list[str]:
    lines = []

    lines.append(
        f"Based on {n} round(s) stored. "
        f"Official index: {current_index:.1f}."
        + (f" Derived from stored rounds: {derived_index:.1f}." if derived_index else "")
    )

    lines.append(f"Trend: {trend['label']}.")

    lines.append(f"Consistency: {_volatility_label(volatility)}.")

    if best3_gap > 0:
        lines.append(
            f"Best-3 average is {best3_gap:.1f} strokes better than current index "
            f"— player has demonstrated ability to perform well above their index."
        )
    else:
        lines.append(
            f"Best-3 average is within {abs(best3_gap):.1f} strokes of index — "
            "no significant performance ceiling gap."
        )

    if posting_days_avg:
        lines.append(f"Average {posting_days_avg:.0f} days between posted scores.")

    for msg in flags["messages"]:
        lines.append(f"⚑ {msg}")

    return lines


# ---------------------------------------------------------------
# Empty profile for players with no score history
# ---------------------------------------------------------------

def _empty_profile(current_index: float) -> dict:
    return {
        "n_rounds":         0,
        "current_index":    current_index,
        "derived_index":    None,
        "trend_direction":  "STABLE",
        "trend_label":      "No data",
        "trend_delta":      0.0,
        "recent_avg":       None,
        "baseline_avg":     None,
        "volatility":       0.0,
        "volatility_label": "N/A (no rounds)",
        "best3_avg":        0.0,
        "best3_gap":        0.0,
        "posting_days_avg": None,
        "flag_red":         False,
        "flag_amber":       False,
        "flag_green":       False,
        "flag_messages":    ["No score history — index taken at face value."],
        "signal":           "NONE",
        "summary_lines":    [
            f"No score history stored. Official index: {current_index:.1f}."
        ],
    }


# ---------------------------------------------------------------
# LLM context formatter
# ---------------------------------------------------------------

def format_intelligence_for_llm(player_name: str, profile: dict) -> str:
    """
    Format a player's intelligence profile as a compact text block
    for inclusion in the LLM advisor's system prompt context packet.
    """
    signal_emoji = {"RED": "🔴", "AMBER": "🟡", "GREEN": "🟢", "NONE": "⚪"}.get(
        profile["signal"], "⚪"
    )
    lines = [
        f"Player: {player_name}",
        f"  Index: {profile['current_index']:.1f}"
        + (f"  |  Derived: {profile['derived_index']:.1f}" if profile["derived_index"] else ""),
        f"  Trend: {profile['trend_label']}",
        f"  Consistency: {profile['volatility_label']}",
        f"  Best-3 gap: {profile['best3_gap']:+.1f} strokes vs index",
        f"  Signal: {signal_emoji} {profile['signal']}",
    ]
    if profile["flag_messages"]:
        for msg in profile["flag_messages"]:
            lines.append(f"    → {msg}")
    return "\n".join(lines)

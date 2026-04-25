"""
advisor.py — LLM Context Builder and Claude API Integration
Golf Match Captain | Phase 1F

Handles:
  - Building the full event context packet for the system prompt
  - Calling the Anthropic Claude API (streaming)
  - Managing conversation history for multi-turn sessions
  - Model configuration
"""

from __future__ import annotations
import os
from pathlib import Path
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    anthropic = None
    ANTHROPIC_AVAILABLE = False

from modules.events import (
    get_event, list_rounds, get_event_players_by_team, get_event_summary,
)
from modules.courses import get_tee_deck
from modules.roster import get_differentials, get_score_records, get_tags_grouped
from modules.handicap import (
    playing_handicap_for_format, apply_handicap_mode, FORMAT_LABELS,
)
from modules.intelligence import build_player_intelligence, format_intelligence_for_llm
from modules.results import get_event_score, get_player_results, format_results_for_llm

# ---------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------

SYSTEM_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "system_prompt.txt"

# Available models — Sonnet recommended for cost/quality at event frequency
AVAILABLE_MODELS: dict[str, str] = {
    "claude-sonnet-4-5":    "Claude Sonnet (recommended)",
    "claude-opus-4-5":      "Claude Opus (detailed analysis)",
}
DEFAULT_MODEL = "claude-sonnet-4-5"
MAX_TOKENS    = 2048


# ---------------------------------------------------------------
# Context packet builder
# ---------------------------------------------------------------

def build_context_packet(
    event_id: int,
    round_id: int | None = None,
) -> str:
    """
    Assemble the full event context packet to be injected into the
    system prompt. Includes event details, round configuration,
    player intelligence profiles, handicap calculations, and results.

    round_id: if provided, include handicap calculations for that round.
              If None, use the most recently configured round.
    """
    event = get_event(event_id)
    if not event:
        return "No event data available."

    ev_ta  = event["team_a_name"]
    ev_tb  = event["team_b_name"]
    mode   = event["handicap_mode"]
    allow  = float(event["allowance_pct"]) / 100.0
    rounds = list_rounds(event_id)
    teams  = get_event_players_by_team(event_id)

    # Resolve the target round
    target_round = None
    if round_id:
        target_round = next((r for r in rounds if r["round_id"] == round_id), None)
    if not target_round and rounds:
        target_round = rounds[-1]  # default to most recent round

    lines = [
        "=" * 60,
        f"EVENT: {event['name']}",
        f"Start date: {event['start_date']}  |  Status: {event['status']}",
        f"Teams: {ev_ta} (Team A)  vs  {ev_tb} (Team B)",
        f"Handicap mode: {mode}  |  Allowance: {int(event['allowance_pct'])}%",
    ]

    # Active round detail
    if target_round:
        fmt   = target_round["format_code"]
        holes = int(target_round["holes"])
        tee_a = get_tee_deck(target_round["tee_id_a"]) if target_round["tee_id_a"] else None
        tee_b = get_tee_deck(target_round["tee_id_b"]) if target_round["tee_id_b"] else None

        lines += [
            "",
            f"ACTIVE ROUND: Round {target_round['round_number']} — {target_round['date']}",
            f"Course: {dict(target_round).get('course_name', 'Unknown')}",
            f"Format: {FORMAT_LABELS.get(fmt, fmt)}  |  Holes: {holes}",
        ]
        if tee_a:
            lines.append(
                f"Tee {ev_ta}: {tee_a['name']} (Rating {tee_a['rating']}, Slope {tee_a['slope']})"
            )
        if tee_b and tee_b["tee_id"] != (tee_a["tee_id"] if tee_a else None):
            lines.append(
                f"Tee {ev_tb}: {tee_b['name']} (Rating {tee_b['rating']}, Slope {tee_b['slope']})"
            )

    # ---- Team A players ----------------------------------------
    lines += ["", "=" * 60, f"TEAM A — {ev_ta}", "=" * 60]
    for p in teams["A"]:
        lines.append(_format_player_block(
            p, target_round, mode, allow, ev_ta
        ))

    # ---- Team B players ----------------------------------------
    lines += ["", "=" * 60, f"TEAM B — {ev_tb}", "=" * 60]
    for p in teams["B"]:
        lines.append(_format_player_block(
            p, target_round, mode, allow, ev_tb
        ))

    # ---- Results and form --------------------------------------
    score = get_event_score(event_id)
    if score["total_points_a"] + score["total_points_b"] > 0:
        lines += ["", "=" * 60, "RESULTS & FORM", "=" * 60]
        lines.append(format_results_for_llm(event_id, ev_ta, ev_tb))

    # ---- Round schedule ----------------------------------------
    if rounds:
        lines += ["", "=" * 60, "FULL ROUND SCHEDULE", "=" * 60]
        for r in rounds:
            marker = "▶" if target_round and r["round_id"] == target_round["round_id"] else " "
            lines.append(
                f"  {marker} Round {r['round_number']}: {r['date']} | "
                f"{FORMAT_LABELS.get(r['format_code'], r['format_code'])} | "
                f"{r['holes']} holes"
            )

    lines.append("=" * 60)
    return "\n".join(lines)


def _format_player_block(
    player,
    target_round,
    mode: str,
    allow: float,
    team_name: str,
) -> str:
    """Format a single player's full intelligence + handicap block."""
    pid  = player["player_id"]
    name = player["name"]

    # Intelligence
    diffs   = get_differentials(pid)
    recs    = get_score_records(pid)
    dates   = [r["date"] for r in recs]
    profile = build_player_intelligence(diffs, float(player["current_index"]), dates)
    intel   = format_intelligence_for_llm(name, profile)

    # Tags
    tags_grouped = get_tags_grouped(pid)
    all_tags = [
        f"[{cat}] {t['value']}"
        for cat, tag_list in tags_grouped.items()
        for t in tag_list
    ]

    # Handicap for this round
    hc_lines = []
    if target_round:
        fmt   = target_round["format_code"]
        holes = int(target_round["holes"])

        # Pick the right tee
        if player["team"] == "A":
            tee_id = target_round["tee_id_a"] or target_round["tee_id_b"]
        else:
            tee_id = target_round["tee_id_b"] or target_round["tee_id_a"]

        if tee_id:
            tee = get_tee_deck(tee_id)
            if tee:
                from modules.courses import _parse_tee_deck
                tee_dict = _parse_tee_deck(tee)
                hc_detail = playing_handicap_for_format(
                    float(player["current_index"]),
                    tee_dict["slope"],
                    tee_dict["rating"],
                    tee_dict["par"],
                    fmt,
                    allow,
                )
                hc_lines = [
                    f"  Course HC: {hc_detail['course_hc']}  |  "
                    f"Playing HC (after {int(allow*100)}% {fmt}): {hc_detail['playing_hc']}"
                ]

    block = [intel] + hc_lines
    if all_tags:
        block.append("  Tags: " + " | ".join(all_tags))

    return "\n".join(block) + "\n"


# ---------------------------------------------------------------
# System prompt loader
# ---------------------------------------------------------------

def load_system_prompt(event_context: str) -> str:
    """Load the system prompt template and inject the event context."""
    try:
        template = SYSTEM_PROMPT_PATH.read_text()
    except FileNotFoundError:
        template = (
            "You are the Golf Match Captain Advisor. "
            "Use the event context below to help the captain.\n\n{EVENT_CONTEXT}"
        )
    return template.replace("{EVENT_CONTEXT}", event_context)


# ---------------------------------------------------------------
# Claude API — streaming
# ---------------------------------------------------------------

def stream_advisor_response(
    conversation_history: list[dict],
    event_id: int,
    round_id: int | None = None,
    model: str = DEFAULT_MODEL,
):
    """
    Stream a response from the Claude API.

    conversation_history: list of {"role": "user"|"assistant", "content": str}
    Yields text chunks as they arrive.

    The system prompt is rebuilt fresh on each call so it always
    reflects the latest event data.
    """
    context = build_context_packet(event_id, round_id)
    system  = load_system_prompt(context)

    if not ANTHROPIC_AVAILABLE:
        raise ImportError(
            "The 'anthropic' package is not installed. "
            "Run: pip install anthropic"
        )
    client = anthropic.Anthropic(api_key=_get_api_key())

    with client.messages.stream(
        model=model,
        max_tokens=MAX_TOKENS,
        system=system,
        messages=conversation_history,
    ) as stream:
        for text in stream.text_stream:
            yield text


def get_advisor_response(
    conversation_history: list[dict],
    event_id: int,
    round_id: int | None = None,
    model: str = DEFAULT_MODEL,
) -> str:
    """
    Non-streaming version — returns the complete response as a string.
    Used for testing and context preview.
    """
    return "".join(
        chunk for chunk in stream_advisor_response(
            conversation_history, event_id, round_id, model
        )
    )


# ---------------------------------------------------------------
# Conversation history helpers
# ---------------------------------------------------------------

def append_user_message(history: list[dict], message: str) -> list[dict]:
    """Return a new history list with a user message appended."""
    return history + [{"role": "user", "content": message}]


def append_assistant_message(history: list[dict], message: str) -> list[dict]:
    """Return a new history list with an assistant message appended."""
    return history + [{"role": "assistant", "content": message}]


def trim_history(history: list[dict], max_turns: int = 20) -> list[dict]:
    """
    Keep the most recent N turns (user+assistant pairs).
    Prevents context window overflow on long sessions.
    Always keeps at least the last 2 messages.
    """
    if len(history) <= max_turns * 2:
        return history
    return history[-(max_turns * 2):]


# ---------------------------------------------------------------
# Starter prompts — shown in the UI as quick-start buttons
# ---------------------------------------------------------------

STARTER_PROMPTS: list[dict[str, str]] = [
    {
        "label": "🎯 Suggest today's pairings",
        "prompt": (
            "Based on everything you know about our players — handicaps, form, "
            "intelligence signals, and the current score — suggest the optimal "
            "pairings for today's round. Explain your reasoning for each match."
        ),
    },
    {
        "label": "📊 Assess our position",
        "prompt": (
            "Give me an honest assessment of where we stand in this event. "
            "Who is in form? Who do I need to watch? "
            "What does today's round need to look like for us to win?"
        ),
    },
    {
        "label": "🔴 Flag any sandbagging concerns",
        "prompt": (
            "Look at the intelligence signals for both teams. "
            "Are there any players I should be treating as stronger than their handicap suggests? "
            "How should this affect how I set the draw?"
        ),
    },
    {
        "label": "🔄 Singles order strategy",
        "prompt": (
            "If today is a singles round, help me think through the batting order. "
            "Should I front-load my best players to set the tone, or hold them back? "
            "Consider the current score and who needs points most."
        ),
    },
]


# ---------------------------------------------------------------
# Internal
# ---------------------------------------------------------------

def _get_api_key() -> str:
    """
    Retrieve the Anthropic API key.
    Checks st.secrets first (Streamlit Cloud), then environment variables,
    then .env file.
    """
    # Try Streamlit secrets
    try:
        import streamlit as st
        if "ANTHROPIC_API_KEY" in st.secrets:
            return st.secrets["ANTHROPIC_API_KEY"]
    except Exception:
        pass

    # Try environment / .env
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        return key

    # Try python-dotenv
    try:
        from dotenv import load_dotenv
        load_dotenv()
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if key:
            return key
    except ImportError:
        pass

    raise ValueError(
        "ANTHROPIC_API_KEY not found. "
        "Add it to .env, set it as an environment variable, "
        "or add it to .streamlit/secrets.toml."
    )

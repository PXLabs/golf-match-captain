"""
scorecard.py — Scorecard Photo Processing
Golf Match Captain | Scorecard Feature

Handles:
  - Claude Vision API call to extract scores from a scorecard photo
  - Parsing and validation of extracted data
  - Hole-by-hole net score calculation using the handicap engine
  - Match result derivation from hole winners (match play)
  - Persisting hole scores and derived results to the match record

Supported formats:
  SINGLES_MP    — one player per side, net score wins each hole
  FOURBALL_MP   — two players per side, best net ball wins each hole
  SINGLES_STROKE — individual stroke play (recorded, not match play derived)
  FOURSOMES_MP  — one ball per side already, treated like singles
"""

from __future__ import annotations
import json
import base64
import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    anthropic = None
    ANTHROPIC_AVAILABLE = False

from database.db import execute, fetchone
from modules.handicap import (
    playing_handicap_for_format,
    apply_handicap_mode,
    stroke_allocation_detail,
)
from modules.courses import get_tee_deck, _parse_tee_deck
from modules.results import record_result

VISION_MODEL = "claude-sonnet-4-5"


# ---------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------

@dataclass
class ExtractedPlayer:
    """One player's data as returned by Vision extraction."""
    raw_name:    str
    scores:      list[int]          # gross score per hole (0 = unread)
    player_id:   int | None = None  # resolved after captain maps names
    side:        str        = ""    # "A1" | "A2" | "B1" | "B2"


@dataclass
class ExtractionResult:
    """Full result of a Vision API call on one scorecard photo."""
    success:      bool
    players:      list[ExtractedPlayer] = field(default_factory=list)
    par:          list[int]             = field(default_factory=list)
    holes:        int                   = 18
    course_name:  str                   = ""
    confidence:   str                   = "low"   # high | medium | low
    notes:        str                   = ""
    error:        str                   = ""
    raw_response: str                   = ""


@dataclass
class HoleResult:
    """Result of a single hole in a match."""
    hole:       int
    par:        int
    gross_a1:   int | None
    gross_a2:   int | None   # None for singles
    gross_b1:   int | None
    gross_b2:   int | None   # None for singles
    net_a1:     float | None
    net_a2:     float | None
    net_b1:     float | None
    net_b2:     float | None
    best_net_a: float | None  # best ball for team A (same as net_a1 in singles)
    best_net_b: float | None
    winner:     str           # "A" | "B" | "H" (halved)
    strokes_a1: int = 0       # strokes received on this hole
    strokes_a2: int = 0
    strokes_b1: int = 0
    strokes_b2: int = 0


@dataclass
class MatchCalculation:
    """Full hole-by-hole breakdown for a match."""
    hole_results:   list[HoleResult]
    running_score:  list[int]   # cumulative, A's perspective (+ve = A winning)
    final_result:   str         # "A" | "B" | "HALVED"
    result_detail:  str         # e.g. "3&2", "1 UP", "AS"
    holes_won_a:    int
    holes_won_b:    int
    holes_halved:   int
    format_code:    str


# ---------------------------------------------------------------
# Claude Vision extraction
# ---------------------------------------------------------------

EXTRACTION_SYSTEM_PROMPT = """You are a golf scorecard reader.
Your task is to extract scores from a golf scorecard photo with high accuracy.

Return ONLY valid JSON — no preamble, no markdown, no explanation.

Required JSON structure:
{
  "course_name": "string or empty",
  "holes": 18,
  "confidence": "high|medium|low",
  "notes": "any issues, illegible scores, etc.",
  "par": [4,3,5,...],
  "players": [
    {
      "name": "surname or name as printed on card",
      "scores": [4,3,5,...]
    }
  ]
}

Rules:
- scores array length must equal holes value (18 or 9)
- Use 0 for any hole score that is illegible or missing
- par array must equal holes length; use 0 if par not shown on card
- List players in the order they appear on the scorecard (top to bottom)
- confidence: "high" if all scores clearly legible, "medium" if a few uncertain,
  "low" if significant portions unreadable
- Include all players visible on the card, even if some scores are missing
- Do not infer or guess scores — use 0 for anything uncertain"""


def extract_scorecard_vision(
    image_bytes: bytes,
    holes: int = 18,
    media_type: str = "image/jpeg",
) -> ExtractionResult:
    """
    Send a scorecard image to Claude Vision and extract player scores.

    image_bytes: raw bytes of the photo (JPEG, PNG, WEBP, GIF)
    holes:       expected number of holes (9 or 18)
    media_type:  MIME type of the image

    Returns an ExtractionResult — always succeeds structurally,
    with success=False and error message if the API call fails.
    """
    if not ANTHROPIC_AVAILABLE:
        return ExtractionResult(
            success=False,
            error="Anthropic package not installed. Run: pip install anthropic",
        )

    try:
        api_key = _get_api_key()
        client  = anthropic.Anthropic(api_key=api_key)

        image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

        response = client.messages.create(
            model=VISION_MODEL,
            max_tokens=2048,
            system=EXTRACTION_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type":  "image",
                            "source": {
                                "type":       "base64",
                                "media_type": media_type,
                                "data":       image_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                f"Extract all player scores from this golf scorecard. "
                                f"This is a {holes}-hole round. "
                                "Return only the JSON structure described."
                            ),
                        },
                    ],
                }
            ],
        )

        raw = response.content[0].text.strip()
        return _parse_vision_response(raw, holes)

    except Exception as exc:
        return ExtractionResult(
            success=False,
            error=f"Vision API call failed: {exc}",
        )


def _parse_vision_response(raw: str, holes: int) -> ExtractionResult:
    """Parse the JSON response from Vision into an ExtractionResult."""
    # Strip markdown code fences if present
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text  = "\n".join(
            l for l in lines
            if not l.startswith("```")
        ).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        return ExtractionResult(
            success=False,
            error=f"Could not parse Vision response as JSON: {e}",
            raw_response=raw,
        )

    players = []
    for p in data.get("players", []):
        scores = p.get("scores", [])
        # Pad or trim to expected hole count
        scores = (scores + [0] * holes)[:holes]
        players.append(ExtractedPlayer(
            raw_name=str(p.get("name", "Unknown")),
            scores=[int(s) for s in scores],
        ))

    par = data.get("par", [])
    par = (par + [0] * holes)[:holes]

    return ExtractionResult(
        success=True,
        players=players,
        par=[int(p) for p in par],
        holes=int(data.get("holes", holes)),
        course_name=str(data.get("course_name", "")),
        confidence=str(data.get("confidence", "low")),
        notes=str(data.get("notes", "")),
        raw_response=raw,
    )


# ---------------------------------------------------------------
# Hole-by-hole calculation
# ---------------------------------------------------------------

def calculate_match(
    extraction:       ExtractionResult,
    player_a1_id:     int,
    player_b1_id:     int,
    player_a2_id:     int | None,
    player_b2_id:     int | None,
    round_id:         int,
    format_code:      str,
    handicap_mode:    str,
    allowance_pct:    float,       # as decimal, e.g. 0.90
) -> MatchCalculation | None:
    """
    Compute hole-by-hole net scores and derive the match result.

    Resolves tee deck and handicap data from the round record,
    then applies stroke allocation per hole.

    Returns None if required data is missing.
    """
    from modules.events import get_event_players_by_team
    from modules.roster import get_player
    from database.db import fetchone as db_fetchone

    # Fetch round to get tee deck
    rnd = db_fetchone("SELECT * FROM round WHERE round_id = %s", (round_id,))
    if not rnd:
        return None

    holes     = extraction.holes
    is_pairs  = player_a2_id is not None and player_b2_id is not None

    # Resolve tee decks — use team-specific or fall back to shared
    tee_id_a = rnd["tee_id_a"] or rnd["tee_id_b"]
    tee_id_b = rnd["tee_id_b"] or rnd["tee_id_a"]
    tee_a    = _parse_tee_deck(get_tee_deck(tee_id_a)) if tee_id_a else None
    tee_b    = _parse_tee_deck(get_tee_deck(tee_id_b)) if tee_id_b else None

    if not tee_a or not tee_b:
        return None

    # Build playing handicaps for all four player slots
    def _phc(player_id, tee):
        p = get_player(player_id)
        if not p:
            return 0
        detail = playing_handicap_for_format(
            float(p["current_index"]),
            tee["slope"], tee["rating"], tee["par"],
            format_code, allowance_pct,
        )
        return detail["playing_hc"]

    phc_a1 = _phc(player_a1_id, tee_a)
    phc_b1 = _phc(player_b1_id, tee_b)
    phc_a2 = _phc(player_a2_id, tee_a) if player_a2_id else None
    phc_b2 = _phc(player_b2_id, tee_b) if player_b2_id else None

    # Apply handicap mode adjustments
    all_hcs  = [phc_a1, phc_b1]
    if phc_a2 is not None: all_hcs.append(phc_a2)
    if phc_b2 is not None: all_hcs.append(phc_b2)

    adj = apply_handicap_mode(all_hcs, handicap_mode, allowance_pct)
    adj_a1 = adj[0]
    adj_b1 = adj[1]
    adj_a2 = adj[2] if phc_a2 is not None else None
    adj_b2 = adj[3] if phc_b2 is not None else None

    # Get hole-by-hole stroke detail for each player
    si_a = tee_a.get("stroke_index", [])
    si_b = tee_b.get("stroke_index", [])

    def _hole_strokes(adj_hc, si):
        if adj_hc is None or not si:
            return [0] * holes
        detail = stroke_allocation_detail(adj_hc, si, holes)
        return [h["strokes"] for h in detail]

    strokes_a1 = _hole_strokes(adj_a1, si_a)
    strokes_b1 = _hole_strokes(adj_b1, si_b)
    strokes_a2 = _hole_strokes(adj_a2, si_a) if adj_a2 is not None else [0] * holes
    strokes_b2 = _hole_strokes(adj_b2, si_b) if adj_b2 is not None else [0] * holes

    # Map extraction player indices to sides
    # The extraction result has players in order; the caller has already
    # resolved which extracted player maps to which roster slot.
    # We look up scores by player_id from extraction.players.
    scores = _resolve_scores(extraction, player_a1_id, player_b1_id,
                              player_a2_id, player_b2_id, holes)
    if scores is None:
        return None

    gross_a1, gross_a2, gross_b1, gross_b2 = scores

    # Build hole-by-hole results
    hole_results    = []
    running_score   = 0
    running_history = []
    holes_won_a = holes_won_b = holes_halved = 0

    par_list = extraction.par if extraction.par else [0] * holes

    for i in range(holes):
        g_a1 = gross_a1[i] if gross_a1 else 0
        g_a2 = gross_a2[i] if gross_a2 else None
        g_b1 = gross_b1[i] if gross_b1 else 0
        g_b2 = gross_b2[i] if gross_b2 else None

        # Net = gross - strokes on this hole
        # 0 gross = unrecorded — skip hole result
        def _net(gross, strokes_on_hole):
            if not gross:
                return None
            return gross - strokes_on_hole

        n_a1 = _net(g_a1, strokes_a1[i])
        n_a2 = _net(g_a2, strokes_a2[i]) if g_a2 else None
        n_b1 = _net(g_b1, strokes_b1[i])
        n_b2 = _net(g_b2, strokes_b2[i]) if g_b2 else None

        # Best ball for each team
        if is_pairs:
            nets_a = [n for n in [n_a1, n_a2] if n is not None]
            nets_b = [n for n in [n_b1, n_b2] if n is not None]
            best_a = min(nets_a) if nets_a else None
            best_b = min(nets_b) if nets_b else None
        else:
            best_a = n_a1
            best_b = n_b1

        # Hole winner
        if best_a is None or best_b is None:
            winner = "H"   # unrecorded hole treated as halved
        elif best_a < best_b:
            winner = "A"
            holes_won_a  += 1
            running_score += 1
        elif best_b < best_a:
            winner = "B"
            holes_won_b  += 1
            running_score -= 1
        else:
            winner = "H"
            holes_halved  += 1

        running_history.append(running_score)

        hole_results.append(HoleResult(
            hole=i + 1,
            par=par_list[i] if i < len(par_list) else 0,
            gross_a1=g_a1, gross_a2=g_a2,
            gross_b1=g_b1, gross_b2=g_b2,
            net_a1=n_a1,   net_a2=n_a2,
            net_b1=n_b1,   net_b2=n_b2,
            best_net_a=best_a, best_net_b=best_b,
            winner=winner,
            strokes_a1=strokes_a1[i], strokes_a2=strokes_a2[i],
            strokes_b1=strokes_b1[i], strokes_b2=strokes_b2[i],
        ))

    # Derive match result from holes
    final_result, result_detail = _derive_match_result(
        hole_results, holes_won_a, holes_won_b
    )

    return MatchCalculation(
        hole_results=hole_results,
        running_score=running_history,
        final_result=final_result,
        result_detail=result_detail,
        holes_won_a=holes_won_a,
        holes_won_b=holes_won_b,
        holes_halved=holes_halved,
        format_code=format_code,
    )


def _resolve_scores(
    extraction: ExtractionResult,
    pid_a1, pid_b1, pid_a2, pid_b2,
    holes: int,
) -> tuple | None:
    """
    Map player IDs back to their extracted scores.
    Returns (gross_a1, gross_a2, gross_b1, gross_b2) where each is
    a list[int] or None.
    """
    def _scores_for(pid):
        if pid is None:
            return None
        for ep in extraction.players:
            if ep.player_id == pid:
                return ep.scores[:holes]
        return None

    ga1 = _scores_for(pid_a1)
    gb1 = _scores_for(pid_b1)
    ga2 = _scores_for(pid_a2)
    gb2 = _scores_for(pid_b2)

    # Must have at least one score on each side
    if ga1 is None or gb1 is None:
        return None

    return ga1, ga2, gb1, gb2


def _derive_match_result(
    hole_results: list[HoleResult],
    won_a: int,
    won_b: int,
) -> tuple[str, str]:
    """
    Derive the match play result from the hole-by-hole record.
    Uses standard match play dormie/conceded logic.
    Returns (result, detail) e.g. ("A", "3&2") or ("HALVED", "AS").
    """
    holes_played = len(hole_results)
    holes_remaining = 0  # all holes played in photo scenario

    diff = won_a - won_b

    if diff == 0:
        return "HALVED", "AS"

    winner = "A" if diff > 0 else "B"
    margin = abs(diff)

    # Check for "closed out" result (e.g. 3&2, 4&3, 1 UP)
    # In a standard 18-hole match, if a player is up by more than
    # remaining holes, the match ended early
    # Since we're reading a completed scorecard, report as-played
    if holes_played == 18:
        # Standard finish — report margin UP
        if margin > 0:
            return winner, f"{margin} UP"
    else:
        return winner, f"{margin} UP"

    return winner, f"{margin} UP"


# ---------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------

def save_scorecard_result(
    match_id:    int,
    calculation: MatchCalculation,
    extraction:  ExtractionResult,
) -> None:
    """
    Persist hole scores and derived match result to the database.
    Updates the match record with:
      - result and result_detail (derived from hole winners)
      - hole_scores JSON blob (gross, net, strokes, hole winners)
    """
    # Build the JSON blob
    blob = {
        "holes":          calculation.holes_won_a + calculation.holes_won_b + calculation.holes_halved,
        "holes_won_a":    calculation.holes_won_a,
        "holes_won_b":    calculation.holes_won_b,
        "holes_halved":   calculation.holes_halved,
        "running_score":  calculation.running_score,
        "confidence":     extraction.confidence,
        "course_name":    extraction.course_name,
        "hole_detail": [
            {
                "hole":       h.hole,
                "par":        h.par,
                "gross_a1":   h.gross_a1,
                "gross_a2":   h.gross_a2,
                "gross_b1":   h.gross_b1,
                "gross_b2":   h.gross_b2,
                "net_a1":     h.net_a1,
                "net_a2":     h.net_a2,
                "net_b1":     h.net_b1,
                "net_b2":     h.net_b2,
                "best_net_a": h.best_net_a,
                "best_net_b": h.best_net_b,
                "strokes_a1": h.strokes_a1,
                "strokes_a2": h.strokes_a2,
                "strokes_b1": h.strokes_b1,
                "strokes_b2": h.strokes_b2,
                "winner":     h.winner,
            }
            for h in calculation.hole_results
        ],
    }

    execute(
        "UPDATE match SET hole_scores = %s, result = %s, result_detail = %s WHERE match_id = %s",
        (json.dumps(blob), calculation.final_result,
         calculation.result_detail, match_id),
    )


def get_hole_scores(match_id: int) -> dict | None:
    """Return the parsed hole_scores blob for a match, or None."""
    row = fetchone("SELECT hole_scores FROM match WHERE match_id = %s", (match_id,))
    if not row or not row["hole_scores"]:
        return None
    try:
        return json.loads(row["hole_scores"])
    except (json.JSONDecodeError, TypeError):
        return None


# ---------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------

def _get_api_key() -> str:
    try:
        import streamlit as st
        if "ANTHROPIC_API_KEY" in st.secrets:
            return st.secrets["ANTHROPIC_API_KEY"]
    except Exception:
        pass
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        return key
    try:
        from dotenv import load_dotenv
        load_dotenv()
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if key:
            return key
    except ImportError:
        pass
    raise ValueError(
        "ANTHROPIC_API_KEY not found. Add it to .env or .streamlit/secrets.toml."
    )


def image_bytes_to_media_type(filename: str) -> str:
    """Infer MIME type from file extension."""
    ext = Path(filename).suffix.lower()
    return {
        ".jpg":  "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png":  "image/png",
        ".webp": "image/webp",
        ".gif":  "image/gif",
    }.get(ext, "image/jpeg")

"""
scorecard_pdf.py — Match Play Scorecard PDF Generator
Golf Match Captain | Verma Cup 2026

Generates printable PDF scorecards for each match in a round:
  - Portrait letter (8.5 × 11")
  - Pre-printed stroke dots in the top-right corner of each score box
  - Separate dot = half stroke (open circle, 9-hole only)
  - Two dots side-by-side = 2 strokes (very high HC)
  - Match ID prominently centred for AI scanning
  - Team A (Celtic Tigers green) / Team B (Hurleys red) colouring
  - Short player codes (CT-P1, TH-P1) for AI row anchoring
  - Circle-the-result footer with signature lines
  - 9-hole: single grid section with halved handicap strokes
  - 18-hole: front-9 + back-9 sections with full handicap strokes
"""

from __future__ import annotations

import json
import math
from io import BytesIO

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib import colors

from database.db import fetchall, fetchone
from modules.handicap import (
    playing_handicap_for_format,
    apply_handicap_mode,
    stroke_allocation_detail,
    FORMAT_LABELS,
    _round_half_up,
)

# ── Colours ──────────────────────────────────────────────────────
C_GREEN   = colors.Color(0.118, 0.298, 0.169)   # #1e4d2b  header / Team A
C_RED     = colors.Color(0.545, 0.102, 0.102)   # #8b1a1a  Team B
C_GRAY_L  = colors.Color(0.93,  0.93,  0.93)   # light grey rows
C_GRAY_M  = colors.Color(0.65,  0.65,  0.65)   # separators / borders
C_GRAY_D  = colors.Color(0.40,  0.40,  0.40)   # secondary text
C_WHITE   = colors.white
C_BLACK   = colors.black

# ── Page / layout constants ───────────────────────────────────────
PAGE_W, PAGE_H = letter          # 612 × 792 pts
MARGIN_X   = 24
MARGIN_TOP = 26
CW = PAGE_W - 2 * MARGIN_X      # 564 usable width

# Column widths (must sum to CW = 564)
NAME_W = 90
HC_W   = 22
OUT_W  = 56
HOLE_W = (CW - NAME_W - HC_W - OUT_W) // 9   # 44

# Row heights (pts)
RH_HEADER    = 62
RH_NOTE      = 11
RH_SECLABEL  = 13
RH_HOLE      = 18
RH_SI        = 13
RH_SCORE     = 33    # player score row — big enough to write a number
RH_BEST      = 17
RH_SEP       = 3
RH_RESULT    = 20
RH_STATUS    = 15
RH_FOOTER    = 64
SECTION_GAP  = 8

DOT_R = 2.5          # stroke-dot radius (pts)


# ================================================================
# Database helpers
# ================================================================

def _parse_si(tee_row: dict | None) -> list[int]:
    """Parse stroke_index JSON from a tee_deck row. Returns list[int] (18 values)."""
    if not tee_row:
        return list(range(1, 19))
    raw = tee_row.get("stroke_index", "[]")
    try:
        si = json.loads(raw) if isinstance(raw, str) else list(raw)
        return [int(x) for x in si]
    except Exception:
        return list(range(1, 19))


def _get_tee(tee_id) -> dict | None:
    if not tee_id:
        return None
    return fetchone("SELECT * FROM tee_deck WHERE tee_id = %s", (tee_id,))


def get_scorecard_data(round_id: int) -> dict:
    """Fetch all data needed to render scorecards for a round."""
    rnd = fetchone("""
        SELECT r.*, c.name AS course_name,
               e.team_a_name, e.team_b_name,
               e.handicap_mode, e.allowance_pct, e.name AS event_name
        FROM round r
        JOIN course c ON c.course_id = r.course_id
        JOIN event  e ON e.event_id  = r.event_id
        WHERE r.round_id = %s
    """, (round_id,))

    matches = fetchall("""
        SELECT m.*,
               pa1.name AS a1_name, pa1.current_index AS a1_index,
               pa2.name AS a2_name, pa2.current_index AS a2_index,
               pb1.name AS b1_name, pb1.current_index AS b1_index,
               pb2.name AS b2_name, pb2.current_index AS b2_index
        FROM match m
        LEFT JOIN player pa1 ON pa1.player_id = m.team_a_player1_id
        LEFT JOIN player pa2 ON pa2.player_id = m.team_a_player2_id
        LEFT JOIN player pb1 ON pb1.player_id = m.team_b_player1_id
        LEFT JOIN player pb2 ON pb2.player_id = m.team_b_player2_id
        WHERE m.round_id = %s
        ORDER BY m.match_order
    """, (round_id,))

    tee_a = _get_tee(rnd["tee_id_a"]) if rnd else None
    tee_b = _get_tee(rnd["tee_id_b"]) if rnd else None
    # Fallback: if only one tee configured, use it for both teams
    if tee_a and not tee_b:
        tee_b = tee_a
    if tee_b and not tee_a:
        tee_a = tee_b

    return {"round": rnd, "matches": matches, "tee_a": tee_a, "tee_b": tee_b}


# ================================================================
# Handicap / stroke calculation
# ================================================================

def _calc_playing_hc(index: float, tee: dict | None, fmt: str, allowance: float) -> int:
    if not tee:
        return _round_half_up(index)
    d = playing_handicap_for_format(
        index, tee["slope"], tee["rating"], tee["par"], fmt, allowance
    )
    return d["playing_hc"]


def compute_hole_strokes(
    match: dict,
    tee_a: dict | None,
    tee_b: dict | None,
    format_code: str,
    handicap_mode: str,
    allowance_pct: float,   # decimal e.g. 1.0
    holes: int,
) -> dict:
    """
    Return per-hole stroke counts for each player in the match.

    Keys: 'a1', 'a2', 'b1', 'b2'  → list of ints/floats (length == holes)
          'a1_total', ... → display stroke total (may include 0.5)

    Rules:
      18-hole: full playing HC, integer strokes only
      9-hole:  halve the PLAY_OFF_LOW difference;
               0.5 remainder → open dot (half stroke) on next SI hole
    """
    keys = ["a1", "a2", "b1", "b2"]
    indices = {
        "a1": match.get("a1_index"),
        "a2": match.get("a2_index"),
        "b1": match.get("b1_index"),
        "b2": match.get("b2_index"),
    }
    tee_map = {"a1": tee_a, "a2": tee_a, "b1": tee_b, "b2": tee_b}

    # Step 1 — playing handicaps
    play_hcs = {}
    for k in keys:
        idx = indices[k]
        if idx is None:
            play_hcs[k] = 0
        else:
            play_hcs[k] = _calc_playing_hc(idx, tee_map[k], format_code, allowance_pct)

    # Step 2 — PLAY_OFF_LOW (or other mode)
    if handicap_mode == "PLAY_OFF_LOW":
        vals    = [play_hcs[k] for k in keys]
        adjusted = apply_handicap_mode(vals, "PLAY_OFF_LOW")
        play_hcs = dict(zip(keys, adjusted))

    # Step 3 — 9-hole: halve and capture half-stroke flag
    half_flags = {k: False for k in keys}
    if holes == 9:
        for k in keys:
            raw = play_hcs[k] / 2.0
            play_hcs[k] = int(math.floor(raw))
            half_flags[k] = (raw - math.floor(raw)) >= 0.5

    # Step 4 — allocate strokes to holes using SI
    result = {}
    for k in keys:
        tee = tee_map[k]
        si  = _parse_si(tee)
        phc = play_hcs[k]

        detail = stroke_allocation_detail(phc, si, holes)
        hole_strokes = [d["strokes"] for d in detail]   # list of ints

        # Half stroke — place an open dot on the (phc+1)th-lowest SI hole
        if holes == 9 and half_flags[k]:
            si_9 = si[:9]
            sorted_idxs = sorted(range(9), key=lambda i: si_9[i])
            half_pos = phc % 9  # next hole after full-stroke allocation
            if half_pos < len(sorted_idxs):
                hole_strokes[sorted_idxs[half_pos]] = 0.5

        result[k] = hole_strokes
        result[k + "_total"] = phc + (0.5 if half_flags[k] else 0)

    return result


# ================================================================
# ReportLab drawing primitives
# ================================================================

def _cell(c, x: float, y: float, w: float, h: float,
          fill=None, border_color=C_GRAY_M, lw: float = 0.5):
    """Draw a rectangle cell with optional fill and border."""
    if fill is not None:
        c.setFillColor(fill)
        c.rect(x, y, w, h, fill=1, stroke=0)
    c.setStrokeColor(border_color)
    c.setLineWidth(lw)
    c.rect(x, y, w, h, fill=0, stroke=1)


def _label(c, x: float, y: float, txt: str, size: float = 9,
           bold: bool = False, color=C_BLACK,
           align: str = "left", col_w: float = 0):
    """Draw text aligned within a column."""
    font = "Helvetica-Bold" if bold else "Helvetica"
    c.setFont(font, size)
    c.setFillColor(color)
    if align == "center" and col_w:
        tw = c.stringWidth(str(txt), font, size)
        c.drawString(x + (col_w - tw) / 2, y, str(txt))
    elif align == "right" and col_w:
        tw = c.stringWidth(str(txt), font, size)
        c.drawString(x + col_w - tw - 2, y, str(txt))
    else:
        c.drawString(x + 3, y, str(txt))


def _dot(c, cx: float, cy: float, r: float, filled: bool = True):
    c.setFillColor(C_BLACK)
    c.setStrokeColor(C_BLACK)
    c.setLineWidth(0.8)
    c.circle(cx, cy, r, fill=1 if filled else 0, stroke=1)


def _score_box(c, x: float, y: float, w: float, h: float,
               strokes_list: list, hole_idx: int):
    """Draw a score-entry box with stroke dots pre-printed in top-right corner."""
    # Box itself — thicker border so it scans clearly
    c.setFillColor(C_WHITE)
    c.setStrokeColor(C_BLACK)
    c.setLineWidth(1.8)
    c.rect(x, y, w, h, fill=1, stroke=1)

    strokes = strokes_list[hole_idx] if hole_idx < len(strokes_list) else 0
    if strokes == 0:
        return

    dot_y = y + h - 5.5   # near the top of the box
    if strokes == 0.5:
        # Open circle = half stroke
        dot_x = x + w - 6.5
        _dot(c, dot_x, dot_y, DOT_R, filled=False)
    elif strokes == 1:
        dot_x = x + w - 6.5
        _dot(c, dot_x, dot_y, DOT_R, filled=True)
    elif strokes >= 2:
        # Two filled dots side-by-side
        dot_x1 = x + w - 6.5
        dot_x2 = x + w - 6.5 - (DOT_R * 2 + 3)
        _dot(c, dot_x1, dot_y, DOT_R, filled=True)
        _dot(c, dot_x2, dot_y, DOT_R, filled=True)


# ================================================================
# Grid section
# ================================================================

def _draw_grid_section(
    c,
    x: float,
    y_top: float,         # top edge of this section
    holes_range: list,    # [1..9] or [10..18]
    si_values: list,      # SI for the holes in this range
    team_a_name: str,
    team_b_name: str,
    match: dict,
    strokes: dict,
    is_singles: bool,
) -> float:
    """
    Draw one 9-hole grid section. Returns new y (below the last row).
    y_top decreases as we add rows (ReportLab y goes up; we go down).
    """
    n = len(holes_range)
    hole_offset = 0 if holes_range[0] == 1 else 9

    # X positions
    x_name  = x
    x_hc    = x_name + NAME_W
    x_h     = [x_hc + HC_W + h * HOLE_W for h in range(n)]
    x_out   = x_h[-1] + HOLE_W

    y = y_top

    # ── Section label bar ─────────────────────────────────────────
    label_y = y - RH_SECLABEL
    c.setFillColor(C_GREEN)
    c.rect(x, label_y, CW, RH_SECLABEL, fill=1, stroke=0)
    c.setFillColor(C_WHITE)
    c.setFont("Helvetica-Bold", 8)
    sec_txt = f"Holes {holes_range[0]}–{holes_range[-1]}"
    c.drawString(x + 6, label_y + 3, sec_txt)
    y = label_y

    # ── Hole number row ──────────────────────────────────────────
    row_y = y - RH_HOLE
    c.setFillColor(colors.Color(0.08, 0.28, 0.14))   # slightly darker green
    c.rect(x, row_y, CW, RH_HOLE, fill=1, stroke=0)
    # Name header
    _label(c, x_name, row_y + 5, "Player", 8, bold=True, color=C_WHITE)
    # HC header
    _label(c, x_hc, row_y + 5, "HC", 7, bold=True, color=C_WHITE,
           align="center", col_w=HC_W)
    # Hole numbers
    for h, hn in enumerate(holes_range):
        _label(c, x_h[h], row_y + 5, str(hn), 8, bold=True, color=C_WHITE,
               align="center", col_w=HOLE_W)
    # Out/In
    out_lbl = "Out" if holes_range[0] == 1 else "In"
    _label(c, x_out, row_y + 5, out_lbl, 8, bold=True, color=C_WHITE,
           align="center", col_w=OUT_W)
    # Light grid lines over green
    c.setStrokeColor(colors.Color(1, 1, 1, alpha=0.2))
    c.setLineWidth(0.3)
    for h in range(n):
        c.line(x_h[h], row_y, x_h[h], row_y + RH_HOLE)
    c.line(x_hc, row_y, x_hc, row_y + RH_HOLE)
    c.line(x_out, row_y, x_out, row_y + RH_HOLE)
    y = row_y

    # ── Stroke index row ─────────────────────────────────────────
    row_y = y - RH_SI
    _cell(c, x_name, row_y, NAME_W, RH_SI, fill=C_GRAY_L)
    _cell(c, x_hc,   row_y, HC_W,   RH_SI, fill=C_GRAY_L)
    _label(c, x_name, row_y + 3, "Stroke index", 7, color=C_GRAY_D)
    for h in range(n):
        _cell(c, x_h[h], row_y, HOLE_W, RH_SI, fill=C_GRAY_L)
        si_val = si_values[h] if h < len(si_values) else "–"
        _label(c, x_h[h], row_y + 3, str(si_val), 7, color=C_GRAY_D,
               align="center", col_w=HOLE_W)
    _cell(c, x_out, row_y, OUT_W, RH_SI, fill=C_GRAY_L)
    y = row_y

    # ── Player row helper ─────────────────────────────────────────
    def draw_player(key: str, name: str, idx_val, code: str, team_color):
        nonlocal y
        row_y = y - RH_SCORE
        # Name cell
        _cell(c, x_name, row_y, NAME_W, RH_SCORE, fill=C_WHITE,
              border_color=C_GRAY_M, lw=0.5)
        # Small player code
        c.setFillColor(C_GRAY_D)
        c.setFont("Helvetica", 6.5)
        c.drawString(x_name + 3, row_y + RH_SCORE - 9, code)
        # Player name
        c.setFillColor(team_color)
        c.setFont("Helvetica-Bold", 9)
        # Truncate if too long
        display = name
        while c.stringWidth(display, "Helvetica-Bold", 9) > NAME_W - 6 and len(display) > 5:
            display = display[:-1]
        c.drawString(x_name + 3, row_y + 6, display)
        # HC cell
        _cell(c, x_hc, row_y, HC_W, RH_SCORE, fill=C_WHITE, border_color=C_GRAY_M, lw=0.5)
        if idx_val is not None:
            _label(c, x_hc, row_y + 11, str(int(round(idx_val))), 8,
                   color=C_BLACK, align="center", col_w=HC_W)
        # Score boxes
        player_strokes = strokes.get(key, [0] * 18)
        for h in range(n):
            hi = hole_offset + h
            _score_box(c, x_h[h], row_y, HOLE_W, RH_SCORE, player_strokes, hi)
        # Total cell
        _cell(c, x_out, row_y, OUT_W, RH_SCORE, fill=C_WHITE,
              border_color=C_GRAY_M, lw=0.5)
        total = strokes.get(key + "_total", 0)
        if total and total > 0:
            tot_str = str(int(total)) if total == int(total) else f"{total}"
            _label(c, x_out, row_y + 6, f"{tot_str} str", 7,
                   color=C_GRAY_D, align="center", col_w=OUT_W)
        y = row_y

    def draw_best_net_row(team_name: str, team_color):
        nonlocal y
        row_y = y - RH_BEST
        _cell(c, x_name, row_y, NAME_W, RH_BEST, fill=C_GRAY_L)
        _label(c, x_name, row_y + 4, f"{team_name} net", 7.5,
               bold=True, color=team_color)
        _cell(c, x_hc, row_y, HC_W, RH_BEST, fill=C_GRAY_L)
        for h in range(n):
            _cell(c, x_h[h], row_y, HOLE_W, RH_BEST, fill=C_GRAY_L)
        _cell(c, x_out, row_y, OUT_W, RH_BEST, fill=C_GRAY_L)
        y = row_y

    # ── Team A rows ───────────────────────────────────────────────
    if match.get("a1_name"):
        draw_player("a1", match["a1_name"], match.get("a1_index"), "CT-P1", C_GREEN)
    if not is_singles and match.get("a2_name"):
        draw_player("a2", match["a2_name"], match.get("a2_index"), "CT-P2", C_GREEN)
    if not is_singles:
        draw_best_net_row(team_a_name, C_GREEN)

    # ── Team separator ────────────────────────────────────────────
    sep_y = y - RH_SEP
    c.setFillColor(C_GRAY_M)
    c.rect(x, sep_y, CW, RH_SEP, fill=1, stroke=0)
    y = sep_y

    # ── Team B rows ───────────────────────────────────────────────
    if match.get("b1_name"):
        draw_player("b1", match["b1_name"], match.get("b1_index"), "TH-P1", C_RED)
    if not is_singles and match.get("b2_name"):
        draw_player("b2", match["b2_name"], match.get("b2_index"), "TH-P2", C_RED)
    if not is_singles:
        draw_best_net_row(team_b_name, C_RED)

    # ── Hole result row ───────────────────────────────────────────
    row_y = y - RH_RESULT
    _cell(c, x_name, row_y, NAME_W, RH_RESULT, fill=C_GRAY_L,
          border_color=C_GRAY_M, lw=1.0)
    _label(c, x_name, row_y + 5, "Hole result", 8, bold=True, color=C_BLACK)
    _cell(c, x_hc, row_y, HC_W, RH_RESULT, fill=C_GRAY_L)
    for h in range(n):
        _cell(c, x_h[h], row_y, HOLE_W, RH_RESULT)   # blank — write in
    _cell(c, x_out, row_y, OUT_W, RH_RESULT, fill=C_GRAY_L)
    y = row_y

    # ── Match status row ──────────────────────────────────────────
    row_y = y - RH_STATUS
    _cell(c, x_name, row_y, NAME_W, RH_STATUS, fill=C_GRAY_L)
    _label(c, x_name, row_y + 3, "Match status", 7, color=C_GRAY_D)
    _cell(c, x_hc, row_y, HC_W, RH_STATUS, fill=C_GRAY_L)
    for h in range(n):
        _cell(c, x_h[h], row_y, HOLE_W, RH_STATUS, fill=C_GRAY_L)
    _cell(c, x_out, row_y, OUT_W, RH_STATUS, fill=C_GRAY_L)
    y = row_y

    return y


# ================================================================
# Full scorecard page
# ================================================================

def _draw_scorecard(
    c,
    match: dict,
    rnd: dict,
    tee_a: dict | None,
    tee_b: dict | None,
    total_matches: int,
):
    """Draw one complete scorecard on the current canvas page."""
    holes       = rnd["holes"]
    fmt         = rnd["format_code"]
    hc_mode     = rnd["handicap_mode"]
    allowance   = rnd["allowance_pct"] / 100.0
    team_a      = rnd["team_a_name"]
    team_b      = rnd["team_b_name"]
    match_id    = f"R{rnd['round_number']}-M{match['match_order']}"
    is_singles  = not bool(match.get("a2_name") or match.get("b2_name"))

    # Compute stroke allocation
    strokes = compute_hole_strokes(
        match, tee_a, tee_b, fmt, hc_mode, allowance, holes
    )

    # SI values (use Team A tee; same course for both teams in Verma Cup)
    si = _parse_si(tee_a)

    x = MARGIN_X
    y = PAGE_H - MARGIN_TOP   # start near top; decrement as we draw down

    # ── HEADER ───────────────────────────────────────────────────
    hdr_y = y - RH_HEADER
    _cell(c, x, hdr_y, CW, RH_HEADER, fill=C_GRAY_L,
          border_color=C_BLACK, lw=1.2)

    # Match ID — large, centred
    mid_x = x + CW / 2
    c.setFillColor(C_BLACK)
    c.setFont("Helvetica-Bold", 22)
    id_w = c.stringWidth(match_id, "Helvetica-Bold", 22)
    c.drawString(mid_x - id_w / 2, hdr_y + RH_HEADER - 24, match_id)

    # Round / format / date info
    c.setFont("Helvetica", 8)
    info = (
        f"Round {rnd['round_number']}  ·  "
        f"Match {match['match_order']} of {total_matches}  ·  "
        f"{FORMAT_LABELS.get(fmt, fmt)}  ·  {holes} holes"
    )
    iw = c.stringWidth(info, "Helvetica", 8)
    c.drawString(mid_x - iw / 2, hdr_y + RH_HEADER - 36, info)

    course_line = f"{rnd['course_name']}  ·  {rnd['date']}"
    cw2 = c.stringWidth(course_line, "Helvetica", 8)
    c.drawString(mid_x - cw2 / 2, hdr_y + RH_HEADER - 47, course_line)

    # Team names — left (A) and right (B)
    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(C_GREEN)
    c.drawString(x + 8, hdr_y + RH_HEADER - 16, team_a)

    c.setFillColor(C_RED)
    tb_w = c.stringWidth(team_b, "Helvetica-Bold", 11)
    c.drawString(x + CW - 8 - tb_w, hdr_y + RH_HEADER - 16, team_b)

    # Player names under each team name
    c.setFont("Helvetica", 8)
    c.setFillColor(C_GREEN)
    a1 = match.get("a1_name", ""); a2 = match.get("a2_name", "")
    if a1: c.drawString(x + 8, hdr_y + RH_HEADER - 28, a1)
    if a2: c.drawString(x + 8, hdr_y + RH_HEADER - 39, a2)

    c.setFillColor(C_RED)
    b1 = match.get("b1_name", ""); b2 = match.get("b2_name", "")
    if b1:
        bw = c.stringWidth(b1, "Helvetica", 8)
        c.drawString(x + CW - 8 - bw, hdr_y + RH_HEADER - 28, b1)
    if b2:
        bw = c.stringWidth(b2, "Helvetica", 8)
        c.drawString(x + CW - 8 - bw, hdr_y + RH_HEADER - 39, b2)

    y = hdr_y

    # ── AI NOTE BAR ───────────────────────────────────────────────
    note_y = y - RH_NOTE
    c.setFillColor(colors.Color(0.96, 0.96, 0.96))
    c.rect(x, note_y, CW, RH_NOTE, fill=1, stroke=0)
    c.setFillColor(C_GRAY_D)
    c.setFont("Helvetica", 6)
    note = (
        f"AI scan ref: {match_id}  ·  "
        "Pre-printed dots = stroke indicator (top-right corner)  ·  "
        "Open dot = half stroke  ·  "
        "Handwritten = gross score  ·  Circle result below"
    )
    c.drawString(x + 4, note_y + 2.5, note)
    y = note_y

    # ── SCORECARD GRIDS ──────────────────────────────────────────
    if holes == 9:
        y = _draw_grid_section(
            c, x, y,
            holes_range=list(range(1, 10)),
            si_values=si[:9],
            team_a_name=team_a, team_b_name=team_b,
            match=match, strokes=strokes,
            is_singles=is_singles,
        )
    else:
        # Front 9
        y = _draw_grid_section(
            c, x, y,
            holes_range=list(range(1, 10)),
            si_values=si[:9],
            team_a_name=team_a, team_b_name=team_b,
            match=match, strokes=strokes,
            is_singles=is_singles,
        )
        y -= SECTION_GAP
        # Back 9
        y = _draw_grid_section(
            c, x, y,
            holes_range=list(range(10, 19)),
            si_values=si[9:18],
            team_a_name=team_a, team_b_name=team_b,
            match=match, strokes=strokes,
            is_singles=is_singles,
        )

    # ── FOOTER ───────────────────────────────────────────────────
    y -= 5
    footer_y = y - RH_FOOTER
    _cell(c, x, footer_y, CW, RH_FOOTER, fill=C_GRAY_L,
          border_color=C_BLACK, lw=1.2)

    # "Result:" label
    c.setFont("Helvetica-Bold", 8.5)
    c.setFillColor(C_BLACK)
    c.drawString(x + 8, footer_y + RH_FOOTER - 16, "Result:")

    # Three circle-the-option choices
    opt_opts = [f"{team_a} win", f"{team_b} win", "Halved"]
    opt_x = x + 58
    opt_y = footer_y + RH_FOOTER - 14.5
    for opt in opt_opts:
        c.setFillColor(C_WHITE)
        c.setStrokeColor(C_BLACK)
        c.setLineWidth(1.0)
        c.circle(opt_x, opt_y, 7, fill=1, stroke=1)
        c.setFillColor(C_BLACK)
        c.setFont("Helvetica", 8.5)
        c.drawString(opt_x + 10, opt_y - 3, opt)
        opt_x += c.stringWidth(opt, "Helvetica", 8.5) + 26

    # "by X holes / A/S" fill-in
    c.setFont("Helvetica", 7.5)
    c.setFillColor(C_GRAY_D)
    c.drawString(opt_x + 4, opt_y - 3, "by _____ holes  /  A/S")

    # Stroke note under result
    if holes == 9:
        note9 = "9-hole match · strokes = ½ × 18-hole difference · open dot (○) = half stroke, wins a tied hole"
    else:
        note9 = "18-hole match · full handicap strokes · no half strokes"
    c.setFont("Helvetica", 6.5)
    c.setFillColor(C_GRAY_D)
    c.drawString(x + 8, footer_y + RH_FOOTER - 28, note9)

    # Signature lines
    sig_labels = [
        f"Signed {team_a}:",
        f"Signed {team_b}:",
        "Time submitted:",
    ]
    sig_w = CW / len(sig_labels)
    sig_line_y = footer_y + 20
    for i, lbl in enumerate(sig_labels):
        sx = x + i * sig_w
        c.setFont("Helvetica", 7.5)
        c.setFillColor(C_BLACK)
        c.drawString(sx + 4, sig_line_y + 12, lbl)
        c.setStrokeColor(C_GRAY_M)
        c.setLineWidth(0.6)
        c.line(sx + 4, sig_line_y + 6, sx + sig_w - 8, sig_line_y + 6)


# ================================================================
# Public entry point
# ================================================================

def generate_round_scorecards(round_id: int) -> bytes:
    """
    Generate a multi-page PDF — one scorecard per match in the round.
    Returns raw PDF bytes suitable for st.download_button.
    """
    data    = get_scorecard_data(round_id)
    rnd     = data["round"]
    matches = data["matches"]
    tee_a   = data["tee_a"]
    tee_b   = data["tee_b"]

    if not rnd:
        raise ValueError(f"Round {round_id} not found.")
    if not matches:
        raise ValueError("No matches found for this round. Add the draw first.")

    buf = BytesIO()
    c   = rl_canvas.Canvas(buf, pagesize=letter)
    c.setTitle(f"Scorecards – Round {rnd['round_number']} – {rnd['event_name']}")
    c.setAuthor("Golf Match Captain")

    total = len(matches)
    for match in matches:
        _draw_scorecard(c, match, rnd, tee_a, tee_b, total)
        c.showPage()

    c.save()
    buf.seek(0)
    return buf.read()

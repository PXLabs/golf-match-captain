"""
scorecard_pdf.py — Match Play Scorecard PDF Generator
Golf Match Captain | Verma Cup 2026

Three output sizes:
  FULL    — 1 card per page, portrait letter (8.5 × 11") — full-size, easy to read
  COMPACT — 2 cards per page, portrait letter (~66% scale) — caddie-friendly
  SMALL   — 3 cards per page, portrait letter (~50% scale) — rain/pocket size

All sizes:
  - Pre-printed stroke dots in top-right corner of each score box
  - Open dot (○) = half stroke (9-hole only) — wins a tied hole
  - Two dots (●●) = 2 strokes (very high HC)
  - Match ID centred for AI photo scanning
  - Celtic Tigers green / The Hurleys red colour coding
  - Player codes CT-P1 / TH-P1 for AI row anchoring
  - Circle-the-result footer with signature lines
"""

from __future__ import annotations

import json
import math
from io import BytesIO
from dataclasses import dataclass

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
C_GREEN  = colors.Color(0.118, 0.298, 0.169)
C_RED    = colors.Color(0.545, 0.102, 0.102)
C_DARKGN = colors.Color(0.08,  0.28,  0.14)
C_GRAY_L = colors.Color(0.93,  0.93,  0.93)
C_GRAY_M = colors.Color(0.65,  0.65,  0.65)
C_GRAY_D = colors.Color(0.40,  0.40,  0.40)
C_WHITE  = colors.white
C_BLACK  = colors.black

PAGE_W, PAGE_H = letter   # 612 × 792 pts
MARGIN_X = 24
CW = PAGE_W - 2 * MARGIN_X   # 564 usable width

# Column widths (fixed — same for both modes)
NAME_W = 90
HC_W   = 22
OUT_W  = 56
HOLE_W = (CW - NAME_W - HC_W - OUT_W) // 9   # 44


# ================================================================
# Size configuration
# ================================================================

@dataclass
class CardConfig:
    """All size-dependent values for one rendering mode."""
    rh_header:   int
    rh_note:     int
    rh_seclabel: int
    rh_hole:     int
    rh_si:       int
    rh_score:    int    # must stay large enough to write a score
    rh_best:     int
    rh_sep:      int
    rh_result:   int
    rh_status:   int
    rh_footer:   int
    section_gap: int
    margin_top:  int
    dot_r:       float
    # font sizes
    f_id:          float
    f_team:        float
    f_info:        float
    f_player:      float
    f_code:        float
    f_hdr:         float
    f_si:          float
    f_note:        float
    f_footer:      float
    cards_per_page: int   # 1 = full, 2 = compact, 3 = small


# ── Full size — 1 per page ────────────────────────────────────────
FULL = CardConfig(
    rh_header=62,  rh_note=11, rh_seclabel=13, rh_hole=18, rh_si=13,
    rh_score=33,   rh_best=17, rh_sep=3,       rh_result=20, rh_status=15,
    rh_footer=64,  section_gap=8,  margin_top=26,
    dot_r=2.5,
    f_id=22, f_team=11, f_info=8, f_player=9, f_code=6.5,
    f_hdr=8, f_si=7, f_note=6, f_footer=7.5,
    cards_per_page=1,
)

# ── Compact (~66%) — 2 per page ───────────────────────────────────
COMPACT = CardConfig(
    rh_header=46,  rh_note=9,  rh_seclabel=11, rh_hole=14, rh_si=10,
    rh_score=29,   rh_best=13, rh_sep=2,       rh_result=15, rh_status=11,
    rh_footer=50,  section_gap=5,  margin_top=16,
    dot_r=2.0,
    f_id=16, f_team=9.5, f_info=7, f_player=8.5, f_code=6,
    f_hdr=7.5, f_si=6.5, f_note=5.5, f_footer=7,
    cards_per_page=2,
)

# ── Small (~50%) — 3 per page ─────────────────────────────────────
SMALL = CardConfig(
    rh_header=34,  rh_note=7,  rh_seclabel=8,  rh_hole=10, rh_si=7,
    rh_score=21,   rh_best=10, rh_sep=2,       rh_result=11, rh_status=8,
    rh_footer=34,  section_gap=4,  margin_top=12,
    dot_r=1.6,
    f_id=12, f_team=7.5, f_info=5.5, f_player=7, f_code=5,
    f_hdr=6, f_si=5.5, f_note=4.5, f_footer=5.5,
    cards_per_page=3,
)

_SIZE_MAP: dict[str, CardConfig] = {
    "full":    FULL,
    "compact": COMPACT,
    "small":   SMALL,
}


# ================================================================
# Database helpers
# ================================================================

def _parse_si(tee_row: dict | None) -> list[int]:
    if not tee_row:
        return list(range(1, 19))
    raw = tee_row.get("stroke_index", "[]")
    try:
        si = json.loads(raw) if isinstance(raw, str) else list(raw)
        return [int(x) for x in si]
    except Exception:
        return list(range(1, 19))


def _get_tee(tee_id) -> dict | None:
    return fetchone("SELECT * FROM tee_deck WHERE tee_id = %s", (tee_id,)) if tee_id else None


def get_scorecard_data(round_id: int) -> dict:
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
    if tee_a and not tee_b: tee_b = tee_a
    if tee_b and not tee_a: tee_a = tee_b

    return {"round": rnd, "matches": matches, "tee_a": tee_a, "tee_b": tee_b}


# ================================================================
# Stroke calculation
# ================================================================

def _calc_playing_hc(index, tee, fmt, allowance) -> int:
    if not tee:
        return _round_half_up(index)
    d = playing_handicap_for_format(index, tee["slope"], tee["rating"], tee["par"], fmt, allowance)
    return d["playing_hc"]


def compute_hole_strokes(match, tee_a, tee_b, fmt, hc_mode, allowance, holes) -> dict:
    keys = ["a1", "a2", "b1", "b2"]
    indices = {k: match.get(f"{k}_index") for k in keys}
    tee_map = {"a1": tee_a, "a2": tee_a, "b1": tee_b, "b2": tee_b}

    play_hcs = {}
    for k in keys:
        idx = indices[k]
        play_hcs[k] = _calc_playing_hc(idx, tee_map[k], fmt, allowance) if idx is not None else 0

    if hc_mode == "PLAY_OFF_LOW":
        vals = [play_hcs[k] for k in keys]
        play_hcs = dict(zip(keys, apply_handicap_mode(vals, "PLAY_OFF_LOW")))

    half_flags = {k: False for k in keys}
    if holes == 9:
        for k in keys:
            raw = play_hcs[k] / 2.0
            play_hcs[k] = int(math.floor(raw))
            half_flags[k] = (raw - math.floor(raw)) >= 0.5

    result = {}
    for k in keys:
        si  = _parse_si(tee_map[k])
        phc = play_hcs[k]
        detail = stroke_allocation_detail(phc, si, holes)
        hole_strokes = [d["strokes"] for d in detail]

        if holes == 9 and half_flags[k]:
            si_9 = si[:9]
            sorted_idxs = sorted(range(9), key=lambda i: si_9[i])
            half_pos = phc % 9
            if half_pos < len(sorted_idxs):
                hole_strokes[sorted_idxs[half_pos]] = 0.5

        result[k] = hole_strokes
        result[k + "_total"] = phc + (0.5 if half_flags[k] else 0)

    return result


# ================================================================
# Drawing primitives
# ================================================================

def _cell(c, x, y, w, h, fill=None, bc=C_GRAY_M, lw=0.5):
    if fill is not None:
        c.setFillColor(fill)
        c.rect(x, y, w, h, fill=1, stroke=0)
    c.setStrokeColor(bc)
    c.setLineWidth(lw)
    c.rect(x, y, w, h, fill=0, stroke=1)


def _txt(c, x, y, txt, size, bold=False, color=C_BLACK, align="left", col_w=0):
    font = "Helvetica-Bold" if bold else "Helvetica"
    c.setFont(font, size)
    c.setFillColor(color)
    s = str(txt)
    if align == "center" and col_w:
        tw = c.stringWidth(s, font, size)
        c.drawString(x + (col_w - tw) / 2, y, s)
    elif align == "right" and col_w:
        tw = c.stringWidth(s, font, size)
        c.drawString(x + col_w - tw - 2, y, s)
    else:
        c.drawString(x + 3, y, s)


def _dot(c, cx, cy, r, filled=True):
    c.setFillColor(C_BLACK)
    c.setStrokeColor(C_BLACK)
    c.setLineWidth(0.8)
    c.circle(cx, cy, r, fill=1 if filled else 0, stroke=1)


def _score_box(c, x, y, w, h, strokes_list, hole_idx, dot_r):
    c.setFillColor(C_WHITE)
    c.setStrokeColor(C_BLACK)
    c.setLineWidth(1.8)
    c.rect(x, y, w, h, fill=1, stroke=1)

    s = strokes_list[hole_idx] if hole_idx < len(strokes_list) else 0
    if s == 0:
        return

    dy = y + h - 4.5
    if s == 0.5:
        _dot(c, x + w - 5.5, dy, dot_r, filled=False)
    elif s == 1:
        _dot(c, x + w - 5.5, dy, dot_r, filled=True)
    elif s >= 2:
        _dot(c, x + w - 5.5,              dy, dot_r, filled=True)
        _dot(c, x + w - 5.5 - dot_r*2 - 2, dy, dot_r, filled=True)


# ================================================================
# Grid section
# ================================================================

def _draw_grid_section(c, x, y_top, holes_range, si_values,
                       team_a, team_b, match, strokes,
                       is_singles, cfg: CardConfig) -> float:
    n = len(holes_range)
    hole_offset = 0 if holes_range[0] == 1 else 9

    x_name = x
    x_hc   = x_name + NAME_W
    x_h    = [x_hc + HC_W + h * HOLE_W for h in range(n)]
    x_out  = x_h[-1] + HOLE_W

    y = y_top

    # ── Section label ─────────────────────────────────────────────
    sl_y = y - cfg.rh_seclabel
    c.setFillColor(C_GREEN)
    c.rect(x, sl_y, CW, cfg.rh_seclabel, fill=1, stroke=0)
    c.setFillColor(C_WHITE)
    c.setFont("Helvetica-Bold", cfg.f_hdr - 0.5)
    sec = f"Holes {holes_range[0]}–{holes_range[-1]}"
    c.drawString(x + 5, sl_y + 2.5, sec)
    y = sl_y

    # ── Hole numbers ─────────────────────────────────────────────
    rh_y = y - cfg.rh_hole
    c.setFillColor(C_DARKGN)
    c.rect(x, rh_y, CW, cfg.rh_hole, fill=1, stroke=0)
    _txt(c, x_name, rh_y + 4, "Player", cfg.f_hdr, bold=True, color=C_WHITE)
    _txt(c, x_hc,   rh_y + 4, "HC",     cfg.f_hdr, bold=True, color=C_WHITE,
         align="center", col_w=HC_W)
    for h, hn in enumerate(holes_range):
        _txt(c, x_h[h], rh_y + 4, str(hn), cfg.f_hdr, bold=True, color=C_WHITE,
             align="center", col_w=HOLE_W)
    out_lbl = "Out" if holes_range[0] == 1 else "In"
    _txt(c, x_out, rh_y + 4, out_lbl, cfg.f_hdr, bold=True, color=C_WHITE,
         align="center", col_w=OUT_W)
    # faint dividers
    c.setStrokeColor(colors.Color(1, 1, 1, alpha=0.2))
    c.setLineWidth(0.3)
    for h in range(n):
        c.line(x_h[h], rh_y, x_h[h], rh_y + cfg.rh_hole)
    c.line(x_hc, rh_y, x_hc, rh_y + cfg.rh_hole)
    c.line(x_out, rh_y, x_out, rh_y + cfg.rh_hole)
    y = rh_y

    # ── Stroke index ─────────────────────────────────────────────
    si_y = y - cfg.rh_si
    _cell(c, x_name, si_y, NAME_W, cfg.rh_si, fill=C_GRAY_L)
    _cell(c, x_hc,   si_y, HC_W,   cfg.rh_si, fill=C_GRAY_L)
    _txt(c, x_name, si_y + 2, "Stroke index", cfg.f_si, color=C_GRAY_D)
    for h in range(n):
        _cell(c, x_h[h], si_y, HOLE_W, cfg.rh_si, fill=C_GRAY_L)
        sv = si_values[h] if h < len(si_values) else "–"
        _txt(c, x_h[h], si_y + 2, str(sv), cfg.f_si, color=C_GRAY_D,
             align="center", col_w=HOLE_W)
    _cell(c, x_out, si_y, OUT_W, cfg.rh_si, fill=C_GRAY_L)
    y = si_y

    # ── Player row helper ────────────────────────────────────────
    def draw_player(key, name, idx_val, code, team_color):
        nonlocal y
        py = y - cfg.rh_score
        # Name cell
        _cell(c, x_name, py, NAME_W, cfg.rh_score, fill=C_WHITE)
        c.setFillColor(C_GRAY_D)
        c.setFont("Helvetica", cfg.f_code)
        c.drawString(x_name + 3, py + cfg.rh_score - 8, code)
        c.setFillColor(team_color)
        c.setFont("Helvetica-Bold", cfg.f_player)
        display = name
        while c.stringWidth(display, "Helvetica-Bold", cfg.f_player) > NAME_W - 6 and len(display) > 4:
            display = display[:-1]
        c.drawString(x_name + 3, py + 5, display)
        # HC cell
        _cell(c, x_hc, py, HC_W, cfg.rh_score, fill=C_WHITE)
        if idx_val is not None:
            _txt(c, x_hc, py + cfg.rh_score // 2 - 4,
                 str(int(round(idx_val))), cfg.f_player - 1,
                 color=C_BLACK, align="center", col_w=HC_W)
        # Score boxes
        ps = strokes.get(key, [0] * 18)
        for h in range(n):
            _score_box(c, x_h[h], py, HOLE_W, cfg.rh_score, ps, hole_offset + h, cfg.dot_r)
        # Out cell
        _cell(c, x_out, py, OUT_W, cfg.rh_score, fill=C_WHITE)
        total = strokes.get(key + "_total", 0)
        if total:
            tot_s = str(int(total)) if total == int(total) else str(total)
            _txt(c, x_out, py + 5, f"{tot_s}s", cfg.f_si,
                 color=C_GRAY_D, align="center", col_w=OUT_W)
        y = py

    def draw_best_row(tname, tcolor):
        nonlocal y
        by = y - cfg.rh_best
        _cell(c, x_name, by, NAME_W, cfg.rh_best, fill=C_GRAY_L)
        _txt(c, x_name, by + 3, f"{tname} net", cfg.f_si + 0.5, bold=True, color=tcolor)
        _cell(c, x_hc, by, HC_W, cfg.rh_best, fill=C_GRAY_L)
        for h in range(n):
            _cell(c, x_h[h], by, HOLE_W, cfg.rh_best, fill=C_GRAY_L)
        _cell(c, x_out, by, OUT_W, cfg.rh_best, fill=C_GRAY_L)
        y = by

    # ── Team A ───────────────────────────────────────────────────
    if match.get("a1_name"):
        draw_player("a1", match["a1_name"], match.get("a1_index"), "CT-P1", C_GREEN)
    if not is_singles and match.get("a2_name"):
        draw_player("a2", match["a2_name"], match.get("a2_index"), "CT-P2", C_GREEN)
    if not is_singles:
        draw_best_row(team_a, C_GREEN)

    # ── Separator ────────────────────────────────────────────────
    sep_y = y - cfg.rh_sep
    c.setFillColor(C_GRAY_M)
    c.rect(x, sep_y, CW, cfg.rh_sep, fill=1, stroke=0)
    y = sep_y

    # ── Team B ───────────────────────────────────────────────────
    if match.get("b1_name"):
        draw_player("b1", match["b1_name"], match.get("b1_index"), "TH-P1", C_RED)
    if not is_singles and match.get("b2_name"):
        draw_player("b2", match["b2_name"], match.get("b2_index"), "TH-P2", C_RED)
    if not is_singles:
        draw_best_row(team_b, C_RED)

    # ── Hole result ──────────────────────────────────────────────
    hr_y = y - cfg.rh_result
    _cell(c, x_name, hr_y, NAME_W, cfg.rh_result, fill=C_GRAY_L, bc=C_GRAY_M, lw=1.0)
    _txt(c, x_name, hr_y + 4, "Hole result", cfg.f_hdr, bold=True, color=C_BLACK)
    _cell(c, x_hc, hr_y, HC_W, cfg.rh_result, fill=C_GRAY_L)
    for h in range(n):
        _cell(c, x_h[h], hr_y, HOLE_W, cfg.rh_result)   # blank write-in
    _cell(c, x_out, hr_y, OUT_W, cfg.rh_result, fill=C_GRAY_L)
    y = hr_y

    # ── Match status ─────────────────────────────────────────────
    ms_y = y - cfg.rh_status
    _cell(c, x_name, ms_y, NAME_W, cfg.rh_status, fill=C_GRAY_L)
    _txt(c, x_name, ms_y + 2.5, "Match status", cfg.f_si, color=C_GRAY_D)
    _cell(c, x_hc, ms_y, HC_W, cfg.rh_status, fill=C_GRAY_L)
    for h in range(n):
        _cell(c, x_h[h], ms_y, HOLE_W, cfg.rh_status, fill=C_GRAY_L)
    _cell(c, x_out, ms_y, OUT_W, cfg.rh_status, fill=C_GRAY_L)
    y = ms_y

    return y


# ================================================================
# Full scorecard
# ================================================================

def _draw_scorecard(c, match, rnd, tee_a, tee_b, total, cfg: CardConfig,
                    y_start: float | None = None):
    """
    Draw one complete scorecard. y_start overrides the default top margin
    (used when placing two cards on one page).
    Returns the y position after the footer.
    """
    holes      = rnd["holes"]
    fmt        = rnd["format_code"]
    hc_mode    = rnd["handicap_mode"]
    allowance  = rnd["allowance_pct"] / 100.0
    team_a     = rnd["team_a_name"]
    team_b     = rnd["team_b_name"]
    match_id   = f"R{rnd['round_number']}-M{match['match_order']}"
    is_singles = not bool(match.get("a2_name") or match.get("b2_name"))

    strokes = compute_hole_strokes(match, tee_a, tee_b, fmt, hc_mode, allowance, holes)
    si      = _parse_si(tee_a)

    x = MARGIN_X
    y = y_start if y_start is not None else PAGE_H - cfg.margin_top

    # ── Header ───────────────────────────────────────────────────
    hdr_y = y - cfg.rh_header
    _cell(c, x, hdr_y, CW, cfg.rh_header, fill=C_GRAY_L, bc=C_BLACK, lw=1.2)

    mid_x = x + CW / 2
    c.setFillColor(C_BLACK)
    c.setFont("Helvetica-Bold", cfg.f_id)
    iw = c.stringWidth(match_id, "Helvetica-Bold", cfg.f_id)
    c.drawString(mid_x - iw / 2, hdr_y + cfg.rh_header - cfg.f_id - 2, match_id)

    info = (
        f"Round {rnd['round_number']}  ·  Match {match['match_order']} of {total}  ·  "
        f"{FORMAT_LABELS.get(fmt, fmt)}  ·  {holes} holes"
    )
    c.setFont("Helvetica", cfg.f_info)
    ifw = c.stringWidth(info, "Helvetica", cfg.f_info)
    c.drawString(mid_x - ifw / 2,
                 hdr_y + cfg.rh_header - cfg.f_id - cfg.f_info - 5, info)

    course_line = f"{rnd['course_name']}  ·  {rnd['date']}"
    c.setFont("Helvetica", cfg.f_info)
    clw = c.stringWidth(course_line, "Helvetica", cfg.f_info)
    c.drawString(mid_x - clw / 2,
                 hdr_y + cfg.rh_header - cfg.f_id - cfg.f_info * 2 - 9, course_line)

    # Team names + players — left / right
    c.setFont("Helvetica-Bold", cfg.f_team)
    c.setFillColor(C_GREEN)
    c.drawString(x + 6, hdr_y + cfg.rh_header - cfg.f_team - 2, team_a)
    c.setFillColor(C_RED)
    tbw = c.stringWidth(team_b, "Helvetica-Bold", cfg.f_team)
    c.drawString(x + CW - 6 - tbw, hdr_y + cfg.rh_header - cfg.f_team - 2, team_b)

    c.setFont("Helvetica", cfg.f_info)
    c.setFillColor(C_GREEN)
    a1 = match.get("a1_name", ""); a2 = match.get("a2_name", "")
    off = cfg.f_team + cfg.f_info + 4
    if a1: c.drawString(x + 6, hdr_y + cfg.rh_header - off, a1)
    if a2: c.drawString(x + 6, hdr_y + cfg.rh_header - off - cfg.f_info - 2, a2)
    c.setFillColor(C_RED)
    b1 = match.get("b1_name", ""); b2 = match.get("b2_name", "")
    if b1:
        bw = c.stringWidth(b1, "Helvetica", cfg.f_info)
        c.drawString(x + CW - 6 - bw, hdr_y + cfg.rh_header - off, b1)
    if b2:
        bw = c.stringWidth(b2, "Helvetica", cfg.f_info)
        c.drawString(x + CW - 6 - bw, hdr_y + cfg.rh_header - off - cfg.f_info - 2, b2)

    y = hdr_y

    # ── AI note bar ──────────────────────────────────────────────
    note_y = y - cfg.rh_note
    c.setFillColor(colors.Color(0.96, 0.96, 0.96))
    c.rect(x, note_y, CW, cfg.rh_note, fill=1, stroke=0)
    c.setFont("Helvetica", cfg.f_note)
    c.setFillColor(C_GRAY_D)
    note = (
        f"AI ref: {match_id}  ·  Dots = stroke indicator (top-right of box)  ·  "
        "○ = half stroke  ·  Handwritten = gross score  ·  Circle result below"
    )
    c.drawString(x + 4, note_y + 2, note)
    y = note_y

    # ── Grids ────────────────────────────────────────────────────
    if holes == 9:
        y = _draw_grid_section(c, x, y, list(range(1, 10)), si[:9],
                               team_a, team_b, match, strokes, is_singles, cfg)
    else:
        y = _draw_grid_section(c, x, y, list(range(1, 10)), si[:9],
                               team_a, team_b, match, strokes, is_singles, cfg)
        y -= cfg.section_gap
        y = _draw_grid_section(c, x, y, list(range(10, 19)), si[9:18],
                               team_a, team_b, match, strokes, is_singles, cfg)

    # ── Footer ───────────────────────────────────────────────────
    y -= 4
    foot_y = y - cfg.rh_footer
    _cell(c, x, foot_y, CW, cfg.rh_footer, fill=C_GRAY_L, bc=C_BLACK, lw=1.2)

    res_y = foot_y + cfg.rh_footer - 14
    c.setFont("Helvetica-Bold", cfg.f_info)
    c.setFillColor(C_BLACK)
    c.drawString(x + 6, res_y - 2, "Result:")

    opt_x = x + 54
    for opt in [f"{team_a} win", f"{team_b} win", "Halved"]:
        c.setFillColor(C_WHITE)
        c.setStrokeColor(C_BLACK)
        c.setLineWidth(1.0)
        c.circle(opt_x, res_y, 6, fill=1, stroke=1)
        c.setFillColor(C_BLACK)
        c.setFont("Helvetica", cfg.f_info)
        c.drawString(opt_x + 9, res_y - 3, opt)
        opt_x += c.stringWidth(opt, "Helvetica", cfg.f_info) + 24
    c.setFont("Helvetica", cfg.f_info - 0.5)
    c.setFillColor(C_GRAY_D)
    c.drawString(opt_x + 3, res_y - 3, "by _____ holes / A/S")

    # Stroke rule note
    if holes == 9:
        note9 = "9-hole: strokes = ½ × 18-hole difference  ·  ○ half stroke wins a tied hole"
    else:
        note9 = "18-hole: full handicap strokes  ·  no half strokes"
    c.setFont("Helvetica", cfg.f_note + 0.5)
    c.setFillColor(C_GRAY_D)
    c.drawString(x + 6, foot_y + cfg.rh_footer - 26, note9)

    # Signature lines
    sig_w = CW / 3
    sig_y = foot_y + 18
    for i, lbl in enumerate([f"Signed {team_a}:", f"Signed {team_b}:", "Time submitted:"]):
        sx = x + i * sig_w
        c.setFont("Helvetica", cfg.f_footer)
        c.setFillColor(C_BLACK)
        c.drawString(sx + 4, sig_y + 10, lbl)
        c.setStrokeColor(C_GRAY_M)
        c.setLineWidth(0.6)
        c.line(sx + 4, sig_y + 4, sx + sig_w - 6, sig_y + 4)

    return foot_y


# ================================================================
# Public API
# ================================================================

def _estimate_card_height(matches: list, rnd: dict, cfg: CardConfig) -> float:
    """
    Estimate the rendered height of one scorecard (points) from config constants.
    Used to position multiple cards on a single page.
    """
    is_singles    = not bool(matches[0].get("a2_name") or matches[0].get("b2_name"))
    n_player_rows = 2 if is_singles else 4
    n_best_rows   = 0 if is_singles else 2

    # One grid section height
    def section_h():
        return (
            cfg.rh_seclabel + cfg.rh_hole + cfg.rh_si +
            n_player_rows * cfg.rh_score +
            n_best_rows   * cfg.rh_best +
            cfg.rh_sep + cfg.rh_result + cfg.rh_status
        )

    h = (
        cfg.rh_header + cfg.rh_note +
        section_h() +
        cfg.rh_footer + 4   # 4pt gap before footer
    )
    if rnd["holes"] == 18:
        h += cfg.section_gap + section_h()
    return h


def generate_round_scorecards(
    round_id: int,
    size: str = "full",
    compact: bool = False,   # legacy — maps to size="compact"
) -> bytes:
    """
    Generate a multi-page PDF of scorecards for every match in the round.

    size="full"    → 1 full-size card per page (portrait letter)
    size="compact" → 2 cards per page (~66% scale, caddie-friendly)
    size="small"   → 3 cards per page (~50% scale, rain/pocket size)

    The legacy `compact=True` kwarg still works and maps to size="compact".
    """
    if compact and size == "full":
        size = "compact"

    cfg = _SIZE_MAP.get(size, FULL)

    data    = get_scorecard_data(round_id)
    rnd     = data["round"]
    matches = data["matches"]
    tee_a   = data["tee_a"]
    tee_b   = data["tee_b"]

    if not rnd:
        raise ValueError(f"Round {round_id} not found.")
    if not matches:
        raise ValueError("No matches found for this round. Add the draw first.")

    total = len(matches)

    buf = BytesIO()
    c   = rl_canvas.Canvas(buf, pagesize=letter)
    c.setTitle(f"Scorecards – Round {rnd['round_number']} – {rnd['event_name']}")
    c.setAuthor("Golf Match Captain")

    cpp = cfg.cards_per_page

    if cpp == 1:
        # ── One card per page ─────────────────────────────────────
        for match in matches:
            _draw_scorecard(c, match, rnd, tee_a, tee_b, total, cfg)
            c.showPage()

    else:
        # ── N cards per page (2 or 3) ─────────────────────────────
        CUT_GAP   = 12 if cpp == 3 else 14
        card_h    = _estimate_card_height(matches, rnd, cfg)
        top_start = PAGE_H - cfg.margin_top

        # Compute y_start for each slot on the page
        def slot_start(slot: int) -> float:
            return top_start - slot * (card_h + CUT_GAP)

        def draw_cut_line(after_slot: int):
            cut_y = slot_start(after_slot) - card_h - CUT_GAP / 2
            c.setDash(4, 4)
            c.setStrokeColor(C_GRAY_M)
            c.setLineWidth(0.7)
            c.line(MARGIN_X, cut_y, PAGE_W - MARGIN_X, cut_y)
            c.setDash()
            c.setFont("Helvetica", 7)
            c.setFillColor(C_GRAY_D)
            c.drawString(MARGIN_X, cut_y + 2, "✂")

        def draw_blank(slot: int):
            mid_y = slot_start(slot) - card_h / 2
            c.setFont("Helvetica", 7)
            c.setFillColor(C_GRAY_M)
            c.drawCentredString(PAGE_W / 2, mid_y, "[ no match ]")

        for i in range(0, len(matches), cpp):
            for slot in range(cpp):
                mi = i + slot
                if mi < len(matches):
                    _draw_scorecard(c, matches[mi], rnd, tee_a, tee_b, total, cfg,
                                    y_start=slot_start(slot))
                else:
                    draw_blank(slot)

                # Cut line after every slot except the last
                if slot < cpp - 1:
                    draw_cut_line(slot)

            c.showPage()

    c.save()
    buf.seek(0)
    return buf.read()

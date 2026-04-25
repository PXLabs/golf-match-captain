-- ============================================================
-- add_handicap_columns.sql
-- Verma Cup 2026 — Supabase Schema Update
--
-- Adds per-player playing handicaps to matches and tee deck
-- data to rounds so the scoring app can calculate per-hole
-- stroke allocation and hole-by-hole match results.
--
-- Run once in the Supabase SQL Editor.
-- Safe to re-run — uses IF NOT EXISTS throughout.
-- ============================================================


-- ── matches: individual adjusted playing handicaps ──────────
-- ph_a1/ph_a2 = Celtic Tigers players (after PLAY_OFF_LOW)
-- ph_b1/ph_b2 = The Hurleys players   (after PLAY_OFF_LOW)
-- The lowest handicap player across all four gets ph = 0.

ALTER TABLE matches ADD COLUMN IF NOT EXISTS ph_a1 int;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS ph_a2 int;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS ph_b1 int;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS ph_b2 int;


-- ── rounds: tee deck data needed for stroke allocation ──────
-- stroke_index: JSON array of 18 SI values, e.g. [7,13,17,...]
-- course_rating, course_slope, course_par: from the tee deck

ALTER TABLE rounds ADD COLUMN IF NOT EXISTS stroke_index  jsonb;
ALTER TABLE rounds ADD COLUMN IF NOT EXISTS course_rating float;
ALTER TABLE rounds ADD COLUMN IF NOT EXISTS course_slope  int;
ALTER TABLE rounds ADD COLUMN IF NOT EXISTS course_par    int;


-- ── match_detail view: drop and recreate to expose ph columns ─

DROP VIEW IF EXISTS match_detail;

CREATE VIEW match_detail AS
SELECT
  m.id,
  m.round_id,
  m.match_number,
  m.status          AS match_status,
  m.result,
  m.result_detail,
  m.points_a,
  m.points_b,
  m.strokes_a,
  m.strokes_b,
  m.ph_a1,
  m.ph_a2,
  m.ph_b1,
  m.ph_b2,
  m.hole_scores,
  pa1.name          AS team_a_p1_name,
  pa2.name          AS team_a_p2_name,
  pb1.name          AS team_b_p1_name,
  pb2.name          AS team_b_p2_name,
  m.team_a_p1_id,
  m.team_a_p2_id,
  m.team_b_p1_id,
  m.team_b_p2_id
FROM  matches m
LEFT JOIN players pa1 ON pa1.id = m.team_a_p1_id
LEFT JOIN players pa2 ON pa2.id = m.team_a_p2_id
LEFT JOIN players pb1 ON pb1.id = m.team_b_p1_id
LEFT JOIN players pb2 ON pb2.id = m.team_b_p2_id;

-- RLS is inherited from the matches table policy.
-- The line below is a safety net only — safe to re-run.
CREATE POLICY "anon read matches" ON matches FOR SELECT USING (true);

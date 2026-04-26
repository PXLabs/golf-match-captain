-- =============================================================
-- Golf Match Captain — PostgreSQL / Supabase Schema
-- Run once in the Supabase SQL Editor.
-- Safe to re-run — uses IF NOT EXISTS throughout.
-- =============================================================

-- -------------------------------------------------------------
-- PLAYER
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS player (
    player_id      SERIAL PRIMARY KEY,
    name           TEXT    NOT NULL,
    cpga_id        TEXT,
    current_index  REAL    NOT NULL DEFAULT 0.0,
    tee_preference TEXT,
    notes          TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- -------------------------------------------------------------
-- SCORE RECORD
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS score_record (
    record_id    SERIAL PRIMARY KEY,
    player_id    INTEGER NOT NULL REFERENCES player(player_id) ON DELETE CASCADE,
    date         TEXT    NOT NULL,
    course       TEXT    NOT NULL,
    tee_deck     TEXT,
    posted_score INTEGER,
    differential REAL    NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- -------------------------------------------------------------
-- PLAYER TAG
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS player_tag (
    tag_id       SERIAL PRIMARY KEY,
    player_id    INTEGER NOT NULL REFERENCES player(player_id) ON DELETE CASCADE,
    tag_type     TEXT    NOT NULL,
    tag_value    TEXT    NOT NULL,
    created_date TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- -------------------------------------------------------------
-- COURSE
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS course (
    course_id  SERIAL PRIMARY KEY,
    name       TEXT NOT NULL,
    location   TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- -------------------------------------------------------------
-- TEE DECK
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tee_deck (
    tee_id       SERIAL PRIMARY KEY,
    course_id    INTEGER NOT NULL REFERENCES course(course_id) ON DELETE CASCADE,
    name         TEXT    NOT NULL,
    rating       REAL    NOT NULL,
    slope        INTEGER NOT NULL,
    par          INTEGER NOT NULL DEFAULT 72,
    total_yards  INTEGER,
    stroke_index TEXT    NOT NULL DEFAULT '[]',
    notes        TEXT
);

-- -------------------------------------------------------------
-- EVENT
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS event (
    event_id      SERIAL PRIMARY KEY,
    name          TEXT    NOT NULL,
    start_date    TEXT    NOT NULL,
    team_a_name   TEXT    NOT NULL DEFAULT 'Team A',
    team_b_name   TEXT    NOT NULL DEFAULT 'Team B',
    handicap_mode TEXT    NOT NULL DEFAULT 'FULL_INDEX',
    allowance_pct REAL    NOT NULL DEFAULT 100.0,
    status        TEXT    NOT NULL DEFAULT 'ACTIVE',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- -------------------------------------------------------------
-- EVENT PLAYER
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS event_player (
    event_id   INTEGER NOT NULL REFERENCES event(event_id)   ON DELETE CASCADE,
    player_id  INTEGER NOT NULL REFERENCES player(player_id) ON DELETE CASCADE,
    team       TEXT    NOT NULL CHECK (team IN ('A', 'B')),
    role       TEXT    DEFAULT 'Player',
    PRIMARY KEY (event_id, player_id)
);

-- -------------------------------------------------------------
-- ROUND
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS round (
    round_id     SERIAL PRIMARY KEY,
    event_id     INTEGER NOT NULL REFERENCES event(event_id)   ON DELETE CASCADE,
    course_id    INTEGER NOT NULL REFERENCES course(course_id),
    tee_id_a     INTEGER REFERENCES tee_deck(tee_id),
    tee_id_b     INTEGER REFERENCES tee_deck(tee_id),
    date         TEXT    NOT NULL,
    holes        INTEGER NOT NULL DEFAULT 18,
    format_code  TEXT    NOT NULL,
    round_number INTEGER NOT NULL DEFAULT 1
);

-- -------------------------------------------------------------
-- MATCH
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS match (
    match_id          SERIAL PRIMARY KEY,
    round_id          INTEGER NOT NULL REFERENCES round(round_id) ON DELETE CASCADE,
    team_a_player1_id INTEGER REFERENCES player(player_id),
    team_a_player2_id INTEGER REFERENCES player(player_id),
    team_b_player1_id INTEGER REFERENCES player(player_id),
    team_b_player2_id INTEGER REFERENCES player(player_id),
    result            TEXT,
    result_detail     TEXT,
    notes             TEXT,
    match_order       INTEGER NOT NULL DEFAULT 1,
    hole_scores       TEXT
);

-- =============================================================
-- END OF SCHEMA
-- =============================================================

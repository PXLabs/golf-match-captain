-- =============================================================
-- Golf Match Captain — SQLite Schema
-- Version: 1.0 (Phase 1A)
-- All entities per Section 3.1 of the Context Document
-- =============================================================

PRAGMA foreign_keys = ON;

-- -------------------------------------------------------------
-- PLAYER
-- Core roster entity. Survives across events.
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS player (
    player_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    cpga_id     TEXT,
    current_index REAL  NOT NULL DEFAULT 0.0,
    tee_preference TEXT,
    notes       TEXT,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- -------------------------------------------------------------
-- SCORE RECORD
-- Up to 20 most recent differentials per player. Manually
-- entered in Phase 1; automated via Playwright in Phase 2.
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS score_record (
    record_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id   INTEGER NOT NULL,
    date        TEXT    NOT NULL,
    course      TEXT    NOT NULL,
    tee_deck    TEXT,
    posted_score INTEGER,
    differential REAL   NOT NULL,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (player_id) REFERENCES player(player_id) ON DELETE CASCADE
);

-- -------------------------------------------------------------
-- PLAYER TAG
-- Free-form captain notes per player. Feeds into LLM context.
-- tag_type: PLAYING_STYLE | TEMPERAMENT | COURSE_AFFINITY |
--           PHYSICAL | CHEMISTRY
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS player_tag (
    tag_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id   INTEGER NOT NULL,
    tag_type    TEXT    NOT NULL,
    tag_value   TEXT    NOT NULL,
    created_date TEXT   NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (player_id) REFERENCES player(player_id) ON DELETE CASCADE
);

-- -------------------------------------------------------------
-- COURSE
-- Reusable across events. Tee decks stored in child table.
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS course (
    course_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    location    TEXT,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- -------------------------------------------------------------
-- TEE DECK
-- One row per tee set per course.
-- stroke_index: JSON array of 18 integers (hole SI values).
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tee_deck (
    tee_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id   INTEGER NOT NULL,
    name        TEXT    NOT NULL,
    rating      REAL    NOT NULL,
    slope       INTEGER NOT NULL,
    par         INTEGER NOT NULL DEFAULT 72,
    total_yards INTEGER,
    stroke_index TEXT   NOT NULL DEFAULT '[]',
    notes       TEXT,
    FOREIGN KEY (course_id) REFERENCES course(course_id) ON DELETE CASCADE
);

-- -------------------------------------------------------------
-- EVENT
-- One per tournament. Controls handicap mode for all rounds.
-- handicap_mode: FULL_INDEX | PERCENTAGE | PLAY_OFF_LOW
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS event (
    event_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL,
    start_date    TEXT    NOT NULL,
    team_a_name   TEXT    NOT NULL DEFAULT 'Team A',
    team_b_name   TEXT    NOT NULL DEFAULT 'Team B',
    handicap_mode TEXT    NOT NULL DEFAULT 'FULL_INDEX',
    allowance_pct REAL    NOT NULL DEFAULT 100.0,
    status        TEXT    NOT NULL DEFAULT 'ACTIVE',
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- -------------------------------------------------------------
-- EVENT PLAYER
-- Assigns players to a team within an event.
-- team: 'A' or 'B'
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS event_player (
    event_id    INTEGER NOT NULL,
    player_id   INTEGER NOT NULL,
    team        TEXT    NOT NULL CHECK (team IN ('A', 'B')),
    role        TEXT    DEFAULT 'Player',
    PRIMARY KEY (event_id, player_id),
    FOREIGN KEY (event_id)  REFERENCES event(event_id)   ON DELETE CASCADE,
    FOREIGN KEY (player_id) REFERENCES player(player_id) ON DELETE CASCADE
);

-- -------------------------------------------------------------
-- ROUND
-- One per day of play within an event.
-- format_code: SINGLES_MP | FOURBALL_MP | FOURSOMES_MP |
--              SINGLES_STROKE | SCRAMBLE
-- holes: 9 or 18
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS round (
    round_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id      INTEGER NOT NULL,
    course_id     INTEGER NOT NULL,
    tee_id_a      INTEGER,
    tee_id_b      INTEGER,
    date          TEXT    NOT NULL,
    holes         INTEGER NOT NULL DEFAULT 18,
    format_code   TEXT    NOT NULL,
    round_number  INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (event_id)  REFERENCES event(event_id)   ON DELETE CASCADE,
    FOREIGN KEY (course_id) REFERENCES course(course_id),
    FOREIGN KEY (tee_id_a)  REFERENCES tee_deck(tee_id),
    FOREIGN KEY (tee_id_b)  REFERENCES tee_deck(tee_id)
);

-- -------------------------------------------------------------
-- MATCH
-- One row per pairing within a round.
-- result: 'A' | 'B' | 'HALVED' | NULL (not yet played)
-- result_detail: e.g. '3&2', '1UP', 'AS'
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS match (
    match_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id           INTEGER NOT NULL,
    team_a_player1_id  INTEGER,
    team_a_player2_id  INTEGER,
    team_b_player1_id  INTEGER,
    team_b_player2_id  INTEGER,
    result             TEXT,
    result_detail      TEXT,
    notes              TEXT,
    match_order        INTEGER NOT NULL DEFAULT 1,
    hole_scores        TEXT,    -- JSON blob: per-player gross scores, net scores, holes won
    FOREIGN KEY (round_id)            REFERENCES round(round_id)   ON DELETE CASCADE,
    FOREIGN KEY (team_a_player1_id)   REFERENCES player(player_id),
    FOREIGN KEY (team_a_player2_id)   REFERENCES player(player_id),
    FOREIGN KEY (team_b_player1_id)   REFERENCES player(player_id),
    FOREIGN KEY (team_b_player2_id)   REFERENCES player(player_id)
);

-- =============================================================
-- END OF SCHEMA
-- =============================================================

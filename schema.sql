-- Codenames AI vs AI — Database Schema

CREATE TABLE IF NOT EXISTS models (
    model_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    elo_rating  REAL NOT NULL DEFAULT 1500.0
);

CREATE TABLE IF NOT EXISTS tournaments (
    tournament_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT,
    board_size      TEXT NOT NULL DEFAULT '5x5',
    games_per_pair  INTEGER NOT NULL DEFAULT 2,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at     TEXT
);

CREATE TABLE IF NOT EXISTS games (
    game_id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id           INTEGER REFERENCES tournaments(tournament_id),
    board_size              TEXT NOT NULL DEFAULT '5x5',
    board_words             TEXT NOT NULL,   -- JSON array of words (row-major)
    board_map               TEXT NOT NULL,   -- JSON array of card types (parallel)
    first_team              TEXT NOT NULL,   -- 'red' or 'blue'
    red_spymaster_model     TEXT NOT NULL,
    red_guesser_model       TEXT NOT NULL,
    blue_spymaster_model    TEXT NOT NULL,
    blue_guesser_model      TEXT NOT NULL,
    winner                  TEXT,            -- 'red', 'blue', or NULL if in-progress
    win_reason              TEXT,            -- 'all_found' or 'assassin'
    losing_team_hit_assassin INTEGER DEFAULT 0,
    total_turns             INTEGER,
    started_at              TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at             TEXT
);

CREATE TABLE IF NOT EXISTS turns (
    turn_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id         INTEGER NOT NULL REFERENCES games(game_id),
    turn_number     INTEGER NOT NULL,
    team            TEXT NOT NULL,
    clue_word       TEXT,
    clue_number     INTEGER,
    clue_raw_response TEXT,
    clue_latency_ms INTEGER,
    clue_valid      INTEGER,
    clue_attempts   INTEGER DEFAULT 1,
    error           TEXT,
    UNIQUE(game_id, turn_number)
);

CREATE TABLE IF NOT EXISTS guesses (
    guess_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    turn_id         INTEGER NOT NULL REFERENCES turns(turn_id),
    guess_number    INTEGER NOT NULL,
    guessed_word    TEXT NOT NULL,
    card_type       TEXT NOT NULL,
    correct         INTEGER NOT NULL,
    raw_response    TEXT,
    latency_ms      INTEGER,
    UNIQUE(turn_id, guess_number)
);

CREATE TABLE IF NOT EXISTS elo_history (
    history_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    model_name  TEXT NOT NULL,
    game_id     INTEGER NOT NULL REFERENCES games(game_id),
    old_elo     REAL NOT NULL,
    new_elo     REAL NOT NULL,
    role        TEXT NOT NULL
);

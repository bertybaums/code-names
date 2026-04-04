"""SQLite database helpers for Codenames AI."""

import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "codenames.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def init_db(path=DB_PATH):
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=FULL")  # fsync after every commit — slower but crash-safe
    conn.executescript(SCHEMA_PATH.read_text())
    return conn


def backup_db(path=DB_PATH):
    """Create a timestamped backup of the database."""
    import shutil
    from datetime import datetime
    backup_path = Path(str(path) + f".backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    # Force WAL checkpoint first so backup is self-contained
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()
    shutil.copy2(str(path), str(backup_path))
    return backup_path


def ensure_model(conn, name, initial_elo=1500.0):
    conn.execute(
        "INSERT OR IGNORE INTO models (name, elo_rating) VALUES (?, ?)",
        (name, initial_elo),
    )
    conn.commit()


def get_model_elo(conn, name):
    row = conn.execute(
        "SELECT elo_rating FROM models WHERE name = ?", (name,)
    ).fetchone()
    return row["elo_rating"] if row else None


def update_model_elo(conn, name, new_elo):
    conn.execute(
        "UPDATE models SET elo_rating = ? WHERE name = ?", (new_elo, name)
    )
    conn.commit()


def insert_tournament(conn, name, board_size, games_per_pair):
    cur = conn.execute(
        """INSERT INTO tournaments (name, board_size, games_per_pair)
           VALUES (?, ?, ?)""",
        (name, board_size, games_per_pair),
    )
    conn.commit()
    return cur.lastrowid


def finish_tournament(conn, tournament_id):
    conn.execute(
        "UPDATE tournaments SET finished_at = datetime('now') WHERE tournament_id = ?",
        (tournament_id,),
    )
    conn.commit()


def insert_game(conn, tournament_id, board_size, board_words, board_map,
                first_team, red_sm, red_g, blue_sm, blue_g):
    cur = conn.execute(
        """INSERT INTO games
           (tournament_id, board_size, board_words, board_map, first_team,
            red_spymaster_model, red_guesser_model,
            blue_spymaster_model, blue_guesser_model)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (tournament_id, board_size,
         json.dumps(board_words), json.dumps(board_map),
         first_team, red_sm, red_g, blue_sm, blue_g),
    )
    conn.commit()
    return cur.lastrowid


def finish_game(conn, game_id, winner, win_reason, assassin_loss, total_turns):
    conn.execute(
        """UPDATE games
           SET winner = ?, win_reason = ?, losing_team_hit_assassin = ?,
               total_turns = ?, finished_at = datetime('now')
           WHERE game_id = ?""",
        (winner, win_reason, int(assassin_loss), total_turns, game_id),
    )
    conn.commit()


def insert_turn(conn, game_id, turn_number, team, clue_word, clue_number,
                clue_raw_response, clue_latency_ms, clue_valid, clue_attempts,
                error=None):
    cur = conn.execute(
        """INSERT INTO turns
           (game_id, turn_number, team, clue_word, clue_number,
            clue_raw_response, clue_latency_ms, clue_valid, clue_attempts, error)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (game_id, turn_number, team, clue_word, clue_number,
         clue_raw_response, clue_latency_ms, int(clue_valid) if clue_valid is not None else None,
         clue_attempts, error),
    )
    conn.commit()
    return cur.lastrowid


def insert_guess(conn, turn_id, guess_number, guessed_word, card_type,
                 correct, raw_response, latency_ms):
    conn.execute(
        """INSERT INTO guesses
           (turn_id, guess_number, guessed_word, card_type, correct,
            raw_response, latency_ms)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (turn_id, guess_number, guessed_word, card_type,
         int(correct), raw_response, latency_ms),
    )
    conn.commit()


def insert_elo_history(conn, model_name, game_id, old_elo, new_elo, role):
    conn.execute(
        """INSERT INTO elo_history (model_name, game_id, old_elo, new_elo, role)
           VALUES (?, ?, ?, ?, ?)""",
        (model_name, game_id, old_elo, new_elo, role),
    )
    conn.commit()


def get_all_ratings(conn):
    return conn.execute(
        "SELECT name, elo_rating FROM models ORDER BY elo_rating DESC"
    ).fetchall()


def get_game(conn, game_id):
    return conn.execute(
        "SELECT * FROM games WHERE game_id = ?", (game_id,)
    ).fetchone()


def get_game_turns(conn, game_id):
    return conn.execute(
        "SELECT * FROM turns WHERE game_id = ? ORDER BY turn_number",
        (game_id,),
    ).fetchall()


def get_turn_guesses(conn, turn_id):
    return conn.execute(
        "SELECT * FROM guesses WHERE turn_id = ? ORDER BY guess_number",
        (turn_id,),
    ).fetchall()


def get_model_stats(conn, model_name):
    """Get win/loss/assassin stats for a model."""
    stats = {}
    # Games as any role
    for role in ["red_spymaster_model", "red_guesser_model",
                 "blue_spymaster_model", "blue_guesser_model"]:
        rows = conn.execute(
            f"SELECT winner, win_reason, losing_team_hit_assassin "
            f"FROM games WHERE {role} = ? AND winner IS NOT NULL",
            (model_name,),
        ).fetchall()
        stats[role] = rows
    return stats

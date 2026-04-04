"""Core game engine for Codenames AI.

Runs a single game between two AI teams, recording all moves to the database.
"""

import logging

from board import Board
from clue_validator import validate_clue
from models import call_llm, parse_json_response, SPYMASTER_SCHEMA, GUESSER_SCHEMA
from prompts import (
    build_spymaster_prompt,
    build_guesser_prompt,
    build_retry_spymaster_prompt,
    build_retry_guesser_prompt,
)
from embedding_player import embedding_spymaster, embedding_guesser
import db

log = logging.getLogger(__name__)


class GameResult:
    def __init__(self, game_id, winner, win_reason, total_turns, assassin_loss):
        self.game_id = game_id
        self.winner = winner
        self.win_reason = win_reason
        self.total_turns = total_turns
        self.assassin_loss = assassin_loss

    def __repr__(self):
        return (
            f"GameResult(game_id={self.game_id}, winner={self.winner}, "
            f"reason={self.win_reason}, turns={self.total_turns}, "
            f"assassin={self.assassin_loss})"
        )


def play_game(board, players, config, conn, tournament_id=None):
    """Play a full game of Codenames.

    Args:
        board: Board instance with words, card_map, first_team, size
        players: dict mapping role -> model_config
            roles: 'red_spymaster', 'red_guesser', 'blue_spymaster', 'blue_guesser'
        config: loaded config.yaml dict
        conn: sqlite3 connection
        tournament_id: optional tournament reference

    Returns:
        GameResult
    """
    game_cfg = config.get("game", {})
    max_clue_attempts = game_cfg.get("max_clue_attempts", 3)
    max_guess_parse = game_cfg.get("max_guess_parse_attempts", 3)


    game_id = db.insert_game(
        conn,
        tournament_id=tournament_id,
        board_size=f"{board.size}x{board.size}",
        board_words=board.words,
        board_map=board.card_map,
        first_team=board.first_team,
        red_sm=players["red_spymaster"]["name"],
        red_g=players["red_guesser"]["name"],
        blue_sm=players["blue_spymaster"]["name"],
        blue_g=players["blue_guesser"]["name"],
    )

    revealed_history = []
    turn_number = 0
    current_team = board.first_team
    max_turns = 50  # safety limit
    winner = None
    win_reason = None
    game_over = False
    consecutive_failures = 0  # circuit breaker: abort if both teams fail repeatedly
    max_consecutive_failures = 6  # 3 rounds of both teams failing

    attempts_without_turn = 0  # safety counter for the while loop
    max_attempts = max_turns * 3  # allow some failures but not infinite

    while turn_number < max_turns and attempts_without_turn < max_attempts:
        opponent = "blue" if current_team == "red" else "red"

        # --- Spymaster phase ---
        sm_key = f"{current_team}_spymaster"
        sm_config = players[sm_key]

        if sm_config.get("player_type") == "embedding":
            clue_word, clue_number, reasoning, clue_latency = (
                embedding_spymaster(board, current_team, sm_config))
            clue_valid = clue_word is not None
            clue_raw = reasoning
        else:
            clue_word, clue_number, clue_raw, clue_latency, clue_valid = (
                _spymaster_turn(board, current_team, sm_config,
                                revealed_history, max_clue_attempts)
            )

        # Failed spymaster = not a real turn, just switch teams
        if not clue_valid:
            consecutive_failures += 1
            attempts_without_turn += 1

            if consecutive_failures >= max_consecutive_failures:
                log.error(f"Game {game_id}: aborting — {consecutive_failures} consecutive "
                          f"failures (likely API outage)")
                win_reason = "aborted"
                break

            log.warning(f"Game {game_id}: {current_team} spymaster failed — skipping (not a turn)")
            current_team = opponent
            continue

        consecutive_failures = 0
        attempts_without_turn = 0
        turn_number += 1

        log.info(f"Game {game_id} Turn {turn_number}: {current_team}'s turn")

        turn_id = db.insert_turn(
            conn, game_id, turn_number, current_team,
            clue_word, clue_number, clue_raw, clue_latency,
            True, 1, None,
        )

        log.info(f"  Spymaster clue: {clue_word} {clue_number}")

        # --- Guesser phase ---
        g_key = f"{current_team}_guesser"
        g_config = players[g_key]

        max_guesses = clue_number + 1
        turn_guesses = []
        game_over = False
        winner = None
        win_reason = None

        for guess_num in range(1, max_guesses + 1):
            if g_config.get("player_type") == "embedding":
                guessed_word, reasoning, guess_latency = embedding_guesser(
                    board, current_team, clue_word, clue_number,
                    turn_guesses, g_config)
                guess_raw = reasoning
            else:
                guessed_word, guess_raw, guess_latency = _guesser_turn(
                    board, current_team, clue_word, clue_number,
                    turn_guesses, revealed_history, g_config, max_guess_parse,
                )

            if guessed_word is None or guessed_word.upper() == "PASS":
                db.insert_guess(
                    conn, turn_id, guess_num, "PASS", "pass", False,
                    guess_raw, guess_latency,
                )
                log.info(f"  Guesser passes")
                break

            card_type = board.reveal(guessed_word)
            correct = card_type == current_team

            db.insert_guess(
                conn, turn_id, guess_num, guessed_word, card_type,
                correct, guess_raw, guess_latency,
            )

            revealed_history.append({
                "word": guessed_word,
                "type": card_type,
                "team": current_team,
            })

            turn_guesses.append({
                "word": guessed_word,
                "result": f"{'CORRECT' if correct else card_type.upper()}",
            })

            log.info(f"  Guess {guess_num}: {guessed_word} → {card_type}")

            if card_type == "assassin":
                winner = opponent
                win_reason = "assassin"
                game_over = True
                break

            if card_type != current_team:
                # Wrong guess — turn ends
                break

            # Check if team found all their words
            if board.remaining_for_team(current_team) == 0:
                winner = current_team
                win_reason = "all_found"
                game_over = True
                break

        if game_over:
            break

        # Check if opponent's words are all found (by accident)
        if board.remaining_for_team(opponent) == 0:
            winner = opponent
            win_reason = "all_found"
            break

        current_team = opponent

    # If max_turns reached or game aborted without a winner
    if winner is None:
        if win_reason == "aborted":
            winner = "none"
        else:
            # The team with fewer remaining words wins
            red_remaining = board.remaining_for_team("red")
            blue_remaining = board.remaining_for_team("blue")
            if red_remaining < blue_remaining:
                winner = "red"
            elif blue_remaining < red_remaining:
                winner = "blue"
            else:
                winner = board.first_team  # tiebreak: first team
            win_reason = "max_turns"

    assassin_loss = win_reason == "assassin"

    db.finish_game(conn, game_id, winner, win_reason, assassin_loss, turn_number)

    log.info(f"Game {game_id} finished: {winner} wins ({win_reason}) in {turn_number} turns")

    return GameResult(game_id, winner, win_reason, turn_number, assassin_loss)


def _spymaster_turn(board, team, model_config, revealed_history, max_attempts):
    """Get a valid clue from the spymaster via structured output.

    Returns (clue_word, clue_number, raw_response, latency_ms, is_valid).
    """
    prompt = build_spymaster_prompt(board, team, revealed_history)

    last_raw = None
    last_latency = 0

    for attempt in range(max_attempts):
        try:
            raw, text, latency = call_llm(model_config, prompt,
                                          response_format=SPYMASTER_SCHEMA)
            last_raw = raw
            last_latency = latency

            parsed = parse_json_response(text)
            if not parsed or "clue" not in parsed or not parsed["clue"]:
                log.warning(f"  Spymaster parse fail (attempt {attempt+1}): {text[:200]}")
                continue

            clue_word = str(parsed["clue"]).strip()
            clue_number = int(parsed.get("number", 1))

            valid, reason = validate_clue(clue_word, board.unrevealed_words())
            if valid:
                return clue_word, clue_number, raw, latency, True

            log.warning(f"  Spymaster invalid clue '{clue_word}': {reason} (attempt {attempt+1})")
            prompt = build_retry_spymaster_prompt(prompt, clue_word, reason)

        except Exception as e:
            log.error(f"  Spymaster error (attempt {attempt+1}): {e}")
            last_raw = str(e)

    return None, 0, last_raw, last_latency, False


def _guesser_turn(board, team, clue_word, clue_number, turn_guesses,
                  revealed_history, model_config, max_parse_attempts):
    """Get a valid guess from the guesser via structured output.

    Returns (guessed_word, raw_response, latency_ms).
    """
    prompt = build_guesser_prompt(
        board, team, clue_word, clue_number, turn_guesses, revealed_history,
    )

    for attempt in range(max_parse_attempts):
        try:
            raw, text, latency = call_llm(model_config, prompt,
                                          response_format=GUESSER_SCHEMA)

            parsed = parse_json_response(text)
            if not parsed or "guess" not in parsed:
                log.warning(f"  Guesser parse fail (attempt {attempt+1}): {text[:200]}")
                continue

            guess = str(parsed["guess"]).strip().upper()

            if guess == "PASS":
                return "PASS", raw, latency

            unrevealed_upper = [w.upper() for w in board.unrevealed_words()]
            if guess in unrevealed_upper:
                idx = unrevealed_upper.index(guess)
                return board.unrevealed_words()[idx], raw, latency

            log.warning(f"  Guesser invalid guess '{guess}' (attempt {attempt+1})")
            prompt = build_retry_guesser_prompt(prompt, guess,
                f"'{guess}' is not in the unrevealed words. Choose from: {', '.join(board.unrevealed_words())}")

        except Exception as e:
            log.error(f"  Guesser error (attempt {attempt+1}): {e}")

    return None, None, 0

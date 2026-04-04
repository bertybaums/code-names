"""Tournament runner with round-robin scheduling and Elo ratings."""

import logging
import random
from itertools import permutations

from board import load_words, generate_board
from engine import play_game
from models import load_config, find_model
import db

log = logging.getLogger(__name__)


def compute_elo_update(rating_a, rating_b, score_a, k=32):
    """Compute new Elo rating for player A.

    score_a: 1 for win, 0 for loss, 0.5 for draw.
    Returns new rating for A.
    """
    expected = 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))
    return rating_a + k * (score_a - expected)


def run_tournament(config, db_path=None, board_size="5x5",
                   games_per_pair=None, name=None, seed=None,
                   only_models=None):
    """Run a round-robin tournament.

    Each model plays as a full team (same model for spymaster + guesser).
    Every ordered pair plays games_per_pair games. Games are run one pair
    at a time so only 2 models are loaded on the server simultaneously.

    If only_models is set, only pairs where at least one model is in
    only_models are played (for integrating new models).
    """
    if db_path is None:
        db_path = db.DB_PATH

    tourney_cfg = config.get("tournament", {})
    if games_per_pair is None:
        games_per_pair = tourney_cfg.get("games_per_pair", 2)
    k_factor = tourney_cfg.get("elo_k_factor", 32)
    initial_elo = tourney_cfg.get("elo_initial", 1500.0)

    model_names = [m["name"] for m in config["models"]]
    words = load_words()

    rng = random.Random(seed)

    # Init DB and ensure models exist
    conn = db.init_db(db_path)
    for name_ in model_names:
        db.ensure_model(conn, name_, initial_elo)

    # Create tournament record
    tournament_id = db.insert_tournament(
        conn, name or f"Round-Robin {board_size}", board_size, games_per_pair,
    )
    conn.close()

    # Generate matchups grouped by model pair.
    # Games are run one pair at a time so only 2 models are loaded on the
    # server simultaneously (avoids model-loading timeouts).
    pairs = list(permutations(model_names, 2))

    # Filter to only pairs involving the specified models
    if only_models:
        only_set = set(only_models)
        pairs = [(r, b) for r, b in pairs if r in only_set or b in only_set]

    pair_games = []
    for red_model, blue_model in pairs:
        seeds = []
        for game_num in range(games_per_pair):
            board_seed = rng.randint(0, 2**31)
            seeds.append((game_num, board_seed))
        pair_games.append((red_model, blue_model, seeds))

    total_games = len(pairs) * games_per_pair
    log.info(
        f"Tournament {tournament_id}: {total_games} games "
        f"({len(model_names)} models, {games_per_pair} games/pair, {board_size})"
    )

    game_results = []

    def _play_one(red_model, blue_model, board_seed):
        thread_conn = db.init_db(db_path)
        try:
            board = generate_board(words, board_size, rng=random.Random(board_seed))

            players = {
                "red_spymaster": find_model(config, red_model),
                "red_guesser": find_model(config, red_model),
                "blue_spymaster": find_model(config, blue_model),
                "blue_guesser": find_model(config, blue_model),
            }

            return play_game(board, players, config, thread_conn, tournament_id)
        except Exception as e:
            log.error(f"Game error ({red_model} vs {blue_model}): {e}")
            return None
        finally:
            thread_conn.close()

    # Run one model pair at a time; games within a pair run sequentially
    completed = 0
    for red_m, blue_m, seeds in pair_games:
        log.info(f"  Pair: {red_m} vs {blue_m} ({len(seeds)} games)")
        for game_num, board_seed in seeds:
            result = _play_one(red_m, blue_m, board_seed)
            completed += 1
            if result:
                game_results.append({
                    "game_id": result.game_id,
                    "red_model": red_m,
                    "blue_model": blue_m,
                    "winner": result.winner,
                    "win_reason": result.win_reason,
                })
                log.info(f"  [{completed}/{total_games}] {red_m} vs {blue_m}: {result}")
            else:
                log.warning(f"  [{completed}/{total_games}] {red_m} vs {blue_m}: FAILED")

        # Backup DB after each model pair completes
        try:
            db.backup_db(db_path)
        except Exception as e:
            log.warning(f"  Backup failed: {e}")

    # Batch Elo update
    conn = db.init_db(db_path)
    _batch_elo_update(conn, game_results, k_factor)
    db.finish_tournament(conn, tournament_id)
    conn.close()

    log.info(f"Tournament {tournament_id} complete: {len(game_results)} games finished")
    return tournament_id


def _batch_elo_update(conn, game_results, k_factor):
    """Update Elo ratings based on all game results.

    Uses snapshot ratings from before the tournament to avoid ordering effects.
    """
    # Snapshot current ratings
    all_ratings = {row["name"]: row["elo_rating"] for row in db.get_all_ratings(conn)}

    # Accumulate deltas
    elo_deltas = {name: 0.0 for name in all_ratings}

    for result in game_results:
        red = result["red_model"]
        blue = result["blue_model"]
        winner = result["winner"]

        # Skip aborted games (API outage, etc.)
        if winner == "none" or result.get("win_reason") == "aborted":
            continue

        red_rating = all_ratings.get(red, 1500.0)
        blue_rating = all_ratings.get(blue, 1500.0)

        if winner == "red":
            red_score, blue_score = 1.0, 0.0
        elif winner == "blue":
            red_score, blue_score = 0.0, 1.0
        else:
            red_score, blue_score = 0.5, 0.5

        new_red = compute_elo_update(red_rating, blue_rating, red_score, k_factor)
        new_blue = compute_elo_update(blue_rating, red_rating, blue_score, k_factor)

        elo_deltas[red] += new_red - red_rating
        elo_deltas[blue] += new_blue - blue_rating

        # Record history for both roles
        game_id = result["game_id"]
        for role, model, old, new in [
            ("red_spymaster", red, red_rating, new_red),
            ("red_guesser", red, red_rating, new_red),
            ("blue_spymaster", blue, blue_rating, new_blue),
            ("blue_guesser", blue, blue_rating, new_blue),
        ]:
            db.insert_elo_history(conn, model, game_id, old, new, role)

    # Apply accumulated deltas
    for name, delta in elo_deltas.items():
        old = all_ratings.get(name, 1500.0)
        db.update_model_elo(conn, name, old + delta)


def print_ratings(db_path=None):
    """Print current Elo ratings table."""
    conn = db.init_db(db_path or db.DB_PATH)
    ratings = db.get_all_ratings(conn)
    conn.close()

    print(f"\n{'Model':<25s} {'Elo':>8s}")
    print("-" * 35)
    for row in ratings:
        print(f"{row['name']:<25s} {row['elo_rating']:>8.1f}")
    print()


def print_model_stats(model_name, db_path=None):
    """Print detailed stats for a model."""
    conn = db.init_db(db_path or db.DB_PATH)

    # Games played and won
    total = 0
    wins = 0
    assassin_losses = 0

    for color in ["red", "blue"]:
        for role in ["spymaster_model", "guesser_model"]:
            col = f"{color}_{role}"
            rows = conn.execute(
                f"SELECT winner, win_reason, losing_team_hit_assassin "
                f"FROM games WHERE {col} = ? AND winner IS NOT NULL",
                (model_name,),
            ).fetchall()
            for row in rows:
                total += 1
                if row["winner"] == color:
                    wins += 1
                elif row["losing_team_hit_assassin"]:
                    assassin_losses += 1

    # Deduplicate (model appears in 2 roles per game)
    total //= 2
    wins //= 2
    assassin_losses //= 2

    elo = db.get_model_elo(conn, model_name)
    conn.close()

    print(f"\n--- {model_name} ---")
    print(f"Elo:             {elo:.1f}" if elo else "Elo:             N/A")
    print(f"Games:           {total}")
    print(f"Wins:            {wins}")
    print(f"Losses:          {total - wins}")
    print(f"Assassin losses: {assassin_losses}")
    if total > 0:
        print(f"Win rate:        {wins/total*100:.1f}%")
    print()

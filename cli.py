"""CLI entry point for Codenames AI."""

import json
import logging
import sys

import click

from board import load_words, generate_board
from engine import play_game
from models import load_config, find_model
from tournament import run_tournament, print_ratings, print_model_stats
import db


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging")
def cli(verbose):
    """Codenames AI vs AI game engine."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


@cli.command()
@click.option("--red", required=True, help="Red team model name")
@click.option("--blue", required=True, help="Blue team model name")
@click.option("--size", default="5x5", type=click.Choice(["5x5", "2x2"]),
              help="Board size")
@click.option("--seed", default=None, type=int, help="Random seed")
def play(red, blue, size, seed):
    """Play a single game between two models."""
    import random

    config = load_config()
    words = load_words()
    rng = random.Random(seed)
    board = generate_board(words, size, rng)

    players = {
        "red_spymaster": find_model(config, red),
        "red_guesser": find_model(config, red),
        "blue_spymaster": find_model(config, blue),
        "blue_guesser": find_model(config, blue),
    }

    conn = db.init_db()
    db.ensure_model(conn, red)
    db.ensure_model(conn, blue)

    print(f"Board ({size}, {board.first_team} goes first):")
    print(board.display_grid(show_map=True))
    print()

    result = play_game(board, players, config, conn)
    conn.close()

    print(f"\nResult: {result.winner.upper()} wins by {result.win_reason}")
    print(f"Total turns: {result.total_turns}")
    if result.assassin_loss:
        print("Game ended by ASSASSIN!")
    print(f"Game ID: {result.game_id}")


@cli.command()
@click.option("--size", default="5x5", type=click.Choice(["5x5", "2x2"]),
              help="Board size")
@click.option("--games-per-pair", "-g", default=None, type=int,
              help="Games per ordered model pair")
@click.option("--name", default=None, help="Tournament name")
@click.option("--seed", default=None, type=int, help="Random seed")
@click.option("--only", "only_models", default=None, help="Only play pairs involving these models (comma-separated)")
def tournament(size, games_per_pair, name, seed, only_models):
    """Run a round-robin tournament between all models."""
    config = load_config()
    model_names = [m["name"] for m in config["models"]]

    n_pairs = len(model_names) * (len(model_names) - 1)
    gpp = games_per_pair or config.get("tournament", {}).get("games_per_pair", 2)
    total = n_pairs * gpp

    print(f"Tournament: {len(model_names)} models, {n_pairs} pairs, "
          f"{gpp} games/pair = {total} games ({size})")
    print(f"Models: {', '.join(model_names)}")
    print()

    only = only_models.split(",") if only_models else None
    tid = run_tournament(
        config, board_size=size,
        games_per_pair=games_per_pair, name=name, seed=seed,
        only_models=only,
    )

    print(f"\nTournament {tid} complete!")
    print_ratings()


@cli.command()
def ratings():
    """Show current Elo ratings."""
    print_ratings()


@cli.command()
@click.argument("game_id", type=int)
def replay(game_id):
    """Replay a game from the database."""
    conn = db.init_db()
    game = db.get_game(conn, game_id)
    if not game:
        print(f"Game {game_id} not found.")
        sys.exit(1)

    board_words = json.loads(game["board_words"])
    board_map = json.loads(game["board_map"])
    size = int(game["board_size"].split("x")[0])

    print(f"Game {game_id}: {game['red_spymaster_model']} (red) vs "
          f"{game['blue_spymaster_model']} (blue)")
    print(f"Board size: {game['board_size']}, First team: {game['first_team']}")
    print()

    # Display board
    print("Board:")
    for row in range(size):
        parts = []
        for col in range(size):
            idx = row * size + col
            tag = board_map[idx][0].upper()
            parts.append(f"{board_words[idx]}({tag})")
        print("  " + "  ".join(f"{p:>20s}" for p in parts))
    print()

    # Display turns
    turns = db.get_game_turns(conn, game_id)
    for turn in turns:
        team = turn["team"].upper()
        clue = turn["clue_word"] or "PASS"
        num = turn["clue_number"] or 0
        print(f"Turn {turn['turn_number']} ({team}): Clue = \"{clue}\" for {num}")

        guesses = db.get_turn_guesses(conn, turn["turn_id"])
        for g in guesses:
            marker = "✓" if g["correct"] else "✗"
            print(f"  {marker} {g['guessed_word']} → {g['card_type']}")

        if turn["error"]:
            print(f"  ERROR: {turn['error']}")
        print()

    print(f"Result: {game['winner'].upper()} wins by {game['win_reason']}")
    if game["losing_team_hit_assassin"]:
        print("ASSASSIN triggered!")
    print(f"Total turns: {game['total_turns']}")

    conn.close()


@cli.command()
@click.argument("model_name")
def stats(model_name):
    """Show stats for a specific model."""
    print_model_stats(model_name)


@cli.command()
@click.option("--output", "-o", default="tournament.html", help="Output HTML path")
def view(output):
    """Generate the tournament viewer HTML."""
    from viewer import generate as gen_viewer
    gen_viewer.main(["--output", output], standalone_mode=False)


if __name__ == "__main__":
    cli()

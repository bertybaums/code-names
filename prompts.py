"""Prompt templates for Codenames AI spymasters and guessers.

Prompts do NOT specify output format — structured outputs (response_format)
handle JSON serialization. The model just needs to reason about the game.
"""


def build_spymaster_prompt(board, team, revealed_history):
    """Build the spymaster prompt."""
    opponent = "blue" if team == "red" else "red"

    team_words = board.team_words(team, unrevealed_only=True)
    opponent_words = board.team_words(opponent, unrevealed_only=True)
    bystander_words = board.team_words("bystander", unrevealed_only=True)
    assassin = board.assassin_word()
    assassin_revealed = board.revealed[board.word_index(assassin)] if assassin else True

    grid_display = board.display_grid(show_map=False)
    history_text = _format_history(revealed_history) if revealed_history else "None yet."

    system = f"""You are playing Codenames as the Spymaster for the {team.upper()} team.

Your job: give a ONE-WORD clue and a number indicating how many of your team's words relate to it.
Your goal is to help your guesser find your team's words while avoiding the assassin and opponent words.

BOARD (unrevealed words):
{grid_display}

YOUR TEAM'S WORDS (you want your guesser to pick these):
{', '.join(team_words)}

OPPONENT'S WORDS (avoid giving clues related to these):
{', '.join(opponent_words) if opponent_words else 'None remaining.'}

BYSTANDER WORDS (neutral, but waste a turn if picked):
{', '.join(bystander_words) if bystander_words else 'None remaining.'}

ASSASSIN (your guesser picks this = YOU LOSE):
{assassin if not assassin_revealed else 'Already revealed.'}

PREVIOUSLY REVEALED:
{history_text}

RULES:
- Your clue must be exactly ONE English word (no spaces, no hyphens, no numbers).
- Your clue CANNOT be any word currently on the board, or any part of a multi-word board entry.
- Your clue CANNOT be a form/variant of a board word (e.g., "BEARS" is illegal if "BEAR" is on the board).
- The number must be at least 1.

Think carefully about what single word connects as many of your team's words as possible while avoiding the assassin and opponent words. Provide your clue, the number of words it relates to, and your reasoning."""

    return [{"role": "user", "content": system}]


def build_guesser_prompt(board, team, clue_word, clue_number,
                         turn_guesses, revealed_history):
    """Build the guesser prompt."""
    unrevealed = board.unrevealed_words()
    history_text = _format_history(revealed_history) if revealed_history else "None yet."

    turn_guess_text = ""
    if turn_guesses:
        parts = []
        for g in turn_guesses:
            parts.append(f"  - {g['word']} → {g['result']}")
        turn_guess_text = "Your guesses so far this turn:\n" + "\n".join(parts)

    guesses_remaining = clue_number + 1 - len(turn_guesses)

    system = f"""You are playing Codenames as the Guesser for the {team.upper()} team.

Your spymaster gave the clue: "{clue_word}" for {clue_number}

UNREVEALED WORDS ON THE BOARD:
{', '.join(unrevealed)}

PREVIOUSLY REVEALED (earlier turns):
{history_text}

{turn_guess_text}

You have {guesses_remaining} guess(es) remaining this turn.

RULES:
- Pick ONE word from the unrevealed words that best matches the clue "{clue_word}".
- You must pick a word that is EXACTLY as written in the unrevealed words list above.
- After each correct guess, you may continue or stop by saying PASS.
- If you're unsure, it's safer to PASS than to risk hitting the assassin.

Think about which unrevealed word best matches the clue. Provide your guess (must be exactly one of the unrevealed words, or PASS to stop) and your reasoning."""

    return [{"role": "user", "content": system}]


def build_retry_spymaster_prompt(original_prompt, clue, rejection_reason):
    """Build a follow-up prompt when a spymaster's clue is rejected."""
    messages = list(original_prompt)
    messages.append({
        "role": "assistant",
        "content": f"I'll give the clue: {clue}"
    })
    messages.append({
        "role": "user",
        "content": (
            f'Your clue "{clue}" is INVALID: {rejection_reason}\n'
            f"Please try a different clue. Same rules apply."
        ),
    })
    return messages


def build_retry_guesser_prompt(original_prompt, guess, reason):
    """Build a follow-up prompt when a guesser's guess is invalid."""
    messages = list(original_prompt)
    messages.append({
        "role": "assistant",
        "content": f"I'll guess: {guess}"
    })
    messages.append({
        "role": "user",
        "content": (
            f'Your guess "{guess}" is INVALID: {reason}\n'
            f"Pick a word that is EXACTLY as written in the unrevealed words list."
        ),
    })
    return messages


def _format_history(revealed_history):
    """Format revealed history for display in prompts."""
    if not revealed_history:
        return "None yet."
    lines = []
    for entry in revealed_history:
        lines.append(f"  - {entry['word']} was {entry['type']} (revealed by {entry['team']})")
    return "\n".join(lines)

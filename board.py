"""Board generation for Codenames AI."""

import random
from dataclasses import dataclass, field
from pathlib import Path


BOARD_CONFIGS = {
    "5x5": {"size": 5, "total": 25, "first": 9, "second": 8, "bystander": 7, "assassin": 1},
    "2x2": {"size": 2, "total": 4, "first": 2, "second": 1, "bystander": 0, "assassin": 1},
}

WORDS_PATH = Path(__file__).parent / "codenames-words.txt"


def load_words(path=WORDS_PATH):
    return [line.strip() for line in path.read_text().splitlines() if line.strip()]


@dataclass
class Board:
    words: list[str]              # flat list, row-major
    card_map: list[str]           # parallel: 'red', 'blue', 'bystander', 'assassin'
    first_team: str               # 'red' or 'blue'
    size: int                     # grid dimension (5 or 2)
    revealed: list[bool] = field(default_factory=list)

    def __post_init__(self):
        if not self.revealed:
            self.revealed = [False] * len(self.words)

    def word_to_type(self, word):
        word_upper = word.upper()
        for i, w in enumerate(self.words):
            if w.upper() == word_upper:
                return self.card_map[i]
        return None

    def word_index(self, word):
        word_upper = word.upper()
        for i, w in enumerate(self.words):
            if w.upper() == word_upper:
                return i
        return None

    def reveal(self, word):
        idx = self.word_index(word)
        if idx is not None:
            self.revealed[idx] = True
            return self.card_map[idx]
        return None

    def unrevealed_words(self):
        return [w for w, r in zip(self.words, self.revealed) if not r]

    def remaining_for_team(self, team):
        return sum(
            1 for m, r in zip(self.card_map, self.revealed)
            if m == team and not r
        )

    def team_words(self, team, unrevealed_only=True):
        return [
            w for w, m, r in zip(self.words, self.card_map, self.revealed)
            if m == team and (not unrevealed_only or not r)
        ]

    def assassin_word(self):
        for w, m in zip(self.words, self.card_map):
            if m == "assassin":
                return w
        return None

    def display_grid(self, show_map=False):
        lines = []
        for row in range(self.size):
            row_parts = []
            for col in range(self.size):
                idx = row * self.size + col
                word = self.words[idx]
                if self.revealed[idx]:
                    label = f"[{word}]"
                elif show_map:
                    label = f"{word}({self.card_map[idx][0].upper()})"
                else:
                    label = word
                row_parts.append(f"{label:>20s}")
            lines.append("  ".join(row_parts))
        return "\n".join(lines)


def generate_board(words, board_size="5x5", rng=None):
    if rng is None:
        rng = random.Random()

    cfg = BOARD_CONFIGS[board_size]
    selected = rng.sample(words, cfg["total"])

    first_team = rng.choice(["red", "blue"])
    second_team = "blue" if first_team == "red" else "red"

    assignments = (
        [first_team] * cfg["first"]
        + [second_team] * cfg["second"]
        + ["bystander"] * cfg["bystander"]
        + ["assassin"] * cfg["assassin"]
    )
    rng.shuffle(assignments)

    return Board(
        words=selected,
        card_map=assignments,
        first_team=first_team,
        size=cfg["size"],
    )

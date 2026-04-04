"""Embedding-based programmatic Codenames player.

Uses Qwen3-Embedding-8B via MindRouter to compute word similarities.
Spymaster: searches a vocabulary for the best clue by cosine similarity.
Guesser: picks the unrevealed word most similar to the clue.

Inspired by the GloVe/Word2Vec agents in Mattinson et al. (2024) which
achieved 5.24 mean turns with 0% assassin rate — dramatically outperforming
all LLM agents.
"""

import json
import logging
import os
import time
from pathlib import Path

import httpx
import numpy as np

log = logging.getLogger(__name__)

# We use the Codenames word list itself as the candidate vocabulary for clues,
# plus a supplementary list of common English words for richer clue options.
VOCAB_PATH = Path(__file__).parent / "clue_vocab.txt"
WORDS_PATH = Path(__file__).parent / "codenames-words.txt"

# Cache embeddings to avoid redundant API calls
_embedding_cache = {}


def _get_embeddings(words, config):
    """Get embeddings for a list of words, using cache."""
    uncached = [w for w in words if w.upper() not in _embedding_cache]

    if uncached:
        api_key = os.environ.get(config.get("api_key_env", "MINDROUTER_API_KEY"))
        endpoint = config.get("endpoint", "https://mindrouter.uidaho.edu/v1").rstrip("/")
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        # Batch in chunks of 100
        for i in range(0, len(uncached), 100):
            batch = uncached[i:i+100]
            body = {"model": config.get("model_id", "Qwen/Qwen3-Embedding-8B"), "input": batch}
            with httpx.Client(timeout=config.get("timeout", 60.0)) as client:
                resp = client.post(f"{endpoint}/embeddings", json=body, headers=headers)
                resp.raise_for_status()
                data = resp.json()
            for item, word in zip(data["data"], batch):
                _embedding_cache[word.upper()] = np.array(item["embedding"])

    return [_embedding_cache[w.upper()] for w in words]


def _cosine_sim(a, b):
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def load_clue_vocab():
    """Load the candidate clue vocabulary."""
    vocab = set()

    # Use codenames words as base vocab
    if WORDS_PATH.exists():
        for line in WORDS_PATH.read_text().splitlines():
            word = line.strip().upper()
            if word and " " not in word:
                vocab.add(word)

    # Add supplementary vocab if available
    if VOCAB_PATH.exists():
        for line in VOCAB_PATH.read_text().splitlines():
            word = line.strip().upper()
            if word and " " not in word and word.isalpha():
                vocab.add(word)

    return sorted(vocab)


def generate_clue_vocab():
    """Generate a supplementary vocabulary of common English words for clues."""
    # Common categories that produce good Codenames clues
    words = set()

    # We'll use a curated list of ~2000 common nouns, adjectives, and concepts
    # that make good Codenames clues. These are words that tend to have
    # interesting semantic connections.
    categories = [
        # Nature
        "ANIMAL", "PLANT", "FLOWER", "GARDEN", "MOUNTAIN", "RIVER", "LAKE",
        "WEATHER", "STORM", "RAIN", "SNOW", "WIND", "THUNDER", "LIGHTNING",
        "EARTH", "GROUND", "SOIL", "ROCK", "STONE", "MINERAL", "CRYSTAL",
        "WAVE", "TIDE", "COAST", "SHORE", "ISLAND", "DESERT", "JUNGLE",
        "VALLEY", "HILL", "CLIFF", "CANYON", "VOLCANO", "GLACIER",
        # Body
        "HEAD", "FACE", "EYE", "NOSE", "MOUTH", "EAR", "HAIR", "NECK",
        "SHOULDER", "ARM", "HAND", "FINGER", "CHEST", "STOMACH", "BACK",
        "LEG", "KNEE", "FOOT", "TOE", "SKIN", "BONE", "BLOOD", "HEART",
        "BRAIN", "MUSCLE", "NERVE", "TOOTH", "TONGUE",
        # Food
        "BREAD", "BUTTER", "CHEESE", "MILK", "EGG", "MEAT", "CHICKEN",
        "FISH", "RICE", "PASTA", "SOUP", "SALAD", "CAKE", "PIE", "COOKIE",
        "CANDY", "CHOCOLATE", "SUGAR", "SALT", "PEPPER", "SPICE", "SAUCE",
        "FRUIT", "APPLE", "ORANGE", "BANANA", "GRAPE", "BERRY", "LEMON",
        "VEGETABLE", "CORN", "POTATO", "TOMATO", "ONION", "CARROT",
        "COFFEE", "TEA", "WINE", "BEER", "JUICE", "WATER",
        # Home
        "HOUSE", "ROOM", "DOOR", "WINDOW", "WALL", "FLOOR", "CEILING",
        "ROOF", "STAIR", "KITCHEN", "BEDROOM", "BATHROOM", "GARAGE",
        "TABLE", "CHAIR", "BED", "COUCH", "DESK", "SHELF", "LAMP",
        "CLOCK", "MIRROR", "CARPET", "CURTAIN", "PILLOW",
        # Clothing
        "SHIRT", "PANTS", "DRESS", "COAT", "JACKET", "SHOE", "BOOT",
        "HAT", "GLOVE", "SCARF", "BELT", "TIE", "SOCK", "UNIFORM",
        # Transportation
        "CAR", "TRUCK", "BUS", "TRAIN", "PLANE", "BOAT", "SHIP",
        "BICYCLE", "MOTORCYCLE", "HELICOPTER", "ROCKET", "SUBWAY",
        "WHEEL", "ENGINE", "FUEL", "ROAD", "BRIDGE", "TUNNEL", "TRACK",
        # Work/Tools
        "HAMMER", "SAW", "DRILL", "NAIL", "SCREW", "ROPE", "CHAIN",
        "WIRE", "PIPE", "TOOL", "MACHINE", "FACTORY", "OFFICE", "SHOP",
        # Arts/Entertainment
        "MUSIC", "SONG", "DANCE", "PAINT", "DRAW", "WRITE", "READ",
        "MOVIE", "THEATER", "STAGE", "ACTOR", "SINGER", "ARTIST",
        "CAMERA", "PHOTO", "PICTURE", "CANVAS", "SCULPTURE",
        "GUITAR", "PIANO", "DRUM", "VIOLIN", "TRUMPET",
        # Sports
        "GAME", "BALL", "GOAL", "SCORE", "TEAM", "PLAYER", "COACH",
        "FIELD", "COURT", "POOL", "RACE", "RUN", "JUMP", "THROW",
        "CATCH", "KICK", "SWIM", "CLIMB", "FIGHT", "BOX", "WRESTLE",
        # Science
        "SCIENCE", "CHEMICAL", "ELEMENT", "ATOM", "MOLECULE", "CELL",
        "GENE", "VIRUS", "BACTERIA", "ENERGY", "FORCE", "GRAVITY",
        "MAGNET", "ELECTRIC", "NUCLEAR", "SOLAR", "SPACE", "STAR",
        "PLANET", "MOON", "ORBIT", "GALAXY", "UNIVERSE", "COSMIC",
        # Abstract
        "LOVE", "HATE", "FEAR", "HOPE", "DREAM", "WISH", "MEMORY",
        "THOUGHT", "IDEA", "PLAN", "TRUTH", "SECRET", "MYSTERY",
        "POWER", "STRENGTH", "SPEED", "BEAUTY", "HONOR", "GLORY",
        "SPIRIT", "SOUL", "MAGIC", "CHARM", "CURSE", "LUCK",
        "FREEDOM", "JUSTICE", "PEACE", "WAR", "BATTLE", "VICTORY",
        # Technology
        "COMPUTER", "PHONE", "SCREEN", "KEYBOARD", "MOUSE", "PRINTER",
        "NETWORK", "SIGNAL", "CODE", "DATA", "FILE", "PROGRAM",
        "ROBOT", "LASER", "RADAR", "SATELLITE", "ANTENNA",
        # Materials
        "WOOD", "METAL", "IRON", "STEEL", "GOLD", "SILVER", "COPPER",
        "GLASS", "PLASTIC", "RUBBER", "LEATHER", "COTTON", "SILK",
        "PAPER", "BRICK", "CONCRETE", "DIAMOND", "PEARL",
        # Geography/Culture
        "CITY", "TOWN", "VILLAGE", "COUNTRY", "NATION", "KINGDOM",
        "EMPIRE", "COLONY", "BORDER", "MAP", "COMPASS", "GLOBE",
        "TEMPLE", "CHURCH", "CASTLE", "TOWER", "PALACE", "FORT",
        "MARKET", "BANK", "SCHOOL", "LIBRARY", "MUSEUM", "HOSPITAL",
        "PRISON", "COURT", "HARBOR", "PORT", "AIRPORT",
        # Actions/Concepts
        "BREAK", "BUILD", "BURN", "CUT", "DIG", "DROP", "FALL",
        "FLY", "GROW", "HIDE", "HOLD", "HUNT", "KILL", "LIFT",
        "LOCK", "MARK", "OPEN", "PULL", "PUSH", "ROLL", "SEAL",
        "SHOOT", "SINK", "SLIDE", "SPIN", "SPLIT", "SPREAD", "STICK",
        "STRIKE", "SWEEP", "SWING", "TOUCH", "TRAP", "TURN", "TWIST",
        "WRAP", "ATTACK", "DEFEND", "ESCAPE", "RESCUE", "CHASE",
        # Misc good clue words
        "ANCIENT", "ARCTIC", "AUTUMN", "BLIND", "BRIGHT", "BROAD",
        "CHEAP", "CLEAN", "COLD", "COOL", "CRISP", "CRUEL", "DARK",
        "DEAD", "DEEP", "DIRTY", "DOUBLE", "DRY", "DULL", "EMPTY",
        "EVIL", "FAIR", "FALSE", "FAMOUS", "FANCY", "FAST", "FAT",
        "FIERCE", "FINAL", "FINE", "FLAT", "FOREIGN", "FORMAL",
        "FRESH", "FROZEN", "GENTLE", "GIANT", "GOLDEN", "GRAND",
        "GRAVE", "GREEN", "GROSS", "GUILTY", "HARD", "HARSH", "HEAVY",
        "HIGH", "HOLLOW", "HOLY", "HOT", "HUGE", "HUMBLE", "HUNGRY",
        "ILLEGAL", "INNOCENT", "INTENSE", "INVISIBLE", "IRON",
        "JOINT", "KEEN", "LARGE", "LATE", "LEGAL", "LIGHT", "LIQUID",
        "LITTLE", "LIVING", "LONE", "LONG", "LOOSE", "LOUD", "LOW",
        "LUCKY", "MAIN", "MAJOR", "MASSIVE", "MINOR", "MODERN",
        "NARROW", "NATIVE", "NATURAL", "NEAT", "NOBLE", "NORMAL",
        "NUDE", "ODD", "OLD", "OPPOSITE", "ORGANIC", "ORIGINAL",
        "OUTER", "PALE", "PARALLEL", "PLAIN", "POLAR", "POOR",
        "PRIME", "PRIVATE", "PROPER", "PROUD", "PUBLIC", "PURE",
        "QUICK", "QUIET", "RANDOM", "RAPID", "RARE", "RAW", "REAL",
        "REGULAR", "REMOTE", "RICH", "RIGID", "ROTTEN", "ROUGH",
        "ROUND", "ROYAL", "RURAL", "SACRED", "SAFE", "SAVAGE",
        "SHARP", "SHINY", "SHORT", "SILENT", "SIMPLE", "SINGLE",
        "SLIM", "SLOW", "SMALL", "SMART", "SMOOTH", "SOFT", "SOLID",
        "SOUR", "SPARE", "SPECIAL", "STEEP", "STIFF", "STILL",
        "STRAIGHT", "STRANGE", "STRICT", "STRONG", "SUBTLE", "SUDDEN",
        "SUPER", "SUPREME", "SWEET", "SWIFT", "TALL", "TENDER",
        "THICK", "THIN", "TIGHT", "TINY", "TOTAL", "TOUGH",
        "TROPICAL", "TWIN", "UGLY", "UNIQUE", "UPPER", "URBAN",
        "USEFUL", "VAGUE", "VAST", "VERTICAL", "VIOLENT", "VIRTUAL",
        "VITAL", "VIVID", "WARM", "WEAK", "WEIRD", "WESTERN", "WHOLE",
        "WIDE", "WILD", "WISE", "WOODEN", "YOUNG",
    ]
    return categories


def _score_clue(clue_embed, team_embeds, avoid_embeds, assassin_embed,
                top_n=None):
    """Score a candidate clue word.

    Returns (score, num_words_connected).
    Higher score = better clue.
    """
    # Similarities to team words
    team_sims = sorted(
        [_cosine_sim(clue_embed, te) for te in team_embeds],
        reverse=True,
    )

    # Similarity to assassin (penalty)
    assassin_sim = _cosine_sim(clue_embed, assassin_embed) if assassin_embed is not None else 0

    # Max similarity to avoid words (opponent + bystander)
    max_avoid_sim = max(
        (_cosine_sim(clue_embed, ae) for ae in avoid_embeds),
        default=0,
    )

    # Find how many team words are "clearly" connected:
    # a team word counts if its similarity to the clue exceeds
    # the max avoid similarity by a margin
    margin = 0.03
    connected = 0
    for ts in team_sims:
        if ts > max_avoid_sim + margin and ts > assassin_sim + margin * 2:
            connected += 1
        else:
            break

    if connected == 0:
        return -1, 0

    # Limit to top_n if specified
    if top_n and connected > top_n:
        connected = top_n

    # Score: sum of similarities for connected words, penalized by avoid/assassin proximity
    score = sum(team_sims[:connected])
    score -= max_avoid_sim * 0.5
    score -= assassin_sim * 1.0  # heavy assassin penalty

    return score, connected


def embedding_spymaster(board, team, config):
    """Programmatic spymaster using embeddings.

    Returns (clue_word, clue_number, reasoning, latency_ms).
    """
    from clue_validator import validate_clue

    start = time.monotonic()

    opponent = "blue" if team == "red" else "red"
    team_words = board.team_words(team, unrevealed_only=True)
    opponent_words = board.team_words(opponent, unrevealed_only=True)
    bystander_words = board.team_words("bystander", unrevealed_only=True)
    assassin = board.assassin_word()
    assassin_revealed = board.revealed[board.word_index(assassin)] if assassin else True

    avoid_words = opponent_words + bystander_words
    all_board_words = board.unrevealed_words()

    # Load vocabulary
    vocab = load_clue_vocab()
    supplementary = generate_clue_vocab()
    all_candidates = list(set(vocab + supplementary))

    # Filter out board words
    candidates = []
    for w in all_candidates:
        valid, _ = validate_clue(w, all_board_words)
        if valid:
            candidates.append(w)

    # Get embeddings for everything
    all_words_to_embed = list(set(
        candidates + team_words + avoid_words +
        ([assassin] if assassin and not assassin_revealed else []) +
        [w.upper() for w in all_board_words]
    ))
    _get_embeddings(all_words_to_embed, config)

    # Get cached embeddings
    team_embeds = [_embedding_cache[w.upper()] for w in team_words]
    avoid_embeds = [_embedding_cache[w.upper()] for w in avoid_words]
    assassin_embed = _embedding_cache.get(assassin.upper()) if assassin and not assassin_revealed else None

    # Score all candidates
    best_score = -1
    best_clue = None
    best_num = 0

    for candidate in candidates:
        embed = _embedding_cache.get(candidate.upper())
        if embed is None:
            continue
        score, num = _score_clue(embed, team_embeds, avoid_embeds, assassin_embed)
        if score > best_score:
            best_score = score
            best_clue = candidate
            best_num = num

    latency = int((time.monotonic() - start) * 1000)

    if best_clue is None:
        return None, 0, "No valid clue found", latency

    # Build reasoning
    clue_embed = _embedding_cache[best_clue.upper()]
    team_sims = [(w, _cosine_sim(clue_embed, _embedding_cache[w.upper()]))
                 for w in team_words]
    team_sims.sort(key=lambda x: -x[1])
    reasoning = f"Clue '{best_clue}' for {best_num}. " + \
        "Similarities: " + ", ".join(f"{w}={s:.3f}" for w, s in team_sims)

    return best_clue, best_num, reasoning, latency


def embedding_guesser(board, team, clue_word, clue_number, turn_guesses, config):
    """Programmatic guesser using embeddings.

    Returns (guess_word, reasoning, latency_ms).
    """
    start = time.monotonic()

    unrevealed = board.unrevealed_words()
    already_guessed = {g["word"].upper() for g in turn_guesses}
    candidates = [w for w in unrevealed if w.upper() not in already_guessed]

    if not candidates:
        return "PASS", "No candidates left", 0

    # Get embeddings
    all_words = candidates + [clue_word]
    _get_embeddings(all_words, config)

    clue_embed = _embedding_cache[clue_word.upper()]

    # Score by similarity to clue
    scored = []
    for word in candidates:
        embed = _embedding_cache.get(word.upper())
        if embed is not None:
            sim = _cosine_sim(clue_embed, embed)
            scored.append((word, sim))

    scored.sort(key=lambda x: -x[1])
    latency = int((time.monotonic() - start) * 1000)

    if not scored:
        return "PASS", "Could not compute similarities", latency

    # Check if we've used enough guesses or similarity is too low
    guesses_made = len(turn_guesses)
    if guesses_made >= clue_number:
        # We've matched the clue number; only continue if very confident
        if scored[0][1] < 0.65:
            reasoning = f"Used all {clue_number} guesses. Top: {scored[0][0]}={scored[0][1]:.3f} (too low)"
            return "PASS", reasoning, latency

    best_word, best_sim = scored[0]
    reasoning = f"Best match: {best_word}={best_sim:.3f}. " + \
        "Others: " + ", ".join(f"{w}={s:.3f}" for w, s in scored[1:4])

    return best_word, reasoning, latency

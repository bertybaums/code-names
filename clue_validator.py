"""Clue validation for Codenames AI.

Enforces that spymaster clues are legal:
- Single word, alphabetic only
- Not any board word or component of a multi-word board entry
- Not a substring of (or containing) a board word (min 3 chars)
- Not sharing a stem with any board word (Porter stemmer)
"""


def validate_clue(clue, board_words):
    """Check if a clue is legal given the board words.

    Returns (is_valid, rejection_reason).
    """
    clue = clue.strip()

    if not clue:
        return False, "Clue is empty"

    if " " in clue or "-" in clue:
        return False, "Clue must be a single word (no spaces or hyphens)"

    if not clue.isalpha():
        return False, "Clue must contain only letters"

    clue_upper = clue.upper()

    # Build set of all tokens from board words (including components of multi-word entries)
    all_tokens = set()
    for w in board_words:
        w_upper = w.strip().upper()
        all_tokens.add(w_upper)
        for part in w_upper.split():
            all_tokens.add(part)

    # Exact match
    if clue_upper in all_tokens:
        return False, f"'{clue}' is a board word or part of one"

    # Substring containment (min 3 chars to avoid false positives)
    for token in all_tokens:
        if len(token) >= 3 and len(clue_upper) >= 3:
            if token in clue_upper or clue_upper in token:
                return False, f"'{clue}' overlaps with board word '{token}'"

    # Stemming check
    clue_stem = _porter_stem(clue.lower())
    for token in all_tokens:
        if _porter_stem(token.lower()) == clue_stem:
            return False, f"'{clue}' stem matches board word '{token}'"

    return True, ""


# ---------------------------------------------------------------------------
# Minimal Porter Stemmer (self-contained, no dependencies)
# Based on the Porter 1980 algorithm.
# ---------------------------------------------------------------------------

def _porter_stem(word):
    """Apply Porter stemming to a single lowercase word."""
    if len(word) <= 2:
        return word

    # Step 1a
    if word.endswith("sses"):
        word = word[:-2]
    elif word.endswith("ies"):
        word = word[:-2]
    elif not word.endswith("ss") and word.endswith("s"):
        word = word[:-1]

    # Step 1b
    step1b_extra = False
    if word.endswith("eed"):
        stem = word[:-3]
        if _measure(stem) > 0:
            word = word[:-1]
    elif word.endswith("ed"):
        stem = word[:-2]
        if _has_vowel(stem):
            word = stem
            step1b_extra = True
    elif word.endswith("ing"):
        stem = word[:-3]
        if _has_vowel(stem):
            word = stem
            step1b_extra = True

    if step1b_extra:
        if word.endswith("at") or word.endswith("bl") or word.endswith("iz"):
            word += "e"
        elif _double_consonant(word) and word[-1] not in "lsz":
            word = word[:-1]
        elif _measure(word) == 1 and _cvc(word):
            word += "e"

    # Step 1c
    if word.endswith("y"):
        stem = word[:-1]
        if _has_vowel(stem):
            word = stem + "i"

    # Step 2
    _step2_map = {
        "ational": "ate", "tional": "tion", "enci": "ence", "anci": "ance",
        "izer": "ize", "abli": "able", "alli": "al", "entli": "ent",
        "eli": "e", "ousli": "ous", "ization": "ize", "ation": "ate",
        "ator": "ate", "alism": "al", "iveness": "ive", "fulness": "ful",
        "ousness": "ous", "aliti": "al", "iviti": "ive", "biliti": "ble",
    }
    for suffix, replacement in _step2_map.items():
        if word.endswith(suffix):
            stem = word[: -len(suffix)]
            if _measure(stem) > 0:
                word = stem + replacement
            break

    # Step 3
    _step3_map = {
        "icate": "ic", "ative": "", "alize": "al",
        "iciti": "ic", "ical": "ic", "ful": "", "ness": "",
    }
    for suffix, replacement in _step3_map.items():
        if word.endswith(suffix):
            stem = word[: -len(suffix)]
            if _measure(stem) > 0:
                word = stem + replacement
            break

    # Step 4
    _step4_suffixes = [
        "al", "ance", "ence", "er", "ic", "able", "ible", "ant",
        "ement", "ment", "ent", "ion", "ou", "ism", "ate", "iti",
        "ous", "ive", "ize",
    ]
    for suffix in _step4_suffixes:
        if word.endswith(suffix):
            stem = word[: -len(suffix)]
            if _measure(stem) > 1:
                if suffix == "ion" and stem and stem[-1] in "st":
                    word = stem
                elif suffix != "ion":
                    word = stem
            break

    # Step 5a
    if word.endswith("e"):
        stem = word[:-1]
        if _measure(stem) > 1 or (_measure(stem) == 1 and not _cvc(stem)):
            word = stem

    # Step 5b
    if _double_consonant(word) and word[-1] == "l" and _measure(word) > 1:
        word = word[:-1]

    return word


def _is_consonant(word, i):
    c = word[i]
    if c in "aeiou":
        return False
    if c == "y":
        return i == 0 or not _is_consonant(word, i - 1)
    return True


def _measure(word):
    """Count VC sequences (the 'm' value in Porter's notation)."""
    n = 0
    i = 0
    length = len(word)
    # Skip initial consonants
    while i < length and _is_consonant(word, i):
        i += 1
    while i < length:
        # Skip vowels
        while i < length and not _is_consonant(word, i):
            i += 1
        if i >= length:
            break
        n += 1
        # Skip consonants
        while i < length and _is_consonant(word, i):
            i += 1
    return n


def _has_vowel(word):
    return any(not _is_consonant(word, i) for i in range(len(word)))


def _double_consonant(word):
    return (
        len(word) >= 2
        and word[-1] == word[-2]
        and _is_consonant(word, len(word) - 1)
    )


def _cvc(word):
    """Check if word ends consonant-vowel-consonant (with c not w/x/y)."""
    if len(word) < 3:
        return False
    return (
        _is_consonant(word, len(word) - 1)
        and not _is_consonant(word, len(word) - 2)
        and _is_consonant(word, len(word) - 3)
        and word[-1] not in "wxy"
    )

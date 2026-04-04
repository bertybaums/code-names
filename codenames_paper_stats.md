# Quantitative Statistics from "Codenames as a Benchmark for Large Language Models"
## arxiv 2412.11373v1 (December 2024)
## Extracted: March 30, 2026

---

## Paper Setup

- **Board**: 25 English words
- **Red team (goes first)**: 9 target words
- **Blue team**: 8 target words
- **Assassin words**: 1
- **Civilian words**: 7
- **Trials per matchup**: 100
- **Total games**: ~4,600

### Models Tested (only 6 could follow rules reliably)
- OpenAI o1-preview (2024-09-12)
- OpenAI o1-mini (2024-09-12)
- OpenAI GPT-4o (2024-08-06)
- Google Gemini-1.5 Pro 002
- Anthropic Claude Sonnet-3.5 (2024-10-22)
- Meta Llama-3.1 70B-Instruct

### Models that failed to follow game rules (no results reported)
- GPT-3.5-turbo (0125), Haiku-3.5 (2024-10-22), Llama 3.2 3B-Instruct, Phi-3-medium 128k-Instruct, Mistral-0.3 7B-Instruct, Mixtral-0.1 8x7B-Instruct

### Word-vector baselines
- Word2Vec, GloVe, Combined (Word2Vec+GloVe)

### Key definitions
- **Loss**: game ended by selecting the assassin word
- **Blue avg**: avg number of opponent (blue) words incorrectly selected per game
- **Civilian avg**: avg number of civilian words incorrectly selected per game
- **Clues avg**: avg clue number given by codemaster per turn
- **Guesses avg**: avg number of guesses made per turn
- **Stop Early**: % of turns guesser stopped before using all allowed guesses
- **Stop Late**: % of turns guesser attempted more guesses than clue number + 1

### Statistical test
- o1-preview superiority confirmed via one-sided t-test (p < 0.05) against all other models in single-team version

### Human baselines
- **None reported in this paper**

---

## TABLE I: Single Team Version (100 trials each)

Format: Codemaster - Guesser | Mean turns | Median | Min | StdDev | Loss% | Blue avg (std) | Civilian avg (std) | Clues avg (std) | Guesses avg (std) | Stop Early% | Stop Late%

### LLM Agent Pairs

| Codemaster | Guesser | Mean | Med | Min | SD | Loss% | Blue avg (sd) | Civ avg (sd) | Clue# avg (sd) | Guess avg (sd) | StopEarly% | StopLate% |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| o1-preview | o1-preview | 8.41 | 6 | 4 | 6.53 | 13% | 0.84 (0.83) | 1.20 (1.08) | 1.95 (0.69) | 1.88 (0.70) | 11.0% | 14.2% |
| o1-mini | o1-mini | 11.10 | 7 | 4 | 7.93 | 24% | 1.74 (1.19) | 1.80 (1.24) | 2.09 (0.70) | 1.91 (0.81) | 11.6% | 16.0% |
| GPT-4o | GPT-4o | 10.58 | 8 | 6 | 6.41 | 16% | 0.96 (0.97) | 1.25 (1.13) | 1.51 (0.60) | 1.45 (0.56) | 0.0% | 0.0% |
| GPT-4o | Gemini-1.5 | 9.81 | 8 | 6 | 5.21 | 10% | 1.19 (1.00) | 1.01 (0.88) | 1.50 (0.60) | 1.39 (0.56) | 6.1% | 0.5% |
| GPT-4o | Sonnet-3.5 | 10.50 | 8 | 6 | 6.20 | 15% | 1.26 (1.16) | 1.13 (0.86) | 1.52 (0.61) | 1.45 (0.57) | 2.0% | 1.6% |
| GPT-4o | Llama-3.1 | 11.17 | 9 | 5 | 6.43 | 17% | 1.43 (1.25) | 1.18 (0.94) | 1.49 (0.60) | 1.41 (0.56) | 3.1% | 3.8% |
| Gemini-1.5 | GPT-4o | 10.95 | 8 | 5 | 6.55 | 17% | 1.42 (1.23) | 1.35 (1.14) | 1.62 (0.72) | 1.49 (0.64) | 0.3% | 0.0% |
| Gemini-1.5 | Gemini-1.5 | 10.38 | 8 | 5 | 6.08 | 14% | 1.36 (1.06) | 1.01 (0.88) | 1.63 (0.73) | 1.46 (0.62) | 3.9% | 0.2% |
| Gemini-1.5 | Sonnet-3.5 | 11.18 | 8 | 5 | 6.84 | 19% | 1.42 (1.08) | 1.15 (0.97) | 1.62 (0.72) | 1.51 (0.65) | 2.9% | 2.8% |
| Gemini-1.5 | Llama-3.1 | 11.28 | 9 | 5 | 6.46 | 17% | 1.76 (1.45) | 1.51 (1.10) | 1.65 (0.71) | 1.48 (0.63) | 3.7% | 1.8% |
| Sonnet-3.5 | GPT-4o | 12.34 | 7 | 5 | 8.39 | 30% | 1.94 (1.05) | 1.87 (1.27) | 2.04 (0.59) | 1.88 (0.58) | 3.7% | 0.0% |
| Sonnet-3.5 | Gemini-1.5 | 10.55 | 8 | 5 | 6.89 | 18% | 1.90 (1.24) | 1.74 (1.06) | 2.03 (0.61) | 1.75 (0.64) | 18.1% | 0.0% |
| Sonnet-3.5 | Sonnet-3.5 | 11.01 | 8 | 5 | 7.55 | 22% | 1.97 (1.15) | 1.81 (1.00) | 2.02 (0.60) | 1.84 (0.61) | 6.9% | 0.6% |
| Sonnet-3.5 | Llama-3.1 | 11.31 | 8 | 5 | 7.20 | 21% | 1.95 (1.34) | 1.66 (1.13) | 1.99 (0.61) | 1.66 (0.65) | 21.3% | 0.5% |
| Llama-3.1 | GPT-4o | 10.56 | 9 | 6 | 5.51 | 12% | 1.13 (0.99) | 0.95 (0.86) | 1.34 (0.53) | 1.29 (0.50) | 0.3% | 0.0% |
| Llama-3.1 | Gemini-1.5 | 10.54 | 9 | 6 | 5.29 | 11% | 1.01 (0.94) | 1.04 (0.93) | 1.32 (0.51) | 1.29 (0.48) | 0.8% | 0.3% |
| Llama-3.1 | Sonnet-3.5 | 10.79 | 9 | 6 | 5.66 | 13% | 1.10 (0.95) | 1.01 (0.99) | 1.34 (0.53) | 1.30 (0.50) | 0.6% | 1.6% |
| Llama-3.1 | Llama-3.1 | 10.18 | 9 | 6 | 4.66 | 8% | 1.28 (1.10) | 1.13 (1.02) | 1.30 (0.51) | 1.30 (0.50) | 0.1% | 5.7% |

### Word-Vector Agent Pairs

| Codemaster | Guesser | Mean | Med | Min | SD | Loss% | Blue avg (sd) | Civ avg (sd) | Clue# avg (sd) | Guess avg (sd) | StopEarly% | StopLate% |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Word2Vec | Word2Vec | 6.81 | 6 | 4 | 0.97 | 0% | 0.0 (0.0) | 0.0 (0.0) | 1.46 (0.64) | 1.46 (0.64) | 0.0% | 0.0% |
| Word2Vec | GloVe | 12.35 | 9 | 5 | 7.14 | 22% | 1.68 (1.78) | 1.38 (1.53) | 1.53 (0.65) | 1.38 (0.58) | 0.0% | 0.0% |
| Word2Vec | Combined | 10.64 | 8 | 5 | 6.72 | 16% | 0.99 (1.48) | 1.05 (1.30) | 1.48 (0.64) | 1.39 (0.60) | 0.0% | 0.0% |
| GloVe | Word2Vec | 12.21 | 9 | 5 | 7.52 | 24% | 2.03 (1.53) | 1.45 (1.19) | 1.74 (0.76) | 1.54 (0.69) | 0.0% | 0.0% |
| GloVe | GloVe | 5.24 | 5 | 4 | 0.79 | 0% | 0.0 (0.0) | 0.0 (0.0) | 1.72 (0.75) | 1.72 (0.75) | 0.0% | 0.0% |
| GloVe | Combined | 5.42 | 5 | 4 | 0.89 | 0% | 0.15 (0.39) | 0.09 (0.29) | 1.71 (0.75) | 1.70 (0.75) | 0.0% | 0.0% |
| Combined | Word2Vec | 11.18 | 8 | 5 | 7.37 | 21% | 1.47 (1.30) | 1.04 (1.07) | 1.66 (0.74) | 1.54 (0.69) | 0.0% | 0.0% |
| Combined | GloVe | 5.86 | 6 | 4 | 2.18 | 1% | 0.09 (0.32) | 0.12 (0.36) | 1.64 (0.73) | 1.63 (0.72) | 0.0% | 0.0% |
| Combined | Combined | 5.53 | 6 | 4 | 0.83 | 0% | 0.0 (0.0) | 0.0 (0.0) | 1.63 (0.73) | 1.63 (0.73) | 0.0% | 0.0% |

---

## TABLE II: Two Teams Version (100 trials each)

Format: Red team vs Blue team | Red win% / Blue win% | Red assassin% / Blue assassin%

### LLM Matchups

| Red Team | Blue Team | Red Win% | Blue Win% | Red Assassin% | Blue Assassin% |
|---|---|---|---|---|---|
| GPT-4o | GPT-4o | 40% | 60% | 13% | 19% |
| GPT-4o | Gemini-1.5 | 59% | 41% | 16% | 13% |
| GPT-4o | Sonnet-3.5 | 52% | 48% | 11% | 19% |
| GPT-4o | Llama-3.1 | 53% | 47% | 14% | 9% |
| Gemini-1.5 | GPT-4o | 30% | 70% | 18% | 12% |
| Gemini-1.5 | Gemini-1.5 | 45% | 55% | 17% | 13% |
| Gemini-1.5 | Sonnet-3.5 | 45% | 55% | 13% | 20% |
| Gemini-1.5 | Llama-3.1 | 46% | 54% | 17% | 13% |
| Sonnet-3.5 | GPT-4o | 50% | 50% | 16% | 20% |
| Sonnet-3.5 | Gemini-1.5 | 58% | 42% | 24% | 13% |
| Sonnet-3.5 | Sonnet-3.5 | 58% | 42% | 18% | 24% |
| Sonnet-3.5 | Llama-3.1 | 61% | 39% | 16% | 15% |
| Llama-3.1 | GPT-4o | 45% | 55% | 8% | 21% |
| Llama-3.1 | Gemini-1.5 | 53% | 47% | 9% | 13% |
| Llama-3.1 | Sonnet-3.5 | 44% | 56% | 15% | 19% |
| Llama-3.1 | Llama-3.1 | 43% | 57% | 10% | 12% |

### Word-Vector Matchups

| Red Team | Blue Team | Red Win% | Blue Win% | Red Assassin% | Blue Assassin% |
|---|---|---|---|---|---|
| Word2Vec | Word2Vec | 49% | 51% | 0% | 0% |
| Word2Vec | GloVe | 28% | 72% | 0% | 0% |
| Word2Vec | Combined | 34% | 66% | 0% | 0% |
| GloVe | Word2Vec | 79% | 21% | 0% | 0% |
| GloVe | GloVe | 55% | 45% | 0% | 0% |
| GloVe | Combined | 63% | 35% | 0% | 0% |
| Combined | Word2Vec | 69% | 31% | 0% | 0% |
| Combined | GloVe | 47% | 53% | 0% | 0% |
| Combined | Combined | 57% | 43% | 0% | 0% |

---

## Aggregated / Derived Statistics

### Two-Team Aggregated Win Rates (from paper text)
- Sonnet-3.5 as red team: **56.75% average win rate** (best red team)
- GPT-4o as blue team: **58.75% average win rate** (best blue team)

### First-Team (Red) Advantage
- Paper states: "There does not appear to be a substantial difference between each side"
- Red goes first but must find 9 words vs blue's 8

### Same-Model Loss Rates (single team, assassin selection)
| Model | Loss% |
|---|---|
| o1-preview | 13% |
| o1-mini | 24% |
| GPT-4o | 16% |
| Gemini-1.5 | 14% |
| Sonnet-3.5 | 22% |
| Llama-3.1 | 8% |

### Codemaster Risk Ranking (by avg clue number, high = risky)
1. o1-mini: 2.09
2. Sonnet-3.5: ~2.02
3. o1-preview: 1.95
4. Gemini-1.5: ~1.63
5. GPT-4o: ~1.51
6. Llama-3.1: ~1.32 (most cautious)

### First Turn Clue Numbers (from Figure 2)
- Gemini-1.5: 2.72 average first turn clue number
- Sonnet-3.5: 2.72 average first turn clue number (identical to Gemini)
- Llama-3.1: exhibits a "much more gradual decrease" across turns

### Best Single-Team Results (same-model pairs)
| Model | Mean Turns | Loss% |
|---|---|---|
| o1-preview | 8.41 | 13% |
| Llama-3.1 | 10.18 | 8% |
| Gemini-1.5 | 10.38 | 14% |
| GPT-4o | 10.58 | 16% |
| Sonnet-3.5 | 11.01 | 22% |
| o1-mini | 11.10 | 24% |

### Best Cross-Model Single-Team Result
- GPT-4o (codemaster) + Gemini-1.5 (guesser): Mean 9.81, Loss 10%

---

## Cost Data

| Provider | Cost (USD) |
|---|---|
| OpenAI total | $514 |
| -- o1-preview alone | $288 |
| Google DeepMind (Gemini) | $141 |
| Anthropic (Claude) | $177 |

---

## Notes
- No human baselines reported
- No temperature or hyperparameter settings reported
- No confidence intervals beyond the one-sided t-test (p < 0.05) for o1-preview
- Invalid clue/guess threshold: 10 consecutive invalid attempts before default action
- Word-vector agents never select assassin (deterministic strategy)
- GloVe-GloVe achieved best mean turns (5.24) but uses deterministic word-vector similarity (not comparable to LLM agents)

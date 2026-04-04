"""Generate a self-contained HTML tournament viewer from codenames.db.

Usage:
    python3 viewer.py [--db codenames.db] [--output tournament.html]
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

import click
import plotly.graph_objects as go

import db


# ---------------------------------------------------------------------------
# Layer 1: SQL Queries
# ---------------------------------------------------------------------------

def _board_sizes(conn):
    rows = conn.execute(
        "SELECT DISTINCT board_size FROM games WHERE winner IS NOT NULL"
    ).fetchall()
    return sorted(set(r["board_size"] for r in rows))


def _leaderboard(conn, board_size=None):
    models = {r["name"]: {"name": r["name"], "elo": r["elo_rating"],
                          "games": 0, "wins": 0}
              for r in db.get_all_ratings(conn)}

    size_clause = "AND board_size = ?" if board_size else ""
    params = (board_size,) if board_size else ()

    rows = conn.execute(
        f"SELECT red_spymaster_model AS model, winner FROM games "
        f"WHERE winner IS NOT NULL AND winner != 'none' {size_clause}",
        params,
    ).fetchall()
    for r in rows:
        m = models.get(r["model"])
        if m:
            m["games"] += 1
            if r["winner"] == "red":
                m["wins"] += 1

    rows = conn.execute(
        f"SELECT blue_spymaster_model AS model, winner FROM games "
        f"WHERE winner IS NOT NULL AND winner != 'none' {size_clause}",
        params,
    ).fetchall()
    for r in rows:
        m = models.get(r["model"])
        if m:
            m["games"] += 1
            if r["winner"] == "blue":
                m["wins"] += 1

    result = []
    for m in sorted(models.values(), key=lambda x: -x["elo"]):
        if m["games"] == 0 and board_size:
            continue
        losses = m["games"] - m["wins"]
        wr = (m["wins"] / m["games"] * 100) if m["games"] > 0 else 0
        result.append({**m, "losses": losses, "win_rate": round(wr, 1)})
    return result


def _elo_history(conn):
    rows = conn.execute(
        "SELECT model_name, game_id, new_elo FROM elo_history "
        "WHERE role LIKE '%spymaster%' ORDER BY game_id"
    ).fetchall()
    by_model = defaultdict(list)
    seen = set()
    for r in rows:
        key = (r["model_name"], r["game_id"])
        if key not in seen:
            seen.add(key)
            by_model[r["model_name"]].append({
                "game_id": r["game_id"], "elo": r["new_elo"]
            })
    return dict(by_model)


def _head_to_head(conn, board_size=None):
    size_clause = "AND board_size = ?" if board_size else ""
    params = (board_size,) if board_size else ()
    rows = conn.execute(
        f"SELECT red_spymaster_model AS red, blue_spymaster_model AS blue, winner "
        f"FROM games WHERE winner IS NOT NULL AND winner != 'none' "
        f"AND win_reason != 'aborted' {size_clause}",
        params,
    ).fetchall()
    h2h = defaultdict(lambda: {"wins": 0, "losses": 0, "total": 0})
    for r in rows:
        red, blue, winner = r["red"], r["blue"], r["winner"]
        # From red's perspective
        key = (red, blue)
        h2h[key]["total"] += 1
        if winner == "red":
            h2h[key]["wins"] += 1
        else:
            h2h[key]["losses"] += 1
    return dict(h2h)


def _model_details(conn, board_size=None):
    size_clause = "AND board_size = ?" if board_size else ""
    g_size_clause = "AND g.board_size = ?" if board_size else ""
    params = (board_size,) if board_size else ()

    models = {}
    for row in db.get_all_ratings(conn):
        name = row["name"]
        m = {"name": name, "elo": row["elo_rating"],
             "games": 0, "wins": 0, "assassin_losses": 0,
             "total_turns_won": 0, "wins_count_for_avg": 0,
             "clue_valid": 0, "clue_total": 0,
             "wins_as_red": 0, "wins_as_blue": 0, "games_as_red": 0, "games_as_blue": 0}
        models[name] = m

    # Games as red
    for r in conn.execute(
        f"SELECT red_spymaster_model AS model, winner, win_reason, "
        f"losing_team_hit_assassin, total_turns FROM games "
        f"WHERE winner IS NOT NULL AND winner != 'none' {size_clause}",
        params,
    ).fetchall():
        m = models.get(r["model"])
        if not m:
            continue
        m["games_as_red"] += 1
        if r["winner"] == "red":
            m["wins_as_red"] += 1
            m["total_turns_won"] += r["total_turns"] or 0
            m["wins_count_for_avg"] += 1
        elif r["losing_team_hit_assassin"]:
            m["assassin_losses"] += 1

    # Games as blue
    for r in conn.execute(
        f"SELECT blue_spymaster_model AS model, winner, win_reason, "
        f"losing_team_hit_assassin, total_turns FROM games "
        f"WHERE winner IS NOT NULL AND winner != 'none' {size_clause}",
        params,
    ).fetchall():
        m = models.get(r["model"])
        if not m:
            continue
        m["games_as_blue"] += 1
        if r["winner"] == "blue":
            m["wins_as_blue"] += 1
            m["total_turns_won"] += r["total_turns"] or 0
            m["wins_count_for_avg"] += 1
        elif r["losing_team_hit_assassin"]:
            m["assassin_losses"] += 1

    # Clue validity
    for r in conn.execute(
        f"SELECT g.red_spymaster_model AS model, t.clue_valid "
        f"FROM turns t JOIN games g ON t.game_id = g.game_id "
        f"WHERE t.team = 'red' AND t.clue_valid IS NOT NULL {g_size_clause}",
        params,
    ).fetchall():
        m = models.get(r["model"])
        if m:
            m["clue_total"] += 1
            if r["clue_valid"]:
                m["clue_valid"] += 1

    for r in conn.execute(
        f"SELECT g.blue_spymaster_model AS model, t.clue_valid "
        f"FROM turns t JOIN games g ON t.game_id = g.game_id "
        f"WHERE t.team = 'blue' AND t.clue_valid IS NOT NULL {g_size_clause}",
        params,
    ).fetchall():
        m = models.get(r["model"])
        if m:
            m["clue_total"] += 1
            if r["clue_valid"]:
                m["clue_valid"] += 1

    result = {}
    for name, m in models.items():
        m["games"] = m["games_as_red"] + m["games_as_blue"]
        if m["games"] == 0 and board_size:
            continue
        m["wins"] = m["wins_as_red"] + m["wins_as_blue"]
        m["losses"] = m["games"] - m["wins"]
        m["win_rate"] = round(m["wins"] / m["games"] * 100, 1) if m["games"] else 0
        m["assassin_rate"] = round(m["assassin_losses"] / m["games"] * 100, 1) if m["games"] else 0
        m["avg_turns_to_win"] = round(m["total_turns_won"] / m["wins_count_for_avg"], 1) if m["wins_count_for_avg"] else 0
        m["clue_validity"] = round(m["clue_valid"] / m["clue_total"] * 100, 1) if m["clue_total"] else 0
        result[name] = m
    return result


def _game_list(conn):
    rows = conn.execute(
        "SELECT game_id, board_size, red_spymaster_model, blue_spymaster_model, "
        "winner, win_reason, total_turns, started_at "
        "FROM games WHERE winner IS NOT NULL ORDER BY game_id"
    ).fetchall()
    return [dict(r) for r in rows]


def _extract_reasoning(raw_response, max_len=3000):
    """Extract reasoning text from raw API response JSON."""
    if not raw_response:
        return None
    try:
        data = json.loads(raw_response)
        msg = data["choices"][0]["message"]
        content = msg.get("content") or ""
        reasoning_content = msg.get("reasoning_content") or ""

        # Try to parse inner JSON for reasoning field
        inner_reasoning = ""
        if content:
            try:
                inner = json.loads(content)
                inner_reasoning = inner.get("reasoning", "")
            except (json.JSONDecodeError, TypeError):
                # Content might have JSON embedded
                import re
                m = re.search(r'\{.*\}', content, re.DOTALL)
                if m:
                    try:
                        inner = json.loads(m.group(0))
                        inner_reasoning = inner.get("reasoning", "")
                    except json.JSONDecodeError:
                        pass

        parts = []
        if inner_reasoning:
            parts.append(inner_reasoning)
        if reasoning_content and reasoning_content != inner_reasoning:
            parts.append(reasoning_content[:max_len])

        result = "\n\n".join(parts) if parts else None
        if result and len(result) > max_len:
            result = result[:max_len] + "..."
        return result
    except (json.JSONDecodeError, KeyError, IndexError):
        return None


def _game_replay_data(conn, game_id):
    game = db.get_game(conn, game_id)
    if not game:
        return None

    board_words = json.loads(game["board_words"])
    board_map = json.loads(game["board_map"])
    size = int(game["board_size"].split("x")[0])

    turns_data = []
    for turn in db.get_game_turns(conn, game_id):
        guesses_data = []
        for g in db.get_turn_guesses(conn, turn["turn_id"]):
            guesses_data.append({
                "guess_number": g["guess_number"],
                "guessed_word": g["guessed_word"],
                "card_type": g["card_type"],
                "correct": bool(g["correct"]),
                "reasoning": _extract_reasoning(g["raw_response"]),
            })

        # Classify error type for display
        error_type = None
        if turn["error"]:
            raw = turn["clue_raw_response"] or ""
            if "Errno" in raw or "nodename" in raw or "timed out" in raw.lower():
                error_type = "API unreachable"
            elif raw.startswith("{"):
                error_type = "Model couldn't produce valid JSON"
            else:
                error_type = turn["error"]

        turns_data.append({
            "turn_number": turn["turn_number"],
            "team": turn["team"],
            "clue_word": turn["clue_word"],
            "clue_number": turn["clue_number"],
            "clue_valid": bool(turn["clue_valid"]) if turn["clue_valid"] is not None else None,
            "clue_reasoning": _extract_reasoning(turn["clue_raw_response"]),
            "error": turn["error"],
            "error_type": error_type,
            "guesses": guesses_data,
        })

    return {
        "game_id": game_id,
        "board_words": board_words,
        "board_map": board_map,
        "board_size": size,
        "first_team": game["first_team"],
        "red_model": game["red_spymaster_model"],
        "blue_model": game["blue_spymaster_model"],
        "winner": game["winner"],
        "win_reason": game["win_reason"],
        "total_turns": game["total_turns"],
        "turns": turns_data,
    }


def _fun_stats(conn, board_size=None):
    size_clause = "AND board_size = ?" if board_size else ""
    g_size_clause = "AND g.board_size = ?" if board_size else ""
    params = (board_size,) if board_size else ()

    top_clues = conn.execute(
        f"SELECT UPPER(t.clue_word) AS clue, COUNT(*) AS cnt "
        f"FROM turns t JOIN games g ON t.game_id = g.game_id "
        f"WHERE t.clue_valid = 1 AND t.clue_word IS NOT NULL {g_size_clause} "
        f"GROUP BY UPPER(t.clue_word) ORDER BY cnt DESC LIMIT 20",
        params,
    ).fetchall()

    longest = conn.execute(
        f"SELECT game_id, red_spymaster_model, blue_spymaster_model, "
        f"winner, total_turns FROM games "
        f"WHERE winner IS NOT NULL AND win_reason != 'aborted' {size_clause} "
        f"ORDER BY total_turns DESC LIMIT 5",
        params,
    ).fetchall()

    assassins = conn.execute(
        f"SELECT game_id, red_spymaster_model, blue_spymaster_model, "
        f"winner, total_turns FROM games WHERE win_reason = 'assassin' {size_clause}",
        params,
    ).fetchall()

    latency = conn.execute(
        f"SELECT g.red_spymaster_model AS model, AVG(t.clue_latency_ms) AS avg_ms "
        f"FROM turns t JOIN games g ON t.game_id = g.game_id "
        f"WHERE t.team = 'red' AND t.clue_latency_ms > 0 {g_size_clause} "
        f"GROUP BY g.red_spymaster_model "
        f"UNION "
        f"SELECT g.blue_spymaster_model AS model, AVG(t.clue_latency_ms) AS avg_ms "
        f"FROM turns t JOIN games g ON t.game_id = g.game_id "
        f"WHERE t.team = 'blue' AND t.clue_latency_ms > 0 {g_size_clause} "
        f"GROUP BY g.blue_spymaster_model",
        params + params,
    ).fetchall()

    # Merge latency (model may appear twice from union)
    lat_map = defaultdict(list)
    for r in latency:
        lat_map[r["model"]].append(r["avg_ms"])
    avg_latency = {m: sum(v) / len(v) for m, v in lat_map.items()}

    # Game length distribution
    game_lengths = conn.execute(
        f"SELECT total_turns FROM games "
        f"WHERE winner IS NOT NULL AND winner != 'none' AND win_reason != 'aborted' {size_clause}",
        params,
    ).fetchall()
    game_lengths = [r["total_turns"] for r in game_lengths if r["total_turns"]]

    # Avg clue number
    avg_clue = conn.execute(
        f"SELECT AVG(t.clue_number) as avg_clue FROM turns t JOIN games g ON t.game_id = g.game_id "
        f"WHERE t.clue_number IS NOT NULL {g_size_clause}",
        params,
    ).fetchone()
    avg_clue_num = round(avg_clue["avg_clue"], 2) if avg_clue["avg_clue"] else 0

    # Assassin rate
    total_real = len(game_lengths)
    assassin_count = len([dict(r) for r in assassins])
    assassin_rate = round(assassin_count / total_real * 100, 1) if total_real else 0

    return {
        "top_clues": [{"clue": r["clue"], "count": r["cnt"]} for r in top_clues],
        "longest_games": [dict(r) for r in longest],
        "assassin_games": [dict(r) for r in assassins],
        "avg_latency": avg_latency,
        "game_lengths": game_lengths,
        "avg_clue_number": avg_clue_num,
        "assassin_rate": assassin_rate,
        "total_real_games": total_real,
    }


def _summary_stats(conn, board_size=None):
    size_clause = "AND board_size = ?" if board_size else ""
    g_size_clause = "AND g.board_size = ?" if board_size else ""
    params = (board_size,) if board_size else ()

    total_games = conn.execute(
        f"SELECT COUNT(*) AS c FROM games WHERE winner IS NOT NULL AND winner != 'none' {size_clause}",
        params,
    ).fetchone()["c"]
    total_models = conn.execute("SELECT COUNT(*) AS c FROM models").fetchone()["c"]
    total_turns = conn.execute(
        f"SELECT COUNT(*) AS c FROM turns t JOIN games g ON t.game_id = g.game_id WHERE 1=1 {g_size_clause}",
        params,
    ).fetchone()["c"]
    total_guesses = conn.execute(
        f"SELECT COUNT(*) AS c FROM guesses gs JOIN turns t ON gs.turn_id = t.turn_id "
        f"JOIN games g ON t.game_id = g.game_id WHERE 1=1 {g_size_clause}",
        params,
    ).fetchone()["c"]
    return {
        "total_games": total_games,
        "total_models": total_models,
        "total_turns": total_turns,
        "total_guesses": total_guesses,
    }


# ---------------------------------------------------------------------------
# Layer 2: Plotly Charts
# ---------------------------------------------------------------------------

MODEL_COLORS = [
    "#e53935", "#1e88e5", "#43a047", "#fb8c00", "#8e24aa",
    "#00acc1", "#d81b60", "#6d4c41", "#546e7a", "#fdd835",
]


def _chart_elo_progression(elo_data, model_names):
    fig = go.Figure()
    for i, name in enumerate(model_names):
        points = elo_data.get(name, [])
        if not points:
            continue
        fig.add_trace(go.Scatter(
            x=list(range(len(points))),
            y=[p["elo"] for p in points],
            mode="lines+markers",
            name=name,
            line=dict(color=MODEL_COLORS[i % len(MODEL_COLORS)], width=2),
            marker=dict(size=5),
        ))
    fig.update_layout(
        title="Elo Rating Progression",
        xaxis_title="Games Played",
        yaxis_title="Elo Rating",
        template="none",
        height=400,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    return fig


def _chart_h2h_heatmap(h2h, model_names):
    n = len(model_names)
    z = [[0.5] * n for _ in range(n)]
    text = [[""] * n for _ in range(n)]

    for i, a in enumerate(model_names):
        for j, b in enumerate(model_names):
            if i == j:
                z[i][j] = None
                text[i][j] = "-"
                continue
            key = (a, b)
            rec = h2h.get(key, {"wins": 0, "losses": 0, "total": 0})
            if rec["total"] > 0:
                wr = rec["wins"] / rec["total"]
                z[i][j] = wr
                text[i][j] = f"{rec['wins']}-{rec['losses']}"
            else:
                z[i][j] = None
                text[i][j] = "N/A"

    fig = go.Figure(go.Heatmap(
        z=z,
        x=model_names,
        y=model_names,
        text=text,
        texttemplate="%{text}",
        colorscale=[[0, "#ef5350"], [0.5, "#ffffff"], [1, "#66bb6a"]],
        zmin=0, zmax=1,
        colorbar=dict(title="Win Rate"),
    ))
    fig.update_layout(
        title="Head-to-Head Win Rate (row vs column, as Red team)",
        template="none",
        height=400,
        xaxis=dict(title="Blue Team (opponent)"),
        yaxis=dict(title="Red Team", autorange="reversed"),
    )
    return fig


def _chart_model_comparison(model_details, model_names):
    metrics = ["win_rate", "assassin_rate", "clue_validity"]
    labels = ["Win Rate %", "Assassin Loss %", "Clue Validity %"]

    fig = go.Figure()
    for i, name in enumerate(model_names):
        d = model_details[name]
        fig.add_trace(go.Bar(
            name=name,
            x=labels,
            y=[d[m] for m in metrics],
            marker_color=MODEL_COLORS[i % len(MODEL_COLORS)],
        ))
    fig.update_layout(
        barmode="group",
        title="Model Comparison",
        template="none",
        height=400,
        yaxis_title="Percentage",
    )
    return fig


def _chart_top_clues(top_clues):
    clues = list(reversed(top_clues[:15]))
    fig = go.Figure(go.Bar(
        x=[c["count"] for c in clues],
        y=[c["clue"] for c in clues],
        orientation="h",
        marker_color="#42a5f5",
    ))
    fig.update_layout(
        title="Most Common Clue Words",
        template="none",
        height=400,
        xaxis_title="Times Used",
    )
    return fig


def _chart_latency(avg_latency):
    names = sorted(avg_latency.keys())
    fig = go.Figure(go.Bar(
        x=names,
        y=[avg_latency[n] / 1000 for n in names],
        marker_color="#fb8c00",
    ))
    fig.update_layout(
        title="Average Spymaster Clue Latency",
        template="none",
        height=350,
        yaxis_title="Seconds",
    )
    return fig


def _render_chart(fig, div_id):
    fig_json = fig.to_json()
    return (
        f'<div class="chart" id="{div_id}"></div>\n'
        f"<script>(function(){{ var d = {fig_json}; "
        f"plotlyDarkLayout(d.layout); "
        f"Plotly.newPlot('{div_id}', d.data, d.layout, {{responsive:true}}); }})();</script>\n"
    )


# ---------------------------------------------------------------------------
# Layer 3: HTML Assembly
# ---------------------------------------------------------------------------

CSS = """
/* ----------------------------------------------------------------
   Design tokens — every color used in the UI flows through these.
   WCAG AA contrast ratios:
     - Normal text on bg: >= 4.5:1
     - Large/bold text on bg: >= 3:1
     - UI components: >= 3:1
   ---------------------------------------------------------------- */
:root {
    /* Surfaces */
    --bg: #fafafa;
    --card-bg: #ffffff;
    --card-shadow: rgba(0,0,0,0.08);
    --surface-hover: #f0f0f0;
    --surface-active: #e3f2fd;

    /* Borders */
    --border: #d0d0d0;
    --border-light: #e0e0e0;

    /* Text — all meet 4.5:1 on --bg / --card-bg */
    --text-primary: #1a1a1a;      /* 14.5:1 on white */
    --text-secondary: #555555;    /* 7.5:1 on white */
    --text-muted: #717171;        /* 4.6:1 on white */

    /* Accent */
    --accent: #1565c0;
    --accent-text: #1565c0;       /* 5.6:1 on white */

    /* Team colors — these are used on colored backgrounds, text is always white */
    --red: #d32f2f;
    --blue: #1976d2;
    --green: #388e3c;
    --yellow: #f57c00;
    --dark: #37474f;

    /* Badge backgrounds (light tints with high-contrast text) */
    --red-bg: #ffebee; --red-text: #b71c1c;
    --blue-bg: #e3f2fd; --blue-text: #0d47a1;
    --green-bg: #e8f5e9; --green-text: #1b5e20;
    --yellow-bg: #fff3e0; --yellow-text: #bf360c;
    --dark-bg: #eceff1; --dark-text: #263238;

    /* Board cards */
    --card-unrevealed-bg: #fff8e1;
    --card-unrevealed-text: #4e342e;
    --card-unrevealed-border: #d7cba8;
    --bystander-text: #333333;

    /* Turn log guess colors — must be readable on tinted backgrounds */
    --guess-correct: #1b5e20;
    --guess-wrong: #b71c1c;

    /* Controls */
    --control-bg: #ffffff;
    --control-text: #1a1a1a;
    --control-border: #bdbdbd;

    /* Code / pre */
    --pre-bg: #f5f5f5;
    --pre-text: #1a1a1a;

    /* Win rate bar */
    --wr-track: #d0d0d0;

    /* Table header */
    --th-bg: #f5f5f5;
    --th-text: #424242;
}

@media (prefers-color-scheme: dark) {
    :root {
        --bg: #121212;
        --card-bg: #1e1e1e;
        --card-shadow: rgba(0,0,0,0.4);
        --surface-hover: #2c2c2c;
        --surface-active: #1a3a5c;

        --border: #444444;
        --border-light: #333333;

        --text-primary: #e8e8e8;      /* 15:1 on #121212 */
        --text-secondary: #b3b3b3;    /* 8.5:1 on #121212 */
        --text-muted: #9e9e9e;        /* 5.8:1 on #121212 */

        --accent: #64b5f6;
        --accent-text: #90caf9;       /* 8.6:1 on #121212 */

        --red: #ef5350;
        --blue: #42a5f5;
        --green: #66bb6a;
        --yellow: #ffa726;
        --dark: #78909c;

        --red-bg: #3e1a1a; --red-text: #ef9a9a;
        --blue-bg: #1a2e4a; --blue-text: #90caf9;
        --green-bg: #1a3a1a; --green-text: #a5d6a7;
        --yellow-bg: #3e2e10; --yellow-text: #ffcc80;
        --dark-bg: #263238; --dark-text: #cfd8dc;

        --card-unrevealed-bg: #3a3520;
        --card-unrevealed-text: #e6d9a6;
        --card-unrevealed-border: #5a5030;
        --bystander-text: #e0e0e0;

        --guess-correct: #a5d6a7;
        --guess-wrong: #ef9a9a;

        --control-bg: #2a2a2a;
        --control-text: #e0e0e0;
        --control-border: #555555;

        --pre-bg: #2a2a2a;
        --pre-text: #d4d4d4;

        --wr-track: #444444;

        --th-bg: #252525;
        --th-text: #b3b3b3;
    }
}

/* ---------------------------------------------------------------- */
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
       background: var(--bg); color: var(--text-primary); line-height: 1.6; }
.container { max-width: 1100px; margin: 0 auto; padding: 20px; }
h1 { font-size: 1.8em; margin-bottom: 4px; }
h2 { font-size: 1.3em; margin: 20px 0 10px; }
h3 { font-size: 1.1em; margin: 12px 0 8px; }

/* Navigation */
nav { display: flex; gap: 0; border-bottom: 2px solid var(--border); margin-bottom: 20px; flex-wrap: wrap; }
nav button { padding: 10px 20px; border: none; background: none; cursor: pointer;
             font-size: 0.95em; color: var(--text-secondary); border-bottom: 3px solid transparent;
             transition: all 0.2s; }
nav button:hover { color: var(--text-primary); background: var(--surface-hover); }
nav button.active { color: var(--accent-text); border-bottom-color: var(--accent); font-weight: 600; }

/* Tabs */
.tab { display: none; }
.tab.active { display: block; }

/* Cards */
.stats-row { display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 20px; }
.stat-card { background: var(--card-bg); border-radius: 8px; padding: 16px 24px;
             box-shadow: 0 1px 4px var(--card-shadow); flex: 1; min-width: 140px; text-align: center; }
.stat-card .value { font-size: 2em; font-weight: 700; color: var(--accent-text); }
.stat-card .label { font-size: 0.85em; color: var(--text-muted); }

/* Tables */
table { width: 100%; border-collapse: collapse; margin: 10px 0; background: var(--card-bg);
        border-radius: 8px; overflow: hidden; box-shadow: 0 1px 4px var(--card-shadow); }
th, td { padding: 10px 14px; text-align: left; border-bottom: 1px solid var(--border-light); }
th { background: var(--th-bg); font-weight: 600; font-size: 0.85em; color: var(--th-text);
     text-transform: uppercase; letter-spacing: 0.5px; cursor: pointer; }
th:hover { background: var(--surface-hover); }
tr:hover { background: var(--surface-hover); }
tr.clickable { cursor: pointer; }
tr.clickable:hover { background: var(--surface-active); }

/* Badges */
.badge { display: inline-block; padding: 2px 10px; border-radius: 12px;
         font-size: 0.8em; font-weight: 600; }
.badge-red { background: var(--red-bg); color: var(--red-text); }
.badge-blue { background: var(--blue-bg); color: var(--blue-text); }
.badge-green { background: var(--green-bg); color: var(--green-text); }
.badge-yellow { background: var(--yellow-bg); color: var(--yellow-text); }
.badge-dark { background: var(--dark-bg); color: var(--dark-text); }

/* Win rate bar */
.wr-bar { display: inline-block; height: 8px; border-radius: 4px; background: var(--wr-track);
          width: 80px; vertical-align: middle; margin-left: 6px; }
.wr-bar-fill { height: 100%; border-radius: 4px; background: var(--green); }

/* Board */
.board-grid { display: grid; gap: 6px; max-width: 600px; margin: 16px auto; }
.board-5x5 { grid-template-columns: repeat(5, 1fr); }
.board-2x2 { grid-template-columns: repeat(2, 1fr); }
.board-card { padding: 14px 6px; text-align: center; border-radius: 8px; font-weight: 700;
              font-size: 0.78em; transition: all 0.3s; min-height: 56px;
              display: flex; align-items: center; justify-content: center;
              border: 2px solid transparent; text-transform: uppercase; letter-spacing: 0.5px; }
.card-unrevealed { background: var(--card-unrevealed-bg); color: var(--card-unrevealed-text);
                   border-color: var(--card-unrevealed-border); }
.card-red { background: var(--red); color: white; }
.card-blue { background: var(--blue); color: white; }
.card-bystander { background: var(--border); color: var(--bystander-text); }
.card-assassin { background: var(--dark); color: white; }
.card-current { border-color: #ffeb3b; box-shadow: 0 0 12px rgba(255,235,59,0.6);
                transform: scale(1.05); }

/* Replay controls */
.replay-controls { display: flex; gap: 8px; justify-content: center; margin: 16px 0;
                   align-items: center; flex-wrap: wrap; }
.replay-controls button { padding: 8px 16px; border: 1px solid var(--control-border); border-radius: 6px;
                          background: var(--control-bg); color: var(--control-text);
                          cursor: pointer; font-size: 0.9em; }
.replay-controls button:hover { background: var(--surface-hover); }
.replay-controls select { padding: 8px 12px; border: 1px solid var(--control-border); border-radius: 6px;
                          font-size: 0.9em; background: var(--control-bg); color: var(--control-text); }
.replay-status { text-align: center; color: var(--text-muted); font-size: 0.9em; margin: 8px 0; }

/* Turn log */
.turn-log { max-width: 700px; margin: 16px auto; }
.turn-entry { padding: 10px 14px; margin: 6px 0; border-radius: 8px;
              border-left: 4px solid var(--border); color: var(--text-primary); }
.turn-entry.red { border-left-color: var(--red); background: var(--red-bg); }
.turn-entry.blue { border-left-color: var(--blue); background: var(--blue-bg); }
.turn-entry.future { opacity: 0.3; }
.turn-entry .clue { font-weight: 700; }
.turn-entry .guess-list { margin-top: 4px; font-size: 0.9em; }
.guess-correct { color: var(--guess-correct); }
.guess-wrong { color: var(--guess-wrong); }
.guess-assassin { color: white; background: var(--dark); padding: 1px 6px; border-radius: 4px; }

/* Filters */
.filters { display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; align-items: center; }
.filters select { padding: 6px 12px; border: 1px solid var(--control-border); border-radius: 6px;
                  background: var(--control-bg); color: var(--control-text); }
.filters label { font-size: 0.85em; color: var(--text-secondary); }

/* Chart container */
.chart { margin: 16px 0; }

/* Model buttons */
.model-btns { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; }
.model-btns button { padding: 6px 16px; border: 2px solid var(--control-border); border-radius: 20px;
                     background: var(--control-bg); color: var(--text-primary);
                     cursor: pointer; font-size: 0.85em; }
.model-btns button:hover { background: var(--surface-hover); }
.model-btns button.active { border-color: var(--accent); background: var(--blue-bg);
                            color: var(--accent-text); }

details { margin: 4px 0; }
summary { cursor: pointer; font-size: 0.85em; color: var(--text-muted); }
details pre { background: var(--pre-bg); color: var(--pre-text); padding: 10px; border-radius: 6px;
              font-size: 0.8em; max-height: 200px; overflow-y: auto;
              white-space: pre-wrap; word-break: break-word; }

.subtitle { color: var(--text-secondary); font-size: 0.9em; margin-bottom: 16px; }
"""


def _build_js_replay():
    return """
let currentGame = null;
let steps = [];
let stepIndex = -1;
let autoplayTimer = null;

function loadGame(gameId) {
    if (autoplayTimer) { clearInterval(autoplayTimer); autoplayTimer = null; }
    currentGame = GAME_DATA[gameId];
    if (!currentGame) return;

    // Build flat step list
    steps = [];
    for (let t = 0; t < currentGame.turns.length; t++) {
        steps.push({type: 'clue', turnIdx: t});
        for (let g = 0; g < currentGame.turns[t].guesses.length; g++) {
            steps.push({type: 'guess', turnIdx: t, guessIdx: g});
        }
    }
    stepIndex = -1;
    renderBoard();
    renderTurnLog();
    updateStatus();
    document.getElementById('replay-result').innerHTML = '';
}

function renderBoard() {
    const grid = document.getElementById('board-grid');
    if (!currentGame) { grid.innerHTML = '<p>Select a game to replay.</p>'; return; }

    grid.className = 'board-grid board-' + currentGame.board_size + 'x' + currentGame.board_size;

    // Figure out which words are revealed up to stepIndex
    const revealed = new Set();
    let currentWord = null;
    for (let i = 0; i <= stepIndex && i < steps.length; i++) {
        const s = steps[i];
        if (s.type === 'guess') {
            const guess = currentGame.turns[s.turnIdx].guesses[s.guessIdx];
            if (guess.guessed_word !== 'PASS') {
                revealed.add(guess.guessed_word.toUpperCase());
                if (i === stepIndex) currentWord = guess.guessed_word.toUpperCase();
            }
        }
    }

    let html = '';
    for (let i = 0; i < currentGame.board_words.length; i++) {
        const word = currentGame.board_words[i];
        const wordUpper = word.toUpperCase();
        const cardType = currentGame.board_map[i];
        let cls = 'board-card ';
        if (revealed.has(wordUpper)) {
            cls += 'card-' + cardType;
            if (wordUpper === currentWord) cls += ' card-current';
        } else {
            cls += 'card-unrevealed';
        }
        html += '<div class="' + cls + '">' + word + '</div>';
    }
    grid.innerHTML = html;
}

function renderTurnLog() {
    const log = document.getElementById('turn-log');
    if (!currentGame) { log.innerHTML = ''; return; }

    // Determine which turn/guess we're at
    let currentTurn = -1;
    let currentGuess = -1;
    if (stepIndex >= 0 && stepIndex < steps.length) {
        const s = steps[stepIndex];
        currentTurn = s.turnIdx;
        currentGuess = s.type === 'guess' ? s.guessIdx : -1;
    }

    // Figure out which guesses have been revealed
    const revealedUpTo = {};  // turnIdx -> max guessIdx revealed
    for (let i = 0; i <= stepIndex && i < steps.length; i++) {
        const s = steps[i];
        if (s.type === 'guess') {
            revealedUpTo[s.turnIdx] = Math.max(revealedUpTo[s.turnIdx] || -1, s.guessIdx);
        }
    }

    let html = '';
    for (let t = 0; t < currentGame.turns.length; t++) {
        const turn = currentGame.turns[t];
        const isFuture = t > currentTurn;
        const cls = turn.team + (isFuture ? ' future' : '');
        html += '<div class="turn-entry ' + cls + '">';
        html += '<span class="clue">Turn ' + turn.turn_number + ' (' + turn.team.toUpperCase() + '): ';
        if (turn.clue_word && turn.clue_valid !== false) {
            html += '"' + turn.clue_word + '" for ' + turn.clue_number;
        } else if (turn.error) {
            const label = turn.error_type || 'FAILED';
            const badge = label.includes('API') ? 'badge-yellow' : 'badge-dark';
            html += '<span class="badge ' + badge + '">' + escHtml(label) + '</span>';
        }
        html += '</span>';

        if (turn.clue_reasoning && !isFuture) {
            html += '<details><summary>Spymaster reasoning</summary><pre>' +
                    escHtml(turn.clue_reasoning) + '</pre></details>';
        }

        // Show guesses up to current step
        const maxGuess = revealedUpTo[t];
        if (maxGuess !== undefined && !isFuture) {
            html += '<div class="guess-list">';
            for (let g = 0; g <= maxGuess && g < turn.guesses.length; g++) {
                const guess = turn.guesses[g];
                if (guess.guessed_word === 'PASS') {
                    html += '<span class="guess-wrong">PASS</span> ';
                    continue;
                }
                let gcls = 'guess-wrong';
                if (guess.correct) gcls = 'guess-correct';
                if (guess.card_type === 'assassin') gcls = 'guess-assassin';
                const icon = guess.correct ? '\\u2713' : '\\u2717';
                html += '<span class="' + gcls + '">' + icon + ' ' + guess.guessed_word +
                        ' (' + guess.card_type + ')</span> ';
                if (guess.reasoning) {
                    html += '<details><summary>reasoning</summary><pre>' +
                            escHtml(guess.reasoning) + '</pre></details>';
                }
            }
            html += '</div>';
        }
        html += '</div>';
    }
    log.innerHTML = html;
}

function updateStatus() {
    const el = document.getElementById('replay-status');
    if (!currentGame) { el.textContent = ''; return; }
    if (stepIndex < 0) {
        el.textContent = 'Ready — press Next to begin';
    } else if (stepIndex >= steps.length) {
        el.textContent = 'Game over';
        showResult();
    } else {
        const s = steps[stepIndex];
        const turn = currentGame.turns[s.turnIdx];
        if (s.type === 'clue') {
            el.textContent = 'Turn ' + turn.turn_number + ': ' + turn.team.toUpperCase() +
                             ' spymaster gives clue';
        } else {
            el.textContent = 'Turn ' + turn.turn_number + ': ' + turn.team.toUpperCase() +
                             ' guesser — guess ' + (s.guessIdx + 1);
        }
    }
}

function showResult() {
    if (!currentGame) return;
    const el = document.getElementById('replay-result');
    const w = currentGame.winner.toUpperCase();
    const reason = currentGame.win_reason;
    let badge = 'badge-green';
    if (reason === 'assassin') badge = 'badge-dark';
    else if (reason === 'max_turns' || reason === 'aborted') badge = 'badge-yellow';
    el.innerHTML = '<h3>' + w + ' wins! <span class="badge ' + badge + '">' + reason + '</span></h3>';
}

function stepForward() {
    if (!currentGame) return;
    if (stepIndex < steps.length - 1) {
        stepIndex++;
        renderBoard();
        renderTurnLog();
        updateStatus();
    } else if (stepIndex === steps.length - 1) {
        stepIndex = steps.length;
        updateStatus();
    }
}

function stepBack() {
    if (!currentGame || stepIndex < 0) return;
    stepIndex--;
    renderBoard();
    renderTurnLog();
    updateStatus();
    document.getElementById('replay-result').innerHTML = '';
}

function stepStart() {
    stepIndex = -1;
    renderBoard();
    renderTurnLog();
    updateStatus();
    document.getElementById('replay-result').innerHTML = '';
}

function stepEnd() {
    if (!currentGame) return;
    stepIndex = steps.length;
    renderBoard();
    renderTurnLog();
    updateStatus();
}

function toggleAutoplay() {
    if (autoplayTimer) {
        clearInterval(autoplayTimer);
        autoplayTimer = null;
        document.getElementById('btn-autoplay').textContent = '\\u25B6 Auto';
    } else {
        autoplayTimer = setInterval(() => {
            if (stepIndex >= steps.length) {
                clearInterval(autoplayTimer);
                autoplayTimer = null;
                document.getElementById('btn-autoplay').textContent = '\\u25B6 Auto';
                return;
            }
            stepForward();
        }, 1200);
        document.getElementById('btn-autoplay').textContent = '\\u23F8 Pause';
    }
}

function escHtml(s) {
    if (!s) return '';
    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function goToGame(gameId) {
    // Switch to replay tab and load game
    switchTab('replay');
    document.getElementById('game-select').value = gameId;
    loadGame(gameId);
}
"""


def _build_js_tabs():
    return """
function switchTab(tabName) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('nav button').forEach(b => b.classList.remove('active'));
    document.getElementById('tab-' + tabName).classList.add('active');
    document.querySelector('nav button[data-tab="' + tabName + '"]').classList.add('active');
}
"""


def _build_js_filters():
    return """
function applyFilters() {
    const model = document.getElementById('filter-model').value;
    const reason = document.getElementById('filter-reason').value;
    const size = currentSize;
    const rows = document.querySelectorAll('#games-table tbody tr');
    rows.forEach(row => {
        let show = true;
        if (model && row.dataset.red !== model && row.dataset.blue !== model) show = false;
        if (reason && row.dataset.reason !== reason) show = false;
        if (size !== 'all' && row.dataset.size !== size) show = false;
        row.style.display = show ? '' : 'none';
    });

    // Also filter replay game selector
    const opts = document.querySelectorAll('#game-select option');
    opts.forEach(opt => {
        if (!opt.value) return; // keep placeholder
        const optSize = opt.dataset.size;
        opt.style.display = (size === 'all' || optSize === size) ? '' : 'none';
    });
}
"""


def _build_js_size_switch():
    return """
const MODEL_COLORS = ['#e53935','#1e88e5','#43a047','#fb8c00','#8e24aa',
                       '#00acc1','#d81b60','#6d4c41','#546e7a','#fdd835'];

function switchSize(size) {
    currentSize = size;
    document.querySelectorAll('#size-toggle button').forEach(b => {
        b.classList.toggle('active', b.textContent.toLowerCase() === size || (b.textContent === 'All' && size === 'all'));
    });

    const s = STATS_BY_SIZE[size];
    if (!s) return;
    MODEL_DETAILS = s.model_details;

    // Update subtitle
    const sub = s.summary;
    document.getElementById('subtitle').textContent =
        sub.total_games + ' games across ' + sub.total_models + ' models — ' +
        sub.total_turns + ' turns, ' + sub.total_guesses + ' guesses';

    // Update summary cards
    document.getElementById('summary-cards').innerHTML =
        '<div class="stat-card"><div class="value">' + sub.total_games + '</div><div class="label">Games Played</div></div>' +
        '<div class="stat-card"><div class="value">' + sub.total_models + '</div><div class="label">Models</div></div>' +
        '<div class="stat-card"><div class="value">' + sub.total_turns + '</div><div class="label">Total Turns</div></div>' +
        '<div class="stat-card"><div class="value">' + sub.total_guesses + '</div><div class="label">Total Guesses</div></div>';

    // Update leaderboard table
    const lb = s.leaderboard;
    let html = '<table><thead><tr><th>Rank</th><th>Model</th><th>Elo</th><th>Games</th>' +
               '<th>Wins</th><th>Losses</th><th>Win Rate</th></tr></thead><tbody>';
    lb.forEach((m, i) => {
        const wrWidth = Math.round(m.win_rate * 0.8);
        html += '<tr><td>' + (i+1) + '</td><td><strong>' + m.name + '</strong></td>' +
                '<td>' + Math.round(m.elo) + '</td><td>' + m.games + '</td><td>' + m.wins + '</td>' +
                '<td>' + m.losses + '</td><td>' + m.win_rate + '%' +
                '<span class="wr-bar"><span class="wr-bar-fill" style="width:' + wrWidth + '%"></span></span>' +
                '</td></tr>';
    });
    html += '</tbody></table>';
    document.getElementById('leaderboard-table').innerHTML = html;

    // Update insight blurb
    const insightEl = document.getElementById('leaderboard-insight');
    if (currentSize === '5x5' && lb.length > 0) {
        const top = lb[0];
        const smallModels = lb.filter(m => m.name.match(/7b|3b|0\\.5b/i));
        const embedModel = lb.find(m => m.name.includes('embedding'));
        let insight = '<strong>Key finding:</strong> ';
        if (smallModels.length > 0 && lb.indexOf(smallModels[0]) < 3) {
            insight += 'Smaller models outperform larger ones at Codenames. ' +
                'Consistent with <a href="https://arxiv.org/abs/2412.11373">Mattinson et al. (2024)</a>, ' +
                'where word-vector agents (GloVe) dramatically beat frontier LLMs. ' +
                'Bigger models give more aggressive clues (higher clue numbers) but hit the assassin far more often. ';
        }
        if (embedModel && lb.indexOf(embedModel) < 4) {
            insight += 'The embedding-based agent (pure word vectors, no LLM) ranks among the top performers &mdash; ' +
                'confirming that semantic similarity alone is a powerful Codenames strategy. ';
        }
        insight += '<em>Caveat: game counts per matchup are small (2 games/pair); ' +
            'rankings may shift with more data.</em>';
        insightEl.innerHTML = insight;
        insightEl.style.display = '';
    } else if (currentSize === '2x2') {
        insightEl.innerHTML = '<strong>Note:</strong> 2&times;2 games are very short (1&ndash;2 turns) ' +
            'and largely determined by the first clue. Rankings here are less stable than 5&times;5.';
        insightEl.style.display = '';
    } else {
        insightEl.innerHTML = '';
        insightEl.style.display = 'none';
    }

    // Update head-to-head heatmap
    renderH2H(s);

    // Update model buttons
    const names = lb.map(m => m.name);
    let btnsHtml = '';
    names.forEach(n => {
        btnsHtml += '<button data-model="' + n + '" onclick="selectModel(\\'' + n + '\\')">' + n + '</button>';
    });
    document.getElementById('model-btns').innerHTML = btnsHtml;
    document.getElementById('model-stats-cards').innerHTML = '<p style="color:var(--text-muted)">Select a model above.</p>';

    // Update comparison chart
    renderComparison(s, names);

    // Update games table filter
    applyFilters();

    // Update fun stats
    renderFunStats(s);
}

function renderH2H(s) {
    const h2h = s.h2h;
    const names = s.leaderboard.map(m => m.name);
    const n = names.length;
    const z = [], text = [];
    for (let i = 0; i < n; i++) {
        z.push([]); text.push([]);
        for (let j = 0; j < n; j++) {
            if (i === j) { z[i].push(null); text[i].push('-'); continue; }
            const key = names[i] + '||' + names[j];
            const rec = h2h[key];
            if (rec && rec.total > 0) {
                z[i].push(rec.wins / rec.total);
                text[i].push(rec.wins + '-' + rec.losses);
            } else {
                z[i].push(null); text[i].push('N/A');
            }
        }
    }
    const layout = {
        title: 'Head-to-Head Win Rate (row vs column, as Red team)',
        template: 'none', height: 500,
        xaxis: {title: {text: 'Blue Team (opponent)', standoff: 20}, tickangle: -45},
        yaxis: {title: {text: 'Red Team', standoff: 20}, autorange: 'reversed'},
        margin: {l: 140, b: 120},
    };
    plotlyDarkLayout(layout);
    Plotly.newPlot('chart-h2h', [{
        type: 'heatmap', z: z, x: names, y: names, text: text,
        texttemplate: '%{text}',
        colorscale: [[0,'#ef5350'],[0.5,'#ffffff'],[1,'#66bb6a']],
        zmin: 0, zmax: 1, colorbar: {title: 'Win Rate'},
    }], layout, {responsive: true});
}

function renderComparison(s, names) {
    const traces = [];
    const metrics = ['win_rate', 'assassin_rate', 'clue_validity'];
    const labels = ['Win Rate %', 'Assassin Loss %', 'Clue Validity %'];
    names.forEach((name, i) => {
        const d = s.model_details[name];
        if (!d) return;
        traces.push({
            type: 'bar', name: name,
            x: labels, y: [d.win_rate, d.assassin_rate, d.clue_validity],
            marker: {color: MODEL_COLORS[i % MODEL_COLORS.length]},
        });
    });
    const layout = {barmode: 'group', title: 'Model Comparison', template: 'none', height: 400, yaxis: {title: 'Percentage'}};
    plotlyDarkLayout(layout);
    Plotly.newPlot('chart-comparison', traces, layout, {responsive: true});
}

// Benchmark data from Mattinson et al. (2024) — 5x5 only
const BENCHMARKS = {
    'o1-preview':    {mean_turns: 8.41, median: 6, loss_pct: 13, clue_avg: 1.95},
    'GPT-4o':        {mean_turns: 10.58, median: 8, loss_pct: 16, clue_avg: 1.51},
    'Gemini-1.5':    {mean_turns: 10.38, median: 8, loss_pct: 14, clue_avg: 1.63},
    'Sonnet-3.5':    {mean_turns: 11.01, median: 8, loss_pct: 22, clue_avg: 2.02},
    'Llama-3.1 70B': {mean_turns: 10.18, median: 9, loss_pct: 8,  clue_avg: 1.30},
    'GloVe-GloVe':   {mean_turns: 5.24,  median: 5, loss_pct: 0,  clue_avg: 1.72},
};

function renderFunStats(s) {
    const fun = s.fun;
    const is5x5 = currentSize === '5x5';

    // Benchmark comparison table (5x5 only)
    let benchHtml = '';
    if (is5x5 && fun.total_real_games > 0) {
        const mean = fun.game_lengths.length > 0 ?
            (fun.game_lengths.reduce((a,b) => a+b, 0) / fun.game_lengths.length).toFixed(1) : '-';
        const sorted = [...fun.game_lengths].sort((a,b) => a-b);
        const median = sorted.length > 0 ? sorted[Math.floor(sorted.length/2)] : '-';

        benchHtml += '<h3>How Our Models Compare (5x5)</h3>';
        benchHtml += '<p style="color:var(--text-secondary);font-size:0.9em">Benchmarks from ' +
            '<a href="https://arxiv.org/abs/2412.11373">Mattinson et al. (2024)</a>, same-model pairs, 100 games each.</p>';
        benchHtml += '<table style="max-width:700px"><thead><tr><th>Source</th><th>Mean Turns</th>' +
            '<th>Median</th><th>Assassin %</th><th>Avg Clue #</th></tr></thead><tbody>';
        benchHtml += '<tr style="font-weight:700;background:var(--blue-bg)"><td>Our Models (avg)</td><td>' +
            mean + '</td><td>' + median + '</td><td>' + fun.assassin_rate + '%</td><td>' +
            fun.avg_clue_number + '</td></tr>';
        Object.keys(BENCHMARKS).forEach(name => {
            const b = BENCHMARKS[name];
            benchHtml += '<tr><td>' + name + '</td><td>' + b.mean_turns + '</td><td>' +
                b.median + '</td><td>' + b.loss_pct + '%</td><td>' + b.clue_avg + '</td></tr>';
        });
        benchHtml += '</tbody></table>';
    }

    // Top clues chart
    const clues = (fun.top_clues || []).slice(0, 15).reverse();
    if (clues.length > 0) {
        const layout = {title: 'Most Common Clue Words', template: 'none', height: 400, xaxis: {title: 'Times Used'}};
        plotlyDarkLayout(layout);
        Plotly.newPlot('chart-clues', [{
            type: 'bar', orientation: 'h',
            x: clues.map(c => c.count), y: clues.map(c => c.clue),
            marker: {color: '#42a5f5'},
        }], layout, {responsive: true});
    } else {
        document.getElementById('chart-clues').innerHTML = '<p style="color:var(--text-muted)">No clue data.</p>';
    }

    // Game length histogram with benchmark lines
    if (fun.game_lengths && fun.game_lengths.length > 0) {
        const traces = [{
            type: 'histogram', x: fun.game_lengths,
            marker: {color: '#42a5f5'}, name: 'Our games',
            xbins: {size: 1},
        }];
        const shapes = [];
        const annotations = [];
        if (is5x5) {
            // Add benchmark reference lines
            const benchLines = [
                {name: 'o1-preview', val: 8.41, color: '#e53935'},
                {name: 'GloVe', val: 5.24, color: '#66bb6a'},
                {name: 'Llama-3.1', val: 10.18, color: '#fb8c00'},
            ];
            benchLines.forEach(bl => {
                shapes.push({
                    type: 'line', x0: bl.val, x1: bl.val, y0: 0, y1: 1, yref: 'paper',
                    line: {color: bl.color, width: 2, dash: 'dash'},
                });
                annotations.push({
                    x: bl.val, y: 1, yref: 'paper', text: bl.name,
                    showarrow: false, yanchor: 'bottom', font: {size: 11, color: bl.color},
                });
            });
        }
        const layout = {
            title: 'Game Length Distribution', template: 'none', height: 350,
            xaxis: {title: 'Turns to Complete', dtick: 1}, yaxis: {title: 'Games'},
            shapes: shapes, annotations: annotations, showlegend: false,
        };
        plotlyDarkLayout(layout);
        Plotly.newPlot('chart-game-length', traces, layout, {responsive: true});
    } else {
        document.getElementById('chart-game-length').innerHTML = '';
    }

    // Tables
    let html = benchHtml;
    if (fun.longest_games && fun.longest_games.length > 0) {
        html += '<h3>Longest Games</h3><table><thead><tr><th>#</th><th>Red</th><th>Blue</th><th>Winner</th><th>Turns</th></tr></thead><tbody>';
        fun.longest_games.forEach(g => {
            html += '<tr class="clickable" onclick="goToGame(' + g.game_id + ')"><td>' + g.game_id + '</td><td>' +
                    g.red_spymaster_model + '</td><td>' + g.blue_spymaster_model + '</td><td>' +
                    g.winner + '</td><td>' + g.total_turns + '</td></tr>';
        });
        html += '</tbody></table>';
    }
    if (fun.assassin_games && fun.assassin_games.length > 0) {
        html += '<h3>Assassin Hits</h3><table><thead><tr><th>#</th><th>Red</th><th>Blue</th><th>Winner</th><th>Turns</th></tr></thead><tbody>';
        fun.assassin_games.forEach(g => {
            html += '<tr class="clickable" onclick="goToGame(' + g.game_id + ')"><td>' + g.game_id + '</td><td>' +
                    g.red_spymaster_model + '</td><td>' + g.blue_spymaster_model + '</td><td>' +
                    g.winner + '</td><td>' + g.total_turns + '</td></tr>';
        });
        html += '</tbody></table>';
    }
    document.getElementById('fun-tables').innerHTML = html;

    // Latency chart
    const lat = fun.avg_latency || {};
    const latNames = Object.keys(lat).sort();
    if (latNames.length > 0) {
        const layout = {title: 'Average Spymaster Clue Latency', template: 'none', height: 350, yaxis: {title: 'Seconds'}};
        plotlyDarkLayout(layout);
        Plotly.newPlot('chart-latency', [{
            type: 'bar', x: latNames, y: latNames.map(n => lat[n] / 1000),
            marker: {color: '#fb8c00'},
        }], layout, {responsive: true});
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => switchSize('all'));
"""


def _build_js_model_select():
    return """
function selectModel(name) {
    document.querySelectorAll('.model-btns button').forEach(b => {
        b.classList.toggle('active', b.dataset.model === name);
    });
    const details = MODEL_DETAILS[name];
    if (!details) return;
    const el = document.getElementById('model-stats-cards');
    el.innerHTML =
        '<div class="stat-card"><div class="value">' + details.games + '</div><div class="label">Games</div></div>' +
        '<div class="stat-card"><div class="value">' + details.win_rate + '%</div><div class="label">Win Rate</div></div>' +
        '<div class="stat-card"><div class="value">' + details.assassin_rate + '%</div><div class="label">Assassin Loss</div></div>' +
        '<div class="stat-card"><div class="value">' + details.avg_turns_to_win + '</div><div class="label">Avg Turns to Win</div></div>' +
        '<div class="stat-card"><div class="value">' + details.clue_validity + '%</div><div class="label">Clue Validity</div></div>' +
        '<div class="stat-card"><div class="value">' + details.wins_as_red + '-' + (details.games_as_red - details.wins_as_red) +
        '</div><div class="label">W-L as Red</div></div>' +
        '<div class="stat-card"><div class="value">' + details.wins_as_blue + '-' + (details.games_as_blue - details.wins_as_blue) +
        '</div><div class="label">W-L as Blue</div></div>';
}
"""


def _build_html(conn):
    from models import load_config
    config = load_config()

    board_sizes = _board_sizes(conn)
    games = _game_list(conn)

    # Build per-size stats
    stats_by_size = {}
    for sz in board_sizes:
        stats_by_size[sz] = {
            "summary": _summary_stats(conn, sz),
            "leaderboard": _leaderboard(conn, sz),
            "h2h": {f"{k[0]}||{k[1]}": v for k, v in _head_to_head(conn, sz).items()},
            "model_details": _model_details(conn, sz),
            "fun": _fun_stats(conn, sz),
        }

    # Also build "all" stats
    stats_by_size["all"] = {
        "summary": _summary_stats(conn),
        "leaderboard": _leaderboard(conn),
        "h2h": {f"{k[0]}||{k[1]}": v for k, v in _head_to_head(conn).items()},
        "model_details": _model_details(conn),
        "fun": _fun_stats(conn),
    }

    elo_data = _elo_history(conn)
    all_model_names = [m["name"] for m in stats_by_size["all"]["leaderboard"]]

    # Build replay data for all games
    all_replays = {}
    for g in games:
        replay = _game_replay_data(conn, g["game_id"])
        if replay:
            all_replays[g["game_id"]] = replay

    # Pre-render Elo chart (global — not per-size since elo_history isn't per-size)
    elo_chart = _chart_elo_progression(elo_data, all_model_names)

    parts = []
    summary_all = stats_by_size["all"]["summary"]

    # Head
    parts.append(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Codenames AI Tournament</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>{CSS}
.size-toggle {{ display: flex; gap: 0; margin-bottom: 16px; }}
.size-toggle button {{ padding: 6px 18px; border: 1px solid var(--control-border);
    background: var(--control-bg); color: var(--text-primary); cursor: pointer; font-size: 0.9em; }}
.size-toggle button:first-child {{ border-radius: 6px 0 0 6px; }}
.size-toggle button:last-child {{ border-radius: 0 6px 6px 0; }}
.size-toggle button.active {{ background: var(--accent); color: white; border-color: var(--accent); }}
</style>
</head>
<body>
<div class="container">
<h1>Codenames AI Tournament</h1>
<p class="subtitle" id="subtitle">{summary_all['total_games']} games across {summary_all['total_models']} models</p>

<div class="size-toggle" id="size-toggle">
  <button class="active" onclick="switchSize('all')">All</button>
""")
    for sz in board_sizes:
        parts.append(f'  <button onclick="switchSize(\'{sz}\')">{sz}</button>\n')
    parts.append("""</div>

<nav>
  <button class="active" data-tab="leaderboard" onclick="switchTab('leaderboard')">Leaderboard</button>
  <button data-tab="h2h" onclick="switchTab('h2h')">Head-to-Head</button>
  <button data-tab="models" onclick="switchTab('models')">Models</button>
  <button data-tab="games" onclick="switchTab('games')">Games</button>
  <button data-tab="replay" onclick="switchTab('replay')">Replay</button>
  <button data-tab="fun" onclick="switchTab('fun')">Fun Stats</button>
  <button data-tab="about" onclick="switchTab('about')">About</button>
</nav>
""")

    # --- Tab 1: Leaderboard ---
    parts.append('<div id="tab-leaderboard" class="tab active">')
    parts.append('<div class="stats-row" id="summary-cards"></div>')
    parts.append("""<div id="leaderboard-insight" style="background:var(--card-bg); border-radius:8px;
        padding:16px 20px; margin-bottom:16px; box-shadow:0 1px 4px var(--card-shadow);
        line-height:1.7; color:var(--text-secondary); font-size:0.95em"></div>""")
    parts.append('<div id="leaderboard-table"></div>')
    parts.append(_render_chart(elo_chart, "chart-elo"))
    parts.append('</div>')

    # --- Tab 2: Head-to-Head ---
    parts.append('<div id="tab-h2h" class="tab">')
    parts.append('<h2>Head-to-Head Results</h2>')
    parts.append('<p>Win rate when row model plays as Red vs column model as Blue.</p>')
    parts.append('<div id="chart-h2h" class="chart"></div>')
    parts.append('</div>')

    # --- Tab 3: Models ---
    parts.append('<div id="tab-models" class="tab">')
    parts.append('<h2>Model Deep Dive</h2>')
    parts.append('<div class="model-btns" id="model-btns"></div>')
    parts.append('<div class="stats-row" id="model-stats-cards"><p style="color:var(--text-muted)">Select a model above.</p></div>')
    parts.append('<div id="chart-comparison" class="chart"></div>')
    parts.append('</div>')

    # --- Tab 4: Games ---
    parts.append('<div id="tab-games" class="tab">')
    parts.append('<h2>Game Browser</h2>')

    reason_options = sorted(set(g["win_reason"] for g in games if g["win_reason"]))
    parts.append('<div class="filters">')
    parts.append('<label>Model:</label><select id="filter-model" onchange="applyFilters()">')
    parts.append('<option value="">All</option>')
    for n in all_model_names:
        parts.append(f'<option value="{n}">{n}</option>')
    parts.append('</select>')
    parts.append('<label>Outcome:</label><select id="filter-reason" onchange="applyFilters()">')
    parts.append('<option value="">All</option>')
    for r in reason_options:
        parts.append(f'<option value="{r}">{r}</option>')
    parts.append('</select>')
    parts.append('</div>')

    parts.append('<table id="games-table"><thead><tr><th>#</th><th>Size</th><th>Red Team</th><th>Blue Team</th>'
                 '<th>Winner</th><th>Reason</th><th>Turns</th></tr></thead><tbody>')
    for g in games:
        winner_badge = "badge-red" if g["winner"] == "red" else ("badge-blue" if g["winner"] == "blue" else "badge-dark")
        reason_badge = "badge-green"
        if g["win_reason"] == "assassin":
            reason_badge = "badge-dark"
        elif g["win_reason"] in ("max_turns", "aborted"):
            reason_badge = "badge-yellow"

        parts.append(
            f'<tr class="clickable" onclick="goToGame({g["game_id"]})" '
            f'data-red="{g["red_spymaster_model"]}" data-blue="{g["blue_spymaster_model"]}" '
            f'data-reason="{g["win_reason"]}" data-size="{g["board_size"]}">'
            f'<td>{g["game_id"]}</td>'
            f'<td>{g["board_size"]}</td>'
            f'<td>{g["red_spymaster_model"]}</td>'
            f'<td>{g["blue_spymaster_model"]}</td>'
            f'<td><span class="badge {winner_badge}">{g["winner"]}</span></td>'
            f'<td><span class="badge {reason_badge}">{g["win_reason"]}</span></td>'
            f'<td>{g["total_turns"] or "-"}</td></tr>'
        )
    parts.append('</tbody></table>')
    parts.append('</div>')

    # --- Tab 5: Replay ---
    parts.append('<div id="tab-replay" class="tab">')
    parts.append('<h2>Game Replay</h2>')
    parts.append('<div class="replay-controls">')
    parts.append('<select id="game-select" onchange="loadGame(parseInt(this.value))">')
    parts.append('<option value="">— Select a game —</option>')
    for g in games:
        label = f"[{g['board_size']}] Game {g['game_id']}: {g['red_spymaster_model']} vs {g['blue_spymaster_model']}"
        parts.append(f'<option value="{g["game_id"]}" data-size="{g["board_size"]}">{label}</option>')
    parts.append('</select>')
    parts.append('</div>')

    parts.append('<div class="replay-controls">')
    parts.append('<button onclick="stepStart()">&#x23EE; Start</button>')
    parts.append('<button onclick="stepBack()">&#x25C0; Prev</button>')
    parts.append('<button onclick="stepForward()">Next &#x25B6;</button>')
    parts.append('<button onclick="stepEnd()">End &#x23ED;</button>')
    parts.append('<button id="btn-autoplay" onclick="toggleAutoplay()">&#x25B6; Auto</button>')
    parts.append('</div>')

    parts.append('<div id="replay-status" class="replay-status">Select a game to begin.</div>')
    parts.append('<div id="board-grid" class="board-grid"><p style="text-align:center;color:var(--text-muted)">No game loaded.</p></div>')
    parts.append('<div id="replay-result" style="text-align:center;margin:12px 0"></div>')
    parts.append('<div id="turn-log" class="turn-log"></div>')
    parts.append('</div>')

    # --- Tab 6: Fun Stats ---
    parts.append('<div id="tab-fun" class="tab">')
    parts.append('<h2>Fun Stats</h2>')
    parts.append('<div id="chart-game-length" class="chart"></div>')
    parts.append('<div id="fun-tables"></div>')
    parts.append('<div id="chart-clues" class="chart"></div>')
    parts.append('<div id="chart-latency" class="chart"></div>')
    parts.append('</div>')

    # --- Tab 7: About ---
    model_list_html = ", ".join(f"<strong>{m['name']}</strong>" for m in config["models"])
    parts.append(f"""<div id="tab-about" class="tab">
<h2>About This Tournament</h2>

<h3>The Game</h3>
<p><a href="https://en.wikipedia.org/wiki/Codenames_(board_game)" target="_blank">Codenames</a>
is a word association party game by Vlaada Chv&aacute;til. Two teams (Red and Blue) compete to
identify their secret agents on a grid of words. Each team has a <strong>Spymaster</strong> who
gives one-word clues and a <strong>Guesser</strong> who picks words based on those clues.</p>

<h3>How It Works Here</h3>
<p>In this experiment, <strong>AI models play both roles</strong> &mdash; each model acts as its own
team&rsquo;s Spymaster and Guesser. Models produce clues and guesses via
<strong>structured outputs</strong> (JSON schema enforcement), which ensures valid responses
regardless of the model&rsquo;s reasoning style. Thinking models (like Nemotron, GPT-OSS, and Qwen)
reason internally before producing their structured answer.</p>
<p>One player is different: the <strong>embedding-agent</strong> is a programmatic player that uses
<strong>Qwen3-Embedding-8B</strong> word vectors instead of an LLM. It computes cosine similarity
between candidate clue words and board words to find optimal clues algorithmically &mdash; inspired by
the GloVe/Word2Vec agents in Mattinson et al. (2024) that dramatically outperformed LLMs.</p>

<h3>Board Sizes</h3>
<table style="max-width: 500px">
<thead><tr><th>Size</th><th>Cards</th><th>1st Team</th><th>2nd Team</th><th>Bystanders</th><th>Assassin</th></tr></thead>
<tbody>
<tr><td>5&times;5</td><td>25</td><td>9</td><td>8</td><td>7</td><td>1</td></tr>
<tr><td>2&times;2</td><td>4</td><td>2</td><td>1</td><td>0</td><td>1</td></tr>
</tbody></table>

<h3>Rules Enforcement</h3>
<ul style="margin: 8px 0 8px 24px; line-height: 1.8">
  <li>Clues must be a single English word &mdash; no spaces, hyphens, or numbers.</li>
  <li>Clues cannot be any word on the board, a component of a multi-word board entry,
      a substring overlap (min 3 chars), or share a stem with any board word (Porter stemmer).</li>
  <li>If a guesser picks the <strong>assassin</strong>, that team loses immediately.</li>
  <li>If a model fails to produce a valid clue after 3 attempts, the turn is skipped (not counted).</li>
</ul>

<h3>Scoring</h3>
<p>Models are rated using the <strong>Elo rating system</strong> (K-factor = 32, initial rating = 1500).
After each tournament, ratings are updated in batch using pre-tournament snapshot ratings to avoid
ordering effects. A win is a win regardless of how it happened &mdash; assassin kills and
finding-all-words count equally. Assassin losses are tracked separately as a fun stat.</p>

<h3>Tournament Format</h3>
<p><strong>Round-robin:</strong> every ordered pair of models plays multiple games (order matters because
the first team gets 9 words vs 8). Games per pair varies from 2 to 10+ across tournament rounds.
Games run one pair at a time so only two models are loaded on the inference server simultaneously.</p>

<h3>Models</h3>
<p>All models are served via <a href="https://mindrouter.uidaho.edu" target="_blank">MindRouter</a>
(University of Idaho). Current lineup: {model_list_html}.</p>

<h3>Source</h3>
<p>Word list: 400 official Codenames words from the base game by Vlaada Chv&aacute;til.</p>

<h3>External Benchmarks</h3>
<p>Reference numbers from <a href="https://arxiv.org/abs/2412.11373" target="_blank">Mattinson et al. (2024),
&ldquo;Codenames as a Benchmark for Large Language Models&rdquo;</a> &mdash; 4,600 games across
6 frontier LLMs and 3 word-vector agents on standard 5&times;5 boards.</p>

<table style="max-width: 700px">
<thead><tr><th>Model Pair</th><th>Mean Turns</th><th>Median</th><th>Loss %</th><th>Avg Clue #</th></tr></thead>
<tbody>
<tr><td>o1-preview (best LLM)</td><td>8.41</td><td>6</td><td>13%</td><td>1.95</td></tr>
<tr><td>GPT-4o</td><td>10.58</td><td>8</td><td>16%</td><td>1.51</td></tr>
<tr><td>Gemini-1.5 Pro</td><td>10.38</td><td>8</td><td>14%</td><td>1.63</td></tr>
<tr><td>Claude Sonnet-3.5</td><td>11.01</td><td>8</td><td>22%</td><td>2.02</td></tr>
<tr><td>Llama-3.1 70B</td><td>10.18</td><td>9</td><td>8%</td><td>1.30</td></tr>
<tr><td>o1-mini</td><td>11.10</td><td>7</td><td>24%</td><td>2.09</td></tr>
<tr style="border-top: 2px solid var(--border)">
  <td>GloVe-GloVe (best non-LLM)</td><td>5.24</td><td>5</td><td>0%</td><td>1.72</td></tr>
</tbody></table>

<p style="margin-top: 12px"><strong>Key finding from this paper:</strong> word-vector agents (GloVe) dramatically
outperform LLMs at Codenames &mdash; faster wins, zero assassin losses. LLMs are more &ldquo;creative&rdquo;
but far more reckless. Our MindRouter models show even more aggressive play (higher clue numbers,
higher assassin rates) than the frontier models in this study.</p>

<p>Additional reference: <a href="https://github.com/SALT-NLP/codenames" target="_blank">SALT-NLP Cultural Codes
dataset</a> &mdash; 794 human Codenames Duet games (cooperative variant), 7,703 turns, 153 players
(Shaikh et al., ACL Findings 2023).</p>
</div>
""")

    # --- Embedded Data + JS ---
    replay_json = json.dumps(all_replays, default=str)
    stats_json = json.dumps(stats_by_size, default=str)

    parts.append(f"""
<script>
const GAME_DATA = {replay_json};
const STATS_BY_SIZE = {stats_json};
let currentSize = 'all';
let MODEL_DETAILS = STATS_BY_SIZE['all'].model_details;
const isDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;

function plotlyDarkLayout(layout) {{
    if (isDark) {{
        layout.paper_bgcolor = '#121212';
        layout.plot_bgcolor = '#1e1e1e';
        layout.font = {{color: '#e0e0e0'}};
        if (layout.xaxis) layout.xaxis.gridcolor = '#444';
        if (layout.yaxis) layout.yaxis.gridcolor = '#444';
    }}
    return layout;
}}
</script>
<script>
{_build_js_tabs()}
{_build_js_filters()}
{_build_js_model_select()}
{_build_js_replay()}
{_build_js_size_switch()}
</script>
""")

    parts.append("""
<footer style="margin-top: 40px; padding: 20px 0; border-top: 1px solid var(--border);
    text-align: center; color: var(--text-muted); font-size: 0.85em; line-height: 1.8">
  <p>Built by <strong style="color: var(--text-secondary)">Bert Baumgaertner</strong>,
  University of Idaho</p>
  <p>All models served by <a href="https://mindrouter.uidaho.edu" target="_blank"
    style="color: var(--accent-text)">MindRouter</a> &mdash; University of Idaho</p>
</footer>
</div></body></html>""")
    return "".join(parts)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.command()
@click.option("--db-path", "db_path", default="codenames.db", help="Path to database")
@click.option("--output", "output_path", default="tournament.html", help="Output HTML path")
def generate(db_path, output_path):
    """Generate the tournament viewer HTML."""
    conn = db.init_db(db_path)
    html = _build_html(conn)
    conn.close()

    Path(output_path).write_text(html)
    size_kb = len(html) / 1024
    print(f"Generated {output_path} ({size_kb:.0f} KB)")


if __name__ == "__main__":
    generate()

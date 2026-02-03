#!/usr/bin/env python3
# Run with: ../server-langgraph/.venv/bin/python plot_results.py
"""AGORA Benchmark — Visualisaties

Leest raw_results.json en pairwise_results.json en genereert plots.

Usage:
    cd benchmark
    ../server-langgraph/.venv/bin/python plot_results.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

# ─── Global font size ─────────────────────────────────────────────────────────

plt.rcParams.update(
    {
        "font.size": 13,
        "axes.titlesize": 15,
        "axes.labelsize": 13,
        "xtick.labelsize": 11,
        "ytick.labelsize": 11,
        "legend.fontsize": 11,
        "figure.titlesize": 18,
    }
)

RESULTS_DIR = Path(__file__).resolve().parent / "results"
RAW_PATH = RESULTS_DIR / "raw_results.json"
PAIRWISE_PATH = RESULTS_DIR / "pairwise_results.json"
PLOTS_DIR = RESULTS_DIR / "plots"
PLOTS_DIR.mkdir(exist_ok=True)

# ─── Dutch labels ─────────────────────────────────────────────────────────────

SCENARIO_LABELS = {
    "greeting": "Begroeting",
    "inspection_start": "Inspectie starten",
    "regulation_query": "Regelgeving vraag",
}

DIMENSION_LABELS = {
    "winner_tools": "Toolgebruik",
    "winner_routing": "Agent routing",
    "winner_quality": "Antwoordkwaliteit",
    "winner_language": "Taalkwaliteit",
}

# ─── Color palette ────────────────────────────────────────────────────────────

COLORS = [
    "#2563eb",  # blue
    "#16a34a",  # green
    "#ea580c",  # orange
    "#9333ea",  # purple
    "#dc2626",  # red
    "#ca8a04",  # yellow
    "#0d9488",  # teal
    "#6366f1",  # indigo
]

# ─── Pricing per 1M output tokens (USD) ──────────────────────────────────────

MODEL_OUTPUT_PRICING: dict[str, float] = {
    "gpt-4o": 10.00,
    "gpt-4o-mini": 0.60,
    "gpt-5.2": 14.00,
    "qwen-2.5-72b": 0.39,
    "gpt-oss-120b": 0.19,
    "mistral-large": 1.50,
    "ministral-14b": 0.20,
}


def load_results() -> dict:
    if not RAW_PATH.exists():
        print(f"Geen resultaten gevonden: {RAW_PATH}")
        print("Draai eerst de benchmark: python benchmark.py")
        raise SystemExit(1)
    return json.loads(RAW_PATH.read_text())


def load_pairwise() -> list[dict] | None:
    if not PAIRWISE_PATH.exists():
        print(f"Geen pairwise resultaten gevonden: {PAIRWISE_PATH}")
        print("Draai de benchmark zonder --skip-scoring voor pairwise vergelijkingen")
        return None
    return json.loads(PAIRWISE_PATH.read_text())


def get_model_color(idx: int) -> str:
    return COLORS[idx % len(COLORS)]


def _tally(comparisons: list[dict], model_ids: list[str]) -> dict[str, dict[str, int]]:
    """Tally pairwise wins into per-model scores."""
    scores: dict[str, dict[str, int]] = {}
    for mid in model_ids:
        scores[mid] = {
            "wins": 0,
            "ties": 0,
            "losses": 0,
            "tools_w": 0,
            "routing_w": 0,
            "quality_w": 0,
            "language_w": 0,
        }

    dim_map = [
        ("winner_tools", "tools_w"),
        ("winner_routing", "routing_w"),
        ("winner_quality", "quality_w"),
        ("winner_language", "language_w"),
    ]
    for c in comparisons:
        for attr, key in dim_map:
            winner = c.get(attr, "tie")
            if winner == c["model_a"]:
                scores[c["model_a"]][key] += 1
                scores[c["model_a"]]["wins"] += 1
                scores[c["model_b"]]["losses"] += 1
            elif winner == c["model_b"]:
                scores[c["model_b"]][key] += 1
                scores[c["model_b"]]["wins"] += 1
                scores[c["model_a"]]["losses"] += 1
            else:
                scores[c["model_a"]]["ties"] += 1
                scores[c["model_b"]]["ties"] += 1

    return scores


# ─── Plot 1: Snelheid per scenario (gegroepeerde staafdiagram) ───────────────


def plot_speed_per_scenario(data: dict) -> None:
    models = list(data.keys())
    scenarios = [
        s
        for s in SCENARIO_LABELS
        if s in {r["scenario_id"] for m in data.values() for r in m}
    ]
    scenario_names = [SCENARIO_LABELS[s] for s in scenarios]

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle("Snelheidsvergelijking per Scenario", fontsize=16, fontweight="bold")

    for ax_idx, (metric, metric_label) in enumerate(
        [
            ("ttft_ms", "Tijd tot eerste token (s)"),
            ("response_ms", "Totale antwoordtijd (s)"),
        ]
    ):
        ax = axes[ax_idx]
        x = np.arange(len(scenarios))
        width = 0.8 / len(models)

        for i, model_id in enumerate(models):
            results_by_scenario = {r["scenario_id"]: r for r in data[model_id]}
            values = []
            for s in scenarios:
                r = results_by_scenario.get(s)
                val = r.get(metric) if r else None
                values.append(val / 1000 if val else 0)  # ms -> seconds

            offset = (i - len(models) / 2 + 0.5) * width
            bars = ax.bar(
                x + offset,
                values,
                width * 0.9,
                label=model_id,
                color=get_model_color(i),
                edgecolor="white",
                linewidth=0.5,
            )

            for bar, val in zip(bars, values):
                if val > 0:
                    ax.text(
                        bar.get_x() + bar.get_width() / 2,
                        bar.get_height() + 0.3,
                        f"{val:.1f}s",
                        ha="center",
                        va="bottom",
                        fontsize=7,
                        rotation=0,
                    )

        ax.set_xlabel("Scenario", fontsize=11)
        ax.set_ylabel(metric_label, fontsize=11)
        ax.set_title(metric_label, fontsize=12)
        ax.set_xticks(x)
        ax.set_xticklabels(scenario_names, fontsize=9)
        ax.legend(fontsize=8, loc="upper left")
        ax.grid(axis="y", alpha=0.3)
        ax.set_axisbelow(True)

    plt.tight_layout()
    path = PLOTS_DIR / "snelheid_per_scenario.png"
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Opgeslagen: {path}")


# ─── Plot 2: Snelheidsoverzicht (horizontale staafdiagram) ───────────────────


def plot_speed_summary(data: dict) -> None:
    models = list(data.keys())

    fig, ax = plt.subplots(figsize=(10, max(4, len(models) * 1.2)))
    fig.suptitle("Gemiddelde Snelheid per Model", fontsize=16, fontweight="bold")

    avg_ttft = []
    avg_response = []

    for model_id in models:
        ttfts = [r["ttft_ms"] for r in data[model_id] if r.get("ttft_ms")]
        resps = [r["response_ms"] for r in data[model_id] if r.get("response_ms")]
        avg_ttft.append(sum(ttfts) / len(ttfts) / 1000 if ttfts else 0)
        avg_response.append(sum(resps) / len(resps) / 1000 if resps else 0)

    y = np.arange(len(models))
    height = 0.35

    bars1 = ax.barh(
        y + height / 2,
        avg_response,
        height,
        label="Totale antwoordtijd",
        color="#2563eb",
        alpha=0.85,
    )
    bars2 = ax.barh(
        y - height / 2,
        avg_ttft,
        height,
        label="Tijd tot eerste token (TTFT)",
        color="#16a34a",
        alpha=0.85,
    )

    for bar, val in zip(bars1, avg_response):
        if val > 0:
            ax.text(
                val + 0.5,
                bar.get_y() + bar.get_height() / 2,
                f"{val:.1f}s",
                va="center",
                fontsize=9,
            )
    for bar, val in zip(bars2, avg_ttft):
        if val > 0:
            ax.text(
                val + 0.5,
                bar.get_y() + bar.get_height() / 2,
                f"{val:.1f}s",
                va="center",
                fontsize=9,
            )

    ax.set_yticks(y)
    ax.set_yticklabels(models, fontsize=10)
    ax.set_xlabel("Tijd (seconden)", fontsize=11)
    ax.legend(fontsize=9, loc="lower right")
    ax.grid(axis="x", alpha=0.3)
    ax.set_axisbelow(True)
    ax.invert_yaxis()

    plt.tight_layout()
    path = PLOTS_DIR / "snelheid_overzicht.png"
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Opgeslagen: {path}")


# ─── Plot 3: Winstpercentage ranking (horizontale staafdiagram) ──────────────


def plot_win_rate_ranking(tally: dict[str, dict[str, int]]) -> None:
    ranked = sorted(
        tally.items(),
        key=lambda x: (x[1]["wins"], x[1]["ties"]),
        reverse=True,
    )
    models = [m for m, _ in ranked]
    wins = [s["wins"] for _, s in ranked]
    ties = [s["ties"] for _, s in ranked]
    losses = [s["losses"] for _, s in ranked]

    fig, ax = plt.subplots(figsize=(10, max(4, len(models) * 1.2)))
    fig.suptitle("Ranking — Pairwise Overwinningen", fontsize=16, fontweight="bold")

    y = np.arange(len(models))
    height = 0.6

    ax.barh(y, wins, height, label="Gewonnen", color="#16a34a")
    ax.barh(y, ties, height, left=wins, label="Gelijk", color="#ca8a04")
    ax.barh(
        y,
        losses,
        height,
        left=[w + t for w, t in zip(wins, ties)],
        label="Verloren",
        color="#dc2626",
    )

    # Win rate labels
    for i, (w, t, l) in enumerate(zip(wins, ties, losses)):
        total = w + t + l
        rate = (w + 0.5 * t) / total * 100 if total else 0
        ax.text(
            total + 0.3, i, f"{rate:.0f}%", va="center", fontsize=10, fontweight="bold"
        )

    ax.set_yticks(y)
    ax.set_yticklabels(models, fontsize=11)
    ax.set_xlabel("Aantal dimensie-vergelijkingen", fontsize=11)
    ax.legend(fontsize=9, loc="upper center", bbox_to_anchor=(0.5, -0.08), ncol=3)
    ax.grid(axis="x", alpha=0.3)
    ax.set_axisbelow(True)
    ax.invert_yaxis()

    plt.tight_layout()
    path = PLOTS_DIR / "ranking_winrate.png"
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Opgeslagen: {path}")


# ─── Plot 4: Dimensie-overwinningen per model ───────────────────────────────


def plot_dimension_wins(tally: dict[str, dict[str, int]]) -> None:
    ranked = sorted(
        tally.items(),
        key=lambda x: (x[1]["wins"], x[1]["ties"]),
        reverse=True,
    )
    models = [m for m, _ in ranked]
    # Exclude routing — always 0 since all models route correctly
    dim_keys = ["tools_w", "quality_w", "language_w"]
    dim_labels = ["Toolgebruik", "Kwaliteit", "Taal"]

    fig, ax = plt.subplots(figsize=(10, max(4, len(models) * 1.2)))
    fig.suptitle("Overwinningen per Dimensie", fontsize=16, fontweight="bold")

    y = np.arange(len(models))
    n_dims = len(dim_keys)
    height = 0.8 / n_dims
    colors = ["#2563eb", "#ea580c", "#9333ea"]

    for d_idx, (key, label) in enumerate(zip(dim_keys, dim_labels)):
        values = [tally[m][key] for m in models]
        offset = (d_idx - n_dims / 2 + 0.5) * height
        ax.barh(y + offset, values, height * 0.9, label=label, color=colors[d_idx])

    ax.set_yticks(y)
    ax.set_yticklabels(models, fontsize=11)
    ax.set_xlabel("Aantal overwinningen", fontsize=11)
    ax.legend(fontsize=9, loc="lower right")
    ax.grid(axis="x", alpha=0.3)
    ax.set_axisbelow(True)
    ax.invert_yaxis()

    plt.tight_layout()
    path = PLOTS_DIR / "dimensie_overwinningen.png"
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Opgeslagen: {path}")


# ─── Plot 5: Head-to-head matrix heatmap ────────────────────────────────────


def plot_h2h_matrix(comparisons: list[dict], model_ids: list[str]) -> None:
    """Heatmap showing total dimension wins: row model vs column model."""
    n = len(model_ids)
    matrix = np.zeros((n, n))

    idx = {mid: i for i, mid in enumerate(model_ids)}

    for c in comparisons:
        a, b = c["model_a"], c["model_b"]
        if a not in idx or b not in idx:
            continue
        for attr in [
            "winner_tools",
            "winner_routing",
            "winner_quality",
            "winner_language",
        ]:
            winner = c.get(attr, "tie")
            if winner == a:
                matrix[idx[a]][idx[b]] += 1
            elif winner == b:
                matrix[idx[b]][idx[a]] += 1

    fig, ax = plt.subplots(figsize=(max(6, n * 1.5 + 1), max(5, n * 1.2 + 1)))
    fig.suptitle(
        "Head-to-Head Matrix (dimensie-overwinningen)", fontsize=16, fontweight="bold"
    )

    # Mask diagonal
    mask = np.eye(n, dtype=bool)
    display = np.where(mask, np.nan, matrix)

    im = ax.imshow(
        display,
        cmap="RdYlGn",
        aspect="auto",
        vmin=0,
        vmax=np.nanmax(display) if np.nanmax(display) > 0 else 1,
    )

    ax.set_xticks(np.arange(n))
    ax.set_xticklabels(model_ids, fontsize=10, rotation=30, ha="right")
    ax.set_yticks(np.arange(n))
    ax.set_yticklabels(model_ids, fontsize=10)
    ax.set_xlabel("Tegenstander", fontsize=11)
    ax.set_ylabel("Model (rij wint)", fontsize=11)

    for i in range(n):
        for j in range(n):
            if i == j:
                ax.text(j, i, "-", ha="center", va="center", fontsize=12, color="gray")
            else:
                val = int(matrix[i][j])
                color = "white" if val < np.nanmax(display) * 0.4 else "black"
                ax.text(
                    j,
                    i,
                    str(val),
                    ha="center",
                    va="center",
                    fontsize=13,
                    fontweight="bold",
                    color=color,
                )

    cbar = plt.colorbar(im, ax=ax, shrink=0.8)
    cbar.set_label("Dimensie-overwinningen", fontsize=10)

    plt.tight_layout()
    path = PLOTS_DIR / "h2h_matrix.png"
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Opgeslagen: {path}")


# ─── Plot 6: Snelheid vs winrate scatter ─────────────────────────────────────


def plot_speed_vs_winrate(data: dict, tally: dict[str, dict[str, int]]) -> None:
    models = list(data.keys())

    fig, ax = plt.subplots(figsize=(10, 7))
    fig.suptitle("Snelheid vs. Winstpercentage", fontsize=16, fontweight="bold")

    xs, ys, text_labels, sizes, colors_list = [], [], [], [], []

    for i, model_id in enumerate(models):
        results = data[model_id]

        # Average response time
        resps = [r["response_ms"] for r in results if r.get("response_ms")]
        avg_resp = sum(resps) / len(resps) / 1000 if resps else 0

        # Win rate
        s = tally.get(model_id, {"wins": 0, "ties": 0, "losses": 0})
        total = s["wins"] + s["ties"] + s["losses"]
        win_rate = (s["wins"] + 0.5 * s["ties"]) / total * 100 if total else 0

        # Price
        price = MODEL_OUTPUT_PRICING.get(model_id)

        xs.append(avg_resp)
        ys.append(win_rate)
        colors_list.append(get_model_color(i))

        if price is not None:
            sizes.append(100 + np.sqrt(price) * 100)
            text_labels.append(f"{model_id}\n${price:.2f}/M")
        else:
            sizes.append(120)
            text_labels.append(model_id)

    # Draw scatter points (variable size = price)
    for x, y, sz, c in zip(xs, ys, sizes, colors_list):
        ax.scatter(x, y, s=sz, c=c, edgecolors="black", linewidth=1, zorder=5)

    # Labels with price
    texts = [
        ax.text(x, y, lbl, fontsize=9, fontweight="bold")
        for x, y, lbl in zip(xs, ys, text_labels)
    ]

    try:
        from adjustText import adjust_text

        adjust_text(
            texts,
            x=xs,
            y=ys,
            ax=ax,
            force_text=(1.5, 1.5),
            force_points=(2.0, 2.0),
            expand=(1.5, 1.5),
            arrowprops=dict(arrowstyle="-", color="gray", lw=0.8),
            min_arrow_len=5,
        )
    except ImportError:
        pass  # Fall back to default placement if adjustText not installed

    # Bubble size legend
    for ref_price in [0.20, 2.00, 14.00]:
        ref_size = 100 + np.sqrt(ref_price) * 100
        ax.scatter(
            [], [], s=ref_size, c="gray", alpha=0.4, edgecolors="black",
            linewidth=0.5, label=f"${ref_price:.2f}/M",
        )
    ax.legend(
        title="Prijs (output tokens)",
        fontsize=9, title_fontsize=10,
        loc="upper right", framealpha=0.9,
        borderpad=1.5, labelspacing=2.0,
    )

    ax.set_xlabel("Gemiddelde antwoordtijd (seconden) -> sneller", fontsize=12)
    ax.set_ylabel("Winstpercentage (%)", fontsize=12)
    ax.set_ylim(0, 105)
    ax.invert_xaxis()
    ax.grid(alpha=0.3)
    ax.set_axisbelow(True)

    plt.tight_layout()
    path = PLOTS_DIR / "snelheid_vs_winrate.png"
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Opgeslagen: {path}")


# ─── Plot 9: Prijs vs winstpercentage scatter ────────────────────────────────


def plot_price_vs_winrate(data: dict, tally: dict[str, dict[str, int]]) -> None:
    """Scatter: price per 1M output tokens vs win rate."""
    import matplotlib.ticker as mticker

    models = list(data.keys())

    fig, ax = plt.subplots(figsize=(10, 7))
    fig.suptitle("Prijs vs. Winstpercentage", fontsize=16, fontweight="bold")

    xs, ys, text_labels, colors_list = [], [], [], []

    for i, model_id in enumerate(models):
        price = MODEL_OUTPUT_PRICING.get(model_id)
        if price is None:
            continue

        s = tally.get(model_id, {"wins": 0, "ties": 0, "losses": 0})
        total = s["wins"] + s["ties"] + s["losses"]
        win_rate = (s["wins"] + 0.5 * s["ties"]) / total * 100 if total else 0

        xs.append(price)
        ys.append(win_rate)
        text_labels.append(model_id)
        colors_list.append(get_model_color(i))

    for x, y, c in zip(xs, ys, colors_list):
        ax.scatter(x, y, s=150, c=c, edgecolors="black", linewidth=1, zorder=5)

    texts = [
        ax.text(x, y, lbl, fontsize=10, fontweight="bold")
        for x, y, lbl in zip(xs, ys, text_labels)
    ]

    try:
        from adjustText import adjust_text

        adjust_text(
            texts,
            x=xs,
            y=ys,
            ax=ax,
            force_text=(1.5, 1.5),
            force_points=(2.0, 2.0),
            expand=(1.5, 1.5),
            arrowprops=dict(arrowstyle="-", color="gray", lw=0.8),
            min_arrow_len=5,
        )
    except ImportError:
        pass

    ax.set_xlabel("Prijs per 1M output tokens ($) → duurder", fontsize=12)
    ax.set_ylabel("Winstpercentage (%)", fontsize=12)
    ax.set_ylim(0, 105)
    ax.set_xscale("log")
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"${v:.2f}"))
    ax.grid(alpha=0.3)
    ax.set_axisbelow(True)

    plt.tight_layout()
    path = PLOTS_DIR / "prijs_vs_winrate.png"
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Opgeslagen: {path}")


# ─── Plot 7: Tool-aanroepen overzicht ─────────────────────────────────────────


def plot_tool_calls(data: dict) -> None:
    models = list(data.keys())
    scenarios = [
        s
        for s in ["inspection_start", "regulation_query"]
        if s in {r["scenario_id"] for m in data.values() for r in m}
    ]

    if not scenarios:
        return

    expected_tools = {
        "inspection_start": {"check_company_exists", "get_inspection_history"},
        "regulation_query": {"search_regulations"},
    }

    fig, axes = plt.subplots(1, len(scenarios), figsize=(6 * len(scenarios), 5))
    fig.suptitle("Correctheid van Tool-aanroepen", fontsize=16, fontweight="bold")

    if len(scenarios) == 1:
        axes = [axes]

    for s_idx, scenario_id in enumerate(scenarios):
        ax = axes[s_idx]
        expected = expected_tools.get(scenario_id, set())

        statuses = []
        for model_id in models:
            results = [r for r in data[model_id] if r["scenario_id"] == scenario_id]
            if not results:
                statuses.append((model_id, 0, len(expected), 0))
                continue
            r = results[0]
            called = {
                tc["name"]
                for tc in r.get("tool_calls", [])
                if not tc["name"].startswith("transfer_to_")
            }
            correct = len(expected & called)
            missing = len(expected - called)
            extra = len(called - expected)
            statuses.append((model_id, correct, missing, extra))

        y = np.arange(len(models))
        correct_vals = [s[1] for s in statuses]
        missing_vals = [s[2] for s in statuses]
        extra_vals = [s[3] for s in statuses]

        ax.barh(y, correct_vals, 0.6, label="Correct", color="#16a34a")
        ax.barh(
            y, missing_vals, 0.6, left=correct_vals, label="Ontbrekend", color="#dc2626"
        )
        ax.barh(
            y,
            extra_vals,
            0.6,
            left=[c + m for c, m in zip(correct_vals, missing_vals)],
            label="Extra",
            color="#ca8a04",
        )

        ax.set_yticks(y)
        ax.set_yticklabels(models, fontsize=9)
        ax.set_xlabel("Aantal tools", fontsize=10)
        ax.set_title(
            f"{SCENARIO_LABELS.get(scenario_id, scenario_id)}\n(verwacht: {', '.join(expected)})",
            fontsize=10,
        )
        ax.legend(fontsize=8, loc="lower right")
        ax.invert_yaxis()
        ax.grid(axis="x", alpha=0.3)
        ax.set_axisbelow(True)

    plt.tight_layout()
    path = PLOTS_DIR / "tool_aanroepen.png"
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Opgeslagen: {path}")


# ─── Plot 8: Per-scenario pairwise uitslag ───────────────────────────────────


def plot_pairwise_per_scenario(comparisons: list[dict]) -> None:
    """For each scenario, show which model won each matchup (stacked per dimension)."""
    scenario_ids = sorted({c["scenario_id"] for c in comparisons})

    if not scenario_ids:
        return

    fig, axes = plt.subplots(
        1, len(scenario_ids), figsize=(5 * len(scenario_ids), 6), sharey=False
    )
    fig.suptitle("Pairwise Resultaten per Scenario", fontsize=16, fontweight="bold")

    if len(scenario_ids) == 1:
        axes = [axes]

    dims = ["winner_tools", "winner_routing", "winner_quality", "winner_language"]

    for s_idx, scenario_id in enumerate(scenario_ids):
        ax = axes[s_idx]
        sc_comps = [c for c in comparisons if c["scenario_id"] == scenario_id]

        # Build matchup labels and tallies
        matchup_labels = []
        matchup_wins_a = []  # wins for model_a per dimension
        matchup_wins_b = []
        matchup_ties = []

        for c in sc_comps:
            label = f"{c['model_a']}\nvs\n{c['model_b']}"
            matchup_labels.append(label)

            wa, wb, wt = [], [], []
            for d in dims:
                winner = c.get(d, "tie")
                if winner == c["model_a"]:
                    wa.append(1)
                    wb.append(0)
                    wt.append(0)
                elif winner == c["model_b"]:
                    wa.append(0)
                    wb.append(1)
                    wt.append(0)
                else:
                    wa.append(0)
                    wb.append(0)
                    wt.append(1)
            matchup_wins_a.append(sum(wa))
            matchup_wins_b.append(sum(wb))
            matchup_ties.append(sum(wt))

        x = np.arange(len(sc_comps))
        width = 0.6

        ax.bar(x, matchup_wins_a, width, label="Model A wint", color="#2563eb")
        ax.bar(
            x,
            matchup_ties,
            width,
            bottom=matchup_wins_a,
            label="Gelijk",
            color="#ca8a04",
        )
        ax.bar(
            x,
            matchup_wins_b,
            width,
            bottom=[a + t for a, t in zip(matchup_wins_a, matchup_ties)],
            label="Model B wint",
            color="#ea580c",
        )

        ax.set_xticks(x)
        ax.set_xticklabels(matchup_labels, fontsize=7)
        ax.set_ylabel("Dimensies gewonnen (max 4)")
        ax.set_title(SCENARIO_LABELS.get(scenario_id, scenario_id), fontsize=12)
        ax.set_ylim(0, 4.5)
        ax.grid(axis="y", alpha=0.3)
        ax.set_axisbelow(True)
        if s_idx == 0:
            ax.legend(fontsize=7, loc="upper right")

    plt.tight_layout()
    path = PLOTS_DIR / "pairwise_per_scenario.png"
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Opgeslagen: {path}")


# ─── Main ────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="AGORA Benchmark — Visualisaties")
    parser.add_argument(
        "--drop-models",
        type=str,
        default=None,
        help="Comma-separated model IDs to exclude from plots",
    )
    args = parser.parse_args()

    print("\n=== AGORA Benchmark Visualisaties ===\n")

    data = load_results()

    # Drop models if requested
    if args.drop_models:
        drop_ids = {m.strip() for m in args.drop_models.split(",")}
        dropped = [m for m in drop_ids if m in data]
        unknown = [m for m in drop_ids if m not in data]
        for mid in dropped:
            del data[mid]
        if dropped:
            print(f"  Dropped: {dropped}")
        if unknown:
            print(f"  Unknown (ignored): {unknown}")
        if not data:
            print("No models left after dropping. Exiting.")
            raise SystemExit(1)

    n_models = len(data)
    n_results = sum(len(v) for v in data.values())
    print(f"  Geladen: {n_models} modellen, {n_results} resultaten\n")

    comparisons = load_pairwise()

    # Filter pairwise comparisons to only include remaining models
    if comparisons and args.drop_models:
        remaining = set(data.keys())
        comparisons = [
            c
            for c in comparisons
            if c["model_a"] in remaining and c["model_b"] in remaining
        ]

    model_ids = list(data.keys())

    print("  Plots genereren...\n")

    # Speed plots (always available)
    plot_speed_per_scenario(data)
    plot_speed_summary(data)
    plot_tool_calls(data)

    # Pairwise plots (require pairwise_results.json)
    if comparisons:
        tally = _tally(comparisons, model_ids)
        plot_win_rate_ranking(tally)
        plot_dimension_wins(tally)
        plot_h2h_matrix(comparisons, model_ids)
        plot_speed_vs_winrate(data, tally)
        plot_price_vs_winrate(data, tally)
        plot_pairwise_per_scenario(comparisons)
    else:
        print("  SKIP  Pairwise plots (geen pairwise_results.json)")

    print(f"\n  Alle plots opgeslagen in: {PLOTS_DIR}/")
    print()


if __name__ == "__main__":
    main()

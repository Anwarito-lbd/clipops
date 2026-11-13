"""Render an Obsidian-style dark-mode knowledge graph diagram from vault/*.md."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import networkx as nx

ROOT = Path(__file__).resolve().parents[1]
VAULT_DIR = ROOT / "vault"
OUT_PNG = ROOT / "docs" / "images" / "vault-graph.png"

TAG_COLORS = {
    "index": "#e8b44c",        # amber gold
    "pipeline": "#22d3ee",     # cyan
    "architecture": "#6366f1", # electric indigo
    "examples": "#3ddc97",     # emerald
    "config": "#f472b6",       # rose
}


def _extract_tag(text: str) -> str:
    m = re.search(r"tags:\s*\n\s*-\s*([a-zA-Z0-9_-]+)", text)
    return m.group(1) if m else "pipeline"


def main() -> None:
    notes = sorted(VAULT_DIR.glob("*.md"))
    link_rx = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")

    g = nx.DiGraph()
    node_tags: dict[str, str] = {}

    for p in notes:
        stem = p.stem
        text = p.read_text(encoding="utf-8")
        node_tags[stem] = _extract_tag(text)
        g.add_node(stem)

    for p in notes:
        src = p.stem
        text = p.read_text(encoding="utf-8")
        for target in link_rx.findall(text):
            dst = target.strip()
            if dst in node_tags and dst != src:
                g.add_edge(src, dst)

    orphans = [n for n in g.nodes if g.in_degree(n) == 0 or g.out_degree(n) == 0]

    # Deterministic radial layout with Home at center
    pos: dict[str, tuple[float, float]] = {"Home": (0.0, 0.0)}
    ring = [n for n in g.nodes if n != "Home"]
    # Order by category for clean visual clustering
    order = {"pipeline": 0, "architecture": 1, "config": 2, "examples": 3}
    ring.sort(key=lambda n: (order.get(node_tags[n], 9), n))
    for i, name in enumerate(ring):
        angle = (2.0 * math.pi * i) / len(ring) - math.pi / 2
        radius = 1.05 if node_tags[name] == "pipeline" else 1.38
        pos[name] = (radius * math.cos(angle), radius * math.sin(angle))

    fig, ax = plt.subplots(figsize=(12, 8.2), dpi=180)
    fig.patch.set_facecolor("#0b0f17")
    ax.set_facecolor("#0b0f17")

    nx.draw_networkx_edges(
        g,
        pos,
        ax=ax,
        edge_color="#334155",
        alpha=0.55,
        width=1.15,
        arrows=True,
        arrowsize=10,
        connectionstyle="arc3,rad=0.08",
        min_source_margin=16,
        min_target_margin=16,
    )

    colors = [TAG_COLORS.get(node_tags[n], "#94a3b8") for n in g.nodes]
    sizes = [1100 if n == "Home" else 420 + 45 * g.degree(n) for n in g.nodes]

    nx.draw_networkx_nodes(
        g,
        pos,
        ax=ax,
        node_color=colors,
        node_size=sizes,
        edgecolors="#0f172a",
        linewidths=2.0,
    )

    for n, (x, y) in pos.items():
        dy = 0.12 if y >= 0 else -0.14
        if n == "Home":
            dy = -0.15
        ax.text(
            x,
            y + dy,
            f"{n}\n({g.in_degree(n)}↓ {g.out_degree(n)}↑)",
            ha="center",
            va="center",
            fontsize=8.5,
            fontweight="bold" if n == "Home" else "normal",
            color="#e5edf8",
            bbox=dict(boxstyle="round,pad=0.22", facecolor="#111827", edgecolor="#243149", alpha=0.88),
        )

    legend_handles = [
        mpatches.Patch(color=col, label=f"#{tag}") for tag, col in TAG_COLORS.items()
    ]
    ax.legend(
        handles=legend_handles,
        loc="upper right",
        frameon=True,
        facecolor="#111827",
        edgecolor="#243149",
        labelcolor="#e5edf8",
        fontsize=9,
    )

    ax.set_title(
        f"ClipOps Obsidian Clipping Brain (vault/) — {g.number_of_nodes()} Notes · {g.number_of_edges()} Wikilinks · {len(orphans)} Orphans",
        color="#e5edf8",
        fontsize=13,
        fontweight="bold",
        pad=14,
    )
    ax.axis("off")
    ax.set_xlim(-1.85, 1.85)
    ax.set_ylim(-1.8, 1.8)

    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(OUT_PNG, dpi=180, facecolor="#0b0f17")
    plt.close(fig)
    print(json.dumps({
        "output": str(OUT_PNG),
        "nodes": g.number_of_nodes(),
        "edges": g.number_of_edges(),
        "orphans": orphans,
    }, indent=2))


if __name__ == "__main__":
    main()

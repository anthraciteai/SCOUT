#!/usr/bin/env python3
"""Render SCOUT data-workflow diagram to PNG."""
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib as mpl
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

mpl.rcParams["text.usetex"] = False
mpl.rcParams["mathtext.default"] = "regular"
mpl.rcParams["font.weight"] = "regular"

OUT = Path(__file__).resolve().parent / "scout-data-workflow.png"

# lane colors
C_IN = "#dbeafe"      # inputs
C_DET = "#dcfce7"     # deterministic matcher
C_LLM = "#ffedd5"     # optional LLM
C_STORE = "#f3e8ff"   # vault
C_OUT = "#fef9c3"     # writing
EDGE = "#1e293b"
MUTED = "#64748b"

W, H = 14.5, 9.2
fig, ax = plt.subplots(figsize=(W, H), dpi=160)
ax.set_xlim(0, 14.5)
ax.set_ylim(0, 9.2)
ax.axis("off")
fig.patch.set_facecolor("#f8fafc")
ax.set_facecolor("#f8fafc")


def box(x, y, w, h, text, facecolor, *, lw=1.2, fs=9, weight="regular"):
    p = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle="round,pad=0.04,rounding_size=0.12",
        linewidth=lw,
        edgecolor=EDGE,
        facecolor=facecolor,
    )
    ax.add_patch(p)
    ax.text(
        x + w / 2,
        y + h / 2,
        text,
        ha="center",
        va="center",
        fontsize=fs,
        color=EDGE,
        fontweight=weight,
        wrap=True,
        family="DejaVu Sans",
        parse_math=False,
    )
    return (x + w / 2, y, x + w / 2, y + h, x, x + w)  # cx, bottom, top, left, right helpers


def arrow(x1, y1, x2, y2, label="", style="-|>", color=EDGE):
    ax.add_patch(
        FancyArrowPatch(
            (x1, y1),
            (x2, y2),
            arrowstyle=style,
            mutation_scale=12,
            linewidth=1.15,
            color=color,
            connectionstyle="arc3,rad=0",
        )
    )
    if label:
        ax.text(
            (x1 + x2) / 2 + 0.08,
            (y1 + y2) / 2 + 0.08,
            label,
            fontsize=7.5,
            color=MUTED,
            ha="left",
            va="bottom",
            style="italic",
            parse_math=False,
        )


def lane(y0, y1, title, color):
    ax.add_patch(
        FancyBboxPatch(
            (0.18, y0),
            14.14,
            y1 - y0,
            boxstyle="round,pad=0.02,rounding_size=0.08",
            linewidth=0,
            facecolor=color,
            alpha=0.22,
            zorder=0,
        )
    )
    ax.text(0.32, (y0 + y1) / 2, title, fontsize=8, color=MUTED, va="center", rotation=90)


ax.text(
    7.25,
    8.85,
    "SCOUT data workflow",
    ha="center",
    va="center",
    fontsize=16,
    fontweight="bold",
    color=EDGE,
)
ax.text(
    7.25,
    8.48,
    "Tag prefixes, not dumps. Inbox ranks every open topic high-to-low. Council is opt-in.",
    ha="center",
    va="center",
    fontsize=9,
    color=MUTED,
)

# lanes (background)
lane(6.55, 8.25, "IN", "#bfdbfe")
lane(4.55, 6.45, "RANK", "#bbf7d0")
lane(2.35, 4.45, "LLM", "#fed7aa")
lane(0.25, 2.25, "VAULT", "#e9d5ff")

# --- inputs ---
box(1.1, 7.05, 2.5, 0.95, "ME resume\nusers/<id>/me.md\nresume/tags.json + v/{sha}", C_IN, fs=8, weight="bold")
box(4.0, 7.05, 2.7, 0.95, "Company pack\nmission + products\ncompanies/<id>/tags.json", C_IN, fs=8, weight="bold")
box(7.15, 7.05, 2.6, 0.95, "Org ACL\nemployees/<you> exists", C_IN, fs=8, weight="bold")
box(10.2, 7.05, 3.3, 0.95, "DSIP public API\nsbirs/<sbir_id>/tags.json", C_IN, fs=8, weight="bold")

# --- ranker ---
box(2.3, 5.05, 4.4, 1.05, "Keyword extract\n(optional cheap LLM → search_queries)", C_DET, fs=9)
box(7.4, 5.05, 5.4, 1.05, "Matcher  ·  no council\nall open topics, greatest → least", C_DET, fs=9, weight="bold")

arrow(2.35, 7.05, 3.6, 6.10)
arrow(5.35, 7.05, 4.6, 6.10)
arrow(8.45, 7.05, 9.2, 6.10, "must be on list")
arrow(11.85, 7.05, 10.7, 6.10)

arrow(6.7, 5.57, 7.4, 5.57)

# hunt
box(1.1, 5.15, 1.0, 0.85, "Hunt\ntimer", C_DET, fs=8)
arrow(2.1, 5.57, 2.3, 5.57)

# inbox
box(4.6, 3.95, 5.3, 0.48, "Inbox  ·  every open topic, high → low  ·  hunt digest", C_DET, fs=8.5)
arrow(10.1, 5.05, 7.25, 4.43)

# --- optional LLM ---
box(1.3, 2.65, 3.5, 1.15, "Flint  (opt-in)\ncreative sparks from ME tools only\n→ flint.json", C_LLM, fs=8.5, weight="bold")
box(5.4, 2.65, 4.5, 1.15, "Council  (opt-in, sequential)\nfit → tech → BD → team → lift\n→ Flint → capture → chair GO/NO-GO", C_LLM, fs=8.5, weight="bold")
box(10.3, 2.65, 3.2, 1.15, "Host Ollama\n:11434  llama3.2:3b\nnever a second bind", C_LLM, fs=8.5)

arrow(5.5, 3.95, 3.05, 3.80, "click Flint")
arrow(8.5, 3.95, 7.65, 3.80, "Deep-score / Council")
arrow(8.9, 3.22, 10.3, 3.22)
arrow(4.8, 3.22, 5.4, 3.22)

# --- vault / writing ---
box(1.1, 0.45, 3.7, 1.55, "Personal cache\nsbir/<topic>/<company>/users/<you>/\n  flint.json   council.json\n  draft.md     chat/<agent>.json", C_STORE, fs=8)
box(5.15, 0.45, 4.3, 1.55, "Federated org\nshared/approaches/<you>.json\nshared/collab.json  (overlap)\nshared/proposal.md  +  council.json", C_STORE, fs=8)
box(9.75, 0.45, 3.85, 1.55, "Group desk\nset-diff flags Ken ∩ Jake\nCollier sees cards, not drafts\npromote → shared proposal", C_OUT, fs=8)

arrow(3.05, 2.65, 2.95, 2.00)
arrow(7.65, 2.65, 7.3, 2.00)
arrow(4.8, 1.22, 5.15, 1.22)
arrow(9.45, 1.22, 9.75, 1.22)

# legend
ax.add_patch(FancyBboxPatch((0.35, 8.15), 0.28, 0.18, boxstyle="round,pad=0.01", fc=C_IN, ec=EDGE, lw=0.6))
ax.text(0.72, 8.24, "input", fontsize=7.5, va="center", color=MUTED)
ax.add_patch(FancyBboxPatch((1.55, 8.15), 0.28, 0.18, boxstyle="round,pad=0.01", fc=C_DET, ec=EDGE, lw=0.6))
ax.text(1.92, 8.24, "deterministic (no council)", fontsize=7.5, va="center", color=MUTED)
ax.add_patch(FancyBboxPatch((4.15, 8.15), 0.28, 0.18, boxstyle="round,pad=0.01", fc=C_LLM, ec=EDGE, lw=0.6))
ax.text(4.52, 8.24, "LLM, user-gated", fontsize=7.5, va="center", color=MUTED)
ax.add_patch(FancyBboxPatch((6.15, 8.15), 0.28, 0.18, boxstyle="round,pad=0.01", fc=C_STORE, ec=EDGE, lw=0.6))
ax.text(6.52, 8.24, "vault files", fontsize=7.5, va="center", color=MUTED)

fig.tight_layout(pad=0.3)
fig.savefig(OUT, dpi=160, bbox_inches="tight", facecolor=fig.get_facecolor())
print(OUT)

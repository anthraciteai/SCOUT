#!/usr/bin/env python3
"""Render SCOUT group-desk overlap sequence diagram to PNG."""
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

mpl.rcParams["text.usetex"] = False
mpl.rcParams["mathtext.default"] = "regular"
mpl.rcParams["font.weight"] = "regular"

OUT = Path(__file__).resolve().parent / "collab-overlap.png"

EDGE = "#1e293b"
MUTED = "#64748b"
PAPER = "#f8fafc"
KEN = "#dbeafe"
JAKE = "#cffafe"
MATT = "#fef3c7"
VAULT = "#f3e8ff"
COLLIER = "#ffedd5"
DET = "#dcfce7"

W, H = 14.4, 11.35
fig, ax = plt.subplots(figsize=(W, H), dpi=160)
ax.set_xlim(0, W)
ax.set_ylim(0, H)
ax.axis("off")
fig.patch.set_facecolor(PAPER)
ax.set_facecolor(PAPER)

ACTORS = [
    ("Ken", 1.55, KEN, "draft + Flint"),
    ("Jake", 4.15, JAKE, "draft + Flint"),
    ("Matt", 6.75, MATT, "capture take"),
    ("Vault", 9.45, VAULT, "cards · collab.json"),
    ("Collier", 12.15, COLLIER, "cards only"),
]
XS = {name: x for name, x, _, _ in ACTORS}
TOP = 9.22
BOT = 0.62


def box(x, y, w, h, facecolor, *, lw=1.05, radius=0.10):
    ax.add_patch(
        FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle=f"round,pad=0.03,rounding_size={radius}",
            linewidth=lw,
            edgecolor=EDGE,
            facecolor=facecolor,
        )
    )


def txt(x, y, s, *, fs=9, color=EDGE, weight="regular", ha="center", va="center"):
    ax.text(
        x,
        y,
        s,
        fontsize=fs,
        color=color,
        fontweight=weight,
        ha=ha,
        va=va,
        family="DejaVu Sans",
        parse_math=False,
    )


def lifeline(x):
    ax.plot([x, x], [BOT, TOP - 0.08], color="#cbd5e1", lw=1.15, ls=(0, (3, 3)), zorder=1)


def arrow(x1, x2, y, color=EDGE, style="-|>"):
    ax.add_patch(
        FancyArrowPatch(
            (x1, y),
            (x2, y),
            arrowstyle=style,
            mutation_scale=11,
            linewidth=1.15,
            color=color,
            connectionstyle="arc3,rad=0",
            zorder=3,
        )
    )


def self_arrow(x, y):
    ax.plot([x + 0.12, x + 0.72, x + 0.72, x + 0.12], [y + 0.22, y + 0.22, y - 0.12, y - 0.12], color=EDGE, lw=1.05, zorder=3)
    ax.add_patch(
        FancyArrowPatch(
            (x + 0.28, y - 0.12),
            (x + 0.12, y - 0.12),
            arrowstyle="-|>",
            mutation_scale=10,
            linewidth=1.05,
            color=EDGE,
            zorder=3,
        )
    )


def bar(x, y, h, color):
    ax.add_patch(
        FancyBboxPatch(
            (x - 0.09, y - h / 2),
            0.18,
            h,
            boxstyle="square,pad=0",
            linewidth=0.6,
            edgecolor=EDGE,
            facecolor=color,
            zorder=2,
        )
    )


ax.text(
    W / 2,
    10.92,
    "SCOUT group desk — overlap without three drafts",
    ha="center",
    va="center",
    fontsize=16,
    fontweight="bold",
    color=EDGE,
    parse_math=False,
)
ax.text(
    W / 2,
    10.48,
    "Approach cards are public to the org. Private draft.md never leaves users/{id}/.\n"
    "Collier sees cards + set-diff only — not the private narrative.",
    ha="center",
    va="center",
    fontsize=9,
    color=MUTED,
    parse_math=False,
)

for name, x, color, sub in ACTORS:
    box(x - 0.95, 9.28, 1.90, 0.72, color)
    txt(x, 9.70, name, fs=10.5, weight="bold")
    txt(x, 9.42, sub, fs=7.2, color=MUTED)
    lifeline(x)

# 1–3 publish cards
bar(XS["Ken"], 8.55, 0.38, KEN)
arrow(XS["Ken"] + 0.10, XS["Vault"] - 0.10, 8.55)
txt(
    (XS["Ken"] + XS["Vault"]) / 2,
    8.78,
    "1  Flint / headed draft  →  shared/approaches/ken.json",
    fs=8.1,
    ha="center",
)

bar(XS["Jake"], 7.55, 0.38, JAKE)
arrow(XS["Jake"] + 0.10, XS["Vault"] - 0.10, 7.55)
txt(
    (XS["Jake"] + XS["Vault"]) / 2,
    7.78,
    "2  Flint  →  shared/approaches/jake.json",
    fs=8.1,
    ha="center",
)

bar(XS["Matt"], 6.55, 0.38, MATT)
arrow(XS["Matt"] + 0.10, XS["Vault"] - 0.10, 6.55)
txt(
    (XS["Matt"] + XS["Vault"]) / 2,
    6.78,
    "3  Flint / win themes  →  shared/approaches/matt.json",
    fs=8.1,
    ha="center",
)

# 4 deterministic
bar(XS["Vault"], 5.35, 0.70, DET)
self_arrow(XS["Vault"], 5.42)
txt(
    XS["Vault"] + 1.55,
    5.55,
    "4  checksum + token set-diff\n    0 tokens.  Ken AND Jake.",
    fs=8.1,
    ha="left",
)

# 5 desk flag
bar(XS["Vault"], 4.22, 0.36, VAULT)
arrow(XS["Vault"] - 0.10, XS["Ken"] + 0.10, 4.22, style="-|>")
txt(
    (XS["Ken"] + XS["Vault"]) / 2,
    4.45,
    "5  Desk flag: Ken · Jake overlap  ·  disconnected health COP",
    fs=8.1,
    ha="center",
)

# 6 collier
bar(XS["Vault"], 3.12, 0.36, VAULT)
bar(XS["Collier"], 3.12, 0.36, COLLIER)
arrow(XS["Vault"] + 0.10, XS["Collier"] - 0.10, 3.12)
txt(
    (XS["Vault"] + XS["Collier"]) / 2,
    3.35,
    "6  three cards + overlap sets   (~1k tok)",
    fs=8.1,
    ha="center",
)

# 7 suggestions
bar(XS["Collier"], 2.12, 0.36, COLLIER)
arrow(XS["Collier"] - 0.10, XS["Vault"] + 0.10, 2.12)
txt(
    (XS["Vault"] + XS["Collier"]) / 2,
    2.35,
    "7  split + promote bullets  →  shared/collab.json",
    fs=8.1,
    ha="center",
)

# 8 promote
bar(XS["Ken"], 1.12, 0.36, KEN)
bar(XS["Vault"], 1.12, 0.36, VAULT)
arrow(XS["Ken"] + 0.10, XS["Vault"] - 0.10, 1.12)
txt(
    (XS["Ken"] + XS["Vault"]) / 2,
    1.35,
    "8  Insert into shared  (If-Match proposal sha)  →  shared/proposal.md",
    fs=8.1,
    ha="center",
)

box(0.28, 0.18, 13.85, 0.52, "#ffffff", lw=0.7)
txt(
    W / 2,
    0.44,
    "Cache key = sha(ken)+sha(jake)+sha(matt). Same cards → no second Collier call. Teammates never read draft.md.",
    fs=8.0,
    color=MUTED,
)

fig.tight_layout(pad=0.28)
fig.savefig(OUT, dpi=160, bbox_inches="tight", facecolor=fig.get_facecolor())
print(OUT)

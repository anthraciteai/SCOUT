#!/usr/bin/env python3
"""Render SCOUT agent working-log (chat) diagram to PNG."""
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

mpl.rcParams["text.usetex"] = False
mpl.rcParams["mathtext.default"] = "regular"
mpl.rcParams["font.weight"] = "regular"

OUT = Path(__file__).resolve().parent / "agent-chat-log.png"

EDGE = "#1e293b"
MUTED = "#64748b"
PAPER = "#f8fafc"
YOU = "#dbeafe"
FLINT = "#fef3c7"
HEWER = "#ffedd5"
DAVY = "#dcfce7"
VAULT = "#f3e8ff"

W, H = 13.2, 10.6
fig, ax = plt.subplots(figsize=(W, H), dpi=160)
ax.set_xlim(0, W)
ax.set_ylim(0, H)
ax.axis("off")
fig.patch.set_facecolor(PAPER)
ax.set_facecolor(PAPER)


def box(x, y, w, h, facecolor, *, lw=1.05, radius=0.12):
    p = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle=f"round,pad=0.04,rounding_size={radius}",
        linewidth=lw,
        edgecolor=EDGE,
        facecolor=facecolor,
    )
    ax.add_patch(p)


def txt(x, y, s, *, fs=9, color=EDGE, weight="regular", ha="left", va="top"):
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
        wrap=True,
    )


ax.text(
    6.6,
    10.22,
    "SCOUT working log",
    ha="center",
    va="center",
    fontsize=16,
    fontweight="bold",
    color=EDGE,
    parse_math=False,
)
ax.text(
    6.6,
    9.82,
    "You talk to each agent. Constraints stick. Every turn is recorded.",
    ha="center",
    va="center",
    fontsize=9,
    color=MUTED,
    parse_math=False,
)

# lane labels
box(0.28, 0.22, 8.55, 9.20, "#ffffff", lw=0.8)
txt(0.48, 9.22, "Chat log  ·  topic A24-123  ·  user ken", fs=8.5, color=MUTED, weight="bold")

box(9.05, 0.22, 3.9, 9.20, VAULT, lw=0.8)
txt(9.22, 9.22, "Vault  (recorded)", fs=8.5, color=MUTED, weight="bold")

# --- bubbles (x, y, w, h, color, who, body, mine?) ---
turns = [
    (
        0.55,
        7.35,
        7.7,
        1.62,
        FLINT,
        "Flint",
        "Spark 2 — TAK overlay as the COP for the health feed.\n"
        "Hook: your ULog parser already has the aircraft state; drop it on TAK\n"
        "so the TPOC sees the same picture as the operators.\n"
        "Tools: TAK, ULog, VEIN C2.\n"
        "Push back if a license or missing skill kills a spark.",
        False,
        "01  opening  (from flint.json)",
    ),
    (
        1.35,
        5.40,
        7.15,
        1.50,
        YOU,
        "You  ·  ken",
        "Due to license we can't ship TAK in this bid.\n"
        "Replace it with MQTT + a custom COP on the stack we already run.\n"
        "Keep the ULog health feed. Do not mention TAK in the proposal.",
        True,
        "02  constraint",
    ),
    (
        0.55,
        3.45,
        7.7,
        1.50,
        FLINT,
        "Flint",
        "Dropped TAK. Substitute: MQTT topics + your existing ULog health\n"
        "feed into a local COP (same operator picture, no TAK license).\n"
        "Paste-ready discriminator: “disconnected health COP over MQTT,\n"
        "fed by the ULog parsers we already ship — no third-party COP tax.”",
        False,
        "03  substitute",
    ),
    (
        0.55,
        2.00,
        7.7,
        1.08,
        HEWER,
        "Hewer",
        "That swap drops lift 6 → 3. MQTT and ULog are already in ME.\n"
        "Adaptation: topic map, COP view, keep VEIN C2 as the safety gate.",
        False,
        "04  lift rewrite",
    ),
    (
        0.55,
        0.48,
        7.7,
        1.12,
        DAVY,
        "Davy",
        "Lock Flint’s MQTT COP as discriminator #1 in shared/proposal.md.\n"
        "Win theme: “we already operate the feed; we are not buying a COP.”",
        False,
        "05  into the draft",
    ),
]

for x, y, w, h, color, who, body, mine, stamp in turns:
    box(x, y, w, h, color)
    who_x = x + w - 0.12 if mine else x + 0.14
    who_ha = "right" if mine else "left"
    txt(who_x, y + h - 0.12, who, fs=8.2, weight="bold", ha=who_ha)
    txt(x + 0.14, y + h - 0.42, body, fs=8.0)
    txt(x + 0.14, y + 0.10, stamp, fs=7.2, color=MUTED)

# vault files (below the column title)
files = [
    (7.72, "chat/flint.json", "opening + your constraint\n+ Flint substitute", FLINT),
    (6.12, "chat/hewer.json", "lift 6 → 3 after the swap", HEWER),
    (4.52, "chat/davy.json", "discriminator locked", DAVY),
    (2.72, "shared/proposal.md", "group writing surface\n(MQTT COP, no TAK)", "#fef9c3"),
    (0.92, "users/ken/…/chat/", "private. teammates see\nthat you wrote, not the log.", VAULT),
]
for y, name, note, color in files:
    box(9.25, y, 3.5, 1.22, "#ffffff")
    box(9.35, y + 0.88, 0.22, 0.18, color, lw=0.6, radius=0.05)
    txt(9.66, y + 0.96, name, fs=8.2, weight="bold", va="center")
    txt(9.42, y + 0.72, note, fs=7.6, color=MUTED)

# arrows from turns into vault
def arrow(x1, y1, x2, y2):
    ax.add_patch(
        FancyArrowPatch(
            (x1, y1),
            (x2, y2),
            arrowstyle="-|>",
            mutation_scale=10,
            linewidth=1.0,
            color=MUTED,
            connectionstyle="arc3,rad=0",
        )
    )


arrow(8.25, 8.15, 9.25, 8.33)
arrow(8.25, 2.54, 9.25, 6.73)
arrow(8.25, 1.04, 9.25, 5.13)
arrow(8.25, 0.90, 9.25, 3.33)

txt(
    9.22,
    0.38,
    "sbir/<topic>/anthracite/users/ken/",
    fs=7.2,
    color=MUTED,
)

fig.tight_layout(pad=0.25)
fig.savefig(OUT, dpi=160, bbox_inches="tight", facecolor=fig.get_facecolor())
print(OUT)

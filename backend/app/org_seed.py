"""Seed Anthracite + Ken / Jake / Matt so an org can collaborate on day one."""
from __future__ import annotations

import hashlib
from pathlib import Path

from .config import settings
from .vault import Vault

COMPANY = "anthracite"

MISSION = """Anthracite AI builds on-prem / air-gapped software for DoD unmanned aviation.
We do not send raw telemetry or ULogs to the cloud. Local LLM (Ollama) on the edge.
Mission: drop a resume, surface qualified SBIR/STTR work, then write the bid as a team.
"""

PRODUCTS = """# Products

**VEIN** — fleet C2 / COP. TAK / ATAK / WinTAK plugin, live vehicle telemetry and video,
mission planning, grouping and assignment, signed commands with audit and replay,
DDIL store-and-forward.

**CANARI** — pre-flight and post-flight health for PX4 drones. ULog parse, phase
segmentation, robust z-score / Mahalanobis vs flock and vs self. GREEN / AMBER / RED
with no LLM in the safety path. Jetson on-device history.

**DAVY** — voice-enabled C2. On-device speech-to-intent, spoken confirmations, local
inference. Emits authorized intent into VEIN; never bypasses command leases.

**SCOUT** — this tool. Rank open DSIP topics, optional council, group writing.
"""

PEOPLE = [
    {
        "user_id": "ken",
        "display_name": "Ken",
        "skills": [
            "PX4",
            "ULog",
            "Jetson",
            "Python",
            "CANARI scoring",
            "companion-computer health",
            "Mahalanobis / robust-z",
        ],
        "me": """Ken — GNC / vehicle health.

Hands-on: PX4, ArduPilot, ULog flight logs, autopilot parameters, motor/vibration/IMU
health, NVIDIA Jetson companion computers, Python, CANARI cohort scoring (median/MAD,
Mahalanobis, IsolationForest). Comfortable wiring on-device history so a bird is judged
against its flock and against itself — not a cloud model.
""",
    },
    {
        "user_id": "jake",
        "display_name": "Jake",
        "skills": [
            "TAK",
            "ATAK",
            "VEIN C2",
            "React",
            "Docker",
            "mission planning",
            "signed commands",
        ],
        "me": """Jake — C2 / TAK / frontend.

Hands-on: TAK / ATAK / WinTAK plugins, VEIN leases and signed commands, React, Docker,
nginx, mission planning UI, grouping/assignment, DDIL store-and-forward. Builds the COP
the operator actually looks at. Does not pretend to tune PX4 PIDs.
""",
    },
    {
        "user_id": "matt",
        "display_name": "Matt",
        "skills": [
            "DAVY voice",
            "Ollama",
            "capture writing",
            "SBIR/STTR",
            "on-device STT",
            "proposal narrative",
        ],
        "me": """Matt — capture + edge voice.

Hands-on: DAVY speech-to-intent, Ollama local inference, on-device STT, SBIR/STTR
proposal narrative, win themes, TPOC questions, debrief mining. Turns Ken's health
math and Jake's C2 into a story a TPOC will fund. Does not invent flight-stack skills.
""",
    },
    {
        "user_id": "dev",
        "display_name": "Dev",
        "skills": ["SCOUT", "local-first"],
        "me": "",
    },
]


def _passwd(user_id: str, password: str) -> str:
    return hashlib.sha256(f"{user_id}:{password}".encode()).hexdigest()


def verify_password(vault: Vault, user_id: str, password: str) -> bool:
    stored = vault.read_text(f"users/{user_id}/passwd").strip()
    if not stored:
        return False
    return stored == _passwd(user_id, password)


def seed_org(vault: Vault) -> None:
    emp_key = f"companies/{COMPANY}/employees.txt"
    if vault.exists(emp_key) and vault.lines(emp_key):
        _maybe_fill_products(vault)
        return

    vault.write_text(f"companies/{COMPANY}/mission.txt", MISSION)
    vault.write_text(f"companies/{COMPANY}/products.md", _products_text())
    vault.write_text(
        f"companies/{COMPANY}/employees.txt",
        "\n".join(p["user_id"] for p in PEOPLE) + "\n",
    )
    vault.write_text(f"groups/{COMPANY}/capture/members.txt", "ken\njake\nmatt\ndev\n")
    vault.write_text(f"groups/{COMPANY}/capture/sbir.txt", "")

    for p in PEOPLE:
        uid = p["user_id"]
        vault.write_text(f"users/{uid}/display_name.txt", p["display_name"] + "\n")
        vault.write_text(f"users/{uid}/passwd", _passwd(uid, uid) + "\n")
        vault.write_text(f"users/{uid}/companies.txt", COMPANY + "\n")
        vault.write_text(f"users/{uid}/skills.txt", "\n".join(p["skills"]) + "\n")
        if p["me"]:
            vault.write_text(f"users/{uid}/me.md", p["me"])
        if not vault.exists(f"users/{uid}/sbir.txt"):
            vault.write_text(f"users/{uid}/sbir.txt", "")


def _products_text() -> str:
    host = Path(__file__).resolve().parents[2] / "data" / "anthracite-capabilities.md"
    if host.is_file():
        return host.read_text(encoding="utf-8")
    vol = Path(settings.data_dir) / "anthracite-capabilities.md"
    if vol.is_file():
        return vol.read_text(encoding="utf-8")
    return PRODUCTS


def _maybe_fill_products(vault: Vault) -> None:
    if not vault.read_text(f"companies/{COMPANY}/products.md").strip():
        vault.write_text(f"companies/{COMPANY}/products.md", _products_text())
    if not vault.read_text(f"companies/{COMPANY}/mission.txt").strip():
        vault.write_text(f"companies/{COMPANY}/mission.txt", MISSION)

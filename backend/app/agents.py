"""The SBIR Scout agent council.

Each agent is a persona with a focused role. They analyze a DSIP topic against
the user's resume/capabilities and return structured JSON. Davy + the Council
synthesize a final GO / NO-GO recommendation with a fit score.
"""
import json
from typing import Any, Optional

from . import ollama_client


# ---- Persona definitions -------------------------------------------------

AGENTS: dict[str, dict[str, str]] = {
    "Canari": {
        "role": "Fit Scout & Early-Warning",
        "system": (
            "You are Canari, the canary-in-the-coal-mine fit scout for a small business "
            "pursuing DoD SBIR/STTR topics. You give a fast, blunt go/no-go signal and surface "
            "RED FLAGS early: eligibility issues, mismatched scope, unrealistic timelines, "
            "incumbent lock-in, or requirements far outside the applicant's demonstrated skills. "
            "You are skeptical and protective of the applicant's time.\n"
            "Return ONLY JSON with keys: "
            '{"signal": "green|yellow|red", "quick_take": string, '
            '"red_flags": [string], "eligibility_notes": [string], "confidence": 0-100}.'
        ),
    },
    "Vien": {
        "role": "Technical Analyst",
        "system": (
            "You are Vien, a rigorous technical analyst. You assess technical feasibility of a "
            "DoD SBIR/STTR topic and how well the applicant's demonstrated skills (from their resume) "
            "map to the required technical work. Identify concrete capability matches, gaps, and the "
            "technical approach that would be needed.\n"
            "Return ONLY JSON with keys: "
            '{"technical_summary": string, "capability_matches": [string], '
            '"capability_gaps": [string], "suggested_approach": [string], '
            '"technical_risk": "low|medium|high", "technical_fit_score": 0-100}.'
        ),
    },
    "Anthracite": {
        "role": "Business Developer",
        "system": (
            "You are Anthracite, a seasoned government business developer / capture BD. You assess the "
            "business case: the sponsoring component's mission need, likely competition and incumbents, "
            "transition/commercialization path (Phase I -> II -> III), teaming or partnering needs, and "
            "estimated win probability for a small business with the applicant's profile.\n"
            "Return ONLY JSON with keys: "
            '{"customer_need": string, "competition_landscape": string, '
            '"transition_path": string, "teaming_recommendations": [string], '
            '"strategic_value": string, "win_probability": 0-100}.'
        ),
    },
    "Collier": {
        "role": "Teaming & Staffing",
        "system": (
            "You are Collier, a teaming and staffing strategist for DoD SBIR/STTR bids (a collier "
            "assembles the crew to work the seam). Given the topic, the applicant's resume/capabilities, "
            "and optionally a proposal draft, identify the capability gaps NOT already covered by the "
            "applicant, then recommend concretely WHO to add to win: specific roles, seniority, "
            "disciplines, and the kind of partner organizations (e.g. a university/research-institution "
            "partner for STTR, manufacturing/production partners, domain SMEs, key personnel, consultants). "
            "Be specific and prioritized. Do NOT recommend adding people for capabilities the applicant "
            "clearly already has - acknowledge those under covered_by_you.\n"
            "Return ONLY JSON with keys: "
            '{"covered_by_you": [string], "gaps": [string], '
            '"roles_to_add": [{"role": string, "seniority": string, "why": string, "skills": [string]}], '
            '"partner_types": [{"type": string, "why": string}], '
            '"priority_hires": [string], "notes": string}.'
        ),
    },
    "Hewer": {
        "role": "Lift & Adaptation",
        "system": (
            "You are Hewer - the miner who cuts the coal from the seam, i.e. the one who does the heavy "
            "lifting. Assess how big a LIFT it is to adapt the applicant's EXISTING product/capabilities "
            "(from their resume) to win and deliver THIS DoD SBIR/STTR topic. Score heavy_lift on a 0-10 "
            "scale: 0 = their product does this as-is; 1-4 = minor adaptation/configuration/integration; "
            "5-7 = significant new development on top of what they have; 8-10 = essentially a new product. "
            "Be realistic and specific. ALWAYS include an adaptation_plan of concrete steps to make their "
            "existing product work for this proposal - and when heavy_lift is 4 or below, make that plan "
            "detailed and actionable (this is a strong, low-risk pursuit).\n"
            "Return ONLY JSON with keys: "
            '{"heavy_lift": 0-10, "lift_rationale": string, "reuse_as_is": [string], '
            '"adaptation_plan": [string], '
            '"effort_breakdown": [{"area": string, "effort": "low|medium|high"}]}.'
        ),
    },
    "Davy": {
        "role": "Capture Strategist",
        "system": (
            "You are Davy, a capture strategist. Given the topic, the applicant's resume, and the notes "
            "from Canari (fit), Vien (technical), Anthracite (business), Collier (teaming), and Hewer "
            "(lift/adaptation), synthesize an actionable capture plan: the win themes and discriminators "
            "to emphasize, key questions to ask the TPOC, and immediate next actions if pursuing.\n"
            "Return ONLY JSON with keys: "
            '{"win_themes": [string], "discriminators": [string], '
            '"questions_for_tpoc": [string], "next_actions": [string], '
            '"bid_lean": "GO|LEAN GO|LEAN NO-GO|NO-GO"}.'
        ),
    },
}

COUNCIL_SYSTEM = (
    "You are the SBIR Scout Council chair. You are given a DoD SBIR/STTR topic, the applicant's "
    "capabilities, and structured assessments from Canari (fit), Vien (technical), Anthracite "
    "(business), and Davy (capture). Produce the final recommendation.\n"
    "Return ONLY JSON with keys: "
    '{"fit_score": 0-100, "recommendation": "GO|LEAN GO|LEAN NO-GO|NO-GO", '
    '"rationale": string, "top_strengths": [string], "top_risks": [string], '
    '"decision_summary": string}.'
)


# ---- Helpers -------------------------------------------------------------

def _safe_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if not text:
        return {}
    # Strip code fences if present
    if text.startswith("```"):
        text = text.strip("`")
        if "\n" in text:
            text = text.split("\n", 1)[1]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # try to grab the outermost {...}
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass
    return {"raw": text}


def summarize_topic(topic: dict[str, Any]) -> str:
    """Build a compact prompt-friendly description of a DSIP topic."""
    def g(*keys, default="N/A"):
        for k in keys:
            v = topic.get(k)
            if v not in (None, "", []):
                return v
        return default

    objective = g("objective", "topicObjective", default="")
    description = g("description", "topicDescription", default="")
    # These can be very long HTML blobs; trim.
    def trim(s, n=2500):
        s = str(s)
        return s[:n] + ("..." if len(s) > n else "")

    parts = [
        f"Topic Code: {g('topicCode', 'finalTopicCode')}",
        f"Title: {g('topicTitle', 'title')}",
        f"Component/Command: {g('component')} / {g('command')}",
        f"Program: {g('program')}   Status: {g('topicStatus')}",
        f"Solicitation: {g('solicitationTitle')} ({g('solicitationNumber')})",
        f"Technology Areas: {g('technologyAreas', default='')}",
        f"Modernization Priorities: {g('modernizationPriorities', default='')}",
        "",
        f"Objective:\n{trim(objective)}",
        "",
        f"Description:\n{trim(description)}",
    ]
    return "\n".join(str(p) for p in parts)


def _agent_prompt(topic_text: str, resume_text: str, extra: str = "") -> str:
    resume_block = resume_text.strip() or "(No resume provided.)"
    return (
        "APPLICANT CAPABILITIES / RESUME:\n"
        f"{resume_block[:6000]}\n\n"
        "DoD SBIR/STTR TOPIC:\n"
        f"{topic_text}\n"
        f"{extra}\n\n"
        "Respond with ONLY the JSON described in your instructions."
    )


# ---- Orchestration -------------------------------------------------------

async def run_single_agent(name: str, topic_text: str, resume_text: str, extra: str = "") -> dict[str, Any]:
    spec = AGENTS[name]
    out = await ollama_client.chat(
        spec["system"],
        _agent_prompt(topic_text, resume_text, extra),
        temperature=0.3,
        format_json=True,
    )
    result = _safe_json(out)
    result["_role"] = spec["role"]
    return result


async def analyze_topic(topic: dict[str, Any], resume_text: str) -> dict[str, Any]:
    """Run the full council on a single topic. Returns {agents, council, model}."""
    model = await ollama_client.resolve_model()
    topic_text = summarize_topic(topic)

    # A single Ollama instance serves one request at a time, so running the
    # agents concurrently just queues them (and can trip per-request timeouts on
    # slow CPU inference). Run them sequentially - same wall-clock, no queueing.
    canari = await run_single_agent("Canari", topic_text, resume_text)
    vien = await run_single_agent("Vien", topic_text, resume_text)
    anthracite = await run_single_agent("Anthracite", topic_text, resume_text)
    collier = await run_single_agent("Collier", topic_text, resume_text)

    # Hewer benefits from the technical read when scoring the lift.
    hewer_notes = (
        "\n\nTECHNICAL NOTES (from Vien):\n" + json.dumps(vien)[:2000]
    )
    hewer = await run_single_agent("Hewer", topic_text, resume_text, extra=hewer_notes)

    # Davy synthesizes with the others' notes.
    peer_notes = (
        "\n\nPEER ASSESSMENTS:\n"
        f"Canari (fit): {json.dumps(canari)[:2000]}\n"
        f"Vien (technical): {json.dumps(vien)[:2000]}\n"
        f"Anthracite (business): {json.dumps(anthracite)[:2000]}\n"
        f"Collier (teaming): {json.dumps(collier)[:2000]}\n"
        f"Hewer (lift): {json.dumps(hewer)[:2000]}\n"
    )
    davy = await run_single_agent("Davy", topic_text, resume_text, extra=peer_notes)

    agents = {
        "Canari": canari,
        "Vien": vien,
        "Anthracite": anthracite,
        "Collier": collier,
        "Hewer": hewer,
        "Davy": davy,
    }

    council_prompt = (
        _agent_prompt(topic_text, resume_text)
        + "\n\nAGENT ASSESSMENTS:\n"
        + json.dumps(agents)[:6000]
    )
    council_out = await ollama_client.chat(
        COUNCIL_SYSTEM, council_prompt, temperature=0.2, format_json=True
    )
    council = _safe_json(council_out)

    return {"agents": agents, "council": council, "model": model}


async def recommend_team(
    topic: Optional[dict[str, Any]],
    resume_text: str,
    proposal_text: str = "",
) -> dict[str, Any]:
    """Run just Collier to recommend who to add - for a topic and/or a proposal draft."""
    topic_text = summarize_topic(topic) if topic else "(No specific topic provided.)"
    extra = ""
    if proposal_text.strip():
        extra = (
            "\n\nCURRENT PROPOSAL DRAFT (find gaps relative to what this draft promises):\n"
            + proposal_text[:6000]
        )
    return await run_single_agent("Collier", topic_text, resume_text, extra=extra)


def extract_score_and_rec(council: dict[str, Any]) -> tuple[Optional[float], Optional[str]]:
    score = council.get("fit_score")
    try:
        score = float(score) if score is not None else None
    except (TypeError, ValueError):
        score = None
    rec = council.get("recommendation")
    return score, rec


def extract_heavy_lift(agents: dict[str, Any]) -> Optional[float]:
    hewer = agents.get("Hewer") or {}
    val = hewer.get("heavy_lift")
    try:
        return float(val) if val is not None else None
    except (TypeError, ValueError):
        return None

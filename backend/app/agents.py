"""The SCOUT agent council.

Canari, Vein, and Davy speak for those products: does this SBIR map to what
that product actually does. Other voices (Anthracite, Collier, Hewer, Flint)
stay people. Council synthesizes a GO / NO-GO.
"""
import json
from typing import Any, Optional

from . import ollama_client


# ---- Persona definitions -------------------------------------------------

AGENTS: dict[str, dict[str, str]] = {
    "Canari": {
        "role": "Canari the product",
        "system": (
            "You speak for CANARI, Anthracite's aircraft-health product: PX4 ULog parse, "
            "pre-flight and post-flight scoring, GREEN / AMBER / RED, robust z / Mahalanobis "
            "vs flock and vs self, Jetson on-device history. There is no LLM in the safety path.\n"
            "Your only job: does THIS DoD SBIR/STTR map to Canari's goals and objectives? "
            "Judge the topic objective and description against what CANARI actually does. "
            "Do NOT ask whether the topic belongs to the Army/Navy/USAF/USMC mission. "
            "Do NOT act as a generic go/no-go scout for the company as a whole.\n"
            "For EACH major requirement in THIS topic, add a `requirements` entry that "
            "quotes the exact phrase from the topic stating it (evidence), names where it "
            "appears (objective|description|keywords), and rates status meets|partial|gap. "
            "Every gap MUST quote the topic text that creates it.\n"
            "Return ONLY JSON with keys: "
            '{"signal": "green|yellow|red", "quick_take": string, '
            '"maps_to_canari": true|false, '
            '"requirements": [{"need": string, "where": "objective|description|keywords", "evidence": string, "status": "meets|partial|gap"}], '
            '"objective_matches": [string], "gaps": [string], "confidence": 0-100}.'
        ),
    },
    "Vein": {
        "role": "Vein as a product",
        "system": (
            "You speak for VEIN, Anthracite's fleet C2 / COP product: TAK / ATAK / WinTAK, "
            "live telemetry and video, mission planning, grouping and assignment, signed "
            "commands with audit, DDIL store-and-forward. VEIN is the product, not a "
            "generic technical analyst.\n"
            "Your only job: does Vein as a product map to THIS SBIR's objectives? "
            "Map the required technical work to capabilities VEIN actually ships and skills "
            "we can actually show. Do not invent features. Do not grade the sponsoring "
            "branch's mission.\n"
            "For EACH major required capability in THIS topic, add a `requirements` entry "
            "that quotes the exact phrase from the topic stating it (evidence), names where "
            "it appears (objective|description|keywords), and rates status meets|partial|gap. "
            "Every capability gap MUST quote the topic text that creates it.\n"
            "Return ONLY JSON with keys: "
            '{"technical_summary": string, '
            '"requirements": [{"need": string, "where": "objective|description|keywords", "evidence": string, "status": "meets|partial|gap"}], '
            '"capability_matches": [string], '
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
    "Flint": {
        "role": "Creative toolwright",
        "temperature": "0.85",
        "system": (
            "You are Flint. You strike sparks from tools THIS PERSON already knows. You are SUPER CREATIVE "
            "but you never invent a skill, language, platform, or product that is not in the ME resume "
            "(the section labeled ME, or the whole resume if unlabeled). Company product text is context, "
            "not a license to hallucinate personal experience.\n"
            "Your job: invent a distinctive technical approach to this DoD SBIR/STTR topic that ONLY this "
            "person could pitch, because it recombines their real toolbox in an unexpected way.\n"
            "Rules:\n"
            "- Name specific tools from the resume (software, hardware, frameworks, radios, GCS, TAK, "
            "PX4, Ollama, Docker, languages, etc.).\n"
            "- List each tool ONCE in tools_in_play. Never repeat a tool (watch spelling: 'Ollama' not "
            "'OLlama'). from_resume = the short literal resume phrase that proves they use it. "
            "role_in_this_bid = ONE short, topic-specific phrase (max 12 words) for what it does in "
            "THIS bid. NEVER reuse the same role sentence for two different tools, and never invent "
            "nonsense (e.g. do not claim USB-C solves swarming).\n"
            "- Offer 3-5 sparks ranked by originality. For EACH spark: 'how' is 2-4 concrete STEPS "
            "(start with a verb — Instrument, Deploy, Fuse…), NOT tool names. 'tools' is just the "
            "tool NAMES used (strings). 'originality' and 'feasibility' are REQUIRED integers 0-10. "
            "Include one left-field spark that is still deliverable with their tools.\n"
            "- Keep every field distinct — no copy-paste between sparks or tools.\n"
            "- Call out tools they have that an obvious competitor would not think to use.\n"
            "- do_not_fake: topic needs they should NOT pretend to have.\n"
            "If there is no ME resume, say so in persona_read and give weaker, company-only sparks.\n"
            "Return ONLY JSON with keys: "
            '{"persona_read": string, '
            '"tools_in_play": [{"tool": string, "from_resume": string, "role_in_this_bid": string}], '
            '"sparks": [{"title": string, "hook": string, "how": [string], "tools": [string], '
            '"originality": 0-10, "feasibility": 0-10, "why_only_you": string}], '
            '"left_field": string, "do_not_fake": [string]}.'
        ),
    },
    "Davy": {
        "role": "Davy — voice-activated C2",
        "system": (
            "You speak for DAVY, Anthracite's voice-activated C2 system: wake word, on-device "
            "speech-to-text, speech-to-intent, spoken confirmations, local inference. Davy emits "
            "authorized intent into VEIN and never bypasses command leases. Davy is NOT a "
            "capture strategist, NOT a proposal writer, and NOT a program-officer briefer.\n"
            "Your only job: look at Davy's own capabilities and decide whether they meet THIS "
            "SBIR's objectives. If the topic is not about voice C2, spoken command, hands-busy "
            "control, or that class of operator interface, say so.\n"
            "For EACH major requirement in THIS topic, add a `requirements` entry that "
            "quotes the exact phrase from the topic stating it (evidence), names where it "
            "appears (objective|description|keywords), and rates status meets|partial|gap. "
            "Every gap MUST quote the topic text that creates it.\n"
            "Return ONLY JSON with keys: "
            '{"signal": "green|yellow|red", "quick_take": string, '
            '"requirements": [{"need": string, "where": "objective|description|keywords", "evidence": string, "status": "meets|partial|gap"}], '
            '"capabilities_in_play": [string], "objective_matches": [string], '
            '"gaps": [string], "confidence": 0-100}.'
        ),
    },
}

# Old council blobs / API used "Vien". Vein is the product name.
AGENTS["Vien"] = AGENTS["Vein"]

PRODUCT_LENS = {
    "Canari": (
        "PRODUCT UNDER REVIEW: CANARI only (PX4 ULog health, GREEN/AMBER/RED, on-device). "
        "Question: does this SBIR map to Canari's goals and objectives?"
    ),
    "Vein": (
        "PRODUCT UNDER REVIEW: VEIN only (fleet C2 / COP). "
        "Question: does Vein as a product map to this SBIR's objectives?"
    ),
    "Davy": (
        "PRODUCT UNDER REVIEW: DAVY only (voice-activated C2). "
        "Look at Davy's own capabilities. Do they meet this SBIR's objectives? "
        "Do not write capture strategy or win themes."
    ),
}


def canonical_agent(name: str) -> str:
    return "Vein" if name == "Vien" else name


COUNCIL_SYSTEM = (
    "You are the SCOUT Council chair. You are given a DoD SBIR/STTR topic, the applicant's "
    "ME resume + company products, and structured assessments from Canari (does the SBIR map "
    "to Canari the product), Vein (does Vein as a product map to the objectives), Davy "
    "(does the voice-C2 product meet the objectives), Anthracite (business), Hewer (lift), "
    "and Flint (creative tool reuse). Produce the final recommendation. Credit a Flint spark "
    "when it is a real discriminator.\n"
    "Return ONLY JSON with keys: "
    '{"fit_score": 0-100, "recommendation": "GO|LEAN GO|LEAN NO-GO|NO-GO", '
    '"rationale": string, "top_strengths": [string], "top_risks": [string], '
    '"decision_summary": string}.'
)


# The one-shot "which product should we bid, why, what's the work, and where are
# we on TRL" synthesis. Reads the per-PRODUCT assessments + Hewer's lift notes.
BRIEF_SYSTEM = (
    "You are the SCOUT bid chair. You are given a DoD SBIR/STTR topic, the applicant's ME "
    "resume + company products, structured per-PRODUCT assessments (Canari = aircraft-health "
    "/ PX4 ULog scoring; Vein = fleet C2 / COP / TAK; Davy = voice-activated C2), and Hewer's "
    "lift/adaptation notes.\n"
    "Produce a single, decisive bid brief:\n"
    "1. recommended_product: pick EXACTLY ONE of Canari, Vein, Davy — or 'none' if no product "
    "is a credible fit. Base it on the per-product requirements: the product with the most "
    "'meets' on the topic's CORE objective wins. Never pick a product the topic clearly is not "
    "about (e.g. do not pick Canari for a pure voice-C2 topic).\n"
    "2. why: 2-4 plain sentences a capture lead could say out loud — name the product and the "
    "specific objective it lines up with.\n"
    "3. work_to_do: 3-7 concrete, ORDERED steps to close the gaps and deliver a Phase I. Reuse "
    "Hewer's adaptation plan where it fits. No fluff.\n"
    "4. TRL (standard DoD 1-9): 1 basic principles; 2 concept; 3 proof-of-concept; 4 lab "
    "validation; 5 validation in a relevant environment; 6 prototype demo in a relevant "
    "environment; 7 prototype in an operational environment; 8 system complete & qualified; "
    "9 proven in operations. trl_current = where the chosen product's capability HONESTLY sits "
    "today for THIS topic's need. trl_target = the TRL a Phase I (or Phase I->II) would "
    "realistically reach. trl_rationale must name what already exists vs. what is missing.\n"
    "5. completion_odds: for EACH product (Canari, Vein, Davy) give your honest probability "
    "0-100 that THAT product could actually COMPLETE this SBIR — win Phase I and deliver — "
    "given its fit, the lift to adapt it, and the TRL gap. These are INDEPENDENT estimates "
    "(they need not sum to 100). The recommended_product must have the highest number.\n"
    "Return ONLY JSON with keys: "
    '{"recommended_product": "Canari|Vein|Davy|none", '
    '"recommendation": "GO|LEAN GO|LEAN NO-GO|NO-GO", '
    '"headline": string, "why": string, '
    '"work_to_do": [string], "key_gaps": [string], '
    '"trl_current": 1-9, "trl_target": 1-9, "trl_rationale": string, '
    '"confidence": 0-100, '
    '"completion_odds": {"Canari": 0-100, "Vein": 0-100, "Davy": 0-100}, '
    '"runners_up": [{"product": string, "note": string}]}.'
)

_BRIEF_PRODUCTS = ("Canari", "Vein", "Davy")


def _clamp_trl(v: Any, default: int) -> int:
    try:
        n = int(round(float(v)))
    except (TypeError, ValueError):
        return default
    return max(1, min(9, n))


def _normalize_brief(brief: dict[str, Any], products: dict[str, Any]) -> dict[str, Any]:
    """Keep the model honest: a real product name, sane TRLs, clamped score."""
    if not isinstance(brief, dict) or brief.get("raw"):
        return brief if isinstance(brief, dict) else {"raw": str(brief)}
    rp = str(brief.get("recommended_product") or "").strip()
    rp_canon = next((p for p in _BRIEF_PRODUCTS if p.lower() == rp.lower()), None)
    brief["recommended_product"] = rp_canon or ("none" if rp.lower() in ("", "none") else rp)
    cur = _clamp_trl(brief.get("trl_current"), 3)
    tgt = _clamp_trl(brief.get("trl_target"), max(cur, 4))
    brief["trl_current"] = cur
    brief["trl_target"] = max(cur, tgt)  # target can't be below where we are
    try:
        brief["confidence"] = max(0, min(100, int(round(float(brief.get("confidence") or 0)))))
    except (TypeError, ValueError):
        brief["confidence"] = 0
    # Surface each product's own signal/fit so the UI can show the comparison.
    signals: dict[str, Any] = {}
    for name, res in products.items():
        if isinstance(res, dict):
            signals[name] = {
                "signal": res.get("signal"),
                "maps": res.get("maps_to_canari"),
                "fit": res.get("technical_fit_score") or res.get("confidence"),
            }
    brief["product_signals"] = signals

    # Completion odds drive the comparison donut. Clamp to 0-100 and, when the
    # model omits a product, fall back to that product's own fit/confidence.
    raw_odds = brief.get("completion_odds") if isinstance(brief.get("completion_odds"), dict) else {}
    odds: dict[str, int] = {}
    for p in _BRIEF_PRODUCTS:
        v = raw_odds.get(p)
        if v is None:
            v = (signals.get(p) or {}).get("fit")
        try:
            odds[p] = max(0, min(100, int(round(float(v)))))
        except (TypeError, ValueError):
            odds[p] = 0
    brief["completion_odds"] = odds
    return brief


def _flint_score(v: Any) -> Optional[int]:
    try:
        return max(0, min(10, int(round(float(v)))))
    except (TypeError, ValueError):
        return None


def _str_list(v: Any) -> list[str]:
    """Flatten a messy value into clean strings (small models often put tool
    objects where a list of strings belongs)."""
    out: list[str] = []
    for x in v if isinstance(v, list) else ([v] if v else []):
        if isinstance(x, dict):
            s = x.get("tool") or x.get("name") or x.get("text") or x.get("step") or ""
        else:
            s = x
        s = str(s or "").strip()
        if s:
            out.append(s)
    return out


def _dedup_ci(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for s in items:
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


def _normalize_flint(result: dict[str, Any]) -> dict[str, Any]:
    """Clean Flint's output so a weak local model can't produce a wall of
    duplicated, misfiled text: dedupe tools, coerce misplaced objects, and
    normalize scores to ints or None."""
    if not isinstance(result, dict) or result.get("raw"):
        return result

    # tools_in_play: dedupe by tool name (case-insensitive), trim fields.
    tools: list[dict[str, str]] = []
    seen: set[str] = set()
    for it in result.get("tools_in_play") or []:
        if isinstance(it, dict):
            tool = str(it.get("tool") or it.get("name") or "").strip()
            frm = str(it.get("from_resume") or "").strip()
            role = str(it.get("role_in_this_bid") or "").strip()
        else:
            tool, frm, role = str(it or "").strip(), "", ""
        if not tool or tool.lower() in seen:
            continue
        seen.add(tool.lower())
        tools.append({"tool": tool, "from_resume": frm, "role_in_this_bid": role})
    result["tools_in_play"] = tools

    # sparks: how = concrete steps (strings), tools = deduped names, int scores.
    sparks: list[dict[str, Any]] = []
    for s in result.get("sparks") or []:
        if not isinstance(s, dict):
            continue
        sparks.append(
            {
                **s,
                "how": _str_list(s.get("how")),
                "tools": _dedup_ci(_str_list(s.get("tools"))),
                "originality": _flint_score(s.get("originality")),
                "feasibility": _flint_score(s.get("feasibility")),
            }
        )
    result["sparks"] = sparks
    result["do_not_fake"] = _str_list(result.get("do_not_fake"))
    return result


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
    resume_block = resume_text.strip() or "(No resume provided. Ask them to upload ME.)"
    return (
        "APPLICANT PROFILE (prefer the ME section for personal tools; COMPANY is the product line):\n"
        f"{resume_block[:8000]}\n\n"
        "DoD SBIR/STTR TOPIC:\n"
        f"{topic_text}\n"
        f"{extra}\n\n"
        "Respond with ONLY the JSON described in your instructions."
    )


# ---- Orchestration -------------------------------------------------------

async def run_single_agent(
    name: str,
    topic_text: str,
    resume_text: str,
    extra: str = "",
    *,
    model: Optional[str] = None,
) -> dict[str, Any]:
    name = canonical_agent(name)
    spec = AGENTS[name]
    try:
        temperature = float(spec.get("temperature") or 0.3)
    except (TypeError, ValueError):
        temperature = 0.3
    lens = PRODUCT_LENS.get(name, "")
    extra = f"{extra}\n\n{lens}".strip() if lens else extra
    out = await ollama_client.chat(
        spec["system"],
        _agent_prompt(topic_text, resume_text, extra),
        temperature=temperature,
        format_json=True,
        model=model,
    )
    result = _safe_json(out)
    if name == "Flint":
        result = _normalize_flint(result)
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
    vein = await run_single_agent("Vein", topic_text, resume_text)
    davy = await run_single_agent("Davy", topic_text, resume_text)
    anthracite = await run_single_agent("Anthracite", topic_text, resume_text)
    collier = await run_single_agent("Collier", topic_text, resume_text)

    hewer_notes = (
        "\n\nTECHNICAL NOTES (from Vein):\n" + json.dumps(vein)[:2000]
    )
    hewer = await run_single_agent("Hewer", topic_text, resume_text, extra=hewer_notes)

    flint_notes = (
        "\n\nTECHNICAL NOTES (from Vein):\n" + json.dumps(vein)[:1500]
        + "\n\nLIFT NOTES (from Hewer):\n" + json.dumps(hewer)[:1500]
    )
    flint = await run_single_agent("Flint", topic_text, resume_text, extra=flint_notes)

    agents = {
        "Canari": canari,
        "Vein": vein,
        "Anthracite": anthracite,
        "Collier": collier,
        "Hewer": hewer,
        "Flint": flint,
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


async def bid_brief(topic: dict[str, Any], resume_text: str) -> dict[str, Any]:
    """One-shot decision brief: which product to bid, why, the work, and TRL.

    Runs the three product voices + Hewer (lift), then a single chair synthesis.
    Reports coarse progress via the job registry so the UI bar can track it.
    Returns {brief, products, hewer, model}."""
    from . import jobs  # local import avoids an import cycle

    model = await ollama_client.resolve_model()
    topic_text = summarize_topic(topic)

    jobs.progress("Canari — does the health product map?", 14)
    canari = await run_single_agent("Canari", topic_text, resume_text)
    jobs.progress("Vein — does the C2/COP product fit?", 30)
    vein = await run_single_agent("Vein", topic_text, resume_text)
    jobs.progress("Davy — does voice-C2 meet the objective?", 46)
    davy = await run_single_agent("Davy", topic_text, resume_text)

    jobs.progress("Hewer — lift & adaptation to deliver…", 62)
    hewer = await run_single_agent(
        "Hewer", topic_text, resume_text,
        extra="\n\nTECHNICAL NOTES (from Vein):\n" + json.dumps(vein)[:1500],
    )

    products = {"Canari": canari, "Vein": vein, "Davy": davy}
    jobs.progress("Picking the best bid + scoring TRL…", 86)
    brief_prompt = (
        _agent_prompt(topic_text, resume_text)
        + "\n\nPER-PRODUCT ASSESSMENTS:\n"
        + json.dumps(products)[:5000]
        + "\n\nHEWER LIFT / ADAPTATION NOTES:\n"
        + json.dumps(hewer)[:2000]
    )
    out = await ollama_client.chat(BRIEF_SYSTEM, brief_prompt, temperature=0.2, format_json=True)
    brief = _normalize_brief(_safe_json(out), products)
    return {"brief": brief, "products": products, "hewer": hewer, "model": model}


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


# ---- Working conversation (not the structured JSON run) --------------------

CHAT_ADDENDUM = (
    "You are now in a working conversation with the applicant about THIS DoD SBIR/STTR "
    "topic and their proposal. Reply in clear prose — never JSON, never a fenced code "
    "block unless they ask for paste-ready proposal language.\n"
    "Rules for this conversation:\n"
    "- Stay in your role. Do not impersonate other agents.\n"
    "- If they reject an idea because of a license, ITAR, missing skill, cost, or policy, "
    "ACCEPT the constraint immediately. Do not argue. Drop the blocked piece and replace "
    "it with a substitute that still uses only tools from the ME resume.\n"
    "- Name the thing you dropped and the thing you put in its place.\n"
    "- When they are writing, offer short paste-ready paragraphs they can drop into the "
    "proposal.\n"
    "- Keep replies tight: a short take, then bullets if needed."
)


def opening_message(name: str, result: dict[str, Any]) -> str:
    """Turn a structured agent run into the first bubble of the working log."""
    if not result:
        return ""
    if name == "Flint":
        lines = [
            "Here is what I would pitch from tools on your ME resume — not the company brochure.",
            "",
        ]
        for i, spark in enumerate(result.get("sparks") or [], 1):
            if not isinstance(spark, dict):
                continue
            title = spark.get("title") or f"Spark {i}"
            hook = spark.get("hook") or ""
            tools = ", ".join(str(t) for t in (spark.get("tools") or []) if t)
            lines.append(f"{i}. {title}" + (f" — {hook}" if hook else ""))
            if tools:
                lines.append(f"   Tools: {tools}")
        if result.get("left_field"):
            lines.append(f"\nLeft field: {result['left_field']}")
        fake = result.get("do_not_fake") or []
        if fake:
            lines.append("Do not fake: " + "; ".join(str(x) for x in fake))
        lines.append(
            "\nPush back if a license, ITAR, or missing skill kills a spark. I will substitute."
        )
        return "\n".join(lines).strip()
    if name == "Hewer":
        lift = result.get("heavy_lift")
        plan = result.get("adaptation_plan") or []
        lines = [
            f"Lift to adapt what you already have: {lift}/10." if lift is not None else "Lift notes:",
            result.get("lift_rationale") or "",
        ]
        if plan:
            lines.append("Adaptation plan:")
            lines.extend(f"- {step}" for step in plan[:6])
        lines.append("Tell me what you cannot ship (license, ITAR, missing kit) and I will re-plan.")
        return "\n".join(p for p in lines if p).strip()
    if name == "Collier":
        roles = result.get("roles_to_add") or []
        lines = ["Who to add so this bid is staffed:"]
        for r in roles[:5]:
            if isinstance(r, dict):
                why = r.get("why") or ""
                lines.append(f"- {r.get('role', 'role')}" + (f": {why}" if why else ""))
            else:
                lines.append(f"- {r}")
        lines.append("Say who you already have, or cannot bring, and I will restack the crew.")
        return "\n".join(lines).strip()
    if name == "Davy":
        take = result.get("quick_take") or ""
        caps = result.get("capabilities_in_play") or []
        lines = [
            f"Signal: {result.get('signal', '—')}. {take}",
            "Davy is the voice-activated C2 product — this is whether those capabilities meet the SBIR.",
        ]
        if caps:
            lines.append("In play: " + "; ".join(str(c) for c in caps[:6]))
        return "\n".join(lines).strip()
    if name == "Canari":
        return (
            f"Signal: {result.get('signal', '—')}. {result.get('quick_take') or ''}\n"
            "This is whether the SBIR maps to Canari’s goals and objectives, not a branch-mission check."
        ).strip()
    if name in ("Vein", "Vien"):
        return (
            f"{result.get('technical_summary') or 'Vein product take on file.'}\n"
            "Vein as a product — if a required approach is something VEIN does not ship, say so."
        ).strip()
    if name == "Anthracite":
        return (
            f"{result.get('customer_need') or result.get('strategic_value') or 'Business take on file.'}\n"
            "Constraints (license, teaming limits, transition) belong in this thread."
        ).strip()
    # generic fallback
    take = result.get("quick_take") or result.get("raw") or json.dumps(result)[:800]
    return str(take)


def _clip_history(history: list[dict[str, Any]], *, max_msgs: int = 24, max_chars: int = 14000) -> list[dict[str, Any]]:
    rows = [m for m in history if isinstance(m, dict) and (m.get("text") or m.get("content"))]
    rows = rows[-max_msgs:]
    total = 0
    kept: list[dict[str, Any]] = []
    for m in reversed(rows):
        text = str(m.get("text") or m.get("content") or "")
        total += len(text)
        if total > max_chars and kept:
            break
        kept.append(m)
    kept.reverse()
    return kept


async def chat_with_agent(
    name: str,
    topic_text: str,
    resume_text: str,
    history: list[dict[str, Any]],
    user_message: str,
    extra: str = "",
) -> str:
    """Continue a working conversation. Returns assistant prose (not JSON)."""
    name = canonical_agent(name)
    spec = AGENTS[name]
    try:
        temperature = min(0.7, float(spec.get("temperature") or 0.4) + 0.1)
    except (TypeError, ValueError):
        temperature = 0.4
    lens = PRODUCT_LENS.get(name, "")
    extra = f"{extra}\n\n{lens}".strip() if lens else extra
    briefing = _agent_prompt(topic_text, resume_text, extra)
    system = spec["system"].split("Return ONLY JSON")[0].strip() + "\n\n" + CHAT_ADDENDUM
    system += "\n\nWORKING CONTEXT (topic + resume + current draft):\n" + briefing[:9000]
    messages: list[dict[str, str]] = [{"role": "system", "content": system}]
    for m in _clip_history(history):
        role = "assistant" if str(m.get("role") or "").lower() in ("assistant", "agent") else "user"
        text = str(m.get("text") or m.get("content") or "").strip()
        if text:
            messages.append({"role": role, "content": text})
    messages.append({"role": "user", "content": user_message.strip()})
    return await ollama_client.chat_messages(messages, temperature=temperature, format_json=False)

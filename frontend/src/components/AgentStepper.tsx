import { useEffect, useRef, useState } from "react";
import { AnalysisApi, CatalogApi, OrgApi } from "../api";
import type { AgentResult, HewerResult, Topic, TeamRecommendation } from "../types";
import { topicMeta } from "../pages/Browse";
import HewerCard, { liftColor } from "./HewerCard";
import TeamCard from "./TeamCard";
import FlintCard, { type FlintResult } from "./FlintCard";
import ChatDrawer from "./ChatDrawer";
import BidBrief from "./BidBrief";
import ErrorBoundary from "./ErrorBoundary";
import {
  AGENTS,
  COLORS,
  CONTRIBUTES,
  ORDER,
  PRODUCT_VOICES,
  ROLES,
  SLICES,
  TEAM_VOICES,
  type AgentName,
  type ContributeId,
  type SliceId,
  asList,
  normalizeAgentResults,
  productHeadings,
  stripHtml,
} from "./agentWorkspace";

function AgentPill({
  name,
  on,
  has,
  onClick,
}: {
  name: AgentName;
  on: boolean;
  has: boolean;
  onClick: () => void;
}) {
  const color = COLORS[name];
  const style: React.CSSProperties = on
    ? {
        background: color,
        color: "#0a0b0d",
        borderColor: color,
        boxShadow: `0 10px 26px -12px ${color}, 0 0 0 1px ${color}`,
      }
    : has
      ? { borderColor: `${color}80`, color, background: `${color}14` }
      : {};
  return (
    <button
      className={`${on ? "small" : "ghost small"} inline-flex items-center gap-1.5`}
      style={style}
      onClick={onClick}
    >
      {name}
      {has && (
        <span
          className="inline-block w-1.5 h-1.5 rounded-full"
          style={{ background: on ? "#0a0b0d" : color, opacity: on ? 0.55 : 1 }}
        />
      )}
    </button>
  );
}

// A verdict word derived from the agent's signal / risk rating.
const SIGNAL_META: Record<string, { label: string; color: string }> = {
  green: { label: "Strong fit", color: "#35d07f" },
  yellow: { label: "Partial fit", color: "#ffc24b" },
  red: { label: "Weak fit", color: "#e0704f" },
  low: { label: "Low risk", color: "#35d07f" },
  medium: { label: "Some risk", color: "#ffc24b" },
  high: { label: "High risk", color: "#e0704f" },
};

// Per-requirement status → badge label + color.
const REQ_STATUS: Record<string, { label: string; color: string }> = {
  meets: { label: "Meets", color: "#35d07f" },
  partial: { label: "Partial", color: "#ffc24b" },
  gap: { label: "Gap", color: "#ff5d5d" },
};

// Fields that carry the agent's core reasoning — this is the "why".
const WHY_KEYS = [
  "quick_take",
  "technical_summary",
  "rationale",
  "lift_rationale",
  "decision_summary",
  "strategic_value",
  "persona_read",
];

// Arrays framed as positives, shown up front.
const STRENGTH_LABELS: Record<string, string> = {
  objective_matches: "Where it lines up",
  capability_matches: "Capabilities that fit",
  capabilities_in_play: "Capabilities in play",
  reuse_as_is: "Reuse as-is",
  top_strengths: "Top strengths",
  covered_by_you: "Already covered by you",
  suggested_approach: "Suggested approach",
};

// Arrays framed as caveats — tucked into a collapsed section, not alarming.
const CAVEAT_LABELS: Record<string, string> = {
  gaps: "Gaps to close",
  capability_gaps: "Capability gaps",
  top_risks: "Watch-outs",
  risks: "Watch-outs",
  do_not_fake: "Don’t overclaim",
};

// Scalar prose fields worth a label.
const PROSE_LABELS: Record<string, string> = {
  customer_need: "Customer need",
  competition_landscape: "Competition",
  transition_path: "Transition path",
  notes: "Notes",
};

// Numeric scores rendered as small chips.
const SCORE_LABELS: Record<string, string> = {
  confidence: "confidence",
  technical_fit_score: "fit",
  win_probability: "win prob",
  fit_score: "fit",
};

/** Human-friendly result: verdict + a prominent "Why", strengths, then caveats. */
function SmartResult({ name, data }: { name: string; data: AgentResult }) {
  if (data?.raw) return <pre className="stream">{String(data.raw)}</pre>;
  const d = data as Record<string, unknown>;

  const signal = typeof d.signal === "string" ? (d.signal as string).toLowerCase() : "";
  const sig = SIGNAL_META[signal];
  const mapsBool = typeof d.maps_to_canari === "boolean" ? (d.maps_to_canari as boolean) : undefined;
  const recommendation = typeof d.recommendation === "string" ? (d.recommendation as string) : "";
  const risk = typeof d.technical_risk === "string" ? (d.technical_risk as string) : "";
  const riskMeta = risk ? SIGNAL_META[risk.toLowerCase()] : undefined;

  const whyKey = WHY_KEYS.find((k) => typeof d[k] === "string" && (d[k] as string).trim());
  const why = whyKey ? String(d[whyKey]) : "";

  // Requirement-by-requirement grounding: each need cites the SBIR text (evidence)
  // and where it appears, so gaps point at the exact part of the topic.
  const requirements = Array.isArray(d.requirements)
    ? (d.requirements as Record<string, unknown>[]).filter((r) => r && typeof r === "object")
    : [];

  const scoreChips = Object.entries(SCORE_LABELS)
    .filter(([k]) => typeof d[k] === "number")
    .map(([k, lbl]) => `${d[k]} ${lbl}`);

  const verdictLabel =
    sig?.label ||
    (mapsBool === true ? "Maps" : mapsBool === false ? "Doesn’t map" : "") ||
    recommendation;
  const verdictColor =
    sig?.color ||
    (mapsBool === true ? "#35d07f" : mapsBool === false ? "#e0704f" : COLORS[name as AgentName] || "#8a7bff");

  const handled = new Set<string>([
    "_role",
    "signal",
    "maps_to_canari",
    "recommendation",
    "technical_risk",
    "requirements",
    ...(whyKey ? [whyKey] : []),
    ...Object.keys(SCORE_LABELS),
  ]);
  // When we have grounded requirements, they subsume the flat match/gap lists.
  if (requirements.length) {
    ["objective_matches", "capability_matches", "gaps", "capability_gaps"].forEach((k) =>
      handled.add(k),
    );
  }

  const strengths = Object.entries(STRENGTH_LABELS)
    .map(([k, lbl]) => {
      handled.add(k);
      return { lbl, items: asList(d[k]) };
    })
    .filter((s) => s.items.length);

  const caveats = Object.entries(CAVEAT_LABELS)
    .map(([k, lbl]) => {
      handled.add(k);
      return { lbl, items: asList(d[k]) };
    })
    .filter((s) => s.items.length);

  const prose = Object.entries(PROSE_LABELS)
    .map(([k, lbl]) => {
      handled.add(k);
      const v = d[k];
      return { lbl, text: typeof v === "string" ? v.trim() : "" };
    })
    .filter((p) => p.text);

  // Keep anything we didn't explicitly place, but quietly at the end.
  const leftover = Object.entries(d).filter(
    ([k, v]) => !handled.has(k) && v != null && v !== "" && !(Array.isArray(v) && v.length === 0),
  );

  return (
    <div className="agent-why">
      {(verdictLabel || riskMeta || scoreChips.length > 0) && (
        <div className="row" style={{ gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          {verdictLabel && (
            <span
              className="tag"
              style={{
                background: `${verdictColor}22`,
                borderColor: verdictColor,
                color: verdictColor,
                fontWeight: 600,
              }}
            >
              {verdictLabel}
            </span>
          )}
          {riskMeta && (
            <span className="tag" style={{ borderColor: riskMeta.color, color: riskMeta.color }}>
              {riskMeta.label}
            </span>
          )}
          {scoreChips.map((c) => (
            <span key={c} className="meta">
              {c}
            </span>
          ))}
        </div>
      )}

      {why && (
        <p style={{ margin: "8px 0 0", fontSize: 14, lineHeight: 1.5 }}>
          <strong className="meta">Why: </strong>
          {why}
        </p>
      )}

      {requirements.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <div className="kv">Requirements ↔ {name} (from the SBIR)</div>
          <div className="req-list">
            {requirements.map((r, i) => {
              const status = String(r.status || "").toLowerCase();
              const sm = REQ_STATUS[status] || REQ_STATUS.partial;
              const evidence = typeof r.evidence === "string" ? r.evidence.trim() : "";
              const where = typeof r.where === "string" ? r.where.trim() : "";
              const need =
                (typeof r.need === "string" && r.need) ||
                (typeof r.point === "string" && r.point) ||
                "";
              return (
                <div key={i} className="req-row">
                  <span
                    className="req-badge"
                    style={{ background: `${sm.color}22`, borderColor: sm.color, color: sm.color }}
                  >
                    {sm.label}
                  </span>
                  <div className="req-body">
                    <div className="req-need">{String(need)}</div>
                    {evidence && (
                      <div className="req-evi">
                        “{evidence}”
                        {where && <span className="meta"> — {where}</span>}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {strengths.map((s) => (
        <div key={s.lbl} style={{ marginTop: 10 }}>
          <div className="kv">{s.lbl}</div>
          <ul className="tight">
            {s.items.map((x, i) => (
              <li key={i}>{x}</li>
            ))}
          </ul>
        </div>
      ))}

      {prose.map((p) => (
        <div key={p.lbl} style={{ marginTop: 10 }}>
          <div className="kv">{p.lbl}</div>
          <div style={{ fontSize: 13 }}>{p.text}</div>
        </div>
      ))}

      {caveats.length > 0 && (
        <details style={{ marginTop: 10 }}>
          <summary className="meta" style={{ cursor: "pointer" }}>
            Caveats ({caveats.reduce((n, c) => n + c.items.length, 0)})
          </summary>
          {caveats.map((c) => (
            <div key={c.lbl} style={{ marginTop: 6 }}>
              <div className="kv">{c.lbl}</div>
              <ul className="tight">
                {c.items.map((x, i) => (
                  <li key={i}>{x}</li>
                ))}
              </ul>
            </div>
          ))}
        </details>
      )}

      {leftover.map(([k, v]) => (
        <div key={k} style={{ marginTop: 10 }}>
          <div className="kv">{k.replace(/_/g, " ")}</div>
          {Array.isArray(v) ? (
            <ul className="tight">
              {asList(v).map((x, i) => (
                <li key={i}>{x}</li>
              ))}
            </ul>
          ) : (
            <div style={{ fontSize: 13 }}>
              {typeof v === "object" ? JSON.stringify(v) : String(v)}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function renderAgent(name: string, data: AgentResult) {
  // Cards self-wrap in their own boundary; SmartResult needs one here so a
  // malformed generic result can't white-screen the workspace.
  if (name === "Hewer") return <HewerCard rec={data as HewerResult} />;
  if (name === "Collier") return <TeamCard rec={data as TeamRecommendation} />;
  if (name === "Flint") return <FlintCard rec={data as FlintResult} />;
  return (
    <ErrorBoundary label={`${name}’s take`} resetKey={data}>
      <SmartResult name={name} data={data} />
    </ErrorBoundary>
  );
}

export default function AgentStepper({
  topic,
  seed,
}: {
  topic: Topic;
  seed?: Record<string, AgentResult> | null;
}) {
  const topicId = topic.topicId || topic.topicCode || "";
  const [results, setResults] = useState<Record<string, AgentResult>>(
    normalizeAgentResults(seed || {}),
  );
  const [busy, setBusy] = useState<string | null>(null);
  const [runningAll, setRunningAll] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<AgentName>("Canari");
  const [focus, setFocus] = useState<SliceId | ContributeId | null>("objective");
  const [mission, setMission] = useState("");
  const [products, setProducts] = useState("");
  const [scoutPhrases, setScoutPhrases] = useState<string[]>([]);
  const docRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (seed && Object.keys(seed).length) setResults(normalizeAgentResults(seed));
  }, [topicId, seed]);

  useEffect(() => {
    OrgApi.company()
      .then((c) => {
        setMission((c.mission || "").trim());
        setProducts((c.products || "").trim());
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!topicId) return;
    CatalogApi.topic(topicId)
      // Phrases come from a cached extract that occasionally carries raw HTML
      // fragments (e.g. a "<p>…</p>" keyword blob). Strip tags so the chips read
      // as plain text instead of showing literal markup.
      .then((t) => setScoutPhrases((t.phrases || []).map((p) => stripHtml(String(p))).filter(Boolean)))
      .catch(() => setScoutPhrases([]));
  }, [topicId]);

  const meta = { [topicId]: topicMeta(topic) };
  const spec = AGENTS[selected];

  const docs: Record<SliceId, string> = {
    component: [topic.component, topic.command, topic.program].filter(Boolean).join(" · "),
    objective: stripHtml(String(topic.objective || topic.topicObjective || "")),
    description: stripHtml(String(topic.description || topic.topicDescription || "")),
    keywords: stripHtml(String(topic.keywords || "")),
    scout_tags: scoutPhrases.join(" · "),
    company_mission: mission,
    products: products,
    me: "Flint / Hewer / Collier read users/{you}/me.md — the ME resume, not the company brochure.",
  };

  function scrollSlice(id: SliceId) {
    setFocus(id);
    const el = docRef.current?.querySelector(`[data-slice="${id}"]`);
    el?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  async function runOne(name: string, acc?: Record<string, AgentResult>) {
    const prior = acc || results;
    setBusy(name);
    setError("");
    setSelected(name as AgentName);
    try {
      const context =
        Object.keys(prior).length > 0 ? JSON.stringify(prior).slice(0, 6000) : undefined;
      const resp = await AnalysisApi.runAgent(topicId, name, meta, context, Boolean(prior[name]));
      const next = { ...prior, [name]: resp.result };
      setResults(next);
      return next;
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      setError(err?.response?.data?.detail || err.message || `${name} failed`);
      return prior;
    } finally {
      setBusy(null);
    }
  }

  async function runAll() {
    setRunningAll(true);
    setResults({});
    let acc: Record<string, AgentResult> = {};
    for (const name of ORDER) {
      acc = await runOne(name, acc);
    }
    setRunningAll(false);
  }

  const headings = productHeadings(products);
  const data = results[selected];
  const running = busy === selected;
  const lift = selected === "Hewer" ? (data as HewerResult)?.heavy_lift : undefined;

  return (
    <div className="card agent-workspace">
      <BidBrief
        topicId={topicId}
        topicsMeta={meta}
        onPick={(p) => setSelected(p as AgentName)}
      />

      <div className="mt-6 mb-1 flex items-center justify-between gap-4 border-t border-hair pt-5">
        <div>
          <h3 style={{ margin: 0 }}>Or work it voice-by-voice</h3>
          <div className="meta">
            Canari, Vein, and Davy each ask whether that product maps to this SBIR. They
            read the topic and our products.md — not a branch-mission gate.
          </div>
        </div>
        <button className="ghost" onClick={runAll} disabled={runningAll || busy != null}>
          {runningAll ? "Running all…" : "Run all in order"}
        </button>
      </div>

      {error && (
        <div className="card" style={{ borderColor: "var(--red)", marginTop: 8 }}>
          {error}
        </div>
      )}

      <div className="agent-workspace-grid">
        <div className="agent-doc" ref={docRef}>
          <div className="kv">Document they are parsing</div>
          {(Object.keys(SLICES) as SliceId[]).map((id) => {
            const cited = spec.reads.includes(id);
            const text = docs[id];
            if (!text && id !== "me" && id !== "scout_tags") return null;
            return (
              <button
                type="button"
                key={id}
                data-slice={id}
                className={`doc-slice ${cited ? "cited" : ""} ${focus === id ? "focus" : ""}`}
                onClick={() => scrollSlice(id)}
              >
                <div className="row spread">
                  <strong>{SLICES[id].label}</strong>
                  <span className="meta">{SLICES[id].source}</span>
                </div>
                {id === "products" && headings.length > 0 ? (
                  <div className="row" style={{ gap: 6, marginTop: 6, flexWrap: "wrap" }}>
                    {headings.map((h) => (
                      <span className="tag" key={h}>
                        {h}
                      </span>
                    ))}
                  </div>
                ) : id === "scout_tags" && scoutPhrases.length > 0 ? (
                  <div className="row" style={{ gap: 6, marginTop: 6, flexWrap: "wrap" }}>
                    {scoutPhrases.map((h) => (
                      <span className="tag" key={h}>
                        {h}
                      </span>
                    ))}
                  </div>
                ) : (
                  <p>{text.length > 420 ? `${text.slice(0, 420).trim()}…` : text || "—"}</p>
                )}
                {cited && <div className="slice-cite">{selected} is reading this</div>}
              </button>
            );
          })}
        </div>

        <div>
          <div className="voice-group" style={{ marginBottom: 10 }}>
            <div className="voice-group-label">Product voices · does this SBIR map?</div>
            <div className="voice-row">
              {PRODUCT_VOICES.map((name) => (
                <AgentPill
                  key={name}
                  name={name}
                  on={selected === name}
                  has={Boolean(results[name])}
                  onClick={() => {
                    setSelected(name);
                    setFocus(AGENTS[name].reads[0] || null);
                  }}
                />
              ))}
            </div>
            <div className="voice-group-label">Team voices · how would we bid it</div>
            <div className="voice-row">
              {TEAM_VOICES.map((name) => (
                <AgentPill
                  key={name}
                  name={name}
                  on={selected === name}
                  has={Boolean(results[name])}
                  onClick={() => {
                    setSelected(name);
                    setFocus(AGENTS[name].reads[0] || null);
                  }}
                />
              ))}
            </div>
          </div>

          <div
            className="card overflow-hidden"
            style={{
              background: "var(--surface-2)",
              borderColor:
                selected === "Hewer" && lift != null ? liftColor(lift) : COLORS[selected],
              boxShadow: `0 0 0 1px ${COLORS[selected]}22, 0 24px 60px -30px ${COLORS[selected]}55`,
            }}
          >
            <span
              aria-hidden
              className="absolute inset-x-0 top-0 h-[3px]"
              style={{ background: COLORS[selected] }}
            />
            <div className="row spread">
              <div className="row" style={{ gap: 8, alignItems: "center" }}>
                <span className="agent-dot" style={{ background: COLORS[selected] }} />
                <strong>{selected}</strong>
                <span className="meta">· {ROLES[selected]}</span>
              </div>
              <div className="row" style={{ gap: 6 }}>
                <button
                  className="ghost small"
                  onClick={() => setChatOpen(true)}
                  title={`Open a chat with ${selected}`}
                >
                  Discuss response
                </button>
                <button
                  className="small"
                  onClick={() => runOne(selected)}
                  disabled={running || runningAll}
                >
                  {running ? "Running…" : data ? "Re-run" : "Run"}
                </button>
              </div>
            </div>
            <p className="meta" style={{ margin: "8px 0 0" }}>
              {spec.because}
            </p>

            <div className="kv" style={{ marginTop: 10 }}>
              Reads
            </div>
            <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
              {spec.reads.map((id) => (
                <button
                  key={id}
                  type="button"
                  className={`cite-chip ${focus === id ? "on" : ""}`}
                  onClick={() => scrollSlice(id)}
                >
                  {SLICES[id].label}
                </button>
              ))}
            </div>

            <div className="kv" style={{ marginTop: 10 }}>
              Can contribute
            </div>
            <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
              {spec.contributes.map((id) => (
                <span key={id} className="contrib-chip open" title={CONTRIBUTES[id].hint}>
                  {CONTRIBUTES[id].label}
                </span>
              ))}
            </div>

            {data && (
              <div
                className="mt-4 pt-4"
                style={{ borderTop: "1px solid var(--border)" }}
              >
                {renderAgent(selected, data)}
              </div>
            )}
          </div>
        </div>
      </div>

      <ChatDrawer
        open={chatOpen}
        topicId={topicId}
        agent={selected}
        topicsMeta={meta}
        onClose={() => setChatOpen(false)}
      />
    </div>
  );
}

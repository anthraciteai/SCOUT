import { useEffect, useRef, useState } from "react";
import { AnalysisApi, CatalogApi, OrgApi } from "../api";
import type { AgentResult, HewerResult, Topic, TeamRecommendation } from "../types";
import { topicMeta } from "../pages/Browse";
import HewerCard, { liftColor } from "./HewerCard";
import TeamCard from "./TeamCard";
import FlintCard, { type FlintResult } from "./FlintCard";
import AgentChat from "./AgentChat";
import {
  AGENTS,
  COLORS,
  CONTRIBUTES,
  PRODUCT_VOICES,
  ROLES,
  SLICES,
  TEAM_VOICES,
  type AgentName,
  type ContributeId,
  type SliceId,
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
        boxShadow: `0 8px 22px -12px ${color}`,
      }
    : has
      ? { borderColor: color, color, background: `${color}12` }
      : {};
  return (
    <button className={on ? "small" : "ghost small"} style={style} onClick={onClick}>
      {name}
      {has ? " ·" : ""}
    </button>
  );
}

function GenericResult({ data }: { data: AgentResult }) {
  if (data?.raw) return <pre className="stream">{String(data.raw)}</pre>;
  return (
    <>
      {Object.entries(data)
        .filter(([k]) => k !== "_role")
        .map(([k, v]) => (
          <div key={k} style={{ marginBottom: 6 }}>
            <div className="kv">{k.replace(/_/g, " ")}</div>
            {Array.isArray(v) ? (
              <ul className="tight">
                {v.map((x, i) => (
                  <li key={i}>{typeof x === "object" ? JSON.stringify(x) : String(x)}</li>
                ))}
              </ul>
            ) : (
              <div style={{ fontSize: 13 }}>{String(v)}</div>
            )}
          </div>
        ))}
    </>
  );
}

function renderAgent(name: string, data: AgentResult) {
  if (name === "Hewer") return <HewerCard rec={data as HewerResult} />;
  if (name === "Collier") return <TeamCard rec={data as TeamRecommendation} />;
  if (name === "Flint") return <FlintCard rec={data as FlintResult} />;
  return <GenericResult data={data} />;
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
      .then((t) => setScoutPhrases(t.phrases || []))
      .catch(() => setScoutPhrases([]));
  }, [topicId]);

  const meta = { [topicId]: topicMeta(topic) };
  const spec = AGENTS[selected];

  const docs: Record<SliceId, string> = {
    component: [topic.component, topic.command, topic.program].filter(Boolean).join(" · "),
    objective: stripHtml(String(topic.objective || topic.topicObjective || "")),
    description: stripHtml(String(topic.description || topic.topicDescription || "")),
    keywords: String(topic.keywords || ""),
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
      <div className="row spread">
        <div>
          <h3 style={{ margin: 0 }}>Agent workspace</h3>
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
            className="card"
            style={{
              background: "var(--surface-2)",
              borderColor:
                selected === "Hewer" && lift != null ? liftColor(lift) : COLORS[selected],
              boxShadow: `0 0 0 1px ${COLORS[selected]}22, 0 24px 60px -30px ${COLORS[selected]}55`,
            }}
          >
            <div className="row spread">
              <div className="row" style={{ gap: 8, alignItems: "center" }}>
                <span className="agent-dot" style={{ background: COLORS[selected] }} />
                <strong>{selected}</strong>
                <span className="meta">· {ROLES[selected]}</span>
              </div>
              <button
                className="ghost small"
                onClick={() => runOne(selected)}
                disabled={running || runningAll}
              >
                {running ? "Running…" : data ? "Re-run" : "Run"}
              </button>
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

            {data && <div style={{ marginTop: 12 }}>{renderAgent(selected, data)}</div>}
            <div style={{ marginTop: 10 }}>
              <AgentChat topicId={topicId} agent={selected} topicsMeta={meta} compact />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

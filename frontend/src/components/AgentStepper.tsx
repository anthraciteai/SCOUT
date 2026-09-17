import { useState } from "react";
import { AnalysisApi } from "../api";
import type { AgentResult, HewerResult, Topic, TeamRecommendation } from "../types";
import { topicMeta } from "../pages/Browse";
import HewerCard, { liftColor } from "./HewerCard";
import TeamCard from "./TeamCard";
import FlintCard, { type FlintResult } from "./FlintCard";

const ORDER = ["Canari", "Vien", "Anthracite", "Collier", "Hewer", "Flint", "Davy"];

const ROLES: Record<string, string> = {
  Canari: "Fit / early warning",
  Vien: "Technical feasibility",
  Anthracite: "Business development",
  Collier: "Who to add (teaming)",
  Hewer: "Heavy lift + adaptation",
  Flint: "Creative — your tools, unexpected uses",
  Davy: "Capture strategy",
};

const COLORS: Record<string, string> = {
  Canari: "#f0c419",
  Vien: "#58a6ff",
  Anthracite: "#9aa4b2",
  Collier: "#c98b3a",
  Hewer: "#e0704f",
  Flint: "#e6c07b",
  Davy: "#3fb950",
};

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

export default function AgentStepper({ topic }: { topic: Topic }) {
  const topicId = topic.topicId || topic.topicCode || "";
  const [results, setResults] = useState<Record<string, AgentResult>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [runningAll, setRunningAll] = useState(false);
  const [error, setError] = useState("");

  const meta = { [topicId]: topicMeta(topic) };

  async function runOne(name: string, acc?: Record<string, AgentResult>) {
    const prior = acc || results;
    setBusy(name);
    setError("");
    try {
      // Give later agents (Hewer, Davy) the peer notes gathered so far.
      const context =
        Object.keys(prior).length > 0 ? JSON.stringify(prior).slice(0, 6000) : undefined;
      const resp = await AnalysisApi.runAgent(topicId, name, meta, context, Boolean(prior[name]));
      const next = { ...prior, [name]: resp.result };
      setResults(next);
      return next;
    } catch (e: any) {
      setError(e?.response?.data?.detail || e.message || `${name} failed`);
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

  return (
    <div className="card">
      <div className="row spread">
        <div>
          <h3 style={{ margin: 0 }}>Run through each agent</h3>
          <div className="meta">
            Step through the council one voice at a time, or run them all in order.
            Flint only sparks from tools on the resume marked ME.
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

      <div style={{ marginTop: 10 }}>
        {ORDER.map((name) => {
          const data = results[name];
          const running = busy === name;
          const lift = name === "Hewer" ? (data as HewerResult)?.heavy_lift : undefined;
          return (
            <div
              key={name}
              className="card"
              style={{
                marginBottom: 8,
                background: "var(--panel-2)",
                borderColor:
                  name === "Flint"
                    ? "#e6c07b"
                    : name === "Hewer" && lift != null
                      ? liftColor(lift)
                      : "var(--border)",
              }}
            >
              <div className="row spread">
                <div className="row" style={{ gap: 8, alignItems: "center" }}>
                  <span className="agent-dot" style={{ background: COLORS[name] }} />
                  <strong>{name}</strong>
                  <span className="meta">· {ROLES[name]}</span>
                </div>
                <button
                  className="ghost small"
                  onClick={() => runOne(name)}
                  disabled={running || runningAll}
                >
                  {running ? "Running…" : data ? "Re-run" : "Run"}
                </button>
              </div>
              {data && <div style={{ marginTop: 8 }}>{renderAgent(name, data)}</div>}
            </div>
          );
        })}
      </div>
    </div>
  );
}

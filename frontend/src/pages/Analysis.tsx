import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AnalysisApi, ResumeApi } from "../api";
import type { AnalysisRun, AgentResult, TeamRecommendation } from "../types";
import { useSelection } from "../selection";
import TeamCard from "../components/TeamCard";

const AGENT_COLORS: Record<string, string> = {
  Canari: "#f0c419",
  Vien: "#58a6ff",
  Anthracite: "#9aa4b2",
  Collier: "#c98b3a",
  Davy: "#3fb950",
};

function recClass(rec?: string) {
  const v = (rec || "").toUpperCase();
  if (v === "GO") return "green";
  if (v === "LEAN GO") return "green";
  if (v === "LEAN NO-GO") return "yellow";
  if (v === "NO-GO") return "red";
  return "muted";
}

function List({ items }: { items?: unknown }) {
  if (!Array.isArray(items) || items.length === 0) return <span className="meta">—</span>;
  return (
    <ul className="tight">
      {items.map((x, i) => (
        <li key={i}>{String(x)}</li>
      ))}
    </ul>
  );
}

function AgentCard({ name, data }: { name: string; data: AgentResult }) {
  const color = AGENT_COLORS[name] || "#8b949e";
  return (
    <div className="card">
      <div className="agent-head">
        <span className="agent-dot" style={{ background: color }} />
        <strong>{name}</strong>
        <span className="meta">· {data._role}</span>
      </div>
      {Object.entries(data)
        .filter(([k]) => k !== "_role")
        .map(([k, v]) => (
          <div key={k} style={{ marginBottom: 6 }}>
            <div className="kv">{k.replace(/_/g, " ")}</div>
            {Array.isArray(v) ? (
              <List items={v} />
            ) : (
              <div style={{ fontSize: 13 }}>{String(v)}</div>
            )}
          </div>
        ))}
    </div>
  );
}

export function CouncilCard({ run }: { run: AnalysisRun }) {
  const council = run.result?.council || {};
  const allAgents = run.result?.agents || {};
  const collier = allAgents["Collier"] as TeamRecommendation | undefined;
  const agents = Object.fromEntries(
    Object.entries(allAgents).filter(([k]) => k !== "Collier")
  );
  const score = council.fit_score ?? run.fit_score;
  const scoreColor =
    score == null ? "var(--muted)" : score >= 70 ? "var(--green)" : score >= 45 ? "var(--yellow)" : "var(--red)";

  return (
    <div className="card">
      <div className="row spread">
        <div>
          <Link to={`/topic/${run.topic_id}`} className="topic-title">
            {run.topic_code} — {run.title}
          </Link>
          <div className="meta">
            model: {run.model} · {new Date(run.created_at).toLocaleString()}
          </div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div className="score" style={{ color: scoreColor }}>
            {score != null ? Math.round(Number(score)) : "—"}
            <span style={{ fontSize: 14, color: "var(--muted)" }}> /100</span>
          </div>
          <span className={`pill ${recClass(council.recommendation)}`}>
            {council.recommendation || "N/A"}
          </span>
        </div>
      </div>

      {council.decision_summary && (
        <p style={{ fontSize: 14, lineHeight: 1.6 }}>{council.decision_summary}</p>
      )}
      {council.rationale && !council.decision_summary && (
        <p style={{ fontSize: 14, lineHeight: 1.6 }}>{council.rationale}</p>
      )}

      <div className="row" style={{ alignItems: "flex-start", gap: 24 }}>
        <div className="grow">
          <div className="kv">Top strengths</div>
          <List items={council.top_strengths} />
        </div>
        <div className="grow">
          <div className="kv">Top risks</div>
          <List items={council.top_risks} />
        </div>
      </div>

      {collier && (
        <div
          className="card"
          style={{ marginTop: 10, background: "var(--panel-2)", borderColor: "#c98b3a" }}
        >
          <TeamCard rec={collier} />
        </div>
      )}

      <details style={{ marginTop: 10 }}>
        <summary style={{ cursor: "pointer", color: "var(--accent)" }}>
          Agent breakdown ({Object.keys(agents).length})
        </summary>
        <div className="agent-grid" style={{ marginTop: 10 }}>
          {Object.entries(agents).map(([name, data]) => (
            <AgentCard key={name} name={name} data={data as AgentResult} />
          ))}
        </div>
      </details>
    </div>
  );
}

export default function Analysis() {
  const { selected, ids, toggle, clear } = useSelection();
  const [runs, setRuns] = useState<AnalysisRun[]>([]);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState("");
  const [hasResume, setHasResume] = useState<boolean | null>(null);
  const [history, setHistory] = useState<AnalysisRun[]>([]);

  useEffect(() => {
    ResumeApi.active().then((r) => setHasResume(Boolean(r && r.chars > 0)));
    AnalysisApi.list().then(setHistory).catch(() => {});
  }, []);

  async function run() {
    if (ids.length === 0) return;
    setRunning(true);
    setRuns([]);
    setProgress(`Running the council on ${ids.length} topic(s) with gpt-oss:20b… this can take a while.`);
    try {
      const results = await AnalysisApi.run(ids);
      setRuns(results);
      setProgress("");
    } catch (e: any) {
      setProgress(e?.response?.data?.detail || e.message || "Analysis failed");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div>
      <h1>Analysis</h1>
      <p className="subtitle">
        Run the agent council — <strong>Canari</strong> (fit), <strong>Vien</strong> (technical),{" "}
        <strong>Anthracite</strong> (business dev), <strong>Collier</strong> (who to add), and{" "}
        <strong>Davy</strong> (capture) — on selected topics against your resume, for a GO / NO-GO
        recommendation.
      </p>

      {hasResume === false && (
        <div className="card" style={{ borderColor: "var(--yellow)" }}>
          No active resume found. Add your capabilities in{" "}
          <Link to="/settings">Settings</Link> so the agents can judge fit.
        </div>
      )}

      <div className="card">
        <div className="row spread">
          <strong>Selected topics ({ids.length})</strong>
          {ids.length > 0 && (
            <button className="ghost small" onClick={clear}>
              Clear
            </button>
          )}
        </div>
        {ids.length === 0 && (
          <div className="meta" style={{ marginTop: 8 }}>
            No topics selected. Go to <Link to="/">Browse Topics</Link> and check some.
          </div>
        )}
        {ids.map((tid) => {
          const t = selected[tid];
          return (
            <div key={tid} className="row spread" style={{ padding: "6px 0" }}>
              <span style={{ fontSize: 14 }}>
                {t.topicCode || t.finalTopicCode} — {t.topicTitle || t.title}
              </span>
              <button className="ghost small" onClick={() => toggle(t)}>
                remove
              </button>
            </div>
          );
        })}
        {ids.length > 0 && (
          <div style={{ marginTop: 12 }}>
            <button onClick={run} disabled={running}>
              {running ? "Analyzing…" : "Run Analysis"}
            </button>
          </div>
        )}
      </div>

      {progress && <div className="card spinner">{progress}</div>}

      {runs.map((r) => (
        <CouncilCard key={r.id} run={r} />
      ))}

      {runs.length === 0 && history.length > 0 && (
        <>
          <h2>Recent analyses</h2>
          <table>
            <thead>
              <tr>
                <th>Topic</th>
                <th>Score</th>
                <th>Rec</th>
                <th>When</th>
              </tr>
            </thead>
            <tbody>
              {history.slice(0, 25).map((h) => (
                <tr key={h.id}>
                  <td>
                    <Link to={`/topic/${h.topic_id}`}>
                      {h.topic_code} — {h.title}
                    </Link>
                  </td>
                  <td>{h.fit_score != null ? Math.round(h.fit_score) : "—"}</td>
                  <td>
                    <span className={`pill ${recClass(h.recommendation)}`}>
                      {h.recommendation || "—"}
                    </span>
                  </td>
                  <td className="meta">{new Date(h.created_at).toLocaleDateString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}

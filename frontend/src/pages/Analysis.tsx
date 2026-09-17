import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AnalysisApi, ResumeApi } from "../api";
import type { AnalysisRun, AgentResult, TeamRecommendation, HewerResult } from "../types";
import { useSelection } from "../selection";
import TeamCard from "../components/TeamCard";
import HewerCard, { liftColor, liftLabel } from "../components/HewerCard";
import FlintCard, { type FlintResult } from "../components/FlintCard";
import { topicMeta } from "./Browse";

const AGENT_COLORS: Record<string, string> = {
  Canari: "#f0c419",
  Vien: "#58a6ff",
  Anthracite: "#9aa4b2",
  Collier: "#c98b3a",
  Hewer: "#e0704f",
  Flint: "#e6c07b",
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
  const hewer = allAgents["Hewer"] as HewerResult | undefined;
  const flint = allAgents["Flint"] as FlintResult | undefined;
  const agents = Object.fromEntries(
    Object.entries(allAgents).filter(([k]) => k !== "Collier" && k !== "Hewer" && k !== "Flint")
  );
  const score = council.fit_score ?? run.fit_score;
  const scoreColor =
    score == null ? "var(--muted)" : score >= 70 ? "var(--green)" : score >= 45 ? "var(--yellow)" : "var(--red)";
  const lift = hewer?.heavy_lift ?? run.heavy_lift;

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
        <div className="row" style={{ gap: 20, alignItems: "flex-start" }}>
          <div style={{ textAlign: "right" }}>
            <div className="score" style={{ color: scoreColor }}>
              {score != null ? Math.round(Number(score)) : "—"}
              <span style={{ fontSize: 14, color: "var(--muted)" }}> /100</span>
            </div>
            <span className={`pill ${recClass(council.recommendation)}`}>
              {council.recommendation || "N/A"}
            </span>
            <div className="meta" style={{ fontSize: 11 }}>fit</div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div className="score" style={{ color: liftColor(lift) }}>
              {lift != null ? Number(lift) : "—"}
              <span style={{ fontSize: 14, color: "var(--muted)" }}> /10</span>
            </div>
            <span className="pill" style={{ borderColor: liftColor(lift), color: liftColor(lift) }}>
              {liftLabel(lift)}
            </span>
            <div className="meta" style={{ fontSize: 11 }}>heavy lift</div>
          </div>
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

      {hewer && (
        <div
          className="card"
          style={{ marginTop: 10, background: "var(--panel-2)", borderColor: liftColor(lift) }}
        >
          <HewerCard rec={hewer} />
        </div>
      )}

      {flint && (
        <div
          className="card"
          style={{ marginTop: 10, background: "var(--panel-2)", borderColor: "#e6c07b" }}
        >
          <FlintCard rec={flint} />
        </div>
      )}

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
  const [hasMe, setHasMe] = useState<boolean | null>(null);
  const [history, setHistory] = useState<AnalysisRun[]>([]);

  useEffect(() => {
    ResumeApi.active().then((r) => setHasResume(Boolean(r && r.chars > 0)));
    ResumeApi.me().then((r) => setHasMe(Boolean(r && r.chars > 0)));
    AnalysisApi.list().then(setHistory).catch(() => {});
  }, []);

  async function run() {
    if (ids.length === 0) return;
    setRunning(true);
    setRuns([]);
    setProgress(`Running the council on ${ids.length} topic(s)… this can take a while.`);
    try {
      const meta: Record<string, ReturnType<typeof topicMeta>> = {};
      for (const tid of ids) meta[tid] = topicMeta(selected[tid]);
      const results = await AnalysisApi.run(ids, meta, undefined, false);
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
      <h1>Council</h1>
      <p className="subtitle">
        Optional deep pass — <strong>Canari</strong>, <strong>Vien</strong>,{" "}
        <strong>Anthracite</strong>, <strong>Collier</strong>, <strong>Hewer</strong>,{" "}
        <strong>Flint</strong> (creative — your tools), and <strong>Davy</strong>. Inbox ranking
        does not run this automatically.
      </p>

      {hasResume === false && (
        <div className="card" style={{ borderColor: "var(--yellow)" }}>
          No active resume found. Add your capabilities in{" "}
          <Link to="/profile">Profile</Link> so the agents can judge fit.
        </div>
      )}
      {hasResume && hasMe === false && (
        <div className="card" style={{ borderColor: "#e6c07b" }}>
          Flint needs a resume marked <strong>ME</strong> or it will only spark from the
          company pack. Upload yours on <Link to="/profile">Profile</Link>.
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
            No topics selected. Go to <Link to="/">Inbox</Link> or{" "}
            <Link to="/browse">Browse</Link> and pick some.
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
                <th>Lift</th>
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
                  <td style={{ color: liftColor(h.heavy_lift) }}>
                    {h.heavy_lift != null ? h.heavy_lift : "—"}
                  </td>
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

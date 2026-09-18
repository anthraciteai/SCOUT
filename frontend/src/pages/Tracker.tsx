import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AnalysisApi, TrackerApi } from "../api";
import type { AnalysisRun, TrackedTopic } from "../types";
import { liftColor, liftLabel } from "../components/HewerCard";
import { useToast } from "../toast";

const OUTCOMES = ["", "pending", "awarded", "not_selected", "withdrawn"];

type Verdict = {
  fit_score?: number;
  heavy_lift?: number;
  recommendation?: string;
};

function recClass(rec?: string) {
  const v = (rec || "").toUpperCase();
  if (v === "GO" || v === "LEAN GO") return "green";
  if (v === "LEAN NO-GO") return "yellow";
  if (v === "NO-GO") return "red";
  return "muted";
}

function metaOf(r: TrackedTopic) {
  return {
    [r.topic_id]: {
      topic_code: r.topic_code,
      title: r.title,
      component: r.component,
      program: r.program,
      topic_status: r.topic_status,
    },
  };
}

export default function Tracker() {
  const [rows, setRows] = useState<TrackedTopic[]>([]);
  const [stages, setStages] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [verdicts, setVerdicts] = useState<Record<string, Verdict>>({});
  const [analyzing, setAnalyzing] = useState<string | null>(null);
  const toast = useToast();

  async function load() {
    setLoading(true);
    const [r, s] = await Promise.all([TrackerApi.list(), TrackerApi.stages()]);
    setRows(r);
    setStages(s);
    try {
      const runs = await AnalysisApi.list();
      const latest: Record<string, Verdict> = {};
      // list() is newest-first; keep the first (latest) per topic.
      for (const run of runs as AnalysisRun[]) {
        if (!latest[run.topic_id]) {
          latest[run.topic_id] = {
            fit_score: run.fit_score,
            heavy_lift: run.heavy_lift,
            recommendation: run.recommendation,
          };
        }
      }
      setVerdicts(latest);
    } catch {
      /* ignore */
    }
    setLoading(false);
  }

  async function analyze(r: TrackedTopic) {
    setAnalyzing(r.topic_id);
    toast("Running the council… this can take a few minutes.");
    try {
      const runs = await AnalysisApi.run([r.topic_id], metaOf(r));
      const run = runs[0];
      setVerdicts((prev) => ({
        ...prev,
        [r.topic_id]: {
          fit_score: run.fit_score,
          heavy_lift: run.heavy_lift,
          recommendation: run.recommendation,
        },
      }));
      toast("Analysis complete", "success");
    } catch (e: any) {
      toast(e?.response?.data?.detail || e?.message || "Analysis failed", "error");
    } finally {
      setAnalyzing(null);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function update(id: number, body: { status?: string; notes?: string; outcome?: string }) {
    const updated = await TrackerApi.update(id, body);
    setRows((prev) => prev.map((r) => (r.id === id ? updated : r)));
  }

  async function remove(id: number) {
    if (!confirm("Remove from tracker?")) return;
    await TrackerApi.remove(id);
    setRows((prev) => prev.filter((r) => r.id !== id));
  }

  if (loading) return <div className="spinner">Loading tracker…</div>;

  return (
    <div>
      <h1>Pipeline</h1>
      <p className="subtitle">
        Your bid pipeline. Move topics through stages and record outcomes. Lost bids can be improved
        by uploading the debrief in the <Link to="/debriefs">Debriefs</Link> tab.
      </p>

      {rows.length === 0 && (
        <div className="empty">
          Nothing tracked yet. Add topics from <Link to="/">Inbox</Link> or{" "}
          <Link to="/browse">Browse</Link>.
        </div>
      )}

      {rows.map((r) => {
        const v = verdicts[r.topic_id];
        return (
        <div className="card" key={r.id}>
          <div className="row spread">
            <Link to={`/topic/${r.topic_id}`} className="topic-title">
              {r.topic_code} — {r.title}
            </Link>
            <div className="row">
              <Link to={`/desk/${r.topic_id}`} className="meta">
                group desk →
              </Link>
              <button className="ghost small danger" onClick={() => remove(r.id)}>
                remove
              </button>
            </div>
          </div>
          <div className="meta" style={{ margin: "4px 0 10px" }}>
            {r.component} · {r.program} · {r.topic_status}
          </div>

          <div
            className="row spread"
            style={{
              alignItems: "center",
              background: "var(--panel-2)",
              borderRadius: 8,
              padding: "8px 12px",
              marginBottom: 10,
            }}
          >
            <div className="row" style={{ gap: 16, alignItems: "center", flexWrap: "wrap" }}>
              {v ? (
                <>
                  <span>
                    <span className="kv">Fit</span>{" "}
                    <strong>{v.fit_score != null ? Math.round(v.fit_score) : "—"}</strong>
                    <span className="meta">/100</span>
                  </span>
                  <span className={`pill ${recClass(v.recommendation)}`}>
                    {v.recommendation || "—"}
                  </span>
                  <span>
                    <span className="kv">Heavy lift</span>{" "}
                    <strong style={{ color: liftColor(v.heavy_lift) }}>
                      {v.heavy_lift != null ? v.heavy_lift : "—"}
                    </strong>
                    <span className="meta">/10</span>
                  </span>
                  <span className="pill" style={{ borderColor: liftColor(v.heavy_lift), color: liftColor(v.heavy_lift) }}>
                    {liftLabel(v.heavy_lift)}
                  </span>
                  <Link to={`/topic/${r.topic_id}`} className="meta">
                    view full council →
                  </Link>
                </>
              ) : (
                <span className="meta">Not analyzed yet.</span>
              )}
            </div>
            <button
              className="small"
              onClick={() => analyze(r)}
              disabled={analyzing === r.topic_id}
            >
              {analyzing === r.topic_id ? "Analyzing…" : v ? "Re-run analysis" : "Run analysis"}
            </button>
          </div>

          <div className="row">
            <label className="kv">
              Stage&nbsp;
              <select value={r.status} onChange={(e) => update(r.id, { status: e.target.value })}>
                {stages.map((s) => (
                  <option key={s} value={s}>
                    {s.replace(/_/g, " ")}
                  </option>
                ))}
              </select>
            </label>
            <label className="kv">
              Outcome&nbsp;
              <select
                value={r.outcome || ""}
                onChange={(e) => update(r.id, { outcome: e.target.value })}
              >
                {OUTCOMES.map((o) => (
                  <option key={o} value={o}>
                    {o ? o.replace(/_/g, " ") : "—"}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <textarea
            style={{ marginTop: 10 }}
            rows={2}
            defaultValue={r.notes}
            placeholder="Notes…"
            onBlur={(e) => {
              if (e.target.value !== r.notes) update(r.id, { notes: e.target.value });
            }}
          />
        </div>
        );
      })}
    </div>
  );
}

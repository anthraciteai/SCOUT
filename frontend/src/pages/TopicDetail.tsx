import { useEffect, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { AnalysisApi, TopicsApi, TrackerApi } from "../api";
import type { AnalysisRun, Topic } from "../types";
import { topicCode, topicTitle, statusClass, topicMeta } from "./Browse";
import { CouncilCard } from "./Analysis";

function stripHtml(s?: string) {
  if (!s) return "";
  return s.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
}

export default function TopicDetail() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const summary = (location.state as { topic?: Topic } | null)?.topic;
  const [topic, setTopic] = useState<Topic | null>(null);
  const [questions, setQuestions] = useState<any[]>([]);
  const [run, setRun] = useState<AnalysisRun | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const t = await TopicsApi.detail(id);
        const nested = (t as any)?.topic ? { ...(t as any), ...(t as any).topic } : t;
        // /details lacks title/code/status; merge in the summary if we have it.
        const merged = summary ? { ...summary, ...nested } : nested;
        setTopic(merged);
      } catch {
        // No details (e.g. very old topic) - fall back to summary if present.
        setTopic(summary || null);
      }
      try {
        const q = await TopicsApi.questions(id);
        setQuestions(Array.isArray(q) ? q : (q as any)?.data || []);
      } catch {
        setQuestions([]);
      }
      try {
        setRun(await AnalysisApi.latestForTopic(id));
      } catch {
        setRun(null);
      }
      setLoading(false);
    })();
  }, [id]);

  async function analyze() {
    setAnalyzing(true);
    try {
      const meta = topic ? { [id]: topicMeta(topic) } : undefined;
      const runs = await AnalysisApi.run([id], meta);
      setRun(runs[0]);
    } finally {
      setAnalyzing(false);
    }
  }

  async function track() {
    if (!topic) return;
    await TrackerApi.track({
      topic_id: id,
      topic_code: topicCode(topic),
      title: topicTitle(topic),
      component: topic.component,
      program: topic.program,
      topic_status: topic.topicStatus,
      raw: topic,
    });
    alert("Added to tracker");
  }

  if (loading) return <div className="spinner">Loading topic…</div>;
  if (!topic) return <div className="empty">Topic not found.</div>;

  const objective = stripHtml(topic.objective || (topic as any).topicObjective);
  const description = stripHtml(topic.description || (topic as any).topicDescription);

  return (
    <div>
      <button className="ghost small" onClick={() => navigate(-1)}>
        ← Back
      </button>
      <h1 style={{ marginTop: 12 }}>
        {topicCode(topic)} — {topicTitle(topic)}
      </h1>
      <div className="row" style={{ marginBottom: 12 }}>
        <span className={`pill ${statusClass(topic.topicStatus)}`}>{topic.topicStatus}</span>
        <span className="tag">{topic.component}</span>
        <span className="tag">{topic.program}</span>
        <span className="meta">{topic.solicitationTitle}</span>
      </div>

      <div className="row" style={{ marginBottom: 16 }}>
        <button onClick={analyze} disabled={analyzing}>
          {analyzing ? "Running council…" : run ? "Re-run Analysis" : "Run Agent Analysis"}
        </button>
        <button className="ghost" onClick={track}>
          Track
        </button>
        <a className="tag" href={TopicsApi.downloadUrl(id, "PDF")} target="_blank" rel="noreferrer">
          Download PDF
        </a>
        <a className="tag" href={TopicsApi.downloadUrl(id, "DOCX")} target="_blank" rel="noreferrer">
          Download DOCX
        </a>
      </div>

      {run?.result && (
        <div style={{ marginBottom: 16 }}>
          <CouncilCard run={run} />
        </div>
      )}

      {objective && (
        <div className="card">
          <h3>Objective</h3>
          <p style={{ fontSize: 14, lineHeight: 1.6 }}>{objective}</p>
        </div>
      )}
      {description && (
        <div className="card">
          <h3>Description</h3>
          <p style={{ fontSize: 14, lineHeight: 1.6, whiteSpace: "pre-wrap" }}>{description}</p>
        </div>
      )}

      <div className="card">
        <h3>Q&amp;A ({questions.length})</h3>
        {questions.length === 0 && <div className="meta">No published questions.</div>}
        {questions.map((q: any, i: number) => (
          <div key={i} style={{ borderBottom: "1px solid var(--border)", padding: "8px 0" }}>
            <div style={{ fontSize: 14 }}>
              <strong>Q:</strong> {q.question || q.questionText || q.text}
            </div>
            {(q.answer || q.answerText) && (
              <div style={{ fontSize: 14, color: "var(--muted)", marginTop: 4 }}>
                <strong>A:</strong> {q.answer || q.answerText}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

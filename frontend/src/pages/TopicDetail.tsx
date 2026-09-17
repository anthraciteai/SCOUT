import { useEffect, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { AnalysisApi, ProposalsApi, TopicsApi, TrackerApi } from "../api";
import type { AnalysisRun, Topic, TrackedTopic } from "../types";
import { topicCode, topicTitle, statusClass, topicMeta, TopicDates } from "./Browse";
import { CouncilCard } from "./Analysis";
import AgentStepper from "../components/AgentStepper";
import OrgDesk from "../components/OrgDesk";
import { useToast } from "../toast";
import { sanitizeHtml, parseAnswer } from "../util/html";

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
  const [view, setView] = useState<"pdf" | "text">("pdf");
  const [tracked, setTracked] = useState<TrackedTopic | null>(null);
  const [stages, setStages] = useState<string[]>([]);
  const toast = useToast();

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
      try {
        const [list, st] = await Promise.all([TrackerApi.list(), TrackerApi.stages()]);
        setTracked(list.find((t) => t.topic_id === id) || null);
        setStages(st);
      } catch {
        /* ignore */
      }
      setLoading(false);
    })();
  }, [id]);

  async function analyze() {
    setAnalyzing(true);
    try {
      const meta = topic ? { [id]: topicMeta(topic) } : undefined;
      const runs = await AnalysisApi.run([id], meta, undefined, Boolean(run));
      setRun(runs[0]);
    } finally {
      setAnalyzing(false);
    }
  }

  async function track(status: string, label: string) {
    if (!topic) return;
    const t = await TrackerApi.track({
      topic_id: id,
      topic_code: topicCode(topic),
      title: topicTitle(topic),
      component: topic.component,
      program: topic.program,
      topic_status: topic.topicStatus,
      status,
      raw: topic,
    });
    // track() returns the existing row if already tracked; enforce requested status.
    const updated = t.status === status ? t : await TrackerApi.update(t.id, { status });
    setTracked(updated);
    toast(label);
  }

  async function updateTracked(body: { status?: string; outcome?: string; notes?: string }) {
    if (!tracked) return;
    const updated = await TrackerApi.update(tracked.id, body);
    setTracked(updated);
    toast("Updated");
  }

  async function createLinkedProposal() {
    if (!topic) return;
    const p = await ProposalsApi.create({
      title: `${topicCode(topic)} — Proposal`,
      topic_id: id,
      topic_code: topicCode(topic),
      status: "submitted",
    });
    toast("Proposal draft created & linked");
    navigate("/proposals", { state: { openProposalId: p.id } });
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
      <div className="row" style={{ marginBottom: 8 }}>
        {topic.topicStatus && (
          <span className={`pill ${statusClass(topic.topicStatus)}`}>{topic.topicStatus}</span>
        )}
        {topic.component && <span className="tag">{topic.component}</span>}
        {topic.program && <span className="tag">{topic.program}</span>}
        {topic.solicitationTitle && <span className="meta">{topic.solicitationTitle}</span>}
      </div>
      <div className="card" style={{ padding: "10px 14px", marginBottom: 12 }}>
        <TopicDates t={topic} />
      </div>

      <div className="row" style={{ marginBottom: 16 }}>
        <button onClick={analyze} disabled={analyzing}>
          {analyzing ? "Running council…" : run ? "Re-run Analysis" : "Run Agent Analysis"}
        </button>
        <a className="tag" href={TopicsApi.downloadUrl(id, "PDF")} target="_blank" rel="noreferrer">
          Download PDF
        </a>
        <a className="tag" href={TopicsApi.downloadUrl(id, "DOCX")} target="_blank" rel="noreferrer">
          Download DOCX
        </a>
      </div>

      {/* One-shot bid workflow */}
      <div className="card" style={{ borderColor: tracked ? "var(--green)" : "var(--border)" }}>
        {!tracked ? (
          <div className="row spread">
            <div>
              <strong>Pursuing this topic?</strong>
              <div className="meta">Record it in one click — no need to jump to the Tracker.</div>
            </div>
            <div className="row">
              <button onClick={() => track("submitted", "Recorded your bid")}>I bid on this</button>
              <button className="ghost" onClick={() => track("watching", "Watching topic")}>
                Watch
              </button>
            </div>
          </div>
        ) : (
          <div>
            <div className="row spread">
              <strong>Your bid</strong>
              <span className="meta">In your pipeline</span>
            </div>
            <div className="row" style={{ marginTop: 8 }}>
              <label className="kv">
                Stage&nbsp;
                <select
                  value={tracked.status}
                  onChange={(e) => updateTracked({ status: e.target.value })}
                >
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
                  value={tracked.outcome || ""}
                  onChange={(e) => updateTracked({ outcome: e.target.value })}
                >
                  {["", "pending", "awarded", "not_selected", "withdrawn"].map((o) => (
                    <option key={o} value={o}>
                      {o ? o.replace(/_/g, " ") : "—"}
                    </option>
                  ))}
                </select>
              </label>
              <button className="ghost" onClick={createLinkedProposal}>
                Create linked proposal
              </button>
            </div>
            <textarea
              style={{ marginTop: 10 }}
              rows={2}
              defaultValue={tracked.notes}
              placeholder="Bid notes…"
              onBlur={(e) => {
                if (e.target.value !== tracked.notes) updateTracked({ notes: e.target.value });
              }}
            />
          </div>
        )}
      </div>

      {run?.result && (
        <div style={{ marginBottom: 16 }}>
          {run.cached && (
            <div className="meta" style={{ marginBottom: 6 }}>
              Serving cached council from the vault — Re-run Analysis to regenerate.
            </div>
          )}
          <CouncilCard run={run} />
        </div>
      )}

      <div style={{ marginBottom: 16 }}>
        <OrgDesk topicId={id} title={topicTitle(topic)} topicCode={topicCode(topic)} />
      </div>

      <div style={{ marginBottom: 16 }}>
        <AgentStepper topic={topic} />
      </div>

      <div className="card">
        <div className="row spread">
          <h3 style={{ margin: 0 }}>Topic content</h3>
          <div className="row" style={{ gap: 6 }}>
            <button
              className={view === "pdf" ? "small" : "ghost small"}
              onClick={() => setView("pdf")}
            >
              PDF
            </button>
            <button
              className={view === "text" ? "small" : "ghost small"}
              onClick={() => setView("text")}
            >
              Text
            </button>
          </div>
        </div>

        {view === "pdf" ? (
          <div style={{ marginTop: 10 }}>
            <iframe
              title="Topic PDF"
              src={TopicsApi.downloadUrl(id, "PDF", true)}
              style={{
                width: "100%",
                height: "80vh",
                border: "1px solid var(--border)",
                borderRadius: 8,
                background: "#fff",
              }}
            />
            <div className="meta" style={{ marginTop: 6 }}>
              If the PDF doesn't render,{" "}
              <a href={TopicsApi.downloadUrl(id, "PDF", true)} target="_blank" rel="noreferrer">
                open it in a new tab
              </a>
              .
            </div>
          </div>
        ) : (
          <div style={{ marginTop: 10 }}>
            {objective && (
              <>
                <h3>Objective</h3>
                <p style={{ fontSize: 14, lineHeight: 1.6 }}>{objective}</p>
              </>
            )}
            {description && (
              <>
                <h3>Description</h3>
                <p style={{ fontSize: 14, lineHeight: 1.6, whiteSpace: "pre-wrap" }}>
                  {description}
                </p>
              </>
            )}
            {!objective && !description && (
              <div className="meta">No text content available — try the PDF.</div>
            )}
          </div>
        )}
      </div>

      <div className="card">
        <h3>Q&amp;A ({questions.length})</h3>
        {questions.length === 0 && <div className="meta">No published questions.</div>}
        {questions.map((q: any, i: number) => {
          const answers: string[] = (q.answers || [])
            .map((a: any) => parseAnswer(a.answer))
            .filter((s: string) => s && s.trim());
          return (
            <div key={q.questionId ?? i} style={{ borderBottom: "1px solid var(--border)", padding: "10px 0" }}>
              <div className="row" style={{ gap: 8, marginBottom: 4 }}>
                <span className="tag">Q{q.questionNo ?? i + 1}</span>
                {q.questionStatusDisplay && (
                  <span className="meta">{q.questionStatusDisplay}</span>
                )}
              </div>
              <div
                className="rich"
                style={{ fontSize: 14 }}
                dangerouslySetInnerHTML={{
                  __html: sanitizeHtml(q.question || q.questionText || q.text || ""),
                }}
              />
              {answers.length > 0 ? (
                answers.map((ans, j) => (
                  <div
                    key={j}
                    className="rich"
                    style={{
                      fontSize: 14,
                      marginTop: 6,
                      paddingLeft: 12,
                      borderLeft: "3px solid var(--green)",
                    }}
                  >
                    <div className="kv" style={{ color: "var(--green)" }}>Answer</div>
                    <div dangerouslySetInnerHTML={{ __html: sanitizeHtml(ans) }} />
                  </div>
                ))
              ) : (
                <div className="meta" style={{ marginTop: 4 }}>
                  Not yet answered.
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

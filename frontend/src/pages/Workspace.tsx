import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import {
  OrgApi,
  TopicIntelApi,
  TopicsApi,
  streamProposalFeedback,
  type TopicFit,
  type TopicSummary,
  type TopicText,
} from "../api";
import type { Topic } from "../types";
import { topicMeta, statusClass, TopicDates } from "./Browse";
import { useToast } from "../toast";
import EvidenceReader from "../components/EvidenceReader";

type Tab = "summary" | "reader" | "fit" | "write" | "source";

function recClass(rec?: string) {
  const v = (rec || "").toUpperCase();
  if (v === "GO" || v === "LEAN GO") return "green";
  if (v === "LEAN NO-GO") return "yellow";
  if (v === "NO-GO") return "red";
  return "muted";
}

function fitClass(n: number) {
  if (n >= 70) return "green";
  if (n >= 45) return "yellow";
  return "muted";
}

export default function Workspace() {
  const { id = "" } = useParams();
  const location = useLocation();
  const toast = useToast();

  const stateTopic = (location.state as { topic?: Topic } | null)?.topic;
  const [topic, setTopic] = useState<Topic | null>(stateTopic || null);
  const [tab, setTab] = useState<Tab>("summary");

  const [summary, setSummary] = useState<TopicSummary | null>(null);
  const [summaryBusy, setSummaryBusy] = useState(false);
  const [fit, setFit] = useState<TopicFit | null>(null);
  const [fitBusy, setFitBusy] = useState(false);
  const [raw, setRaw] = useState<TopicText | null>(null);
  const [rawBusy, setRawBusy] = useState(false);
  const [err, setErr] = useState("");

  // Write tab
  const [draft, setDraft] = useState("");
  const [feedback, setFeedback] = useState("");
  const [feedbackBusy, setFeedbackBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const meta = useMemo(() => (topic ? topicMeta(topic) : null), [topic]);

  useEffect(() => {
    if (!topic) {
      TopicsApi.detail(id)
        .then(setTopic)
        .catch(() => {});
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function doSummary(force = false) {
    setSummaryBusy(true);
    setErr("");
    try {
      const s = await TopicIntelApi.summarize(id, force);
      setSummary(s);
    } catch (e: any) {
      setErr(e?.response?.data?.detail || e.message || "Summary failed");
    } finally {
      setSummaryBusy(false);
    }
  }

  async function doFit(force = false) {
    setFitBusy(true);
    setErr("");
    try {
      const f = await TopicIntelApi.fit(id, force);
      setFit(f);
      if (!summary) {
        // fit guarantees a summary was built — pull the cheap cached copy.
        TopicIntelApi.summarize(id).then(setSummary).catch(() => {});
      }
    } catch (e: any) {
      setErr(e?.response?.data?.detail || e.message || "Fit scoring failed");
    } finally {
      setFitBusy(false);
    }
  }

  async function doRaw(force = false) {
    setRawBusy(true);
    setErr("");
    try {
      const t = await TopicIntelApi.text(id, force);
      setRaw(t);
    } catch (e: any) {
      setErr(e?.response?.data?.detail || e.message || "Text extraction failed");
    } finally {
      setRawBusy(false);
    }
  }

  function seedDraft() {
    if (!summary) return;
    const lines: string[] = [];
    lines.push(`# Proposal — ${meta?.topic_code || id}`);
    lines.push(`\n## Problem\n${summary.problem || summary.objective}`);
    lines.push(`\n## Our approach\n_Describe how our products/experience solve this._`);
    lines.push("\n## How we meet each requirement");
    for (const r of summary.requirements) {
      lines.push(`\n### ${r.need}\n> ${r.evidence}\n\n_Our response: _`);
    }
    setDraft((prev) => (prev.trim() ? prev : lines.join("\n")));
    setTab("write");
  }

  async function runFeedback() {
    if (!draft.trim()) {
      toast("Write a draft first", "error");
      return;
    }
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;
    setFeedback("");
    setFeedbackBusy(true);
    try {
      await streamProposalFeedback(
        { content: draft, topic_id: id },
        (chunk) => setFeedback((prev) => prev + chunk),
        ac.signal
      );
    } catch (e: any) {
      if (e?.name !== "AbortError") toast(e.message || "Feedback failed", "error");
    } finally {
      setFeedbackBusy(false);
    }
  }

  async function saveToDesk() {
    if (!draft.trim()) {
      toast("Nothing to save", "error");
      return;
    }
    setSaving(true);
    try {
      await OrgApi.grant(id, meta ? (meta as Record<string, string>) : { topic_id: id });
      await OrgApi.saveShared(id, "proposal.md", draft);
      toast("Saved to Group desk → proposal.md");
    } catch (e: any) {
      toast(e?.response?.data?.detail || e.message || "Save failed", "error");
    } finally {
      setSaving(false);
    }
  }

  // The reader needs both the summary (for requirements + evidence) and the
  // full OCR text; pull the text lazily the first time the tab is opened.
  useEffect(() => {
    if (tab === "reader" && summary && !raw && !rawBusy) {
      void doRaw(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, summary, raw, rawBusy]);

  // Opening the fit tab: show *your* already-scored fit instantly (no model
  // call / no tokens). Scoring only runs when you click the button.
  useEffect(() => {
    if (tab === "fit" && !fit && !fitBusy) {
      TopicIntelApi.fitCached(id)
        .then((f) => {
          if (f) setFit(f);
        })
        .catch(() => {});
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const title = meta?.title || topic?.topicTitle || topic?.title || id;
  const code = meta?.topic_code || topic?.topicCode;

  return (
    <div>
      <div className="meta" style={{ marginBottom: 6 }}>
        <Link to="/">← Inbox</Link> · <Link to="/browse">Browse</Link>
      </div>
      <h1 style={{ marginBottom: 2 }}>
        {code ? `${code} — ` : ""}
        {title}
      </h1>
      <p className="subtitle" style={{ marginBottom: 12 }}>
        {topic?.component && <>{topic.component} · </>}
        {topic?.program && <>{topic.program} · </>}
        {topic?.topicStatus && (
          <span className={`pill ${statusClass(topic.topicStatus)}`}>{topic.topicStatus}</span>
        )}
      </p>

      <div className="row" style={{ marginBottom: 10 }}>
        <a className="meta" href={TopicsApi.downloadUrl(id, "PDF", true)} target="_blank" rel="noreferrer">
          Official PDF ↗
        </a>
        <a className="meta" href={TopicsApi.downloadUrl(id, "DOCX")}>
          DOCX ↓
        </a>
        <Link className="meta" to={`/topic/${id}`} state={{ topic }}>
          Classic view ↗
        </Link>
      </div>

      <div className="tabs">
        <button className={`tab ${tab === "summary" ? "active" : ""}`} onClick={() => setTab("summary")}>
          Summary
        </button>
        <button className={`tab ${tab === "reader" ? "active" : ""}`} onClick={() => setTab("reader")}>
          Reader
        </button>
        <button className={`tab ${tab === "fit" ? "active" : ""}`} onClick={() => setTab("fit")}>
          Fit vs you
          {fit && (
            <span className={`pill ${fitClass(fit.overall_fit)}`}>{Math.round(fit.overall_fit)}</span>
          )}
        </button>
        <button className={`tab ${tab === "write" ? "active" : ""}`} onClick={() => setTab("write")}>
          Write
        </button>
        <button className={`tab ${tab === "source" ? "active" : ""}`} onClick={() => setTab("source")}>
          Source text
        </button>
      </div>

      {err && (
        <div className="card" style={{ color: "var(--red)" }}>
          {err}
        </div>
      )}

      {/* ---- SUMMARY ---- */}
      {tab === "summary" && (
        <div>
          {!summary && !summaryBusy && (
            <div className="card">
              <p style={{ marginTop: 0 }} className="meta">
                Read the PDF and condense it into a brief + requirements.
              </p>
              <button onClick={() => doSummary(false)}>Summarize this topic</button>
            </div>
          )}
          {summaryBusy && (
            <div className="card spinner">OCR + summarizing (first run downloads & reads the PDF)…</div>
          )}
          {summary && (
            <>
              <div className="card">
                <div className="row spread">
                  <h2 style={{ margin: 0 }}>TL;DR</h2>
                  <div className="row">
                    <span className="meta">
                      source: {summary.source} · {summary.chars?.toLocaleString()} chars
                      {summary.model ? ` · ${summary.model}` : ""}
                    </span>
                    <button className="ghost small" onClick={() => doSummary(true)} disabled={summaryBusy}>
                      Re-summarize
                    </button>
                  </div>
                </div>
                <p style={{ fontSize: 15 }}>{summary.tldr}</p>
                <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
                  {summary.keywords.map((k) => (
                    <span className="tag" key={k}>
                      {k}
                    </span>
                  ))}
                </div>
              </div>

              <div className="agent-grid">
                <div className="card">
                  <h3 style={{ marginTop: 0 }}>Problem / gap</h3>
                  <p>{summary.problem}</p>
                </div>
                <div className="card">
                  <h3 style={{ marginTop: 0 }}>Objective</h3>
                  <p>{summary.objective}</p>
                </div>
              </div>

              <div className="card">
                <h3 style={{ marginTop: 0 }}>Who cares / transition</h3>
                <p style={{ margin: 0 }}>{summary.who_cares}</p>
                {summary.phases.length > 0 && (
                  <>
                    <h3>Phases</h3>
                    <ul className="tight">
                      {summary.phases.map((p, i) => (
                        <li key={i}>{p}</li>
                      ))}
                    </ul>
                  </>
                )}
              </div>

              <div className="card">
                <div className="row spread">
                  <h3 style={{ margin: 0 }}>Key requirements ({summary.requirements.length})</h3>
                  <button className="ghost small" onClick={() => doFit(false)} disabled={fitBusy}>
                    Score fit vs you →
                  </button>
                </div>
                <div className="req-list">
                  {summary.requirements.map((r, i) => (
                    <div className="req-row" key={i}>
                      <span className="req-badge" style={{ borderColor: "var(--border-strong)" }}>
                        {i + 1}
                      </span>
                      <div className="req-body">
                        <div className="req-need">{r.need}</div>
                        {r.evidence && <div className="req-evi">{r.evidence}</div>}
                      </div>
                    </div>
                  ))}
                </div>
                <div className="row" style={{ marginTop: 12 }}>
                  <button className="ghost small" onClick={seedDraft}>
                    Start a proposal from this →
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      )}

      {/* ---- READER (evidence grounding) ---- */}
      {tab === "reader" && (
        <div>
          {!summary ? (
            <div className="card">
              <p style={{ marginTop: 0 }} className="meta">
                Summarize first — the reader highlights the sentence each requirement came from.
              </p>
              <button onClick={() => doSummary(false)} disabled={summaryBusy}>
                {summaryBusy ? "Summarizing…" : "Summarize this topic"}
              </button>
            </div>
          ) : rawBusy || !raw ? (
            <div className="card spinner">Loading the source text…</div>
          ) : !raw.text ? (
            <div className="card meta">No source text could be extracted for this topic.</div>
          ) : (
            <div className="card">
              <p className="meta" style={{ marginTop: 0 }}>
                Hover a requirement to find its source sentence — or hover the highlighted
                text to see which requirement it drove. Colors tie the two together.
              </p>
              <EvidenceReader text={raw.text} requirements={summary.requirements} />
            </div>
          )}
        </div>
      )}

      {/* ---- FIT ---- */}
      {tab === "fit" && (
        <div>
          {!fit && !fitBusy && (
            <div className="card">
              <p style={{ marginTop: 0 }} className="meta">
                Score each requirement against your profile — meets / partial / gap.
              </p>
              <button onClick={() => doFit(false)}>Score fit vs your profile</button>
            </div>
          )}
          {fitBusy && <div className="card spinner">Comparing requirements to your profile…</div>}
          {fit && (
            <>
              <div className="card">
                <div className="row spread">
                  <div>
                    <div className={`score ${fitClass(fit.overall_fit)}`}>
                      {Math.round(fit.overall_fit)}
                      <span style={{ fontSize: 13, color: "var(--muted)" }}> / 100 fit</span>
                    </div>
                    {fit.recommendation && (
                      <span className={`pill ${recClass(fit.recommendation)}`} style={{ marginTop: 6 }}>
                        {fit.recommendation}
                      </span>
                    )}
                  </div>
                  <div className="row">
                    <span className="meta">profile: {fit.cap_source}</span>
                    <button className="ghost small" onClick={() => doFit(true)} disabled={fitBusy}>
                      Re-score
                    </button>
                  </div>
                </div>
                {fit.summary && <p style={{ marginBottom: 0 }}>{fit.summary}</p>}
              </div>

              <div className="card">
                <h3 style={{ marginTop: 0 }}>Requirement-by-requirement</h3>
                <div className="req-list">
                  {fit.requirements.map((r, i) => (
                    <div className="req-row" key={i}>
                      <span className={`req-badge ${r.status}`}>{r.status}</span>
                      <div className="req-body">
                        <div className="req-need">{r.need}</div>
                        {r.evidence && <div className="req-evi">{r.evidence}</div>}
                        {r.matched_capability && (
                          <div className="req-match">✓ {r.matched_capability}</div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="agent-grid">
                <div className="card">
                  <h3 style={{ marginTop: 0 }}>Strengths</h3>
                  <ul className="tight">
                    {fit.strengths.map((s, i) => (
                      <li key={i}>{s}</li>
                    ))}
                  </ul>
                </div>
                <div className="card">
                  <h3 style={{ marginTop: 0, color: "var(--red)" }}>Gaps to close</h3>
                  <ul className="tight">
                    {fit.gaps.map((g, i) => (
                      <li key={i}>{g}</li>
                    ))}
                  </ul>
                </div>
              </div>
              <p className="meta">
                Weak fit? Add the missing capability on{" "}
                <Link to="/org">Company & products</Link> or your <Link to="/profile">Profile</Link>,
                then re-score.
              </p>
            </>
          )}
        </div>
      )}

      {/* ---- WRITE ---- */}
      {tab === "write" && (
        <div className="agent-grid">
          <div className="card">
            <div className="row spread">
              <h3 style={{ margin: 0 }}>Draft</h3>
              <div className="row">
                <button className="ghost small" onClick={seedDraft} disabled={!summary}>
                  Seed from summary
                </button>
                <button className="ghost small" onClick={saveToDesk} disabled={saving}>
                  {saving ? "Saving…" : "Save to Group desk"}
                </button>
              </div>
            </div>
            <textarea
              rows={26}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Write your proposal here. Use 'Seed from summary' to start from the extracted requirements."
            />
          </div>
          <div className="card">
            <div className="row spread">
              <h3 style={{ margin: 0 }}>Live feedback</h3>
              <button className="ghost small" onClick={runFeedback} disabled={feedbackBusy}>
                {feedbackBusy ? "Reviewing…" : "Get feedback"}
              </button>
            </div>
            {feedback ? (
              <pre className="stream">{feedback}</pre>
            ) : (
              <p className="meta">
                Feedback checks your draft against this topic's requirements. Write something,
                then hit <em>Get feedback</em>.
              </p>
            )}
          </div>
        </div>
      )}

      {/* ---- SOURCE TEXT ---- */}
      {tab === "source" && (
        <div>
          {!raw && !rawBusy && (
            <div className="card">
              <p style={{ marginTop: 0 }} className="meta">
                The raw OCR text the summary and fit are built from.
              </p>
              <button onClick={() => doRaw(false)}>Load raw text</button>
            </div>
          )}
          {rawBusy && <div className="card spinner">Extracting…</div>}
          {raw && (
            <div className="card">
              <div className="row spread">
                <span className="meta">
                  source: <strong>{raw.source}</strong> · {raw.chars.toLocaleString()} chars
                </span>
                <button className="ghost small" onClick={() => doRaw(true)} disabled={rawBusy}>
                  Re-extract
                </button>
              </div>
              <pre className="stream" style={{ maxHeight: "70vh" }}>
                {raw.text || "(no text extracted)"}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

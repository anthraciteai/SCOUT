import { useEffect, useRef, useState } from "react";
import {
  ProposalsApi,
  TeamApi,
  streamProposalFeedback,
  streamSavedFeedback,
} from "../api";
import type { Proposal, TeamRecommendation } from "../types";
import TeamCard from "../components/TeamCard";
import TopicPicker from "../components/TopicPicker";

export default function Proposals() {
  const [list, setList] = useState<Proposal[]>([]);
  const [current, setCurrent] = useState<Proposal | null>(null);
  const [title, setTitle] = useState("");
  const [topicId, setTopicId] = useState("");
  const [topicCode, setTopicCode] = useState("");
  const [content, setContent] = useState("");
  const [status, setStatus] = useState("draft");
  const [feedback, setFeedback] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [focus, setFocus] = useState("");
  const [teamRec, setTeamRec] = useState<TeamRecommendation | null>(null);
  const [teamLoading, setTeamLoading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  async function load() {
    setList(await ProposalsApi.list());
  }
  useEffect(() => {
    load();
  }, []);

  function edit(p: Proposal) {
    setCurrent(p);
    setTitle(p.title);
    setTopicId(p.topic_id || "");
    setTopicCode(p.topic_code || "");
    setContent(p.content);
    setStatus(p.status);
    setFeedback("");
    setTeamRec(null);
  }

  function newDraft() {
    setCurrent(null);
    setTitle("New Proposal");
    setTopicId("");
    setTopicCode("");
    setContent("");
    setStatus("draft");
    setFeedback("");
    setTeamRec(null);
  }

  async function save() {
    const body = {
      title,
      content,
      topic_id: topicId || undefined,
      topic_code: topicCode || undefined,
      status,
    };
    const saved = current
      ? await ProposalsApi.update(current.id, body)
      : await ProposalsApi.create(body);
    setCurrent(saved);
    await load();
  }

  async function remove(p: Proposal) {
    if (!confirm(`Delete "${p.title}"?`)) return;
    await ProposalsApi.remove(p.id);
    if (current?.id === p.id) newDraft();
    await load();
  }

  async function liveFeedback() {
    setStreaming(true);
    setFeedback("");
    const ac = new AbortController();
    abortRef.current = ac;
    try {
      await streamProposalFeedback(
        { content, topic_id: topicId || undefined, focus: focus || undefined },
        (chunk) => setFeedback((f) => f + chunk),
        ac.signal
      );
    } catch (e: any) {
      if (e.name !== "AbortError") setFeedback((f) => f + `\n[error: ${e.message}]`);
    } finally {
      setStreaming(false);
    }
  }

  async function fullReview() {
    if (!current) {
      alert("Save the proposal first for a full review (uses topic + debrief context).");
      return;
    }
    setStreaming(true);
    setFeedback("");
    const ac = new AbortController();
    abortRef.current = ac;
    try {
      await streamSavedFeedback(current.id, (chunk) => setFeedback((f) => f + chunk), ac.signal);
    } catch (e: any) {
      if (e.name !== "AbortError") setFeedback((f) => f + `\n[error: ${e.message}]`);
    } finally {
      setStreaming(false);
    }
  }

  function stop() {
    abortRef.current?.abort();
    setStreaming(false);
  }

  async function whoToAdd() {
    setTeamLoading(true);
    setTeamRec(null);
    try {
      const res = await TeamApi.recommend({
        topic_id: topicId || undefined,
        proposal_content: content || undefined,
      });
      setTeamRec(res.recommendation);
    } catch (e: any) {
      alert(e?.response?.data?.detail || e.message || "Failed to get recommendations");
    } finally {
      setTeamLoading(false);
    }
  }

  return (
    <div>
      <h1>Proposals</h1>
      <p className="subtitle">
        Draft proposals and get live LLM feedback while you write (gpt-oss:20b). A full review also
        pulls in the target topic and any uploaded debriefs.
      </p>

      <div className="row" style={{ alignItems: "flex-start", gap: 16 }}>
        {/* List */}
        <div style={{ width: 240 }}>
          <button className="small" onClick={newDraft} style={{ marginBottom: 10 }}>
            + New draft
          </button>
          {list.map((p) => (
            <div
              key={p.id}
              className="card"
              style={{
                padding: 10,
                cursor: "pointer",
                borderColor: current?.id === p.id ? "var(--accent)" : "var(--border)",
              }}
              onClick={() => edit(p)}
            >
              <div style={{ fontSize: 14, fontWeight: 600 }}>{p.title}</div>
              <div className="meta">
                {p.status} · {new Date(p.updated_at).toLocaleDateString()}
                {p.topic_code ? ` · ${p.topic_code}` : ""}
              </div>
              <button
                className="ghost small danger"
                onClick={(e) => {
                  e.stopPropagation();
                  remove(p);
                }}
                style={{ marginTop: 6 }}
              >
                delete
              </button>
            </div>
          ))}
        </div>

        {/* Editor */}
        <div className="grow">
          <div className="card">
            <div className="row">
              <input
                className="grow"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Proposal title"
              />
              <select value={status} onChange={(e) => setStatus(e.target.value)}>
                <option value="draft">draft</option>
                <option value="submitted">submitted</option>
                <option value="awarded">awarded</option>
                <option value="not_selected">not selected</option>
              </select>
            </div>
            <div style={{ marginTop: 8 }}>
              <TopicPicker
                value={topicId}
                onChange={(sel) => {
                  setTopicId(sel.topic_id);
                  setTopicCode(sel.topic_code || "");
                }}
              />
            </div>
            <textarea
              style={{ marginTop: 8 }}
              rows={16}
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="Write your proposal here…"
            />
            <div className="row" style={{ marginTop: 10 }}>
              <button onClick={save}>Save</button>
              <input
                className="grow"
                value={focus}
                onChange={(e) => setFocus(e.target.value)}
                placeholder="Feedback focus (optional): technical approach, commercialization…"
              />
              <button className="ghost" onClick={liveFeedback} disabled={streaming || !content}>
                Live feedback
              </button>
              <button className="ghost" onClick={fullReview} disabled={streaming}>
                Full review
              </button>
              <button className="ghost" onClick={whoToAdd} disabled={teamLoading}>
                {teamLoading ? "Thinking…" : "Who to add"}
              </button>
              {streaming && (
                <button className="danger" onClick={stop}>
                  Stop
                </button>
              )}
            </div>
          </div>

          {(teamRec || teamLoading) && (
            <div className="card" style={{ borderColor: "#c98b3a" }}>
              <h3 style={{ marginTop: 0 }}>
                Team recommendations{" "}
                {teamLoading && <span className="spinner">· Collier is thinking…</span>}
              </h3>
              {teamRec && <TeamCard rec={teamRec} />}
            </div>
          )}

          {(feedback || streaming) && (
            <div className="card">
              <h3>LLM feedback {streaming && <span className="spinner">· generating…</span>}</h3>
              <pre className="stream">{feedback || "…"}</pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

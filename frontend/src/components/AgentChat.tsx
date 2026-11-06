import { useEffect, useRef, useState } from "react";
import { COLORS } from "./agentWorkspace";
import { AnalysisApi } from "../api";
import type { TopicMeta } from "../api";
import type { AgentChatLog, ChatMessage } from "../types";

export const AGENT_COLORS = COLORS;

const PLACEHOLDER =
  "Due to license we can't do that — replace it with …";

export default function AgentChat({
  topicId,
  agent,
  topicsMeta,
  proposalText,
  compact,
  fill,
}: {
  topicId: string;
  agent: string;
  topicsMeta?: Record<string, TopicMeta>;
  proposalText?: string;
  compact?: boolean;
  fill?: boolean;
}) {
  const [log, setLog] = useState<AgentChatLog | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const scroller = useRef<HTMLDivElement>(null);
  const color = (AGENT_COLORS as Record<string, string>)[agent] || "var(--accent)";

  async function load() {
    try {
      const data = await AnalysisApi.getChat(topicId, agent);
      setLog(data);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e.message || "Could not load chat");
    }
  }

  useEffect(() => {
    setLog(null);
    setError("");
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topicId, agent]);

  useEffect(() => {
    const el = scroller.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [log?.messages.length, busy]);

  async function send() {
    const message = draft.trim();
    if (!message || busy) return;
    setBusy(true);
    setError("");
    const optimistic: ChatMessage = { role: "user", text: message, at: new Date().toISOString() };
    setLog((prev) =>
      prev
        ? { ...prev, messages: [...prev.messages, optimistic] }
        : { agent, messages: [optimistic] }
    );
    setDraft("");
    try {
      const data = await AnalysisApi.sendChat({
        topic_id: topicId,
        agent,
        message,
        proposal_text: proposalText,
        topics_meta: topicsMeta,
      });
      setLog(data);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e.message || "Send failed");
      setDraft(message);
    } finally {
      setBusy(false);
    }
  }

  const messages = log?.messages || [];

  return (
    <div className={`agent-chat${fill ? " fill" : ""}`} style={{ borderColor: color }}>
      <div className="row spread" style={{ marginBottom: 8 }}>
        <div className="meta">
          Working log with {agent}
          {log?.path ? <span> · recorded at {log.path.replace(/^.*\/users\//, "…/")}</span> : null}
        </div>
        {log?.updated_at && (
          <span className="meta">{new Date(log.updated_at).toLocaleString()}</span>
        )}
      </div>
      <div
        ref={scroller}
        className="agent-chat-log"
        style={fill ? { flex: 1, minHeight: 0 } : { maxHeight: compact ? 220 : 340 }}
      >
        {messages.length === 0 && !busy && (
          <div className="meta" style={{ padding: "8px 4px" }}>
            {agent} can work the proposal with you. Push back on a spark — license, ITAR,
            missing kit — and they will substitute. Turns are saved to the vault.
          </div>
        )}
        {messages.map((m, i) => {
          const mine = m.role === "user";
          const who = mine ? "You" : m.speaker || agent;
          const avatarColor = mine ? "var(--muted)" : color;
          const initial = (who || "?").trim().charAt(0).toUpperCase();
          return (
            <div key={i} className={`chat-row ${mine ? "mine" : "theirs"}`}>
              <div className="chat-meta">
                <span className="chat-avatar" style={{ background: avatarColor }}>
                  {initial}
                </span>
                <span className="chat-who" style={mine ? undefined : { color }}>
                  {who}
                </span>
              </div>
              <div className="chat-bubble" style={mine ? undefined : { borderColor: color }}>
                {m.text}
              </div>
            </div>
          );
        })}
        {busy && (
          <div className="chat-row theirs">
            <div className="chat-meta">
              <span className="chat-avatar" style={{ background: color }}>
                {agent.charAt(0).toUpperCase()}
              </span>
              <span className="chat-who" style={{ color }}>
                {agent}
              </span>
            </div>
            <div className="chat-bubble" style={{ borderColor: color }}>
              <span className="chat-typing">thinking…</span>
            </div>
          </div>
        )}
      </div>
      {error && (
        <div className="meta" style={{ color: "var(--red)", marginTop: 6 }}>
          {error}
        </div>
      )}
      <div className="row" style={{ marginTop: 8, alignItems: "flex-end" }}>
        <textarea
          rows={compact ? 2 : 3}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={PLACEHOLDER}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
              e.preventDefault();
              send();
            }
          }}
        />
        <button className="small" onClick={send} disabled={busy || !draft.trim()}>
          {busy ? "…" : "Send"}
        </button>
      </div>
    </div>
  );
}

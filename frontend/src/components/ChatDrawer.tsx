import { useEffect } from "react";
import AgentChat from "./AgentChat";
import { COLORS, ROLES, type AgentName } from "./agentWorkspace";
import type { TopicMeta } from "../api";

/** Right-side, ChatGPT-style chat panel for one agent. History is loaded and
 *  persisted per (topic, agent) by AgentChat via the vault. */
export default function ChatDrawer({
  open,
  topicId,
  agent,
  topicsMeta,
  onClose,
}: {
  open: boolean;
  topicId: string;
  agent: string;
  topicsMeta?: Record<string, TopicMeta>;
  onClose: () => void;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  const color = COLORS[agent as AgentName] || "var(--accent)";
  const role = ROLES[agent as AgentName] || "";

  return (
    <>
      <div className="chat-drawer-scrim" onClick={onClose} />
      <aside
        className="chat-drawer"
        style={{ borderColor: color }}
        role="dialog"
        aria-label={`Chat with ${agent}`}
      >
        <div className="chat-drawer-head">
          <div className="row" style={{ gap: 8, alignItems: "center" }}>
            <span className="agent-dot" style={{ background: color }} />
            <strong>{agent}</strong>
            {role && <span className="meta">· {role}</span>}
          </div>
          <button className="ghost small" onClick={onClose} aria-label="Close chat">
            ✕
          </button>
        </div>
        <div className="chat-drawer-body">
          {/* key forces a fresh load when switching agents */}
          <AgentChat
            key={`${topicId}:${agent}`}
            topicId={topicId}
            agent={agent}
            topicsMeta={topicsMeta}
            fill
          />
        </div>
      </aside>
    </>
  );
}

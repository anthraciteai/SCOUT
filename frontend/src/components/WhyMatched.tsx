import { useState } from "react";
import { streamWhyMatched } from "../api";

/**
 * Inline "why did this match?" panel. Streams a short LLM explanation quoting
 * the exact phrases we already stored for this match — turns the opaque score
 * chip into a decision aid without any new tagging pass.
 */
export default function WhyMatched({ topicId, topicCode }: { topicId: string; topicCode?: string }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function run() {
    setText("");
    setError("");
    setBusy(true);
    setOpen(true);
    try {
      await streamWhyMatched(topicId, (chunk) => setText((prev) => prev + chunk));
    } catch (e: any) {
      setError(e?.message || "Explanation failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ marginTop: 10 }}>
      {!open && (
        <button
          className="ghost small"
          onClick={run}
          title="LLM explains why this topic matched — quotes the phrases that hit."
        >
          Why did this match?
        </button>
      )}
      {open && (
        <div
          className="card"
          style={{
            marginTop: 6,
            background: "var(--panel-2)",
            borderColor: "#e6c07b",
            padding: 12,
          }}
        >
          <div className="row spread" style={{ marginBottom: 6 }}>
            <strong style={{ fontSize: 13 }}>
              Why {topicCode || topicId} matched
            </strong>
            <div className="row" style={{ gap: 6 }}>
              <button
                className="ghost small"
                disabled={busy || !text}
                onClick={() => navigator.clipboard.writeText(text)}
                title="Copy explanation"
              >
                Copy
              </button>
              <button className="ghost small" onClick={run} disabled={busy}>
                {busy ? "Thinking…" : "Regenerate"}
              </button>
              <button className="ghost small" onClick={() => setOpen(false)} disabled={busy}>
                Hide
              </button>
            </div>
          </div>
          {error && <div style={{ color: "var(--red)", fontSize: 13 }}>{error}</div>}
          <RenderWithBackticks text={text} />
          {busy && !text && <div className="meta">Reading phrases and reasons…</div>}
        </div>
      )}
    </div>
  );
}

/** Renders text with `backtick` runs styled as inline chips so the quoted phrases
 * are visually distinct — the whole point of this feature is to see WHAT matched. */
function RenderWithBackticks({ text }: { text: string }) {
  if (!text) return null;
  const parts = text.split(/(`[^`]+`)/g);
  return (
    <div style={{ fontSize: 13.5, lineHeight: 1.5, whiteSpace: "pre-wrap" }}>
      {parts.map((chunk, i) => {
        if (chunk.startsWith("`") && chunk.endsWith("`") && chunk.length > 2) {
          return (
            <span
              key={i}
              className="tag"
              style={{
                margin: "0 3px",
                background: "rgba(255,122,26,0.14)",
                color: "var(--ember)",
                border: "1px solid rgba(255,122,26,0.4)",
              }}
            >
              {chunk.slice(1, -1)}
            </span>
          );
        }
        return <span key={i}>{chunk}</span>;
      })}
    </div>
  );
}

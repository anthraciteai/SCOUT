import type { AgentResult } from "../types";

export type FlintSpark = {
  title?: string;
  hook?: string;
  how?: string[];
  tools?: string[];
  originality?: number;
  feasibility?: number;
  why_only_you?: string;
};

export type FlintTool = {
  tool?: string;
  from_resume?: string;
  role_in_this_bid?: string;
};

export type FlintResult = AgentResult & {
  persona_read?: string;
  tools_in_play?: FlintTool[];
  sparks?: FlintSpark[];
  left_field?: string;
  do_not_fake?: string[];
};

export default function FlintCard({ rec }: { rec: FlintResult }) {
  const sparks = Array.isArray(rec.sparks) ? rec.sparks : [];
  const tools = Array.isArray(rec.tools_in_play) ? rec.tools_in_play : [];
  const fake = Array.isArray(rec.do_not_fake) ? rec.do_not_fake : [];
  return (
    <div>
      <div className="row" style={{ gap: 8, marginBottom: 8 }}>
        <strong>Flint</strong>
        <span className="meta">· creative toolwright — only your real stack</span>
      </div>
      {rec.persona_read && (
        <p style={{ fontSize: 14, lineHeight: 1.55, marginTop: 0 }}>{rec.persona_read}</p>
      )}
      {tools.length > 0 && (
        <>
          <div className="kv">Tools in play</div>
          <div className="row" style={{ gap: 6, marginBottom: 10 }}>
            {tools.map((t, i) => (
              <span className="tag" key={i} title={t.from_resume || t.role_in_this_bid}>
                {t.tool}
                {t.role_in_this_bid ? ` → ${t.role_in_this_bid}` : ""}
              </span>
            ))}
          </div>
        </>
      )}
      {sparks.map((s, i) => (
        <div
          key={i}
          className="card"
          style={{ background: "var(--panel)", marginBottom: 8, padding: 12 }}
        >
          <div className="row spread">
            <strong style={{ fontSize: 14 }}>{s.title || `Spark ${i + 1}`}</strong>
            <span className="meta">
              orig {s.originality ?? "—"} · feas {s.feasibility ?? "—"}
            </span>
          </div>
          {s.hook && <p style={{ fontSize: 13, margin: "6px 0" }}>{s.hook}</p>}
          {Array.isArray(s.how) && s.how.length > 0 && (
            <ul className="tight">
              {s.how.map((h, j) => (
                <li key={j}>{h}</li>
              ))}
            </ul>
          )}
          {s.why_only_you && (
            <div className="meta" style={{ marginTop: 4 }}>
              Why only you: {s.why_only_you}
            </div>
          )}
          {Array.isArray(s.tools) && s.tools.length > 0 && (
            <div className="row" style={{ gap: 6, marginTop: 6 }}>
              {s.tools.map((t) => (
                <span className="tag" key={t}>
                  {t}
                </span>
              ))}
            </div>
          )}
        </div>
      ))}
      {rec.left_field && (
        <div className="card" style={{ borderColor: "var(--accent)", padding: 12 }}>
          <div className="kv">Left field</div>
          <div style={{ fontSize: 13 }}>{rec.left_field}</div>
        </div>
      )}
      {fake.length > 0 && (
        <>
          <div className="kv">Do not fake</div>
          <ul className="tight">
            {fake.map((x, i) => (
              <li key={i}>{x}</li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

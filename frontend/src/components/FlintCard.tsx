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

/** Coerce any model value into a safe React child. The LLM sometimes returns
 *  an object (e.g. {tool, role_in_this_bid}) where a string is expected, which
 *  otherwise crashes the render with React error #31. */
function asText(v: unknown): string {
  if (v == null) return "";
  if (typeof v === "string") return v;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  if (typeof v === "object") {
    const o = v as Record<string, unknown>;
    const name = o.tool ?? o.name ?? o.title ?? o.text;
    if (typeof name === "string" && name.trim()) {
      const role = o.role_in_this_bid;
      return typeof role === "string" && role.trim() && role !== name
        ? `${name} → ${role}`
        : name;
    }
    try {
      return JSON.stringify(v);
    } catch {
      return String(v);
    }
  }
  return String(v);
}

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
        <p style={{ fontSize: 14, lineHeight: 1.55, marginTop: 0 }}>{asText(rec.persona_read)}</p>
      )}
      {tools.length > 0 && (
        <>
          <div className="kv">Tools in play</div>
          <div className="row" style={{ gap: 6, marginBottom: 10 }}>
            {tools.map((t, i) => (
              <span className="tag" key={i} title={t.from_resume || t.role_in_this_bid}>
                {asText(t.tool)}
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
            <strong style={{ fontSize: 14 }}>{asText(s.title) || `Spark ${i + 1}`}</strong>
            <span className="meta">
              orig {s.originality ?? "—"} · feas {s.feasibility ?? "—"}
            </span>
          </div>
          {s.hook && <p style={{ fontSize: 13, margin: "6px 0" }}>{asText(s.hook)}</p>}
          {Array.isArray(s.how) && s.how.length > 0 && (
            <ul className="tight">
              {s.how.map((h, j) => (
                <li key={j}>{asText(h)}</li>
              ))}
            </ul>
          )}
          {s.why_only_you && (
            <div className="meta" style={{ marginTop: 4 }}>
              Why only you: {asText(s.why_only_you)}
            </div>
          )}
          {Array.isArray(s.tools) && s.tools.length > 0 && (
            <div className="row" style={{ gap: 6, marginTop: 6 }}>
              {s.tools.map((t, j) => (
                <span className="tag" key={j}>
                  {asText(t)}
                </span>
              ))}
            </div>
          )}
        </div>
      ))}
      {rec.left_field && (
        <div className="card" style={{ borderColor: "var(--accent)", padding: 12 }}>
          <div className="kv">Left field</div>
          <div style={{ fontSize: 13 }}>{asText(rec.left_field)}</div>
        </div>
      )}
      {fake.length > 0 && (
        <>
          <div className="kv">Do not fake</div>
          <ul className="tight">
            {fake.map((x, i) => (
              <li key={i}>{asText(x)}</li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

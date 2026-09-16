import type { HewerResult } from "../types";

export function liftColor(v?: number): string {
  if (v == null) return "var(--muted)";
  if (v <= 4) return "var(--green)";
  if (v <= 7) return "var(--yellow)";
  return "var(--red)";
}

export function liftLabel(v?: number): string {
  if (v == null) return "—";
  if (v === 0) return "Works as-is";
  if (v <= 4) return "Light lift";
  if (v <= 7) return "Significant build";
  return "New product";
}

export default function HewerCard({ rec }: { rec: HewerResult }) {
  if (!rec) return null;
  if (rec.raw && rec.heavy_lift == null && !rec.adaptation_plan) {
    return <pre className="stream">{rec.raw}</pre>;
  }

  const lift = rec.heavy_lift;
  const lightLift = lift != null && lift <= 4;

  return (
    <div>
      <div className="agent-head">
        <span className="agent-dot" style={{ background: "#e0704f" }} />
        <strong>Hewer</strong>
        <span className="meta">· How heavy a lift to adapt your product</span>
      </div>

      <div className="row" style={{ gap: 12, alignItems: "center", marginBottom: 6 }}>
        <div className="score" style={{ color: liftColor(lift), fontSize: 26 }}>
          {lift != null ? lift : "—"}
          <span style={{ fontSize: 13, color: "var(--muted)" }}> /10</span>
        </div>
        <span
          className="pill"
          style={{ borderColor: liftColor(lift), color: liftColor(lift) }}
        >
          {liftLabel(lift)}
        </span>
        {lightLift && (
          <span className="meta">Low-risk pursuit — adaptation plan below.</span>
        )}
      </div>

      {rec.lift_rationale && (
        <p style={{ fontSize: 13, lineHeight: 1.5, margin: "4px 0" }}>{rec.lift_rationale}</p>
      )}

      {rec.reuse_as_is && rec.reuse_as_is.length > 0 && (
        <div style={{ marginBottom: 6 }}>
          <div className="kv">Reuse as-is</div>
          <div className="row" style={{ gap: 6 }}>
            {rec.reuse_as_is.map((r, i) => (
              <span key={i} className="pill green">
                {r}
              </span>
            ))}
          </div>
        </div>
      )}

      {rec.adaptation_plan && rec.adaptation_plan.length > 0 && (
        <div style={{ marginBottom: 6 }}>
          <div className="kv">
            {lightLift ? "How to make your product work for this proposal" : "Adaptation plan"}
          </div>
          <ul className="tight">
            {rec.adaptation_plan.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ul>
        </div>
      )}

      {rec.effort_breakdown && rec.effort_breakdown.length > 0 && (
        <div>
          <div className="kv">Effort breakdown</div>
          <ul className="tight">
            {rec.effort_breakdown.map((e, i) => (
              <li key={i}>
                {e.area}
                {e.effort ? ` — ${e.effort}` : ""}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

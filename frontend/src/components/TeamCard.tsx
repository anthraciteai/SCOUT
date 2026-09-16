import type { TeamRecommendation } from "../types";

export default function TeamCard({ rec }: { rec: TeamRecommendation }) {
  if (!rec) return null;
  if (rec.raw && !rec.roles_to_add && !rec.gaps) {
    return <pre className="stream">{rec.raw}</pre>;
  }

  const roles = rec.roles_to_add || [];
  const partners = rec.partner_types || [];

  return (
    <div>
      <div className="agent-head">
        <span className="agent-dot" style={{ background: "#c98b3a" }} />
        <strong>Collier</strong>
        <span className="meta">· Who you should add</span>
      </div>

      {rec.covered_by_you && rec.covered_by_you.length > 0 && (
        <div style={{ marginBottom: 8 }}>
          <div className="kv">You already cover</div>
          <div className="row" style={{ gap: 6 }}>
            {rec.covered_by_you.map((c, i) => (
              <span key={i} className="pill green">
                {c}
              </span>
            ))}
          </div>
        </div>
      )}

      {rec.gaps && rec.gaps.length > 0 && (
        <div style={{ marginBottom: 8 }}>
          <div className="kv">Gaps to fill</div>
          <div className="row" style={{ gap: 6 }}>
            {rec.gaps.map((g, i) => (
              <span key={i} className="pill yellow">
                {g}
              </span>
            ))}
          </div>
        </div>
      )}

      {roles.length > 0 && (
        <div style={{ marginBottom: 8 }}>
          <div className="kv">Roles to add</div>
          {roles.map((r, i) => (
            <div
              key={i}
              className="card"
              style={{ padding: 10, margin: "6px 0", background: "var(--panel-2)" }}
            >
              <div className="row spread">
                <strong>{r.role}</strong>
                {r.seniority && <span className="tag">{r.seniority}</span>}
              </div>
              {r.why && (
                <div style={{ fontSize: 13, color: "var(--muted)", marginTop: 4 }}>{r.why}</div>
              )}
              {r.skills && r.skills.length > 0 && (
                <div className="row" style={{ gap: 6, marginTop: 6 }}>
                  {r.skills.map((s, j) => (
                    <span key={j} className="tag">
                      {s}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {partners.length > 0 && (
        <div style={{ marginBottom: 8 }}>
          <div className="kv">Partner organizations</div>
          <ul className="tight">
            {partners.map((p, i) => (
              <li key={i}>
                <strong>{p.type}</strong>
                {p.why ? ` — ${p.why}` : ""}
              </li>
            ))}
          </ul>
        </div>
      )}

      {rec.priority_hires && rec.priority_hires.length > 0 && (
        <div style={{ marginBottom: 8 }}>
          <div className="kv">Priority (hire/partner first)</div>
          <ul className="tight">
            {rec.priority_hires.map((p, i) => (
              <li key={i}>{p}</li>
            ))}
          </ul>
        </div>
      )}

      {rec.notes && <div style={{ fontSize: 13, marginTop: 6 }}>{rec.notes}</div>}
    </div>
  );
}

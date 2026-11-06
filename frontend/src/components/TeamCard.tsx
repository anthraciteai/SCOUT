import type { TeamRecommendation } from "../types";
import { asText, asList } from "./agentWorkspace";
import ErrorBoundary from "./ErrorBoundary";

const AMBER = "#c98b3a";

function TeamCardInner({ rec }: { rec: TeamRecommendation }) {
  if (!rec) return null;
  if (rec.raw && !rec.roles_to_add && !rec.gaps) {
    return <pre className="stream">{asText(rec.raw)}</pre>;
  }

  const covered = asList(rec.covered_by_you);
  const gaps = asList(rec.gaps);
  const roles = Array.isArray(rec.roles_to_add) ? rec.roles_to_add : [];
  const partners = Array.isArray(rec.partner_types) ? rec.partner_types : [];
  const priority = asList(rec.priority_hires);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <span className="h-2.5 w-2.5 rounded-full" style={{ background: AMBER, boxShadow: `0 0 8px ${AMBER}` }} />
        <strong className="text-[15px]">Collier</strong>
        <span className="text-[12px] text-faint">· who you should add</span>
      </div>

      {covered.length > 0 && (
        <div>
          <div className="mb-1.5 text-[10.5px] font-bold uppercase tracking-[0.12em] text-faint">You already cover</div>
          <div className="flex flex-wrap gap-1.5">
            {covered.map((c, i) => (
              <span
                key={i}
                className="inline-flex items-center rounded-full px-2.5 py-1 text-[12px]"
                style={{ border: "1px solid var(--green)", color: "var(--green)" }}
              >
                {c}
              </span>
            ))}
          </div>
        </div>
      )}

      {gaps.length > 0 && (
        <div>
          <div className="mb-1.5 text-[10.5px] font-bold uppercase tracking-[0.12em] text-faint">Gaps to fill</div>
          <div className="flex flex-wrap gap-1.5">
            {gaps.map((g, i) => (
              <span
                key={i}
                className="inline-flex items-center rounded-full px-2.5 py-1 text-[12px]"
                style={{ border: "1px solid var(--yellow)", color: "var(--yellow)" }}
              >
                {g}
              </span>
            ))}
          </div>
        </div>
      )}

      {roles.length > 0 && (
        <div>
          <div className="mb-1.5 text-[10.5px] font-bold uppercase tracking-[0.12em] text-faint">Roles to add</div>
          <div className="flex flex-col gap-2">
            {roles.map((r, i) => (
              <div key={i} className="rounded-xl border border-hair bg-surface2/60 p-3">
                <div className="flex items-start justify-between gap-2">
                  <strong className="text-[14px] text-ink">{asText(r.role)}</strong>
                  {r.seniority && (
                    <span className="shrink-0 rounded-full border border-hairstrong px-2 py-0.5 text-[11.5px] text-muted">
                      {asText(r.seniority)}
                    </span>
                  )}
                </div>
                {r.why && <div className="mt-1 text-[13px] leading-relaxed text-muted">{asText(r.why)}</div>}
                {asList(r.skills).length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {asList(r.skills).map((s, j) => (
                      <span
                        key={j}
                        className="inline-flex items-center rounded-full border border-hairstrong px-2 py-0.5 text-[11.5px] text-muted"
                      >
                        {s}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {partners.length > 0 && (
        <div>
          <div className="mb-1.5 text-[10.5px] font-bold uppercase tracking-[0.12em] text-faint">Partner organizations</div>
          <ul className="m-0 list-disc space-y-0.5 pl-4 text-[13px]">
            {partners.map((p, i) => (
              <li key={i}>{asText(p)}</li>
            ))}
          </ul>
        </div>
      )}

      {priority.length > 0 && (
        <div>
          <div className="mb-1.5 text-[10.5px] font-bold uppercase tracking-[0.12em] text-faint">
            Priority (hire/partner first)
          </div>
          <ul className="m-0 list-disc space-y-0.5 pl-4 text-[13px]">
            {priority.map((p, i) => (
              <li key={i}>{p}</li>
            ))}
          </ul>
        </div>
      )}

      {rec.notes && <div className="text-[13px] leading-relaxed text-muted">{asText(rec.notes)}</div>}
    </div>
  );
}

export default function TeamCard({ rec }: { rec: TeamRecommendation }) {
  return (
    <ErrorBoundary label="Collier’s teaming read" resetKey={rec}>
      <TeamCardInner rec={rec} />
    </ErrorBoundary>
  );
}

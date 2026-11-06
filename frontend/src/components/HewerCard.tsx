import type { HewerResult } from "../types";
import { asText, asList } from "./agentWorkspace";
import ErrorBoundary from "./ErrorBoundary";

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

function HewerCardInner({ rec }: { rec: HewerResult }) {
  if (!rec) return null;
  if (rec.raw && rec.heavy_lift == null && !rec.adaptation_plan) {
    return <pre className="stream">{asText(rec.raw)}</pre>;
  }

  const lift = rec.heavy_lift;
  const color = liftColor(lift);
  const lightLift = lift != null && lift <= 4;
  const reuse = asList(rec.reuse_as_is);
  const plan = asList(rec.adaptation_plan);
  const effort = Array.isArray(rec.effort_breakdown) ? rec.effort_breakdown : [];

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <span className="h-2.5 w-2.5 rounded-full" style={{ background: "#e0704f", boxShadow: "0 0 8px #e0704f" }} />
        <strong className="text-[15px]">Hewer</strong>
        <span className="text-[12px] text-faint">· how heavy a lift to adapt your product</span>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="text-[26px] font-bold leading-none" style={{ color }}>
          {lift != null ? lift : "—"}
          <span className="text-[13px] font-normal text-muted"> /10</span>
        </div>
        <span
          className="rounded-full px-2.5 py-1 text-[12px] font-semibold"
          style={{ border: `1px solid ${color}`, color }}
        >
          {liftLabel(lift)}
        </span>
        {lightLift && <span className="text-[12px] text-faint">Low-risk pursuit — plan below.</span>}
      </div>

      {rec.lift_rationale && (
        <p className="m-0 text-[13px] leading-relaxed text-ink">{asText(rec.lift_rationale)}</p>
      )}

      {reuse.length > 0 && (
        <div>
          <div className="mb-1.5 text-[10.5px] font-bold uppercase tracking-[0.12em] text-faint">Reuse as-is</div>
          <div className="flex flex-wrap gap-1.5">
            {reuse.map((r, i) => (
              <span
                key={i}
                className="inline-flex items-center rounded-full px-2.5 py-1 text-[12px]"
                style={{ border: "1px solid var(--green)", color: "var(--green)" }}
              >
                {r}
              </span>
            ))}
          </div>
        </div>
      )}

      {plan.length > 0 && (
        <div>
          <div className="mb-1.5 text-[10.5px] font-bold uppercase tracking-[0.12em] text-faint">
            {lightLift ? "How to make your product fit this proposal" : "Adaptation plan"}
          </div>
          <ol className="m-0 list-decimal space-y-1 pl-4 text-[13px] leading-relaxed">
            {plan.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ol>
        </div>
      )}

      {effort.length > 0 && (
        <div>
          <div className="mb-1.5 text-[10.5px] font-bold uppercase tracking-[0.12em] text-faint">Effort breakdown</div>
          <ul className="m-0 list-disc space-y-0.5 pl-4 text-[13px]">
            {effort.map((e, i) => (
              <li key={i}>{asText(e)}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export default function HewerCard({ rec }: { rec: HewerResult }) {
  return (
    <ErrorBoundary label="Hewer’s lift read" resetKey={rec}>
      <HewerCardInner rec={rec} />
    </ErrorBoundary>
  );
}

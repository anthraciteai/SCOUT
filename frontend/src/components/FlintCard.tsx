import type { AgentResult } from "../types";
import { asText, asList, COLORS } from "./agentWorkspace";
import ErrorBoundary from "./ErrorBoundary";

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

const GOLD = COLORS.Flint;

function FlintCardInner({ rec }: { rec: FlintResult }) {
  const sparks = Array.isArray(rec.sparks) ? rec.sparks : [];
  const tools = Array.isArray(rec.tools_in_play) ? rec.tools_in_play : [];
  const fake = asList(rec.do_not_fake);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <span className="h-2.5 w-2.5 rounded-full" style={{ background: GOLD, boxShadow: `0 0 8px ${GOLD}` }} />
        <strong className="text-[15px]">Flint</strong>
        <span className="text-[12px] text-faint">· creative toolwright — only your real stack</span>
      </div>

      {rec.persona_read && (
        <p className="m-0 text-[14px] leading-relaxed text-ink">{asText(rec.persona_read)}</p>
      )}

      {tools.length > 0 && (
        <div>
          <div className="mb-1.5 text-[10.5px] font-bold uppercase tracking-[0.12em] text-faint">
            Tools in play
          </div>
          <div className="flex flex-col gap-1.5">
            {tools.map((t, i) => (
              <div
                key={i}
                className="flex flex-wrap items-baseline gap-x-2 text-[13px] leading-relaxed"
                title={t.from_resume || undefined}
              >
                <span className="font-semibold" style={{ color: GOLD }}>
                  {asText(t.tool)}
                </span>
                {t.role_in_this_bid && <span className="text-muted">{asText(t.role_in_this_bid)}</span>}
              </div>
            ))}
          </div>
        </div>
      )}

      {sparks.map((s, i) => (
        <div key={i} className="rounded-xl border border-hair bg-surface2/60 p-3">
          <div className="flex items-start justify-between gap-3">
            <strong className="text-[14px] text-ink">{asText(s.title) || `Spark ${i + 1}`}</strong>
            {(s.originality != null || s.feasibility != null) && (
              <span className="shrink-0 text-[11px] text-faint">
                orig {s.originality ?? "—"} · feas {s.feasibility ?? "—"}
              </span>
            )}
          </div>
          {s.hook && <p className="my-1.5 text-[13px] leading-relaxed text-muted">{asText(s.hook)}</p>}
          {asList(s.how).length > 0 && (
            <ul className="my-1 list-disc space-y-0.5 pl-4 text-[13px]">
              {asList(s.how).map((h, j) => (
                <li key={j}>{h}</li>
              ))}
            </ul>
          )}
          {s.why_only_you && (
            <div className="mt-1 text-[12px] text-faint">Why only you: {asText(s.why_only_you)}</div>
          )}
          {asList(s.tools).length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {asList(s.tools).map((t, j) => (
                <span
                  key={j}
                  className="inline-flex items-center rounded-full border border-hairstrong px-2 py-0.5 text-[11.5px] text-muted"
                >
                  {t}
                </span>
              ))}
            </div>
          )}
        </div>
      ))}

      {rec.left_field && (
        <div className="rounded-xl border p-3" style={{ borderColor: `${GOLD}66`, background: `${GOLD}10` }}>
          <div className="mb-1 text-[10.5px] font-bold uppercase tracking-[0.12em]" style={{ color: GOLD }}>
            Left field
          </div>
          <div className="text-[13px] leading-relaxed">{asText(rec.left_field)}</div>
        </div>
      )}

      {fake.length > 0 && (
        <div>
          <div className="mb-1 text-[10.5px] font-bold uppercase tracking-[0.12em] text-faint">
            Do not fake
          </div>
          <ul className="list-disc space-y-0.5 pl-4 text-[13px] text-muted">
            {fake.map((x, i) => (
              <li key={i}>{x}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export default function FlintCard({ rec }: { rec: FlintResult }) {
  return (
    <ErrorBoundary label="Flint’s sparks" resetKey={rec}>
      <FlintCardInner rec={rec} />
    </ErrorBoundary>
  );
}

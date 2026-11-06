import { useMemo, useRef, useState } from "react";
import {
  buildEvidenceModel,
  colorForReq,
  rgba,
  type EvidenceInput,
} from "../lib/evidence";

export type FitStatus = "meets" | "partial" | "gap";

export interface EvidenceRequirement extends EvidenceInput {
  need: string;
  evidence?: string;
  /** When present, the reader colors by fit and shows the coverage note. */
  status?: FitStatus;
  /** Why it fits (your matched capability) or what's missing. */
  note?: string;
}

const STATUS_COLOR: Record<FitStatus, string> = {
  meets: "#35d07f",
  partial: "#ffc24b",
  gap: "#ff5d5d",
};

const STATUS_LABEL: Record<FitStatus, string> = {
  meets: "You meet this",
  partial: "Partial",
  gap: "Gap",
};

/**
 * Two-pane evidence reader. Left: the extracted requirements. Right: the raw
 * OCR text with each requirement's source sentence highlighted. Hovering either
 * side lights up the other and scrolls the matching sentence into view.
 *
 * When requirements carry a fit `status`, highlights are colored by fit
 * (green = you meet it, amber = partial, red = gap) and the sidebar + hover
 * tooltip explain *why* — turning the source text into a fit heat-map.
 */
export default function EvidenceReader({
  text,
  requirements,
}: {
  text: string;
  requirements: EvidenceRequirement[];
}) {
  const model = useMemo(
    () => buildEvidenceModel(text, requirements),
    [text, requirements]
  );
  const [active, setActive] = useState<number | null>(null);
  const segRefs = useRef<Record<number, HTMLSpanElement | null>>({});

  const hasStatus = requirements.some((r) => r.status);
  const colorFor = (ri: number): string => {
    const st = requirements[ri]?.status;
    return st ? STATUS_COLOR[st] : colorForReq(ri);
  };

  function focusReq(ri: number | null) {
    setActive(ri);
    if (ri == null) return;
    const si = model.segmentByReq[ri]?.[0];
    if (si != null) {
      segRefs.current[si]?.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-[minmax(240px,320px)_1fr] items-start">
      {/* Requirements (color key + hover targets) */}
      <div className="flex flex-col gap-2 md:max-h-[70vh] md:overflow-y-auto pr-1">
        <div className="text-[11px] text-faint font-bold uppercase tracking-[0.1em]">
          {model.locatedCount}/{requirements.length} grounded in the text
        </div>
        {hasStatus && (
          <div className="flex flex-wrap gap-2 pb-1">
            {(Object.keys(STATUS_COLOR) as FitStatus[]).map((st) => (
              <span key={st} className="inline-flex items-center gap-1.5 text-[11px] text-muted">
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: STATUS_COLOR[st] }} />
                {STATUS_LABEL[st]}
              </span>
            ))}
          </div>
        )}
        {requirements.map((r, ri) => {
          const color = colorFor(ri);
          const located = (model.segmentByReq[ri]?.length ?? 0) > 0;
          const on = active === ri;
          return (
            <div
              key={ri}
              onMouseEnter={() => focusReq(ri)}
              onMouseLeave={() => setActive(null)}
              className="rounded-[10px] p-2.5 cursor-pointer transition-colors"
              style={{
                border: `1px solid ${on ? color : "var(--border)"}`,
                background: on ? rgba(color, 0.12) : "var(--surface-2)",
              }}
            >
              <div className="flex items-start gap-2">
                <span
                  className="mt-1 h-2.5 w-2.5 rounded-full flex-none"
                  style={{ background: color }}
                />
                <div className="min-w-0">
                  <div className="flex items-start gap-2">
                    {r.status && (
                      <span
                        className="mt-0.5 shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide"
                        style={{ border: `1px solid ${color}`, color }}
                      >
                        {STATUS_LABEL[r.status]}
                      </span>
                    )}
                    <div className="text-[13px] leading-snug text-ink">{r.need}</div>
                  </div>
                  {r.evidence && (
                    <div className="text-[12px] text-muted italic mt-1">"{r.evidence}"</div>
                  )}
                  {r.note && (
                    <div className="text-[12px] mt-1" style={{ color }}>
                      {r.status === "gap" ? "Missing: " : "Your coverage: "}
                      <span className="text-muted">{r.note}</span>
                    </div>
                  )}
                  {!located && (
                    <div className="text-[11px] text-faint mt-1">
                      no matching sentence found
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Raw OCR with highlighted evidence sentences */}
      <div
        className="rounded-[10px] p-3.5 text-[13px] leading-relaxed whitespace-pre-wrap break-words md:max-h-[70vh] overflow-y-auto"
        style={{ border: "1px solid var(--border)", background: "var(--surface-2)" }}
      >
        {model.segments.map((seg, si) => {
          if (seg.reqs.length === 0) {
            return <span key={si}>{seg.text}</span>;
          }
          const primary = seg.reqs[0];
          const color = colorFor(primary);
          const on = active != null && seg.reqs.includes(active);
          const tip = seg.reqs
            .map((ri) => {
              const r = requirements[ri];
              if (!r) return "";
              const label = r.status ? `[${STATUS_LABEL[r.status]}] ` : "";
              const why = r.note ? ` — ${r.status === "gap" ? "missing" : "you have"}: ${r.note}` : "";
              return `${label}${r.need}${why}`;
            })
            .filter(Boolean)
            .join("\n");
          return (
            <span
              key={si}
              ref={(el) => {
                segRefs.current[si] = el;
              }}
              title={tip}
              onMouseEnter={() => setActive(primary)}
              onMouseLeave={() => setActive(null)}
              className="rounded cursor-help transition-colors"
              style={{
                background: rgba(color, on ? 0.42 : 0.16),
                boxShadow: on ? `inset 0 -2px 0 ${color}` : `inset 0 -2px 0 ${rgba(color, 0.5)}`,
                padding: "0 1px",
              }}
            >
              {seg.text}
            </span>
          );
        })}
      </div>
    </div>
  );
}

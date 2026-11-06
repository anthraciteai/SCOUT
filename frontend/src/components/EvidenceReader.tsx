import { useMemo, useRef, useState } from "react";
import {
  buildEvidenceModel,
  colorForReq,
  rgba,
  type EvidenceInput,
} from "../lib/evidence";

export interface EvidenceRequirement extends EvidenceInput {
  need: string;
  evidence?: string;
}

/**
 * Two-pane evidence reader. Left: the extracted requirements, each in its own
 * color. Right: the raw OCR text with the source sentence for each requirement
 * highlighted in that same color. Hovering either side lights up the other and
 * scrolls the matching sentence into view.
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
        {requirements.map((r, ri) => {
          const color = colorForReq(ri);
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
                  <div className="text-[13px] leading-snug text-ink">{r.need}</div>
                  {r.evidence && (
                    <div className="text-[12px] text-muted italic mt-1">"{r.evidence}"</div>
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
          const color = colorForReq(primary);
          const on = active != null && seg.reqs.includes(active);
          const needs = seg.reqs
            .map((ri) => requirements[ri]?.need)
            .filter(Boolean)
            .join(" • ");
          return (
            <span
              key={si}
              ref={(el) => {
                segRefs.current[si] = el;
              }}
              title={needs}
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

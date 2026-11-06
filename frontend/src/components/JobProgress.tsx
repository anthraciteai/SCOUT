import { useEffect, useRef, useState } from "react";
import type { JobStatus } from "../api";

/**
 * Poll a server-side job's status while `active`, exposing the latest snapshot.
 *
 * The caller flips `active` on when it kicks off (or reconnects to) a heavy
 * local-LLM job — fit, summary, scan — and the backend tracks the real
 * progress, so this keeps working across reloads and new tabs. Polling stops
 * when `active` goes false; the caller typically turns it off once the action's
 * own request resolves, or in a "settled" effect watching `status.state`.
 */
export function useJobPoll<T = unknown>(
  fetcher: () => Promise<JobStatus<T>>,
  active: boolean
): JobStatus<T> | null {
  const [status, setStatus] = useState<JobStatus<T> | null>(null);
  // Keep the latest fetcher without restarting the poll loop every render.
  const fref = useRef(fetcher);
  fref.current = fetcher;

  useEffect(() => {
    if (!active) {
      setStatus(null);
      return;
    }
    let alive = true;
    let timer: number | undefined;
    const tick = async () => {
      try {
        const s = await fref.current();
        if (alive) setStatus(s);
      } catch {
        /* transient — keep polling */
      }
      if (alive) timer = window.setTimeout(tick, 1200);
    };
    tick();
    return () => {
      alive = false;
      if (timer) window.clearTimeout(timer);
    };
  }, [active]);

  return active ? status : null;
}

/**
 * Thin progress bar for a running job. Renders the coarse stage label, a
 * percentage fill, and elapsed seconds. Returns null when there's nothing to
 * show, so callers can drop it in unconditionally:
 *
 *   <JobProgress status={fitJob} label="Scoring fit" />
 */
export default function JobProgress({
  status,
  label,
}: {
  status: JobStatus | null | undefined;
  label?: string;
}) {
  if (!status || status.state === "idle") return null;
  const pct = status.state === "done" ? 100 : Math.max(3, Math.min(99, status.pct || 0));
  const err = status.state === "error";
  const elapsed = status.elapsed != null ? `${Math.round(status.elapsed)}s` : "";
  return (
    <div className="card" style={{ padding: "10px 14px" }}>
      <div
        className="row"
        style={{ justifyContent: "space-between", alignItems: "baseline", gap: 10 }}
      >
        <span style={{ fontSize: 13 }}>
          {err ? (
            <span style={{ color: "var(--red)" }}>
              {label ? `${label}: ` : ""}
              {status.error || "failed"}
            </span>
          ) : (
            <>
              {label && <strong style={{ marginRight: 6 }}>{label}</strong>}
              {status.stage}
            </>
          )}
        </span>
        <span className="meta" style={{ fontSize: 12 }}>
          {err ? "" : elapsed}
        </span>
      </div>
      {!err && (
        <div
          style={{
            marginTop: 8,
            height: 6,
            borderRadius: 999,
            background: "var(--line, #2a2a33)",
            overflow: "hidden",
          }}
        >
          <span
            style={{
              display: "block",
              height: "100%",
              width: `${pct}%`,
              background: "var(--ember, #ff7a1a)",
              borderRadius: 999,
              transition: "width .4s ease",
            }}
          />
        </div>
      )}
      <div className="meta" style={{ fontSize: 11, marginTop: 6 }}>
        Running on the server — safe to leave this page or open another tab; it won't restart or
        double-charge.
      </div>
    </div>
  );
}

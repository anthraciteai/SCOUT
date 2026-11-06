import { useEffect, useState } from "react";
import { AnalysisApi, type BidBriefResponse, type TopicMeta } from "../api";
import { COLORS, ROLES, type AgentName } from "./agentWorkspace";
import JobProgress, { useJobPoll } from "./JobProgress";

function recColor(rec?: string) {
  const v = (rec || "").toUpperCase();
  if (v === "GO") return "#35d07f";
  if (v === "LEAN GO") return "#8fd14f";
  if (v === "LEAN NO-GO") return "#ffc24b";
  if (v === "NO-GO") return "#ff5d5d";
  return "#a3a9b4";
}

/** 1–9 DoD TRL track with a "now" fill and a hollow "target" reach. */
function TrlMeter({ current, target }: { current: number; target: number }) {
  const cur = Math.max(1, Math.min(9, current || 1));
  const tgt = Math.max(cur, Math.min(9, target || cur));
  return (
    <div>
      <div className="flex items-end justify-between">
        <span className="text-[10.5px] font-bold uppercase tracking-[0.12em] text-faint">
          Technology Readiness
        </span>
        <span className="text-[12px] text-muted">
          now <strong className="text-ink">TRL {cur}</strong> → target{" "}
          <strong style={{ color: "#35d07f" }}>TRL {tgt}</strong>
        </span>
      </div>
      <div className="mt-2 flex gap-1">
        {Array.from({ length: 9 }, (_, i) => {
          const n = i + 1;
          const filled = n <= cur;
          const reach = n > cur && n <= tgt;
          return (
            <div key={n} className="flex-1" title={`TRL ${n}`}>
              <div
                className="h-2 rounded-full transition-colors"
                style={{
                  background: filled ? "#ff7a1a" : reach ? "rgba(53,208,127,0.35)" : "var(--surface-2)",
                  border: reach ? "1px solid rgba(53,208,127,0.6)" : "1px solid var(--border)",
                }}
              />
              <div className="mt-1 text-center text-[9px] text-faint">{n}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function BidBrief({
  topicId,
  topicsMeta,
}: {
  topicId: string;
  topicsMeta?: Record<string, TopicMeta>;
}) {
  const [resp, setResp] = useState<BidBriefResponse | null>(null);
  const [active, setActive] = useState(false);
  const [err, setErr] = useState("");
  const job = useJobPoll<BidBriefResponse>(() => AnalysisApi.briefStatus(topicId), active);

  // Reconnect: show a cached brief instantly, and reattach to one already
  // running on the server (another tab / after a reload).
  useEffect(() => {
    let alive = true;
    setResp(null);
    setActive(false);
    AnalysisApi.briefCached(topicId)
      .then((b) => alive && b && setResp(b))
      .catch(() => {});
    AnalysisApi.briefStatus(topicId)
      .then((s) => alive && s.state === "running" && setActive(true))
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [topicId]);

  // When a reconnected run finishes, drop in its result.
  useEffect(() => {
    if (active && job && (job.state === "done" || job.state === "error")) {
      if (job.state === "done" && job.result) setResp(job.result);
      setActive(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job?.state]);

  async function run(force = false) {
    setActive(true);
    setErr("");
    try {
      const data = await AnalysisApi.brief(topicId, topicsMeta, force);
      setResp(data);
    } catch (e: any) {
      setErr(e?.response?.data?.detail || e.message || "Bid brief failed");
    } finally {
      setActive(false);
    }
  }

  const brief = resp?.brief;
  const product = brief?.recommended_product || "";
  const isProduct = product && product.toLowerCase() !== "none";
  const color = isProduct ? COLORS[product as AgentName] || "#ff7a1a" : "#a3a9b4";

  return (
    <div
      className="relative overflow-hidden rounded-2xl border p-5"
      style={{
        borderColor: isProduct ? color : "var(--border)",
        background: "linear-gradient(180deg, var(--surface-2), var(--bg-2))",
        boxShadow: isProduct ? `0 0 0 1px ${color}22, 0 24px 60px -34px ${color}66` : undefined,
      }}
    >
      {isProduct && (
        <span aria-hidden className="absolute inset-x-0 top-0 h-[3px]" style={{ background: color }} />
      )}

      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-[10.5px] font-bold uppercase tracking-[0.12em] text-faint">
            Bid decision brief
          </div>
          <h3 className="m-0 mt-0.5 text-lg font-semibold tracking-tight">
            Which product should we bid — and are we ready?
          </h3>
        </div>
        <button
          className={brief ? "ghost small" : "small"}
          onClick={() => run(Boolean(brief))}
          disabled={active}
        >
          {active ? "Working…" : brief ? "Re-run" : "Recommend a bid"}
        </button>
      </div>

      {err && <div className="mt-3 rounded-xl border border-red/40 bg-red/10 px-3 py-2 text-[13px] text-red">{err}</div>}

      {job && (
        <div className="mt-3">
          <JobProgress status={job} label="Weighing the products" />
        </div>
      )}

      {!brief && !job && (
        <p className="mt-3 max-w-2xl text-[13px] leading-relaxed text-muted">
          Runs all three product voices (Canari, Vein, Davy) plus a lift check, then picks the single
          best product to bid this topic with, says why, lists the work to do, and scores where we
          sit on TRL. One click instead of clicking each voice.
        </p>
      )}

      {brief && brief.raw && (
        <pre className="mt-3 overflow-auto rounded-xl bg-surface2 p-3 text-[12px]">{brief.raw}</pre>
      )}

      {brief && !brief.raw && (
        <div className="mt-4 flex flex-col gap-4">
          {/* verdict line */}
          <div className="flex flex-wrap items-center gap-2.5">
            {isProduct ? (
              <span
                className="inline-flex items-center gap-2 rounded-full px-3 py-1 text-sm font-bold"
                style={{ background: `${color}1c`, border: `1px solid ${color}`, color }}
              >
                <span className="h-2 w-2 rounded-full" style={{ background: color, boxShadow: `0 0 8px ${color}` }} />
                Bid with {product}
              </span>
            ) : (
              <span className="inline-flex items-center rounded-full border border-hairstrong px-3 py-1 text-sm font-bold text-muted">
                No product is a clean fit
              </span>
            )}
            <span
              className="rounded-full px-2.5 py-1 text-[12px] font-bold"
              style={{
                background: `${recColor(brief.recommendation)}1c`,
                border: `1px solid ${recColor(brief.recommendation)}`,
                color: recColor(brief.recommendation),
              }}
            >
              {brief.recommendation || "—"}
            </span>
            {typeof brief.confidence === "number" && (
              <span className="text-[12px] text-muted">{brief.confidence}% confidence</span>
            )}
            {isProduct && (
              <span className="text-[12px] text-faint">· {ROLES[product as AgentName]}</span>
            )}
          </div>

          {brief.why && <p className="m-0 text-[14.5px] leading-relaxed">{brief.why}</p>}

          {/* TRL */}
          {(brief.trl_current || brief.trl_target) && (
            <div className="rounded-xl border border-hair bg-bg2/40 p-3.5">
              <TrlMeter current={brief.trl_current || 1} target={brief.trl_target || 1} />
              {brief.trl_rationale && (
                <p className="mb-0 mt-2.5 text-[12.5px] leading-relaxed text-muted">{brief.trl_rationale}</p>
              )}
            </div>
          )}

          {/* work + gaps */}
          <div className="grid gap-4 sm:grid-cols-2">
            {brief.work_to_do && brief.work_to_do.length > 0 && (
              <div>
                <div className="text-[10.5px] font-bold uppercase tracking-[0.12em] text-faint">
                  What needs to be done
                </div>
                <ol className="mt-2 flex flex-col gap-1.5 pl-0">
                  {brief.work_to_do.map((step, i) => (
                    <li key={i} className="flex gap-2.5 text-[13px] leading-snug">
                      <span
                        className="mt-px inline-flex h-5 w-5 flex-none items-center justify-center rounded-full text-[11px] font-bold"
                        style={{ background: `${color}1c`, color, border: `1px solid ${color}55` }}
                      >
                        {i + 1}
                      </span>
                      <span>{step}</span>
                    </li>
                  ))}
                </ol>
              </div>
            )}
            {brief.key_gaps && brief.key_gaps.length > 0 && (
              <div>
                <div className="text-[10.5px] font-bold uppercase tracking-[0.12em] text-faint">
                  Gaps to close
                </div>
                <ul className="mt-2 flex flex-col gap-1.5 pl-0">
                  {brief.key_gaps.map((g, i) => (
                    <li key={i} className="flex gap-2 text-[13px] leading-snug text-muted">
                      <span className="mt-1.5 h-1.5 w-1.5 flex-none rounded-full bg-amber" />
                      <span>{g}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {/* runners-up */}
          {brief.runners_up && brief.runners_up.length > 0 && (
            <div className="border-t border-hair pt-3">
              <div className="text-[10.5px] font-bold uppercase tracking-[0.12em] text-faint">
                Why not the others
              </div>
              <div className="mt-2 flex flex-col gap-1.5">
                {brief.runners_up.map((r, i) => (
                  <div key={i} className="text-[12.5px] text-muted">
                    <strong className="text-ink">{r.product}:</strong> {r.note}
                  </div>
                ))}
              </div>
            </div>
          )}

          {resp?.model && (
            <div className="text-[11px] text-faint">
              {resp.cached ? "cached" : "fresh"} · {resp.model}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

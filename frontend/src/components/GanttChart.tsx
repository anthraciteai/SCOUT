import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { GanttApi, type GanttData, type GanttRow } from "../api";

/** Color map for persona checkpoint dots — matches PastReviews.tsx. */
const PERSONA_COLORS: Record<string, string> = {
  technical: "#5aa9ff",
  military: "#ff7a1a",
  researcher: "#8a7bff",
};

const STAGE_COLORS: Record<string, string> = {
  watching: "rgba(138, 123, 255, 0.35)",
  drafting: "rgba(255, 122, 26, 0.55)",
  submitted: "rgba(53, 208, 127, 0.55)",
  awarded: "rgba(53, 208, 127, 0.85)",
  not_selected: "rgba(255, 93, 93, 0.55)",
  withdrawn: "rgba(160, 160, 160, 0.45)",
};

function fmtDate(ms?: number | null) {
  if (!ms) return "—";
  return new Date(ms).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "2-digit",
  });
}

/** Fit `bar` into [minMs, maxMs] and return {leftPct, widthPct}. */
function span(start: number | null, end: number | null, minMs: number, maxMs: number) {
  if (!start || !end || end <= start) return null;
  const clip0 = Math.max(start, minMs);
  const clip1 = Math.min(end, maxMs);
  if (clip1 <= clip0) return null;
  const total = maxMs - minMs;
  return {
    leftPct: ((clip0 - minMs) / total) * 100,
    widthPct: ((clip1 - clip0) / total) * 100,
  };
}

/** Marker (single point) percentage across the window. */
function markerPct(at: number | null | undefined, minMs: number, maxMs: number) {
  if (!at || at < minMs || at > maxMs) return null;
  return ((at - minMs) / (maxMs - minMs)) * 100;
}

/** Build a shared [minMs, maxMs] window across every row so the axis is fair.
 * We include prerelease..close plus a small pad, and always include `now`. */
function computeWindow(rows: GanttRow[], now: number) {
  const stamps: number[] = [now];
  for (const r of rows) {
    for (const t of [r.prerelease_ms, r.open_ms, r.close_ms]) {
      if (t) stamps.push(t);
    }
    for (const rv of r.reviews) {
      if (rv.created_ms) stamps.push(rv.created_ms);
    }
    if (r.verdict?.at_ms) stamps.push(r.verdict.at_ms);
  }
  if (stamps.length < 2) {
    // No dates known — show ±30 days around now so the chart isn't empty.
    return { minMs: now - 30 * 86400000, maxMs: now + 30 * 86400000 };
  }
  const raw_min = Math.min(...stamps);
  const raw_max = Math.max(...stamps);
  const pad = Math.max((raw_max - raw_min) * 0.05, 3 * 86400000);
  return { minMs: raw_min - pad, maxMs: raw_max + pad };
}

/** Emit vertical grid ticks at month boundaries. */
function monthTicks(minMs: number, maxMs: number) {
  const ticks: { at: number; label: string }[] = [];
  const start = new Date(minMs);
  start.setDate(1);
  start.setHours(0, 0, 0, 0);
  for (let t = start.getTime(); t < maxMs; ) {
    if (t >= minMs) {
      ticks.push({
        at: t,
        label: new Date(t).toLocaleDateString(undefined, {
          month: "short",
          year: "2-digit",
        }),
      });
    }
    const d = new Date(t);
    d.setMonth(d.getMonth() + 1);
    t = d.getTime();
  }
  return ticks;
}

export default function GanttChart() {
  const [data, setData] = useState<GanttData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    GanttApi.load()
      .then((d) => setData(d))
      .catch((e) => setError(e?.response?.data?.detail || e.message || "Gantt failed"))
      .finally(() => setLoading(false));
  }, []);

  const rows = data?.rows || [];
  const now = data?.now_ms || Date.now();
  const { minMs, maxMs } = useMemo(() => computeWindow(rows, now), [rows, now]);
  const ticks = useMemo(() => monthTicks(minMs, maxMs), [minMs, maxMs]);
  const nowPct = markerPct(now, minMs, maxMs);

  if (loading) return <div className="spinner">Loading deadline gantt…</div>;
  if (error) return <div className="card" style={{ color: "var(--red)" }}>{error}</div>;
  if (rows.length === 0) return null;

  return (
    <div className="card" style={{ padding: 16 }}>
      <div className="row spread" style={{ marginBottom: 10 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 18 }}>Deadline gantt</h2>
          <div className="meta" style={{ marginTop: 2 }}>
            Pre-release → open → close for every tracked topic. Dots are persona
            reviews you've run; the ember dot is the council verdict.
          </div>
        </div>
        <Legend />
      </div>

      {/* Axis */}
      <div style={{ position: "relative", height: 22, marginBottom: 4 }}>
        {ticks.map((t) => {
          const pct = markerPct(t.at, minMs, maxMs);
          if (pct == null) return null;
          return (
            <div
              key={t.at}
              className="meta"
              style={{
                position: "absolute",
                left: `${pct}%`,
                transform: "translateX(-50%)",
                fontSize: 11,
                whiteSpace: "nowrap",
              }}
            >
              {t.label}
            </div>
          );
        })}
      </div>

      {rows.map((r) => (
        <GanttRowView key={r.tracked_id} row={r} minMs={minMs} maxMs={maxMs} nowPct={nowPct} />
      ))}
    </div>
  );
}

function GanttRowView({
  row,
  minMs,
  maxMs,
  nowPct,
}: {
  row: GanttRow;
  minMs: number;
  maxMs: number;
  nowPct: number | null;
}) {
  const preOpen = span(row.prerelease_ms, row.open_ms, minMs, maxMs);
  const openClose = span(row.open_ms, row.close_ms, minMs, maxMs);
  // If we only know one of open/close, still draw a hair-line so the row isn't blank
  const singleOpen = markerPct(row.open_ms, minMs, maxMs);
  const singleClose = markerPct(row.close_ms, minMs, maxMs);

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "220px 1fr 90px",
        alignItems: "center",
        gap: 12,
        padding: "8px 0",
        borderTop: "1px solid var(--panel-2)",
      }}
    >
      <div style={{ minWidth: 0 }}>
        <Link
          to={`/topic/${row.topic_id}`}
          className="topic-title"
          style={{
            display: "block",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            fontSize: 13,
          }}
          title={row.title || row.topic_code}
        >
          {row.topic_code || row.topic_id}
        </Link>
        <div className="meta" style={{ fontSize: 11 }}>
          {row.component || "—"} · <StageBadge stage={row.stage} />
        </div>
      </div>

      <div
        style={{
          position: "relative",
          height: 26,
          background: "var(--panel-2)",
          borderRadius: 6,
        }}
      >
        {nowPct != null && (
          <div
            title="Today"
            style={{
              position: "absolute",
              top: -2,
              bottom: -2,
              left: `${nowPct}%`,
              width: 1,
              background: "var(--ember)",
              opacity: 0.7,
            }}
          />
        )}
        {preOpen && (
          <div
            title={`Pre-release: ${fmtDate(row.prerelease_ms)} → ${fmtDate(row.open_ms)}`}
            style={{
              position: "absolute",
              top: 6,
              bottom: 6,
              left: `${preOpen.leftPct}%`,
              width: `${preOpen.widthPct}%`,
              background: "rgba(138, 123, 255, 0.35)",
              border: "1px dashed rgba(138, 123, 255, 0.7)",
              borderRadius: 4,
            }}
          />
        )}
        {openClose ? (
          <div
            title={`Open: ${fmtDate(row.open_ms)} → ${fmtDate(row.close_ms)}`}
            style={{
              position: "absolute",
              top: 3,
              bottom: 3,
              left: `${openClose.leftPct}%`,
              width: `${openClose.widthPct}%`,
              background: STAGE_COLORS[row.stage] || "rgba(255, 122, 26, 0.5)",
              borderRadius: 4,
              boxShadow: "inset 0 0 0 1px rgba(255,255,255,0.05)",
            }}
          />
        ) : singleOpen != null ? (
          <div
            title={`Opens ${fmtDate(row.open_ms)}`}
            style={{
              position: "absolute",
              top: 3,
              bottom: 3,
              left: `${singleOpen}%`,
              width: 3,
              background: STAGE_COLORS[row.stage] || "rgba(255, 122, 26, 0.6)",
              borderRadius: 2,
            }}
          />
        ) : null}
        {singleClose != null && openClose && (
          <div
            title={`Closes ${fmtDate(row.close_ms)}`}
            style={{
              position: "absolute",
              top: -3,
              bottom: -3,
              left: `${singleClose}%`,
              width: 2,
              background: "var(--red)",
            }}
          />
        )}
        {row.reviews.map((rv) => {
          const pct = markerPct(rv.created_ms, minMs, maxMs);
          if (pct == null) return null;
          return (
            <div
              key={rv.id}
              title={`${rv.persona} review · ${rv.created_at ? new Date(rv.created_at).toLocaleString() : ""}`}
              style={{
                position: "absolute",
                top: "50%",
                left: `${pct}%`,
                transform: "translate(-50%, -50%)",
                width: 10,
                height: 10,
                borderRadius: "50%",
                background: PERSONA_COLORS[rv.persona] || "#aaa",
                border: "2px solid var(--panel)",
              }}
            />
          );
        })}
        {row.verdict?.at_ms && (
          <div
            title={`Council: ${row.verdict.recommendation || "—"} · fit ${row.verdict.fit_score ?? "—"}`}
            style={{
              position: "absolute",
              top: 0,
              left: `${markerPct(row.verdict.at_ms, minMs, maxMs)}%`,
              transform: "translateX(-50%)",
              width: 0,
              height: 0,
              borderLeft: "6px solid transparent",
              borderRight: "6px solid transparent",
              borderTop: "8px solid var(--ember)",
            }}
          />
        )}
      </div>

      <div className="meta" style={{ fontSize: 11, textAlign: "right" }}>
        {row.close_ms ? (
          <span title={new Date(row.close_ms).toLocaleString()}>
            close {fmtDate(row.close_ms)}
          </span>
        ) : (
          <span>no close date</span>
        )}
      </div>
    </div>
  );
}

function StageBadge({ stage }: { stage: string }) {
  return (
    <span
      style={{
        display: "inline-block",
        width: 8,
        height: 8,
        borderRadius: 2,
        marginRight: 4,
        background: STAGE_COLORS[stage] || "var(--muted)",
        verticalAlign: "middle",
      }}
    />
  );
}

function Legend() {
  return (
    <div className="row" style={{ gap: 10, alignItems: "center", flexWrap: "wrap", fontSize: 11 }}>
      <LegendSwatch color="rgba(138, 123, 255, 0.5)" label="pre-release" dashed />
      <LegendSwatch color="rgba(255, 122, 26, 0.6)" label="open window" />
      <LegendSwatch color="var(--red)" label="close" bar />
      <LegendDot color={PERSONA_COLORS.technical} label="technical" />
      <LegendDot color={PERSONA_COLORS.military} label="military" />
      <LegendDot color={PERSONA_COLORS.researcher} label="researcher" />
      <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
        <span
          style={{
            width: 0,
            height: 0,
            borderLeft: "5px solid transparent",
            borderRight: "5px solid transparent",
            borderTop: "7px solid var(--ember)",
          }}
        />
        council
      </span>
    </div>
  );
}

function LegendSwatch({
  color,
  label,
  dashed,
  bar,
}: {
  color: string;
  label: string;
  dashed?: boolean;
  bar?: boolean;
}) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
      <span
        style={{
          width: bar ? 2 : 16,
          height: bar ? 12 : 10,
          background: color,
          borderRadius: bar ? 1 : 3,
          border: dashed ? "1px dashed rgba(255,255,255,0.35)" : undefined,
        }}
      />
      {label}
    </span>
  );
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
      <span
        style={{
          width: 8,
          height: 8,
          borderRadius: "50%",
          background: color,
        }}
      />
      {label}
    </span>
  );
}

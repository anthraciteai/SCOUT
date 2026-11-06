import { useMemo } from "react";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import type { MatchItem } from "../types";

// Bucket thresholds match the "big enough to be worth writing a proposal" intuition.
// Anything under OK collapses into the grey slice so the eye lands on real matches.
export interface Bucket {
  key: "strong" | "good" | "ok" | "weak";
  label: string;
  min: number;
  color: string;
  hint: string;
}

export const BUCKETS: Bucket[] = [
  { key: "strong", label: "Strong", min: 75, color: "#ff7a1a", hint: "≥ 75 — write today" },
  { key: "good", label: "Good", min: 60, color: "#35d07f", hint: "60–74 — solid fit" },
  { key: "ok", label: "OK", min: 40, color: "#8a7bff", hint: "40–59 — worth a look" },
  { key: "weak", label: "Not great", min: 0, color: "#3a3a44", hint: "< 40 — long tail" },
];

export function bucketFor(score: number): Bucket {
  for (const b of BUCKETS) {
    if (score >= b.min) return b;
  }
  return BUCKETS[BUCKETS.length - 1];
}

export function MatchBreakdown({ matches }: { matches: MatchItem[] }) {
  const counts = useMemo(() => {
    const out: Record<string, number> = { strong: 0, good: 0, ok: 0, weak: 0 };
    for (const m of matches) {
      out[bucketFor(m.score || 0).key] += 1;
    }
    return out;
  }, [matches]);

  const total = matches.length;
  const data = BUCKETS.map((b) => ({
    name: b.label,
    value: counts[b.key],
    color: b.color,
    hint: b.hint,
  }));
  const nonZero = data.filter((d) => d.value > 0);

  if (!total) {
    return null;
  }

  return (
    <div className="card" style={{ marginBottom: 12 }}>
      <div className="row spread" style={{ alignItems: "center", gap: 20 }}>
        <div style={{ width: 180, height: 160, position: "relative", flexShrink: 0 }}>
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Tooltip
                contentStyle={{
                  background: "#1a1a20",
                  border: "1px solid #2a2a34",
                  borderRadius: 6,
                  fontSize: 12,
                  color: "#e6e6ea",
                }}
                formatter={(value: number, name: string) => [`${value} topics`, name]}
              />
              <Pie
                data={nonZero.length ? nonZero : [{ name: "empty", value: 1, color: "#3a3a44" }]}
                dataKey="value"
                cx="50%"
                cy="50%"
                innerRadius={48}
                outerRadius={72}
                paddingAngle={2}
                stroke="none"
                startAngle={90}
                endAngle={-270}
              >
                {(nonZero.length ? nonZero : [{ color: "#3a3a44" }]).map((d, i) => (
                  <Cell key={i} fill={d.color} />
                ))}
              </Pie>
            </PieChart>
          </ResponsiveContainer>
          <div
            style={{
              position: "absolute",
              inset: 0,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              pointerEvents: "none",
            }}
          >
            <div style={{ fontSize: 28, fontWeight: 700, lineHeight: 1 }}>{total}</div>
            <div className="meta" style={{ fontSize: 11 }}>
              open topics
            </div>
          </div>
        </div>

        <div className="grow" style={{ minWidth: 0 }}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 8 }}>
            {BUCKETS.map((b) => {
              const n = counts[b.key];
              const pct = total ? Math.round((100 * n) / total) : 0;
              const active = n > 0;
              return (
                <div
                  key={b.key}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    padding: "6px 8px",
                    borderRadius: 6,
                    background: active ? "rgba(255,255,255,0.03)" : "transparent",
                    opacity: active ? 1 : 0.55,
                  }}
                >
                  <span
                    style={{
                      width: 12,
                      height: 12,
                      borderRadius: 3,
                      background: b.color,
                      flexShrink: 0,
                    }}
                  />
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                      <strong style={{ fontSize: 13 }}>{b.label}</strong>
                      <span className="meta" style={{ fontSize: 12 }}>
                        {n} · {pct}%
                      </span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

export default MatchBreakdown;

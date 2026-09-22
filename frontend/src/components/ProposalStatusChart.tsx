import { useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Proposal } from "../types";

const STATUS_META: Record<string, { color: string; label: string; order: number }> = {
  draft: { color: "#8a7bff", label: "Draft", order: 0 },
  submitted: { color: "#ff7a1a", label: "Submitted", order: 1 },
  awarded: { color: "#35d07f", label: "Awarded", order: 2 },
  not_selected: { color: "#3a3a44", label: "Not selected", order: 3 },
};

const KNOWN = Object.keys(STATUS_META);

function statusFor(s?: string) {
  const key = (s || "draft").toLowerCase();
  return STATUS_META[key] || { color: "#3a3a44", label: key, order: 99 };
}

export default function ProposalStatusChart({
  proposals,
  reviewCounts,
}: {
  proposals: Proposal[];
  /** proposal_id -> total review count. Drives the "reviewed" overlay bar. */
  reviewCounts: Record<number, number>;
}) {
  const data = useMemo(() => {
    const counts: Record<string, { count: number; reviewed: number }> = {};
    for (const k of KNOWN) counts[k] = { count: 0, reviewed: 0 };
    for (const p of proposals) {
      const key = KNOWN.includes((p.status || "draft").toLowerCase())
        ? p.status.toLowerCase()
        : "draft";
      counts[key].count += 1;
      if ((reviewCounts[p.id] || 0) > 0) counts[key].reviewed += 1;
    }
    return KNOWN.map((k) => ({
      key: k,
      label: STATUS_META[k].label,
      color: STATUS_META[k].color,
      count: counts[k].count,
      reviewed: counts[k].reviewed,
      unreviewed: counts[k].count - counts[k].reviewed,
    }));
  }, [proposals, reviewCounts]);

  const total = data.reduce((s, d) => s + d.count, 0);
  const reviewedTotal = data.reduce((s, d) => s + d.reviewed, 0);

  if (!total) {
    return (
      <div className="card" style={{ marginBottom: 12 }}>
        <div className="meta">
          No proposals yet. Draft one on the right, then run Technical / Military / Researcher
          reviews — every run is snapshotted so you can compare.
        </div>
      </div>
    );
  }

  return (
    <div className="card" style={{ marginBottom: 12 }}>
      <div className="row spread" style={{ alignItems: "baseline", marginBottom: 6 }}>
        <h3 style={{ margin: 0 }}>Proposals at a glance</h3>
        <span className="meta">
          {total} proposals · {reviewedTotal} have persona reviews
        </span>
      </div>
      <div style={{ width: "100%", height: 160 }}>
        <ResponsiveContainer>
          <BarChart data={data} barCategoryGap={12}>
            <CartesianGrid stroke="#22222c" vertical={false} />
            <XAxis dataKey="label" stroke="#8a8f9a" fontSize={12} tickLine={false} />
            <YAxis stroke="#8a8f9a" fontSize={12} allowDecimals={false} width={28} />
            <Tooltip
              contentStyle={{
                background: "#1a1a20",
                border: "1px solid #2a2a34",
                borderRadius: 6,
                fontSize: 12,
                color: "#e6e6ea",
              }}
              formatter={(value: number, name: string) => [`${value}`, name]}
            />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="reviewed" stackId="s" name="Has persona reviews" radius={[0, 0, 4, 4]}>
              {data.map((d, i) => (
                <Cell key={i} fill={d.color} />
              ))}
            </Bar>
            <Bar
              dataKey="unreviewed"
              stackId="s"
              name="Not yet reviewed"
              radius={[4, 4, 0, 0]}
            >
              {data.map((d, i) => (
                <Cell key={i} fill={`${d.color}44`} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export { statusFor };

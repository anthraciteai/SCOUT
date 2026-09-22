import { useMemo } from "react";
import {
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Topic } from "../types";

// Anthracite-web palette so all charts read as the same family.
const PALETTE = ["#ff7a1a", "#35d07f", "#8a7bff", "#ffc24b", "#e0704f", "#c98b3a", "#a3a9b4"];

export default function ComponentBreakdown({
  topics,
  maxBars = 8,
}: {
  topics: Topic[];
  maxBars?: number;
}) {
  const data = useMemo(() => {
    const counts = new Map<string, number>();
    for (const t of topics) {
      const key = (t.component || t.program || "Unknown").trim() || "Unknown";
      counts.set(key, (counts.get(key) || 0) + 1);
    }
    return [...counts.entries()]
      .map(([key, count]) => ({ key, count }))
      .sort((a, b) => b.count - a.count)
      .slice(0, maxBars);
  }, [topics, maxBars]);

  if (!data.length) return null;

  return (
    <div className="card" style={{ marginBottom: 12 }}>
      <div className="row spread" style={{ alignItems: "baseline", marginBottom: 6 }}>
        <h3 style={{ margin: 0 }}>What's on the wire</h3>
        <span className="meta">
          {topics.length} topics · top {data.length} components
        </span>
      </div>
      <div style={{ width: "100%", height: 140 }}>
        <ResponsiveContainer>
          <BarChart data={data} layout="vertical" margin={{ left: 8, right: 20 }}>
            <XAxis type="number" stroke="#8a8f9a" fontSize={11} allowDecimals={false} />
            <YAxis
              dataKey="key"
              type="category"
              stroke="#8a8f9a"
              fontSize={11}
              width={90}
              tickLine={false}
            />
            <Tooltip
              contentStyle={{
                background: "#1a1a20",
                border: "1px solid #2a2a34",
                borderRadius: 6,
                fontSize: 12,
                color: "#e6e6ea",
              }}
              formatter={(value: number) => [`${value} topics`, "count"]}
            />
            <Bar dataKey="count" radius={[0, 4, 4, 0]}>
              {data.map((_, i) => (
                <Cell key={i} fill={PALETTE[i % PALETTE.length]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

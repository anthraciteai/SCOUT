import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { defineChart, dot } from "@tanstack/charts";
import { scaleLinear } from "@tanstack/charts/scales/linear";
import { tooltip as tooltipExtension } from "@tanstack/charts/tooltip";
import { Chart } from "@tanstack/charts/react";
import { sqrtRadiusScale, type TopicPoint } from "../lib/opportunity";

/**
 * Opportunity map: inbox match score (x) vs Council fit (y), each topic sized
 * by its matched-signal scope with an explicit square-root radius scale, and
 * colored by DoD component. The original TopicPoint row rides along on every
 * dot so tooltip + focus/select callbacks are fully typed.
 */
export default function TopicScatter({ points }: { points: TopicPoint[] }) {
  const navigate = useNavigate();
  const [hovered, setHovered] = useState<TopicPoint | null>(null);

  const definition = useMemo(() => {
    // Explicit sqrt radius scale over the scope (matched-signal) counts.
    const rScale = sqrtRadiusScale(points.map((p) => p.scope));
    return defineChart({
      marks: [
        dot(points, {
          x: "matchScore",
          y: "fitScore",
          color: "component", // categorical → colored by segment
          r: (d) => d.scope, // sized by scope …
          rScale, // … through the sqrt scale
          key: "topicId",
          fillOpacity: 0.82,
          stroke: "#0a0b0d",
          strokeWidth: 1,
        }),
      ],
      scales: {
        // Compact linear scales let TanStack Charts infer both domains.
        x: {
          scale: scaleLinear,
          nice: true,
          grid: true,
          axis: { label: "Inbox match score" },
        },
        y: {
          scale: scaleLinear,
          nice: true,
          grid: true,
          axis: { label: "Council fit score" },
        },
      },
      tooltip: tooltipExtension,
    });
  }, [points]);

  if (points.length === 0) {
    return (
      <p className="meta">
        No topics have both a match and a Council fit yet. Run Council on a few
        ranked topics and they'll plot here.
      </p>
    );
  }

  return (
    <div>
      <Chart<TopicPoint, number, number>
        definition={definition}
        ariaLabel="SBIR topics plotted by inbox match score on the x axis versus Council fit score on the y axis, each dot sized by its matched-signal scope and colored by DoD component"
        aspectRatio={2.1}
        className="w-full"
        onFocusChange={(point) => setHovered(point?.datum ?? null)}
        onSelect={(point) => {
          if (point) navigate(`/work/${point.datum.topicId}`);
        }}
      />
      <div className="meta mt-2 min-h-[1.2em]">
        {hovered ? (
          <>
            <strong className="text-ink">{hovered.topicCode}</strong> —{" "}
            {hovered.title} · match {hovered.matchScore} · fit {hovered.fitScore} ·{" "}
            {hovered.scope} signals · {hovered.component}
            {hovered.recommendation ? ` · ${hovered.recommendation}` : ""}
          </>
        ) : (
          <>Hover a dot for details · click to open its workspace · x=match, y=fit, size=scope, color=component</>
        )}
      </div>
    </div>
  );
}

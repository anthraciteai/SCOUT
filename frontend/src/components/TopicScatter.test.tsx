import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import TopicScatter from "./TopicScatter";
import type { TopicPoint } from "../lib/opportunity";

function renderScatter(points: TopicPoint[]) {
  return render(
    <MemoryRouter>
      <TopicScatter points={points} />
    </MemoryRouter>
  );
}

const sample: TopicPoint[] = [
  {
    topicId: "t1",
    topicCode: "AF251-001",
    title: "Edge autonomy",
    component: "AF",
    matchScore: 82,
    fitScore: 71,
    scope: 6,
    recommendation: "LEAN GO",
  },
  {
    topicId: "t2",
    topicCode: "ARM26-010",
    title: "Swarm C2",
    component: "ARMY",
    matchScore: 64,
    fitScore: 55,
    scope: 3,
  },
];

describe("TopicScatter", () => {
  it("shows an empty state when there are no points", () => {
    renderScatter([]);
    expect(screen.getByText(/No topics have both a match and a Council fit/i)).toBeInTheDocument();
  });

  it("mounts an accessible chart with the helper caption when given points", () => {
    renderScatter(sample);
    // The React adapter renders an SVG carrying our ariaLabel.
    expect(
      screen.getByLabelText(/plotted by inbox match score .* versus Council fit score/i)
    ).toBeInTheDocument();
    expect(screen.getByText(/x=match, y=fit, size=scope, color=component/i)).toBeInTheDocument();
  });
});

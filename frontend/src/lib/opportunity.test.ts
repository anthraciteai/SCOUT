import { describe, expect, it } from "vitest";
import { buildTopicPoints, sqrtRadiusScale, type FitVerdict } from "./opportunity";
import type { MatchItem } from "../types";

function match(partial: Partial<MatchItem>): MatchItem {
  return {
    id: 1,
    topic_id: "t1",
    topic_code: "AF251-001",
    title: "Autonomy",
    component: "ARMY",
    program: "SBIR",
    score: 80,
    reasons: ["a", "b"],
    queries: [],
    phrases: ["x", "y", "z"],
    ...partial,
  } as MatchItem;
}

describe("sqrtRadiusScale", () => {
  it("maps 0 (or missing) to the minimum radius", () => {
    const scale = sqrtRadiusScale([1, 4, 9], 4, 22);
    expect(scale(0)).toBe(4);
    expect(scale(Number.NaN)).toBe(4);
    expect(scale(-5)).toBe(4);
  });

  it("maps the domain max to the maximum radius", () => {
    const scale = sqrtRadiusScale([1, 4, 9], 4, 22);
    expect(scale(9)).toBeCloseTo(22, 6);
  });

  it("is a square-root (not linear) mapping", () => {
    const scale = sqrtRadiusScale([0, 100], 0, 10);
    // sqrt(25/100) = 0.5 → half the range, which linear would NOT give (0.25).
    expect(scale(25)).toBeCloseTo(5, 6);
  });

  it("clamps values above the domain max to the max radius", () => {
    const scale = sqrtRadiusScale([4], 4, 22);
    expect(scale(99)).toBe(22);
  });

  it("is monotonic non-decreasing", () => {
    const scale = sqrtRadiusScale([1, 10], 3, 20);
    const a = scale(2);
    const b = scale(5);
    const c = scale(9);
    expect(a).toBeLessThanOrEqual(b);
    expect(b).toBeLessThanOrEqual(c);
  });

  it("handles an empty domain without throwing", () => {
    const scale = sqrtRadiusScale([], 4, 22);
    expect(Number.isFinite(scale(1))).toBe(true);
  });
});

describe("buildTopicPoints", () => {
  const fit = new Map<string, FitVerdict>([
    ["t1", { fit_score: 72, recommendation: "LEAN GO" }],
    ["t3", { fit_score: 0, recommendation: "NO-GO" }],
  ]);

  it("drops topics with no Council fit", () => {
    const pts = buildTopicPoints(
      [match({ topic_id: "t1" }), match({ topic_id: "t2" })],
      fit
    );
    expect(pts.map((p) => p.topicId)).toEqual(["t1"]);
  });

  it("keeps a fit score of exactly 0 (only null/undefined are dropped)", () => {
    const pts = buildTopicPoints([match({ topic_id: "t3", score: 40 })], fit);
    expect(pts).toHaveLength(1);
    expect(pts[0].fitScore).toBe(0);
    expect(pts[0].recommendation).toBe("NO-GO");
  });

  it("maps axes, scope (phrases + reasons) and rounds scores", () => {
    const pts = buildTopicPoints(
      [match({ topic_id: "t1", score: 80.6, phrases: ["x", "y", "z"], reasons: ["a", "b"] })],
      fit
    );
    expect(pts[0]).toMatchObject({
      topicId: "t1",
      component: "ARMY",
      matchScore: 81,
      fitScore: 72,
      scope: 5,
    });
  });

  it("falls back to sensible defaults for missing fields", () => {
    const pts = buildTopicPoints(
      [match({ topic_id: "t1", component: undefined, title: undefined, phrases: undefined, reasons: [] })],
      fit
    );
    expect(pts[0].component).toBe("Other");
    expect(pts[0].scope).toBe(0);
  });
});

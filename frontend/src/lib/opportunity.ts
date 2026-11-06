// Pure data transforms for the opportunity scatter. Kept framework-free so
// they can be unit/regression tested without mounting a chart.
import type { MatchItem } from "../types";

/** One plotted SBIR topic. The original-ish row is preserved for typed
 *  tooltip + focus callbacks on the chart. */
export interface TopicPoint {
  topicId: string;
  topicCode: string;
  title: string;
  component: string; // color / segment
  matchScore: number; // x — inbox ranker, 0..100
  fitScore: number; // y — Council fit, 0..100
  scope: number; // size — matched-signal count (keywords + reasons)
  recommendation?: string;
}

/** Latest-council verdict keyed by topic id (subset of AnalysisRun). */
export interface FitVerdict {
  fit_score?: number | null;
  recommendation?: string;
}

/**
 * Explicit square-root radius scale. Area ∝ value (perceptually correct for
 * sizing dots) by taking the sqrt of the normalized value before mapping into
 * the [rMin, rMax] pixel range. Returns a plain numeric scale function, which
 * is exactly what TanStack Charts' `rScale` accepts.
 */
export function sqrtRadiusScale(
  values: readonly number[],
  rMin = 4,
  rMax = 22
): (value: number) => number {
  const positives = values.filter((v) => Number.isFinite(v) && v > 0);
  const max = positives.length ? Math.max(...positives) : 1;
  return (value: number) => {
    const safe = Number.isFinite(value) && value > 0 ? value : 0;
    const t = Math.sqrt(safe / max); // <- the square-root step
    return rMin + (rMax - rMin) * Math.min(1, t);
  };
}

/**
 * Join inbox matches (match score, component, signals) with their latest
 * Council verdict (fit score) into chart points. Topics without a Council fit
 * are dropped — the scatter is match-vs-fit, so both axes must be real.
 */
export function buildTopicPoints(
  matches: readonly MatchItem[],
  fitByTopic: Map<string, FitVerdict>
): TopicPoint[] {
  const points: TopicPoint[] = [];
  for (const m of matches) {
    const verdict = fitByTopic.get(m.topic_id);
    const fit = verdict?.fit_score;
    if (fit == null) continue;
    points.push({
      topicId: m.topic_id,
      topicCode: m.topic_code || m.topic_id,
      title: m.title || "",
      component: m.component || "Other",
      matchScore: Math.round(m.score ?? 0),
      fitScore: Math.round(fit),
      scope: (m.phrases?.length ?? 0) + (m.reasons?.length ?? 0),
      recommendation: verdict?.recommendation,
    });
  }
  return points;
}

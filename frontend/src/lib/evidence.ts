// Ground each extracted requirement back to the sentence in the raw OCR text
// it was derived from, so the reader can hover either side and see the link.
//
// Pure + framework-free so the matching is unit-testable.

const STOP = new Set([
  "the", "and", "for", "with", "that", "this", "shall", "must", "will", "are",
  "was", "were", "from", "into", "than", "then", "its", "has", "have", "had",
  "which", "such", "can", "may", "not", "all", "any", "per", "via", "use",
  "used", "using", "system", "systems", // generic filler that over-matches
]);

/** Significant words (lowercased, 3+ chars, de-noised) used for overlap. */
export function tokenize(s: string): string[] {
  return (s.toLowerCase().match(/[a-z0-9]{3,}/g) || []).filter((t) => !STOP.has(t));
}

/**
 * Split text into sentence-ish segments. Guarantees the segments concatenate
 * back to the exact original text (so highlighting never drops characters).
 * A segment ends right after a sentence terminator or a newline.
 */
export function splitSegments(text: string): string[] {
  const segs: string[] = [];
  let cur = "";
  for (const ch of text) {
    cur += ch;
    if (ch === "\n" || ch === "." || ch === "!" || ch === "?") {
      segs.push(cur);
      cur = "";
    }
  }
  if (cur) segs.push(cur);
  return segs;
}

export interface EvidenceSegment {
  text: string;
  /** Requirement indices this segment is evidence for (usually 0 or 1). */
  reqs: number[];
}

export interface EvidenceModel {
  segments: EvidenceSegment[];
  /** For each requirement: the segment indices that back it (for scroll/focus). */
  segmentByReq: number[][];
  /** How many requirements were located in the text. */
  locatedCount: number;
}

export interface EvidenceInput {
  evidence?: string;
}

interface BuildOpts {
  minShared?: number; // require at least this many shared significant tokens
  minFrac?: number; // and this fraction of the evidence's tokens present
}

/**
 * Locate each requirement's evidence quote in the OCR text by token overlap
 * (robust to LLM paraphrase / OCR noise, unlike exact substring search).
 * Each requirement lights its single best-matching segment; a segment may back
 * more than one requirement.
 */
export function buildEvidenceModel(
  text: string,
  requirements: readonly EvidenceInput[],
  opts: BuildOpts = {}
): EvidenceModel {
  const minShared = opts.minShared ?? 2;
  const minFrac = opts.minFrac ?? 0.4;

  const rawSegs = splitSegments(text || "");
  const segTokens = rawSegs.map((s) => new Set(tokenize(s)));
  const segReqs: number[][] = rawSegs.map(() => []);
  const segmentByReq: number[][] = requirements.map(() => []);

  requirements.forEach((req, ri) => {
    const query = Array.from(new Set(tokenize(req.evidence || "")));
    if (query.length === 0) return;

    let bestSeg = -1;
    let bestFrac = 0;
    let bestShared = 0;
    for (let si = 0; si < rawSegs.length; si++) {
      const toks = segTokens[si];
      if (toks.size === 0) continue;
      let shared = 0;
      for (const q of query) if (toks.has(q)) shared++;
      const frac = shared / query.length;
      if (
        shared >= minShared &&
        frac >= minFrac &&
        (frac > bestFrac || (frac === bestFrac && shared > bestShared))
      ) {
        bestSeg = si;
        bestFrac = frac;
        bestShared = shared;
      }
    }

    if (bestSeg >= 0) {
      segReqs[bestSeg].push(ri);
      segmentByReq[ri].push(bestSeg);
    }
  });

  const segments = rawSegs.map((t, i) => ({ text: t, reqs: segReqs[i] }));
  const locatedCount = segmentByReq.filter((segs) => segs.length > 0).length;
  return { segments, segmentByReq, locatedCount };
}

/** Distinct, on-brand-ish highlight palette; cycles if there are many reqs. */
export const EVIDENCE_PALETTE = [
  "#ff7a1a", // ember
  "#35d07f", // canari
  "#8a7bff", // davy
  "#ffc24b", // gold
  "#4fc3f7", // sky
  "#ff6b9d", // pink
  "#9ccc65", // lime
  "#ff8a65", // coral
  "#4dd0e1", // teal
  "#ba68c8", // violet
] as const;

export function colorForReq(i: number): string {
  return EVIDENCE_PALETTE[i % EVIDENCE_PALETTE.length];
}

/** Hex (#rrggbb) → rgba() string at the given alpha. */
export function rgba(hex: string, alpha: number): string {
  const h = hex.replace("#", "");
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

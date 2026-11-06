export const RANK_WARN =
  "Re-ranking scores every open SBIR against your current resume and refreshes cached matches. This can take several minutes. Continue?";

export function confirmRerank(): boolean {
  return window.confirm(RANK_WARN);
}

// Scores are an HONEST absolute blend (keyword overlap + phrase Jaccard +
// stretched embedding cosine) — no longer rescaled so the top always hits 100.
// Real top-of-inbox matches land ~30-40; a 35+ means keyword, tag, and strong
// semantic signal all fired, which is as close to a slam dunk as DSIP gets.
export function scoreClass(n: number) {
  if (n >= 35) return "green";
  if (n >= 20) return "yellow";
  return "muted";
}

export function matchBadge(n: number): { text: string; cls: string } | null {
  if (n >= 35) return { text: "Strong match", cls: "green" };
  if (n >= 20) return { text: "Match", cls: "yellow" };
  if (n > 0) return { text: `${Math.round(n)}`, cls: "muted" };
  return null;
}

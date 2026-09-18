export const RANK_WARN =
  "Re-ranking scores every open SBIR against your current resume and refreshes cached matches. This can take several minutes. Continue?";

export function confirmRerank(): boolean {
  return window.confirm(RANK_WARN);
}

export function scoreClass(n: number) {
  if (n >= 40) return "green";
  if (n >= 20) return "yellow";
  return "muted";
}

export function matchBadge(n: number): { text: string; cls: string } | null {
  if (n >= 40) return { text: "Strong match", cls: "green" };
  if (n >= 20) return { text: "Match", cls: "yellow" };
  if (n > 0) return { text: `${Math.round(n)}`, cls: "muted" };
  return null;
}

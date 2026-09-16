/**
 * Minimal HTML sanitizer for rendering DSIP-provided rich text (questions,
 * objectives). Removes scripts/styles/event handlers, javascript: URLs, and
 * inline color/background styles (which would be invisible on the dark theme).
 */
export function sanitizeHtml(html: string): string {
  if (!html) return "";
  return html
    .replace(/<\s*script[^>]*>[\s\S]*?<\s*\/\s*script>/gi, "")
    .replace(/<\s*style[^>]*>[\s\S]*?<\s*\/\s*style>/gi, "")
    .replace(/\son\w+\s*=\s*"[^"]*"/gi, "")
    .replace(/\son\w+\s*=\s*'[^']*'/gi, "")
    .replace(/\sstyle\s*=\s*"[^"]*"/gi, "")
    .replace(/\sstyle\s*=\s*'[^']*'/gi, "")
    .replace(/javascript:/gi, "");
}

/** DSIP answers are stored as a JSON string: {"content": "<html>", "length": N}. */
export function parseAnswer(answer: unknown): string {
  if (typeof answer !== "string") return "";
  try {
    const obj = JSON.parse(answer);
    if (obj && typeof obj === "object" && "content" in obj) {
      return String((obj as { content?: unknown }).content ?? "");
    }
  } catch {
    /* not JSON - fall through */
  }
  return answer;
}

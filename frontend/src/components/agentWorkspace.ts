/** Product voices map that product to this SBIR. People voices (Collier, Hewer, Flint) stay people. */

export const ORDER = ["Canari", "Vein", "Anthracite", "Collier", "Hewer", "Flint", "Davy"] as const;
export type AgentName = (typeof ORDER)[number];

export const ROLES: Record<AgentName, string> = {
  Canari: "Canari the product",
  Vein: "Vein as a product",
  Anthracite: "Business development",
  Collier: "Who to add (teaming)",
  Hewer: "Heavy lift + adaptation",
  Flint: "Creative — your tools, unexpected uses",
  Davy: "Davy — voice-activated C2",
};

export const COLORS: Record<AgentName, string> = {
  Canari: "#35d07f", // green — matches anthracite-web
  Vein: "#ff7a1a", // ember
  Anthracite: "#a3a9b4",
  Collier: "#c98b3a",
  Hewer: "#e0704f",
  Flint: "#ffc24b",
  Davy: "#8a7bff", // violet — matches anthracite-web
};

export const PRODUCT_VOICES: AgentName[] = ["Canari", "Vein", "Davy"];
export const TEAM_VOICES: AgentName[] = ["Anthracite", "Collier", "Hewer", "Flint"];

export type SliceId =
  | "component"
  | "objective"
  | "description"
  | "keywords"
  | "scout_tags"
  | "company_mission"
  | "products"
  | "me";

export type ContributeId =
  | "technical_approach"
  | "work_plan"
  | "win_themes"
  | "teaming"
  | "risks"
  | "transition";

export const SLICES: Record<SliceId, { label: string; source: string }> = {
  component: { label: "Sponsoring branch", source: "DSIP component / command" },
  objective: { label: "Topic objective", source: "DSIP topic" },
  description: { label: "Topic description", source: "DSIP topic" },
  keywords: { label: "DSIP keywords", source: "topic listing" },
  scout_tags: { label: "Scout phrases", source: "cached extract — open vocab" },
  company_mission: { label: "Company mission", source: "companies/…/mission.txt" },
  products: { label: "Products we already ship", source: "companies/…/products.md" },
  me: { label: "ME toolbox", source: "users/…/me.md" },
};

export const CONTRIBUTES: Record<ContributeId, { label: string; hint: string }> = {
  technical_approach: { label: "Technical Approach", hint: "How this product would actually do the work" },
  work_plan: { label: "Work plan / adaptation", hint: "Timeline, lift, what already exists" },
  win_themes: { label: "Win themes", hint: "What a TPOC can brief" },
  teaming: { label: "Teaming", hint: "Who else has to be in the room" },
  risks: { label: "Risks / eligibility", hint: "What would kill the bid" },
  transition: { label: "Transition path", hint: "Phase I → II → III / the customer" },
};

const PRODUCT_READS: SliceId[] = ["products", "objective", "description", "keywords", "scout_tags"];

export const AGENTS: Record<
  AgentName,
  { reads: SliceId[]; contributes: ContributeId[]; because: string }
> = {
  Canari: {
    reads: PRODUCT_READS,
    contributes: ["technical_approach"],
    because: "Does this SBIR map to Canari’s goals and objectives?",
  },
  Vein: {
    reads: PRODUCT_READS,
    contributes: ["technical_approach"],
    because:
      "Vein as a product — does it map to this SBIR’s objectives? Maps the required technical work to skills we can actually show.",
  },
  Anthracite: {
    reads: ["component", "objective", "company_mission", "scout_tags"],
    contributes: ["transition"],
    because: "Is the customer’s mission the same story as ours, and is there a transition path?",
  },
  Collier: {
    reads: ["description", "products", "me"],
    contributes: ["teaming"],
    because: "Gaps in the topic vs. the people we already have.",
  },
  Hewer: {
    reads: ["products", "me", "objective"],
    contributes: ["work_plan"],
    because: "What we already ship, and how heavy a lift to make it do this job.",
  },
  Flint: {
    reads: ["me", "objective", "products"],
    contributes: ["technical_approach"],
    because: "Only tools on the ME resume — unexpected pairings that still deliver.",
  },
  Davy: {
    reads: PRODUCT_READS,
    contributes: ["technical_approach"],
    because:
      "Davy is a voice-activated C2 system. Do its own capabilities meet this SBIR’s objectives?",
  },
};

/** Old council blobs stored Vien. Show them on Vein. */
export function normalizeAgentResults<T extends Record<string, unknown>>(
  seed?: T | null,
): T {
  if (!seed) return {} as T;
  const next = { ...seed };
  const vien = (next as Record<string, unknown>).Vien;
  if (vien && !(next as Record<string, unknown>).Vein) {
    (next as Record<string, unknown>).Vein = vien;
  }
  return next;
}

export function productHeadings(md: string): string[] {
  return (md || "")
    .split("\n")
    .map((ln) => ln.match(/^#{1,3}\s+(.+)$/)?.[1]?.trim())
    .filter((x): x is string => Boolean(x))
    .slice(0, 8);
}

export function stripHtml(s?: string): string {
  if (!s) return "";
  return s.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
}

/**
 * Coerce ANY value a local model might emit into a safe React child string.
 * The LLM frequently returns an object where a string is expected (e.g.
 * {tool, role_in_this_bid} or {area, effort}); rendering that raw throws
 * React error #31 and white-screens the page. This picks the most meaningful
 * field, pairs it with a detail when present, and never returns an object.
 */
export function asText(v: unknown): string {
  if (v == null) return "";
  if (typeof v === "string") return v.trim();
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  if (Array.isArray(v)) return v.map(asText).filter(Boolean).join(", ");
  if (typeof v === "object") {
    const o = v as Record<string, unknown>;
    const headKeys = ["tool", "name", "title", "text", "area", "role", "type", "need", "point", "label"];
    const detailKeys = ["role_in_this_bid", "why", "effort", "evidence", "detail", "note", "description"];
    const head = headKeys.map((k) => o[k]).find((x) => typeof x === "string" && x.trim());
    if (typeof head === "string") {
      const detail = detailKeys.map((k) => o[k]).find((x) => typeof x === "string" && x.trim() && x !== head);
      return typeof detail === "string" ? `${head.trim()} — ${detail.trim()}` : head.trim();
    }
    try {
      return JSON.stringify(v);
    } catch {
      return String(v);
    }
  }
  return String(v);
}

/** Normalize any value into a clean list of display strings. */
export function asList(v: unknown): string[] {
  if (v == null || v === "") return [];
  const arr = Array.isArray(v) ? v : [v];
  return arr.map(asText).filter((s) => s && s !== "null" && s !== "undefined");
}

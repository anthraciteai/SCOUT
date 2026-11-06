import { api, API_BASE } from "./client";
import type {
  AgentChatLog,
  AgentMeta,
  AgentRunResponse,
  AnalysisRun,
  CatalogTopic,
  CollabReport,
  Debrief,
  OllamaStatus,
  Proposal,
  MatchInbox,
  ResumeInfo,
  SearchResponse,
  TeamResponse,
  Topic,
  TrackedTopic,
  AuthStatus,
  OrgCompany,
  ScoutUser,
  SbirWorkspace,
} from "../types";

// ---- Topics (DSIP proxy) ----
export type TopicScope = "open" | "openonly" | "prerelease" | "all";

export interface SearchParams {
  searchText?: string;
  scope?: TopicScope; // open (default) | openonly | prerelease | all (incl. closed)
  component?: string;
  program?: string;
  technologyAreaIds?: string;
  sortBy?: string;
  size?: number;
  page?: number;
}

export const TopicsApi = {
  search: (params: SearchParams) =>
    api.get<SearchResponse>("/topics/search", { params }).then((r) => r.data),
  detail: (id: string) => api.get<Topic>(`/topics/${id}`).then((r) => r.data),
  questions: (id: string) =>
    api.get(`/topics/${id}/questions`).then((r) => r.data),
  reference: (name: string, params?: Record<string, string>) =>
    api.get(`/topics/reference/${name}`, { params }).then((r) => r.data),
  downloadUrl: (id: string, fmt: "PDF" | "DOCX", inline = false) =>
    `${API_BASE}/topics/${id}/download/${fmt}${inline ? "?inline=1" : ""}`,
};

// ---- Topic intelligence (OCR → summarize → fit vs profile) ----
export interface TopicText {
  topic_id: string;
  chars: number;
  source: string; // "pdf-ocr" | "dsip-json" | "none"
  cached_at?: number;
  text: string;
}

export interface TopicRequirement {
  need: string;
  evidence: string;
}

export interface TopicSummary {
  topic_id: string;
  source?: string;
  chars?: number;
  model?: string;
  tldr: string;
  problem: string;
  objective: string;
  who_cares: string;
  phases: string[];
  requirements: TopicRequirement[];
  keywords: string[];
}

export interface FitRequirement {
  need: string;
  status: "meets" | "partial" | "gap";
  evidence: string;
  matched_capability: string;
}

export interface TopicFit {
  topic_id: string;
  scope?: { company_id: string; user_id: string; display_name?: string };
  cap_source?: string;
  model?: string;
  overall_fit: number;
  recommendation: string;
  summary: string;
  requirements: FitRequirement[];
  strengths: string[];
  gaps: string[];
}

export const TopicIntelApi = {
  text: (id: string, force = false) =>
    api.get<TopicText>(`/topics/${id}/text`, { params: { force } }).then((r) => r.data),
  summarize: (id: string, force = false) =>
    api.post<TopicSummary>(`/topics/${id}/summary`, null, { params: { force } }).then((r) => r.data),
  fit: (id: string, force = false) =>
    api.post<TopicFit>(`/topics/${id}/fit`, null, { params: { force } }).then((r) => r.data),
  // Cheap read of the caller's cached fit (no model call); null if not scored yet.
  fitCached: (id: string) =>
    api.get<TopicFit | null>(`/topics/${id}/fit`).then((r) => r.data),
  // Which of these topics the caller has already scored a fit on (no model call).
  fitStatus: (ids: string[]) =>
    api
      .get<{ scored: string[] }>(`/topics/mine/fits`, { params: { ids: ids.join(",") } })
      .then((r) => r.data.scored),
};

// ---- Analysis ----
export interface TopicMeta {
  topic_code?: string;
  title?: string;
  component?: string;
  program?: string;
  topic_status?: string;
  solicitation_title?: string;
}

export const AnalysisApi = {
  run: (
    topic_ids: string[],
    topics_meta?: Record<string, TopicMeta>,
    resume_id?: number,
    force = false
  ) =>
    api
      .post<{ runs: AnalysisRun[] }>("/analysis/run", { topic_ids, resume_id, topics_meta, force })
      .then((r) => r.data.runs),
  list: () => api.get<AnalysisRun[]>("/analysis").then((r) => r.data),
  get: (id: number) => api.get<AnalysisRun>(`/analysis/${id}`).then((r) => r.data),
  latestForTopic: (topicId: string) =>
    api.get<AnalysisRun>(`/analysis/topic/${topicId}`).then((r) => r.data),
  agentNames: () => api.get<AgentMeta[]>("/analysis/agents").then((r) => r.data),
  runAgent: (
    topic_id: string,
    agent: string,
    topics_meta?: Record<string, TopicMeta>,
    context?: string,
    force = false
  ) =>
    api
      .post<AgentRunResponse>("/analysis/agent", { topic_id, agent, topics_meta, context, force })
      .then((r) => r.data),
  getChat: (topic_id: string, agent: string) =>
    api.get<AgentChatLog>(`/analysis/chat/${topic_id}/${agent}`).then((r) => r.data),
  listChats: (topic_id: string) =>
    api
      .get<{ topic_id: string; chats: Record<string, AgentChatLog> }>(`/analysis/chat/${topic_id}`)
      .then((r) => r.data),
  sendChat: (body: {
    topic_id: string;
    agent: string;
    message: string;
    proposal_text?: string;
    topics_meta?: Record<string, TopicMeta>;
  }) => api.post<AgentChatLog>("/analysis/chat", body).then((r) => r.data),
};

// ---- Team (Collier) ----
export const TeamApi = {
  recommend: (body: { topic_id?: string; proposal_content?: string; resume_id?: number }) =>
    api.post<TeamResponse>("/team/recommend", body).then((r) => r.data),
};

// ---- Tracker ----
export const TrackerApi = {
  list: () => api.get<TrackedTopic[]>("/tracker").then((r) => r.data),
  stages: () => api.get<string[]>("/tracker/stages").then((r) => r.data),
  track: (body: Partial<TrackedTopic> & { topic_id: string; raw?: unknown }) =>
    api.post<TrackedTopic>("/tracker", body).then((r) => r.data),
  update: (
    id: number,
    body: { status?: string; notes?: string; outcome?: string }
  ) => api.patch<TrackedTopic>(`/tracker/${id}`, body).then((r) => r.data),
  remove: (id: number) => api.delete(`/tracker/${id}`).then((r) => r.data),
};

// ---- Proposals ----
export type ReviewPersona = "technical" | "military" | "researcher";

export interface PersonaMeta {
  key: ReviewPersona;
  label: string;
  blurb: string;
}

export interface ProposalReview {
  id: number;
  proposal_id: number;
  persona: ReviewPersona;
  persona_label: string;
  title: string;
  topic_id?: string;
  topic_code?: string;
  proposal_sha: string;
  proposal_chars: number;
  body: string;
  model: string;
  created_at: string;
}

export const ProposalsApi = {
  list: () => api.get<Proposal[]>("/proposals").then((r) => r.data),
  get: (id: number) => api.get<Proposal>(`/proposals/${id}`).then((r) => r.data),
  create: (body: Partial<Proposal>) =>
    api.post<Proposal>("/proposals", body).then((r) => r.data),
  update: (id: number, body: Partial<Proposal>) =>
    api.put<Proposal>(`/proposals/${id}`, body).then((r) => r.data),
  remove: (id: number) => api.delete(`/proposals/${id}`).then((r) => r.data),
  personas: () => api.get<PersonaMeta[]>("/proposals/personas").then((r) => r.data),
  reviews: (proposalId: number, persona?: ReviewPersona) =>
    api
      .get<ProposalReview[]>(`/proposals/${proposalId}/reviews`, {
        params: persona ? { persona } : {},
      })
      .then((r) => r.data),
  deleteReview: (rid: number) =>
    api.delete(`/proposals/reviews/${rid}`).then((r) => r.data),
  reviewsSummary: () =>
    api
      .get<{
        total: number;
        by_persona: Record<string, number>;
        by_proposal: Record<string, Record<string, number>>;
      }>("/proposals/reviews/summary")
      .then((r) => r.data),
  // ---- task plan (Gantt) ----
  tasks: (pid: number) =>
    api.get<TaskPlanResponse>(`/proposals/${pid}/tasks`).then((r) => r.data),
  taskHistory: (pid: number) =>
    api
      .get<TaskPlanSnapshot[]>(`/proposals/${pid}/tasks/history`)
      .then((r) => r.data),
  generateTasks: (pid: number) =>
    api
      .post<TaskPlanSnapshot>(`/proposals/${pid}/tasks/generate`)
      .then((r) => r.data),
  // ---- cost studio ----
  cost: (pid: number) =>
    api.get<CostState>(`/proposals/${pid}/cost`).then((r) => r.data),
  putBom: (pid: number, bom: BomLine[]) =>
    api.put<CostState>(`/proposals/${pid}/cost/bom`, { bom }).then((r) => r.data),
  putRates: (pid: number, body: Partial<CostRates> & { phase?: CostPhase }) =>
    api.put<CostState>(`/proposals/${pid}/cost/rates`, body).then((r) => r.data),
  clearCostChat: (pid: number) =>
    api.delete<CostState>(`/proposals/${pid}/cost/chat`).then((r) => r.data),
  rollup: (pid: number) =>
    api.post<CostRollup>(`/proposals/${pid}/cost/rollup`).then((r) => r.data),
};

// ---- Task-plan types ----
export interface TaskPlanRequirement {
  id: string;
  text: string;
}
export interface TaskPlanPhase {
  key: string;
  label: string;
  duration_weeks: number;
}
export interface TaskPlanTask {
  id: string;
  title: string;
  phase: string;
  start_week: number;
  duration_weeks: number;
  depends_on: string[];
  deliverable?: string;
  requirements?: string[];
  owner_role?: string;
}
export interface TaskPlan {
  phases: TaskPlanPhase[];
  requirements: TaskPlanRequirement[];
  tasks: TaskPlanTask[];
  assumptions?: string;
}
export interface TaskPlanSnapshot {
  id: number;
  proposal_id: number;
  proposal_sha: string;
  proposal_chars: number;
  plan: TaskPlan;
  model: string;
  created_at: string;
}
export interface TaskPlanResponse {
  proposal_id: number;
  current_chars: number;
  min_chars: number;
  ready: boolean;
  current_sha: string;
  snapshot: TaskPlanSnapshot | null;
}

// ---- Cost studio types ----
export type CostPhase = "phase1" | "phase2" | "direct_to_phase2";
export type BomCategory =
  | "labor"
  | "materials"
  | "equipment"
  | "travel"
  | "subcontract"
  | "odc";

export interface BomLine {
  id?: string;
  category: BomCategory;
  name: string;
  qty: number;
  unit: string;
  unit_cost: number;
  notes?: string;
}

export interface CostRates {
  fringe_pct: number;
  overhead_pct: number;
  ga_pct: number;
  fee_pct: number;
}

export interface CostChatTurn {
  role: "user" | "assistant";
  content: string;
}

export interface CostRollup {
  phase: CostPhase;
  phase_label: string;
  phase_cap: number | null;
  lines: (BomLine & { subtotal: number })[];
  by_category: Record<BomCategory, number>;
  labor: number;
  fringe: number;
  overhead: number;
  direct_non_labor: number;
  g_and_a: number;
  fee: number;
  total: number;
  headroom: number | null;
  warnings: string[];
  narrative?: string;
}

export interface CostState {
  proposal_id: number;
  phase: CostPhase;
  phase_label: string;
  phase_cap: number | null;
  bom: BomLine[];
  rates: CostRates;
  chat: CostChatTurn[];
  rollup: CostRollup | null;
  updated_at: string;
}

export async function streamDynomite(
  proposalId: number,
  message: string,
  onChunk: (text: string) => void,
  signal?: AbortSignal
): Promise<void> {
  const resp = await fetch(`${API_BASE}/proposals/${proposalId}/cost/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
    signal,
  });
  if (!resp.ok || !resp.body) {
    const detail = await resp.text().catch(() => "");
    throw new Error(detail || `Dynomite failed: ${resp.status}`);
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    onChunk(decoder.decode(value, { stream: true }));
  }
}

export async function streamPersonaReview(
  proposalId: number,
  persona: ReviewPersona,
  onChunk: (text: string) => void,
  signal?: AbortSignal
): Promise<void> {
  const resp = await fetch(
    `${API_BASE}/proposals/${proposalId}/review/${persona}`,
    { method: "POST", signal }
  );
  if (!resp.ok || !resp.body) {
    throw new Error(`Persona review failed: ${resp.status}`);
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    onChunk(decoder.decode(value, { stream: true }));
  }
}

// ---- Debriefs ----
export const DebriefsApi = {
  list: () => api.get<Debrief[]>("/debriefs").then((r) => r.data),
  upload: (file: File, meta: { title?: string; topic_id?: string; proposal_id?: number }) => {
    const fd = new FormData();
    fd.append("file", file);
    if (meta.title) fd.append("title", meta.title);
    if (meta.topic_id) fd.append("topic_id", meta.topic_id);
    if (meta.proposal_id != null) fd.append("proposal_id", String(meta.proposal_id));
    return api
      .post<Debrief>("/debriefs", fd, { headers: { "Content-Type": "multipart/form-data" } })
      .then((r) => r.data);
  },
  analyze: (id: number) =>
    api.post<Debrief>(`/debriefs/${id}/analyze`).then((r) => r.data),
  remove: (id: number) => api.delete(`/debriefs/${id}`).then((r) => r.data),
};

// ---- Resume ----
export const ResumeApi = {
  list: () => api.get<ResumeInfo[]>("/resume").then((r) => r.data),
  active: () => api.get<ResumeInfo | null>("/resume/active").then((r) => r.data),
  me: () => api.get<ResumeInfo | null>("/resume/me").then((r) => r.data),
  extract: (resume_id?: number, force = true) =>
    api
      .post<ResumeInfo>("/resume/extract", null, { params: { resume_id, force } })
      .then((r) => r.data),
  fromText: (name: string, text: string, kind: "me" | "company" = "company") =>
    api.post<ResumeInfo>("/resume/text", { name, text, kind }).then((r) => r.data),
  upload: (file: File, name?: string, kind: "me" | "company" = "company") => {
    const fd = new FormData();
    fd.append("file", file);
    if (name) fd.append("name", name);
    fd.append("kind", kind);
    return api
      .post<ResumeInfo>("/resume/upload", fd, { headers: { "Content-Type": "multipart/form-data" } })
      .then((r) => r.data);
  },
  update: (id: number, body: Partial<ResumeInfo>) =>
    api.put<ResumeInfo>(`/resume/${id}`, body).then((r) => r.data),
  remove: (id: number) => api.delete(`/resume/${id}`).then((r) => r.data),
};

// ---- Matches (inbox ranker) ----
export type ScanMode = "me" | "employee" | "company";

export interface ScanBody {
  resume_id?: number;
  force_extract?: boolean;
  mode?: ScanMode;
  employee_id?: string;
  include_company?: boolean;
}

export interface RerankOption {
  user_id: string;
  display_name: string;
  me_chars: number;
  has_resume: boolean;
}

export interface RerankOptions {
  identity: { user_id: string; company_id: string } | null;
  company_id: string | null;
  you: RerankOption | null;
  coworkers: RerankOption[];
  company: { mission_chars: number; product_chars: number };
}

export const MatchesApi = {
  list: (resume_id?: number) =>
    api.get<MatchInbox>("/matches", { params: { resume_id } }).then((r) => r.data),
  scan: (body?: ScanBody) =>
    api.post<MatchInbox>("/matches/scan", body || {}).then((r) => r.data),
  rerankOptions: () =>
    api.get<RerankOptions>("/matches/rerank/options").then((r) => r.data),
};

export async function streamWhyMatched(
  topicId: string,
  onChunk: (text: string) => void,
  signal?: AbortSignal
): Promise<void> {
  const resp = await fetch(`${API_BASE}/matches/${encodeURIComponent(topicId)}/why`, {
    method: "POST",
    signal,
  });
  if (!resp.ok || !resp.body) {
    const detail = await resp.text().catch(() => "");
    throw new Error(detail || `Why-matched failed: ${resp.status}`);
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    onChunk(decoder.decode(value, { stream: true }));
  }
}

// ---- Pipeline gantt ----
export interface GanttReviewCheckpoint {
  id: number;
  persona: string;
  created_at: string | null;
  created_ms: number | null;
  chars: number;
}

export interface GanttRow {
  tracked_id: number;
  topic_id: string;
  topic_code?: string;
  title?: string;
  component?: string;
  program?: string;
  stage: string;
  topic_status?: string;
  outcome?: string;
  prerelease_ms: number | null;
  open_ms: number | null;
  close_ms: number | null;
  verdict: {
    fit_score?: number;
    recommendation?: string;
    heavy_lift?: number;
    at_ms?: number | null;
  };
  reviews: GanttReviewCheckpoint[];
}

export interface GanttData {
  now_ms: number;
  rows: GanttRow[];
}

export const GanttApi = {
  load: () => api.get<GanttData>("/tracker/gantt").then((r) => r.data),
};

export interface MatchingSignal {
  identity: { user_id: string; company_id: string } | null;
  resume?: { chars: number; phrases: string[]; source?: string; updated_at?: string };
  company?: {
    mission_chars: number;
    product_chars: number;
    phrases: string[];
    source?: string;
    updated_at?: string;
  };
}

export const CatalogApi = {
  status: () => api.get("/catalog/status").then((r) => r.data),
  signal: () => api.get<MatchingSignal>("/catalog/signal").then((r) => r.data),
  refreshSignal: () => api.post("/catalog/signal/refresh").then((r) => r.data),
  enrichStart: () => api.post("/catalog/enrich/start").then((r) => r.data),
  refresh: (force = false) =>
    api.post("/catalog/refresh", {}, { params: { force } }).then((r) => r.data),
  topic: (topic_id: string) =>
    api.get<CatalogTopic>(`/catalog/topics/${topic_id}`).then((r) => r.data),
};

// ---- System ----
export const SystemApi = {
  ollama: () => api.get<OllamaStatus>("/system/ollama").then((r) => r.data),
  pull: (name?: string) =>
    api.post("/system/ollama/pull", null, { params: name ? { name } : {} }).then((r) => r.data),
  agents: () => api.get<AgentMeta[]>("/system/agents").then((r) => r.data),
};

export const AuthApi = {
  status: () => api.get<AuthStatus>("/auth/status").then((r) => r.data),
  login: (username: string, password = "", company_id?: string) =>
    api
      .post<{ token: string; user: ScoutUser }>("/auth/login", { username, password, company_id })
      .then((r) => r.data),
  me: () => api.get<ScoutUser>("/auth/me").then((r) => r.data),
};

export const OrgApi = {
  company: () => api.get<OrgCompany>("/org/company").then((r) => r.data),
  saveMission: (text: string) => api.put("/org/company/mission", { text }).then((r) => r.data),
  saveProducts: (text: string) => api.put("/org/company/products", { text }).then((r) => r.data),
  saveMe: (body: { me?: string; skills?: string[]; display_name?: string }) =>
    api.put("/org/me", body).then((r) => r.data),
  hireEmployee: (
    user_id: string,
    body?: { display_name?: string; skills?: string[]; me?: string }
  ) =>
    api
      .post(`/org/company/employees/${encodeURIComponent(user_id)}`, body || {})
      .then((r) => r.data),
  editEmployee: (
    user_id: string,
    body: { display_name?: string; skills?: string[]; me?: string }
  ) =>
    api
      .put(`/org/company/employees/${encodeURIComponent(user_id)}`, body)
      .then((r) => r.data),
  unhireEmployee: (user_id: string) =>
    api.delete(`/org/company/employees/${encodeURIComponent(user_id)}`).then((r) => r.data),
  employeeResume: (user_id: string) =>
    api
      .get<{
        user_id: string;
        chars: number;
        filename?: string | null;
        resume_sha?: string;
        updated_at?: string;
        text: string;
      }>(`/org/company/employees/${encodeURIComponent(user_id)}/resume`)
      .then((r) => r.data),
  uploadEmployeeResume: (user_id: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return api
      .post<{
        ok: boolean;
        user_id: string;
        chars: number;
        filename?: string | null;
        resume_sha?: string;
      }>(`/org/company/employees/${encodeURIComponent(user_id)}/resume`, fd, {
        headers: { "Content-Type": "multipart/form-data" },
      })
      .then((r) => r.data);
  },
  deleteEmployeeResume: (user_id: string) =>
    api
      .delete(`/org/company/employees/${encodeURIComponent(user_id)}/resume`)
      .then((r) => r.data),
  sbirs: () => api.get<{ sbirs: SbirWorkspace[] }>("/org/sbir").then((r) => r.data.sbirs),
  workspace: (topic_id: string) =>
    api.get<SbirWorkspace>(`/org/sbir/${topic_id}`).then((r) => r.data),
  grant: (topic_id: string, meta?: Record<string, string>) =>
    api.post<SbirWorkspace>(`/org/sbir/${topic_id}/grant`, meta || { topic_id }).then((r) => r.data),
  saveShared: (topic_id: string, name: "proposal.md" | "notes.md", text: string, expected_sha?: string) =>
    api.put(`/org/sbir/${topic_id}/shared/${name}`, { text, expected_sha }).then((r) => r.data),
  saveMine: (topic_id: string, name: "draft.md" | "notes.md", text: string) =>
    api.put(`/org/sbir/${topic_id}/mine/${name}`, { text }).then((r) => r.data),
  collab: (topic_id: string) =>
    api.get<CollabReport>(`/org/sbir/${topic_id}/collab`).then((r) => r.data),
  refreshCollab: (topic_id: string, force = false) =>
    api
      .post<CollabReport>(`/org/sbir/${topic_id}/collab/refresh`, {}, { params: { force } })
      .then((r) => r.data),
  promoteCollab: (
    topic_id: string,
    body: { theme?: string; bullets?: string[]; expected_sha?: string }
  ) => api.post(`/org/sbir/${topic_id}/collab/promote`, body).then((r) => r.data),
};

// ---- Streaming helper (for live proposal feedback) ----
export async function streamProposalFeedback(
  body: { content: string; topic_id?: string; focus?: string },
  onChunk: (text: string) => void,
  signal?: AbortSignal
): Promise<void> {
  const resp = await fetch(`${API_BASE}/proposals/feedback-live`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!resp.ok || !resp.body) {
    throw new Error(`Feedback failed: ${resp.status}`);
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    onChunk(decoder.decode(value, { stream: true }));
  }
}

export async function streamSavedFeedback(
  proposalId: number,
  onChunk: (text: string) => void,
  signal?: AbortSignal
): Promise<void> {
  const resp = await fetch(`${API_BASE}/proposals/${proposalId}/feedback`, {
    method: "POST",
    signal,
  });
  if (!resp.ok || !resp.body) {
    throw new Error(`Feedback failed: ${resp.status}`);
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    onChunk(decoder.decode(value, { stream: true }));
  }
}

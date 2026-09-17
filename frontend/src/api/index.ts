import { api, API_BASE } from "./client";
import type {
  AgentMeta,
  AgentRunResponse,
  AnalysisRun,
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
export const ProposalsApi = {
  list: () => api.get<Proposal[]>("/proposals").then((r) => r.data),
  get: (id: number) => api.get<Proposal>(`/proposals/${id}`).then((r) => r.data),
  create: (body: Partial<Proposal>) =>
    api.post<Proposal>("/proposals", body).then((r) => r.data),
  update: (id: number, body: Partial<Proposal>) =>
    api.put<Proposal>(`/proposals/${id}`, body).then((r) => r.data),
  remove: (id: number) => api.delete(`/proposals/${id}`).then((r) => r.data),
};

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
export const MatchesApi = {
  list: (resume_id?: number) =>
    api.get<MatchInbox>("/matches", { params: { resume_id } }).then((r) => r.data),
  scan: (opts?: { resume_id?: number; force_extract?: boolean }) =>
    api
      .post<MatchInbox>("/matches/scan", null, { params: opts || {} })
      .then((r) => r.data),
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
  sbirs: () => api.get<{ sbirs: SbirWorkspace[] }>("/org/sbir").then((r) => r.data.sbirs),
  workspace: (topic_id: string) =>
    api.get<SbirWorkspace>(`/org/sbir/${topic_id}`).then((r) => r.data),
  grant: (topic_id: string, meta?: Record<string, string>) =>
    api.post<SbirWorkspace>(`/org/sbir/${topic_id}/grant`, meta || { topic_id }).then((r) => r.data),
  saveShared: (topic_id: string, name: "proposal.md" | "notes.md", text: string) =>
    api.put(`/org/sbir/${topic_id}/shared/${name}`, { text }).then((r) => r.data),
  saveMine: (topic_id: string, name: "draft.md" | "notes.md", text: string) =>
    api.put(`/org/sbir/${topic_id}/mine/${name}`, { text }).then((r) => r.data),
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

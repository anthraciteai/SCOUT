export interface Topic {
  topicId: string;
  topicCode?: string;
  finalTopicCode?: string;
  topicTitle?: string;
  title?: string;
  topicStatus?: string;
  component?: string;
  command?: string;
  program?: string;
  solicitationTitle?: string;
  solicitationNumber?: string;
  topicQuestionCount?: number;
  noOfPublishedQuestions?: number;
  objective?: string;
  description?: string;
  // epoch-ms date fields (present on search summaries)
  topicPreReleaseStartDate?: number;
  topicPreReleaseEndDate?: number;
  topicStartDate?: number;
  topicEndDate?: number;
  topicQAStartDate?: number;
  topicQAEndDate?: number;
  keywords?: string;
  [key: string]: unknown;
}

export interface SearchResponse {
  total: number;
  data: Topic[];
}

export interface AgentResult {
  _role?: string;
  [key: string]: unknown;
}

export interface CouncilResult {
  fit_score?: number;
  recommendation?: string;
  rationale?: string;
  top_strengths?: string[];
  top_risks?: string[];
  decision_summary?: string;
  [key: string]: unknown;
}

export interface EffortItem {
  area: string;
  effort?: string;
}

export interface HewerResult {
  _role?: string;
  heavy_lift?: number;
  lift_rationale?: string;
  reuse_as_is?: string[];
  adaptation_plan?: string[];
  effort_breakdown?: EffortItem[];
  raw?: string;
}

export interface AnalysisRun {
  id: number;
  topic_id: string;
  topic_code?: string;
  title?: string;
  model: string;
  fit_score?: number;
  heavy_lift?: number;
  recommendation?: string;
  created_at: string;
  cached?: boolean;
  cached_at?: string;
  result?: {
    agents: Record<string, AgentResult>;
    council: CouncilResult;
    model: string;
  };
}

export interface AgentRunResponse {
  agent: string;
  result: AgentResult;
  model: string;
  cached?: boolean;
  cached_at?: string;
}

export interface TrackedTopic {
  id: number;
  topic_id: string;
  topic_code?: string;
  title?: string;
  component?: string;
  program?: string;
  status: string;
  topic_status?: string;
  notes: string;
  outcome?: string;
  created_at: string;
  updated_at: string;
}

export interface Proposal {
  id: number;
  title: string;
  content: string;
  topic_id?: string;
  topic_code?: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface Debrief {
  id: number;
  topic_id?: string;
  proposal_id?: number;
  title: string;
  filename?: string;
  extracted_text: string;
  analysis?: string;
  created_at: string;
}

export interface ResumeExtract {
  summary?: string;
  skills?: string[];
  domains?: string[];
  search_queries?: string[];
  keywords?: string[];
  _source?: string;
}

export interface ResumeInfo {
  id: number;
  name: string;
  filename?: string;
  is_active: boolean;
  kind?: "me" | "company";
  chars: number;
  text?: string;
  extract?: ResumeExtract | null;
  extracted_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface MatchItem {
  id: number;
  topic_id: string;
  topic_code?: string;
  title?: string;
  component?: string;
  program?: string;
  topic_status?: string;
  score: number;
  reasons: string[];
  queries: string[];
  topic?: Topic;
  created_at?: string;
}

export interface MatchInbox {
  resume: { id: number; name: string; chars: number } | null;
  profile: ResumeExtract | null;
  scanned_at: string | null;
  queries: string[];
  match_count: number;
  model: string;
  matches: MatchItem[];
}

export interface RoleToAdd {
  role: string;
  seniority?: string;
  why?: string;
  skills?: string[];
}

export interface PartnerType {
  type: string;
  why?: string;
}

export interface TeamRecommendation {
  _role?: string;
  covered_by_you?: string[];
  gaps?: string[];
  roles_to_add?: RoleToAdd[];
  partner_types?: PartnerType[];
  priority_hires?: string[];
  notes?: string;
  raw?: string;
}

export interface TeamResponse {
  recommendation: TeamRecommendation;
  model: string;
  topic_id?: string;
}

export interface OllamaStatus {
  base_url: string;
  configured_model: string;
  fallback_model: string;
  available_models: string[];
  model_ready: boolean;
}

export interface AgentMeta {
  name: string;
  role: string;
}

export interface ScoutUser {
  user_id: string;
  display_name: string;
  company_id?: string;
  groups?: string[];
  auth?: string;
  skills?: string[];
  sbirs?: string[];
  in_company?: boolean;
}

export interface AuthStatus {
  auth_disabled: boolean;
  keycloak_url?: string;
  keycloak_realm?: string;
  keycloak_client_id?: string;
  default_company: string;
  users: { user_id: string; display_name: string }[];
}

export interface OrgEmployee {
  user_id: string;
  display_name: string;
  skills: string[];
  sbirs: string[];
}

export interface OrgCompany {
  company_id: string;
  mission: string;
  products: string;
  employees: OrgEmployee[];
  groups: { group_id: string; members: string[]; sbirs: string[] }[];
  sbirs: string[];
}

export interface SbirWorkspace {
  topic_id: string;
  title?: string;
  topic_code?: string;
  cached_council: boolean;
  cached_flint: boolean;
  has_shared_proposal: boolean;
  has_my_draft: boolean;
  writers: string[];
  cached_at?: string;
  shared_proposal?: string;
  shared_notes?: string;
  my_draft?: string;
  my_notes?: string;
  my_council?: { result?: unknown; cached_at?: string; model?: string } | null;
  shared_council?: { result?: unknown; cached_at?: string; model?: string } | null;
  my_flint?: { result?: unknown; cached_at?: string; model?: string } | null;
  teammates?: {
    user_id: string;
    display_name: string;
    skills: string[];
    has_flint: boolean;
    has_draft: boolean;
  }[];
  paths?: Record<string, string>;
}

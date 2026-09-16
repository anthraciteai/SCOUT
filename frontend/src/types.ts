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

export interface ResumeInfo {
  id: number;
  name: string;
  filename?: string;
  is_active: boolean;
  chars: number;
  text?: string;
  created_at: string;
  updated_at: string;
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

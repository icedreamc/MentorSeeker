export type DiscoveryJob = {
  id: string;
  school: string;
  interested_field: string;
  status: "pending" | "running" | "cancelling" | "success" | "failed" | "cancelled";
  max_steps: number;
  target_mentor_count: number;
  enrich_limit: number;
  progress_message: string;
  raw_output_file: string;
  enriched_output_file: string;
  error_message: string;
  mentor_count: number;
  created_at: string;
  updated_at: string;
};

export type MentorSummary = {
  id: number;
  school: string;
  interested_field: string;
  name: string;
  title: string;
  research_direction: string;
  high_level_summary: string;
  ai_keywords: string[];
  is_favorite: boolean;
  is_auto_enriched: boolean;
  updated_at: string;
};

export type MentorDetail = {
  id: number;
  school: string;
  interested_field: string;
  name: string;
  title: string;
  research_direction: string;
  profile_urls: string[];
  structured_profile: Record<string, unknown>;
  publications: Array<Record<string, unknown>>;
  papers_summary: string;
  high_level_summary: string;
  ai_keywords: string[];
  user_note: string;
  user_tags: string[];
  is_favorite: boolean;
  is_auto_enriched: boolean;
  updated_at: string;
};

export type MentorList = {
  items: MentorSummary[];
  page: number;
  page_size: number;
  total: number;
};

export type MentorBatchEnrichResult = {
  requested_count: number;
  enriched_count: number;
  skipped_count: number;
  updated_ids: number[];
  output_file: string;
};

export type MentorBatchDeleteResult = {
  requested_count: number;
  deleted_count: number;
  not_found_count: number;
  deleted_ids: number[];
  not_found_ids: number[];
  deleted_favorites: number;
  deleted_notes: number;
  deleted_timeline: number;
};

export type LocalSecretsState = {
  llm_base_url: string;
  llm_model: string;
  provider_email: string;
  has_llm_api_key: boolean;
  has_browser_cookie: boolean;
};

export type LocalSecretsUpdateResult = {
  updated: boolean;
  has_llm_api_key: boolean;
  has_browser_cookie: boolean;
};

export type ProfileSettingsState = {
  profile_text: string;
  library_summary_text: string;
  has_profile: boolean;
  has_library_summary: boolean;
};

export type ProfileSettingsUpdateResult = {
  updated: boolean;
  profile_text: string;
  library_summary_text: string;
  has_profile: boolean;
  has_library_summary: boolean;
};

export type TimelineEvent = {
  id: number;
  user_id: number;
  mentor_id: number;
  mentor_name: string;
  event_type: string;
  event_date: string;
  content: string;
  created_at: string;
  updated_at: string;
};

export type TimelineList = {
  items: TimelineEvent[];
  page: number;
  page_size: number;
  total: number;
};

export type TimelineDailyPoint = {
  event_date: string;
  count: number;
  type_counts: Record<string, number>;
};

export type TimelineDailyOverview = {
  items: TimelineDailyPoint[];
};

export type AdvisorRecommendation = {
  mentor_id: number;
  name: string;
  school: string;
  title: string;
  research_direction: string;
  match_score: number;
  reason: string;
};

export type AdvisorMessage = {
  id: number;
  role: "user" | "assistant";
  content: string;
  recommendations: AdvisorRecommendation[];
  created_at: string;
};

export type AdvisorSessionSummary = {
  id: number;
  user_id: number;
  title: string;
  message_count: number;
  created_at: string;
  updated_at: string;
};

export type AdvisorSessionDetail = {
  id: number;
  user_id: number;
  title: string;
  created_at: string;
  updated_at: string;
  messages: AdvisorMessage[];
};

export type AdvisorAskResult = {
  session_id: number;
  session_created: boolean;
  answer: string;
  used_llm: boolean;
  memory_text: string;
  used_personalization: boolean;
  retrieval_debug: Record<string, string>;
  recommendations: AdvisorRecommendation[];
};

export type AdvisorMemory = {
  user_id: number;
  memory_text: string;
  updated_at: string;
};

export type AdvisorVectorIndexStatus = {
  vector_enabled: boolean;
  embedding_model: string;
  total_mentors: number;
  indexed_mentors: number;
  outdated_mentors: number;
};

export type AdvisorVectorIndexRebuildResult = {
  vector_enabled: boolean;
  embedding_model: string;
  total_mentors: number;
  updated_mentors: number;
  skipped_mentors: number;
};

export type AdvisorLibrarySummaryGenerateResult = {
  summary_text: string;
  used_llm: boolean;
  source_count: number;
  updated: boolean;
};

export type ContactDraftGenerateResult = {
  mentor_id: number;
  subject: string;
  body: string;
  used_llm: boolean;
  key_fit_points: string[];
};

export type ContactDraftCommitResult = {
  id: number;
  user_id: number;
  mentor_id: number;
  event_type: string;
  event_date: string;
  content: string;
  created_at: string;
  updated_at: string;
};

